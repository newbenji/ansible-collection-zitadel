# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Benjamin Andersen (@newbenji)
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run api_token's main() end to end against an in-memory fake ZITADEL."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import io
import json
import os
import stat
from unittest import mock

import pytest

from ansible.module_utils.testing import patch_module_args
from ansible_collections.newbenji.zitadel.plugins.module_utils import zitadel
from ansible_collections.newbenji.zitadel.plugins.modules import api_token

ENDPOINT = "https://z.example.com"
USER = "ci-user"


class Exit(Exception):
    def __init__(self, result):
        super(Exit, self).__init__("exit_json")
        self.result = result


class Fail(Exception):
    def __init__(self, result):
        super(Fail, self).__init__(result.get("msg"))
        self.result = result


class FakeZitadel(object):
    """Stands in for fetch_url, routing calls to an in-memory set of PATs."""

    def __init__(self, tokens=None, status=None):
        self.tokens = list(tokens or [])
        self.status = status  # force every call to return this HTTP status
        self.calls = []

    def __call__(self, module, url, data=None, headers=None, method=None, timeout=10):
        path = url[len(ENDPOINT):]
        self.calls.append((method, path, data, headers))
        if self.status:
            return None, {"status": self.status, "body": b'{"message":"denied"}', "msg": "HTTP Error"}

        if path == "/oauth/v2/token":
            body = {"access_token": "minted-access-token", "token_type": "Bearer"}
        elif method == "POST" and path == "/v2/users/pats/search":
            req = json.loads(data)
            user = req["filters"][0]["userIdFilter"]["id"]
            matching = [t for t in self.tokens if t["userId"] == user]
            page = req["pagination"]
            result = matching[page["offset"]:page["offset"] + page["limit"]]
            body = {"pagination": {"totalResult": str(len(matching))}, "result": result}
        elif method == "POST" and path == "/v2/users/%s/pats" % USER:
            new = {"id": "tok-new", "userId": USER}
            new.update(json.loads(data))
            self.tokens.append(new)
            body = {"tokenId": "tok-new", "token": "SECRET-PAT", "creationDate": "2026-10-16T00:00:00Z"}
        elif method == "DELETE" and path.startswith("/v2/users/%s/pats/" % USER):
            token_id = path.rsplit("/", 1)[1]
            self.tokens = [t for t in self.tokens if t["id"] != token_id]
            body = {}
        else:
            return None, {"status": 404, "body": b"not found", "msg": "Not Found"}
        return io.BytesIO(json.dumps(body).encode()), {"status": 200}

    def methods(self):
        return [(c[0], c[1]) for c in self.calls]


def token(token_id, expires=None):
    tok = {"id": token_id, "userId": USER}
    if expires:
        tok["expirationDate"] = expires
    return tok


@pytest.fixture(autouse=True)
def patch_exits(monkeypatch):
    def exit_json(self, **kwargs):
        raise Exit(kwargs)

    def fail_json(self, **kwargs):
        raise Fail(kwargs)

    monkeypatch.setattr(api_token.AnsibleModule, "exit_json", exit_json)
    monkeypatch.setattr(api_token.AnsibleModule, "fail_json", fail_json)
    for var in ("ZITADEL_ENDPOINT", "ZITADEL_API_TOKEN", "ZITADEL_SERVICE_ACCOUNT_KEY"):
        monkeypatch.delenv(var, raising=False)


def run_module(fake, check_mode=False, **args):
    params = {"endpoint": ENDPOINT, "api_token": "admin-pat", "user_id": USER}
    params.update(args)
    # Drop explicit None so mutually_exclusive sees the option as unset.
    params = dict((k, v) for k, v in params.items() if v is not None)
    if check_mode:
        params["_ansible_check_mode"] = True
    with patch_module_args(params), mock.patch.object(zitadel, "fetch_url", fake):
        with pytest.raises(Exit) as ctx:
            api_token.main()
    return ctx.value.result


def run_failing(fake, **args):
    params = {"endpoint": ENDPOINT, "api_token": "admin-pat", "user_id": USER}
    params.update(args)
    params = dict((k, v) for k, v in params.items() if v is not None)
    with patch_module_args(params), mock.patch.object(zitadel, "fetch_url", fake):
        with pytest.raises(Fail) as ctx:
            api_token.main()
    return ctx.value.result


# -- state=present -----------------------------------------------------------

def test_creates_when_user_has_no_token():
    fake = FakeZitadel()
    result = run_module(fake, expiration_date="2027-01-01T00:00:00Z")
    assert result["changed"]
    assert result["token_id"] == "tok-new"
    assert result["token"] == "SECRET-PAT"
    assert ("POST", "/v2/users/%s/pats" % USER) in fake.methods()
    assert fake.tokens[0]["expirationDate"] == "2027-01-01T00:00:00Z"
    assert fake.calls[0][3]["Authorization"] == "Bearer admin-pat"


