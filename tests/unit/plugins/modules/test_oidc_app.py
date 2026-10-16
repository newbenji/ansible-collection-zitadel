# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Benjamin Andersen (@newbenji)
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import pytest

from ansible_collections.newbenji.zitadel.plugins.modules import oidc_app
from ansible_collections.newbenji.zitadel.tests.unit.plugins.modules.conftest import FakeZitadel

PROJECT = "p-1"
REDIRECT = ["https://grafana.example.com/login/generic_oauth"]


def app(**config):
    """An existing app as the API returns it: default values left out."""
    base = {"redirectUris": REDIRECT, "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
            "grantTypes": ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"], "clientId": "a-1@project"}
    base.update(config)
    return {"applicationId": "a-1", "projectId": PROJECT, "name": "grafana",
            "state": "APPLICATION_STATE_ACTIVE", "oidcConfiguration": base}


def calls(fake, rpc):
    return [c[2] for c in fake.calls if c[1].endswith("/" + rpc)]


# -- create ------------------------------------------------------------------

def test_creates_web_app_with_defaults_and_returns_secret(run):
    fake = FakeZitadel()
    result = run(oidc_app.main, fake, project_id=PROJECT, name="grafana", redirect_uris=REDIRECT)
    assert result["changed"]
    assert result["client_id"].endswith("@project")
    assert result["client_secret"].startswith("SECRET-")
    created = calls(fake, "CreateApplication")[0]
    assert created["projectId"] == PROJECT and created["name"] == "grafana"
    assert created["oidcConfiguration"] == {
        "redirectUris": REDIRECT,
        "applicationType": "OIDC_APP_TYPE_WEB",
        "authMethodType": "OIDC_AUTH_METHOD_TYPE_BASIC",
        "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
        "grantTypes": ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"],
    }


def test_spa_defaults_to_public_client_without_secret(run):
    fake = FakeZitadel()
    result = run(oidc_app.main, fake, project_id=PROJECT, name="dash", app_type="user_agent",
                 redirect_uris=["https://dash.example.com/cb"])
    created = calls(fake, "CreateApplication")[0]["oidcConfiguration"]
    assert created["authMethodType"] == "OIDC_AUTH_METHOD_TYPE_NONE"
    assert "client_secret" not in result


def test_maps_all_options_on_create(run):
    fake = FakeZitadel()
    run(oidc_app.main, fake, project_id=PROJECT, name="grafana", redirect_uris=REDIRECT,
        auth_method="post", grant_types=["authorization_code", "refresh_token"],
        access_token_type="jwt", access_token_role_assertion=True, id_token_role_assertion=True,
        id_token_userinfo_assertion=True, development_mode=False, clock_skew=2,
        post_logout_redirect_uris=["https://grafana.example.com/login"],
        additional_origins=["https://other.example.com"],
        back_channel_logout_uri="https://grafana.example.com/logout")
    created = calls(fake, "CreateApplication")[0]["oidcConfiguration"]
    assert created["authMethodType"] == "OIDC_AUTH_METHOD_TYPE_POST"
    assert created["grantTypes"] == ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE", "OIDC_GRANT_TYPE_REFRESH_TOKEN"]
    assert created["accessTokenType"] == "OIDC_TOKEN_TYPE_JWT"
    assert created["clockSkew"] == "2s"
    assert created["idTokenUserinfoAssertion"] is True
    assert created["backChannelLogoutUri"] == "https://grafana.example.com/logout"


# -- idempotency and update --------------------------------------------------

def test_idempotent_with_defaults_omitted_by_api(run):
    # Stored without WEB/BASIC/BEARER/false/0s, as protojson would return it.
    fake = FakeZitadel(apps=[app()])
    result = run(oidc_app.main, fake, project_id=PROJECT, name="grafana", redirect_uris=REDIRECT,
                 app_type="web", auth_method="basic", access_token_type="bearer",
                 development_mode=False, clock_skew=0, grant_types=["authorization_code"])
    assert not result["changed"]
    assert result["client_id"] == "a-1@project"
    assert "client_secret" not in result
    assert "UpdateApplication" not in fake.rpcs()


def test_list_order_does_not_matter(run):
    fake = FakeZitadel(apps=[app(redirectUris=["https://b", "https://a"])])
    assert not run(oidc_app.main, fake, project_id=PROJECT, name="grafana",
                   redirect_uris=["https://a", "https://b"])["changed"]


def test_updates_only_changed_settings_without_secret(run):
    fake = FakeZitadel(apps=[app()])
    new_redirects = REDIRECT + ["https://grafana2.example.com/cb"]
    result = run(oidc_app.main, fake, project_id=PROJECT, name="grafana",
                 redirect_uris=new_redirects, access_token_type="jwt", diff=True)
    assert result["changed"]
    assert "client_secret" not in result
    update = calls(fake, "UpdateApplication")[0]
    assert update == {"applicationId": "a-1", "projectId": PROJECT, "oidcConfiguration": {
        "redirectUris": new_redirects, "accessTokenType": "OIDC_TOKEN_TYPE_JWT"}}
    assert result["diff"]["before"] == {"redirectUris": REDIRECT, "accessTokenType": "OIDC_TOKEN_TYPE_BEARER"}


def test_regenerate_secret(run):
    fake = FakeZitadel(apps=[app()])
    result = run(oidc_app.main, fake, project_id=PROJECT, name="grafana", regenerate_secret=True)
    assert result["changed"]
    assert result["client_secret"] == "ROTATED-a-1"
    assert calls(fake, "GenerateClientSecret") == [{"applicationId": "a-1", "projectId": PROJECT}]


def test_regenerate_secret_rejected_for_public_client(run_failing):
    fake = FakeZitadel(apps=[app(authMethodType="OIDC_AUTH_METHOD_TYPE_NONE")])
    result = run_failing(oidc_app.main, fake, project_id=PROJECT, name="grafana", regenerate_secret=True)
    assert "basic or post" in result["msg"]


def test_check_mode_makes_no_changes(run):
    fake = FakeZitadel(apps=[app()])
    assert run(oidc_app.main, fake, project_id=PROJECT, name="new", check_mode=True)["changed"]
    assert run(oidc_app.main, fake, project_id=PROJECT, name="grafana", access_token_type="jwt",
               check_mode=True)["changed"]
    assert run(oidc_app.main, fake, project_id=PROJECT, name="grafana", regenerate_secret=True,
               check_mode=True)["changed"]
    assert run(oidc_app.main, fake, project_id=PROJECT, name="grafana", state="absent",
               check_mode=True)["changed"]
    mutating = {"CreateApplication", "UpdateApplication", "GenerateClientSecret", "DeleteApplication"}
    assert not mutating & set(fake.rpcs())


# -- delete ------------------------------------------------------------------

def test_deletes_app(run):
    fake = FakeZitadel(apps=[app()])
    result = run(oidc_app.main, fake, project_id=PROJECT, name="grafana", state="absent")
    assert result["changed"]
    assert calls(fake, "DeleteApplication") == [{"applicationId": "a-1", "projectId": PROJECT}]


def test_absent_is_noop_when_missing(run):
    assert not run(oidc_app.main, FakeZitadel(), project_id=PROJECT, name="grafana", state="absent")["changed"]


# -- validation --------------------------------------------------------------

@pytest.mark.parametrize("args,error", [
    ({"clock_skew": 9}, "between 0 and 5"),
    ({"redirect_uris": []}, "cannot be emptied"),
])
def test_rejects_invalid_options(run_failing, args, error):
    assert error in run_failing(oidc_app.main, FakeZitadel(), project_id=PROJECT, name="grafana", **args)["msg"]


def test_non_oidc_app_with_same_name_fails(run_failing):
    api_app = {"applicationId": "a-2", "projectId": PROJECT, "name": "grafana",
               "apiConfiguration": {"clientId": "x"}}
    result = run_failing(oidc_app.main, FakeZitadel(apps=[api_app]), project_id=PROJECT, name="grafana")
    assert "not an OIDC application" in result["msg"]
