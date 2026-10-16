# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Benjamin Andersen (@newbenji)
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared fixtures: an in-memory ZITADEL speaking the v2 Connect JSON protocol."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import io
import json
from unittest import mock

import pytest

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.testing import patch_module_args
from ansible_collections.newbenji.zitadel.plugins.module_utils import zitadel

ENDPOINT = "https://z.example.com"
OWN_ORG = "org-1"

# protojson omits fields that hold their default value; the fake does the same
# so the modules' normalization is exercised.
ENUM_DEFAULTS = {
    "OIDC_APP_TYPE_WEB", "OIDC_AUTH_METHOD_TYPE_BASIC", "OIDC_TOKEN_TYPE_BEARER",
    "OIDC_VERSION_1_0", "PRIVATE_LABELING_SETTING_UNSPECIFIED",
}


def strip_defaults(data):
    def is_default(value):
        if isinstance(value, list):
            return value == []
        return value in (False, "", "0s", None) or (isinstance(value, str) and value in ENUM_DEFAULTS)

    return dict((k, v) for k, v in data.items() if not is_default(v))


class Exit(Exception):
    def __init__(self, result):
        super(Exit, self).__init__("exit_json")
        self.result = result


class Fail(Exception):
    def __init__(self, result):
        super(Fail, self).__init__(result.get("msg"))
        self.result = result


class FakeZitadel(object):
    """Stands in for fetch_url. Holds projects and applications in memory."""

    def __init__(self, projects=None, apps=None):
        self.projects = list(projects or [])
        self.apps = list(apps or [])
        self.calls = []
        self._next_id = 100

    def new_id(self):
        self._next_id += 1
        return str(self._next_id)

    def rpcs(self):
        return [c[1].rsplit("/", 1)[-1] for c in self.calls]

    def __call__(self, module, url, data=None, headers=None, method=None, timeout=10):
        path = url[len(ENDPOINT):]
        body = json.loads(data) if data else {}
        self.calls.append((method, path, body, headers))
        handler = getattr(self, "on_" + path.rsplit("/", 1)[-1], None)
        if path == "/auth/v1/users/me":
            reply = {"user": {"id": "admin", "details": {"resourceOwner": OWN_ORG}}}
        elif handler is None:
            return None, {"status": 404, "body": b'{"code":"unimplemented"}', "msg": "Not Found"}
        else:
            reply = handler(body)
            if isinstance(reply, tuple):
                return None, {"status": reply[0], "body": json.dumps(reply[1]).encode(), "msg": "error"}
        return io.BytesIO(json.dumps(reply).encode()), {"status": 200}

    @staticmethod
    def page(items, key, body):
        page = body.get("pagination") or {}
        offset, limit = page.get("offset", 0), page.get("limit", 100)
        return {key: items[offset:offset + limit], "pagination": {"totalResult": str(len(items))}}

    # -- ProjectService ------------------------------------------------------
    def on_ListProjects(self, body):
        found = self.projects
        for flt in body.get("filters", []):
            if "projectNameFilter" in flt:
                found = [p for p in found if p["name"] == flt["projectNameFilter"]["projectName"]]
            if "organizationIdFilter" in flt:
                found = [p for p in found if p["organizationId"] == flt["organizationIdFilter"]["organizationId"]]
        return self.page(found, "projects", body)

    def on_CreateProject(self, body):
        project = strip_defaults(body)
        project["projectId"] = self.new_id()
        project["state"] = "PROJECT_STATE_ACTIVE"
        self.projects.append(project)
        return {"projectId": project["projectId"], "creationDate": "2026-10-16T00:00:00Z"}

    def on_UpdateProject(self, body):
        index = [p["projectId"] for p in self.projects].index(body["projectId"])
        self.projects[index] = strip_defaults(dict(self.projects[index], **body))
        return {"changeDate": "2026-10-16T00:00:01Z"}

    def on_DeleteProject(self, body):
        self.projects = [p for p in self.projects if p["projectId"] != body["projectId"]]
        return {}

    # -- ApplicationService --------------------------------------------------
    def on_ListApplications(self, body):
        found = self.apps
        for flt in body.get("filters", []):
            if "projectIdFilter" in flt:
                found = [a for a in found if a["projectId"] == flt["projectIdFilter"]["projectId"]]
            if "nameFilter" in flt:
                found = [a for a in found if a["name"] == flt["nameFilter"]["name"]]
        return self.page(found, "applications", body)

    def on_CreateApplication(self, body):
        app_id = self.new_id()
        config = body["oidcConfiguration"]
        client_id = "%s@project" % app_id
        self.apps.append({
            "applicationId": app_id, "projectId": body["projectId"], "name": body["name"],
            "state": "APPLICATION_STATE_ACTIVE",
            "oidcConfiguration": dict(strip_defaults(config), clientId=client_id),
        })
        reply = {"clientId": client_id, "nonCompliant": False}
        if config.get("authMethodType") in ("OIDC_AUTH_METHOD_TYPE_BASIC", "OIDC_AUTH_METHOD_TYPE_POST"):
            reply["clientSecret"] = "SECRET-%s" % app_id
        return {"applicationId": app_id, "creationDate": "2026-10-16T00:00:00Z",
                "oidcConfiguration": strip_defaults(reply)}

    def on_UpdateApplication(self, body):
        app = [a for a in self.apps if a["applicationId"] == body["applicationId"]][0]
        config = dict(app["oidcConfiguration"], **body["oidcConfiguration"])
        app["oidcConfiguration"] = strip_defaults(config)
        return {"changeDate": "2026-10-16T00:00:01Z"}

    def on_GenerateClientSecret(self, body):
        return {"clientSecret": "ROTATED-%s" % body["applicationId"], "creationDate": "2026-10-16T00:00:02Z"}

    def on_DeleteApplication(self, body):
        self.apps = [a for a in self.apps if a["applicationId"] != body["applicationId"]]
        return {}


@pytest.fixture(autouse=True)
def patch_exits(monkeypatch):
    def exit_json(self, **kwargs):
        raise Exit(kwargs)

    def fail_json(self, **kwargs):
        raise Fail(kwargs)

    monkeypatch.setattr(AnsibleModule, "exit_json", exit_json)
    monkeypatch.setattr(AnsibleModule, "fail_json", fail_json)
    for var in ("ZITADEL_ENDPOINT", "ZITADEL_API_TOKEN", "ZITADEL_SERVICE_ACCOUNT_KEY"):
        monkeypatch.delenv(var, raising=False)


def _run(module_main, fake, expect, check_mode=False, diff=False, **args):
    params = {"endpoint": ENDPOINT, "api_token": "admin-pat"}
    params.update(args)
    params = dict((k, v) for k, v in params.items() if v is not None)
    if check_mode:
        params["_ansible_check_mode"] = True
    if diff:
        params["_ansible_diff"] = True
    with patch_module_args(params), mock.patch.object(zitadel, "fetch_url", fake):
        with pytest.raises(expect) as ctx:
            module_main()
    return ctx.value.result


@pytest.fixture
def run():
    """run(module.main, fake, **args) -> exit_json result."""
    return lambda module_main, fake, **kw: _run(module_main, fake, Exit, **kw)


@pytest.fixture
def run_failing():
    """run_failing(module.main, fake, **args) -> fail_json result."""
    return lambda module_main, fake, **kw: _run(module_main, fake, Fail, **kw)
