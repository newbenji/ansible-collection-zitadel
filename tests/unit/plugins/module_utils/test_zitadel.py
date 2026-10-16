# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Benjamin Andersen (@newbenji)
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import base64
import json

import pytest

from ansible_collections.newbenji.zitadel.plugins.module_utils import zitadel

cryptography = pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402


def _unb64(part):
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def key_file(rsa_key):
    pem = rsa_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()).decode()
    return {"type": "serviceaccount", "keyId": "kid-1", "key": pem, "userId": "admin-sa"}


@pytest.mark.parametrize("value", [
    "2023-01-15T01:30:15Z",
    "2023-01-15T01:30:15.01Z",
    "2023-01-15T01:30:15.123456789Z",
    "2023-01-15T01:30:15+02:00",
])
def test_parse_timestamp_accepts_rfc3339(value):
    assert zitadel.parse_timestamp(value) is not None


@pytest.mark.parametrize("value", ["2023-01-15", "next year", "", None])
def test_parse_timestamp_rejects_other_values(value):
    assert zitadel.parse_timestamp(value) is None


def test_parse_timestamp_applies_offset():
    assert zitadel.parse_timestamp("2023-01-15T02:00:00+02:00") == zitadel.parse_timestamp("2023-01-15T00:00:00Z")


def test_load_key_accepts_json_string(key_file):
    assert zitadel.load_service_account_key(json.dumps(key_file))["keyId"] == "kid-1"


@pytest.mark.parametrize("value,error", [
    ({"keyId": "k"}, "missing: key, userId"),
    ("not json", "JSON key file contents"),
    ("[1, 2]", "JSON object"),
])
def test_load_key_rejects_bad_input(value, error):
    with pytest.raises(ValueError, match=error):
        zitadel.load_service_account_key(value)


def test_jwt_assertion_is_signed_and_has_claims(rsa_key, key_file):
    assertion = zitadel.build_jwt_assertion(key_file, "https://z.example.com", now=1000)
    head, claims, sig = assertion.split(".")

    assert json.loads(_unb64(head)) == {"alg": "RS256", "kid": "kid-1"}
    assert json.loads(_unb64(claims)) == {
        "iss": "admin-sa", "sub": "admin-sa", "aud": "https://z.example.com", "iat": 1000, "exp": 1300}
    rsa_key.public_key().verify(
        _unb64(sig), ("%s.%s" % (head, claims)).encode(), padding.PKCS1v15(), hashes.SHA256())


def test_quote_path_escapes_slashes():
    assert zitadel.quote_path("a/b c") == "a%2Fb%20c"