def test_idempotent_when_active_token_exists():
    fake = FakeZitadel([token("tok-1", "2099-01-01T00:00:00.123456789Z")])
    result = run_module(fake)
    assert not result["changed"]
    assert result["token_id"] == "tok-1"
    assert "token" not in result
    assert fake.methods() == [("POST", "/v2/users/pats/search")]


def test_token_without_expiry_counts_as_active():
    assert not run_module(FakeZitadel([token("tok-1")]))["changed"]


def test_creates_when_only_expired_tokens_exist():
    result = run_module(FakeZitadel([token("tok-old", "2020-01-01T00:00:00Z")]))
    assert result["changed"]
    assert result["token_id"] == "tok-new"


def test_check_mode_does_not_create():
    fake = FakeZitadel()
    result = run_module(fake, check_mode=True)
    assert result["changed"]
    assert fake.methods() == [("POST", "/v2/users/pats/search")]
    assert fake.tokens == []


def test_token_path_writes_secret_instead_of_returning_it(tmp_path):
    path = str(tmp_path / "ci.pat")
    result = run_module(FakeZitadel(), token_path=path)
    assert "token" not in result
    with open(path) as handle:
        assert handle.read() == "SECRET-PAT"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_warns_when_token_exists_but_token_path_missing(tmp_path):
    with mock.patch.object(api_token.AnsibleModule, "warn") as warn:
        result = run_module(FakeZitadel([token("tok-1")]), token_path=str(tmp_path / "missing.pat"))
    assert not result["changed"]
    warn.assert_called_once()


def test_paginates_token_list():
    count = zitadel.PAGE_SIZE + 5
    fake = FakeZitadel([token("tok-%d" % i, "2020-01-01T00:00:00Z") for i in range(count)])
    result = run_module(fake, check_mode=True)
    assert len(result["tokens"]) == count
    assert fake.methods().count(("POST", "/v2/users/pats/search")) == 2


def test_credentials_from_environment(monkeypatch):
    monkeypatch.setenv("ZITADEL_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("ZITADEL_API_TOKEN", "env-pat")
    fake = FakeZitadel([token("tok-1")])
    run_module(fake, endpoint=None, api_token=None)
    assert fake.calls[0][3]["Authorization"] == "Bearer env-pat"


# -- state=absent ------------------------------------------------------------

def test_removes_all_tokens_of_user():
    fake = FakeZitadel([token("tok-1"), token("tok-2")])
    result = run_module(fake, state="absent")
    assert result["changed"]
    assert result["removed"] == ["tok-1", "tok-2"]
    assert fake.tokens == []


def test_removes_only_given_token_id():
    fake = FakeZitadel([token("tok-1"), token("tok-2")])
    result = run_module(fake, state="absent", token_id="tok-2")
    assert result["removed"] == ["tok-2"]
    assert [t["id"] for t in fake.tokens] == ["tok-1"]


def test_noop_when_nothing_to_remove():
    fake = FakeZitadel()
    result = run_module(fake, state="absent")
    assert not result["changed"]
    assert "DELETE" not in [call[0] for call in fake.methods()]


def test_check_mode_does_not_delete():
    fake = FakeZitadel([token("tok-1")])
    result = run_module(fake, state="absent", check_mode=True)
    assert result["changed"]
    assert len(fake.tokens) == 1


# -- validation and errors ---------------------------------------------------

def test_token_id_rejected_with_present():
    assert "token_id" in run_failing(FakeZitadel(), token_id="tok-1")["msg"]


def test_bad_expiration_date_rejected():
    assert "RFC 3339" in run_failing(FakeZitadel(), expiration_date="next year")["msg"]


def test_http_error_fails_with_status():
    result = run_failing(FakeZitadel(status=403))
    assert "HTTP 403" in result["msg"]
    assert "denied" in result["msg"]


# -- service-account key auth ------------------------------------------------

def test_exchanges_key_for_access_token():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()).decode()
    key_file = {"type": "serviceaccount", "keyId": "kid-1", "key": pem, "userId": "admin-sa"}

    fake = FakeZitadel([token("tok-1")])
    run_module(fake, api_token=None, service_account_key=json.dumps(key_file))
    method, path, data, dummy = fake.calls[0]
    assert (method, path) == ("POST", "/oauth/v2/token")
    assert "grant-type%3Ajwt-bearer" in data
    assert "urn%3Azitadel%3Aiam%3Aorg%3Aproject%3Aid%3Azitadel%3Aaud" in data
    assert fake.calls[1][3]["Authorization"] == "Bearer minted-access-token"


def test_incomplete_key_file_fails():
    result = run_failing(FakeZitadel(), api_token=None, service_account_key={"keyId": "k"})
    assert "missing" in result["msg"]
