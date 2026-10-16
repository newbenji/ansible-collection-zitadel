# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Benjamin Andersen (@newbenji)
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible_collections.newbenji.zitadel.plugins.modules import project
from ansible_collections.newbenji.zitadel.tests.unit.plugins.modules.conftest import OWN_ORG, FakeZitadel


def existing(**fields):
    base = {"projectId": "p-1", "organizationId": OWN_ORG, "name": "homelab", "state": "PROJECT_STATE_ACTIVE"}
    base.update(fields)
    return base


def test_creates_project_in_own_org(run):
    fake = FakeZitadel()
    result = run(project.main, fake, name="homelab", project_role_assertion=True)
    assert result["changed"]
    assert result["organization_id"] == OWN_ORG
    assert result["project_id"] == fake.projects[0]["projectId"]
    create = [c for c in fake.calls if c[1].endswith("/CreateProject")][0]
    assert create[1] == "/zitadel.project.v2.ProjectService/CreateProject"
    assert create[2] == {"organizationId": OWN_ORG, "name": "homelab", "projectRoleAssertion": True}
    assert create[3]["Connect-Protocol-Version"] == "1"


def test_explicit_organization_skips_lookup(run):
    fake = FakeZitadel()
    run(project.main, fake, name="homelab", organization_id="org-9")
    assert "/auth/v1/users/me" not in [c[1] for c in fake.calls]
    assert fake.projects[0]["organizationId"] == "org-9"


def test_idempotent_when_defaults_are_omitted_by_api(run):
    # The API omits false booleans and the UNSPECIFIED enum; asking for those
    # values must not cause an update.
    fake = FakeZitadel([existing()])
    result = run(project.main, fake, name="homelab", project_role_assertion=False,
                 private_labeling_setting="unspecified")
    assert not result["changed"]
    assert result["project_id"] == "p-1"
    assert "UpdateProject" not in fake.rpcs()


def test_updates_only_changed_fields(run):
    fake = FakeZitadel([existing(projectRoleAssertion=True)])
    result = run(project.main, fake, name="homelab", project_role_assertion=True,
                 authorization_required=True, diff=True)
    assert result["changed"]
    update = [c for c in fake.calls if c[1].endswith("/UpdateProject")][0][2]
    assert update == {"projectId": "p-1", "authorizationRequired": True}
    assert result["diff"] == {"before": {"authorizationRequired": False}, "after": {"authorizationRequired": True}}
    assert result["project"]["authorizationRequired"] is True


def test_check_mode_makes_no_changes(run):
    fake = FakeZitadel([existing()])
    assert run(project.main, fake, name="homelab", authorization_required=True, check_mode=True)["changed"]
    assert run(project.main, fake, name="new", check_mode=True)["changed"]
    assert run(project.main, fake, name="homelab", state="absent", check_mode=True)["changed"]
    assert not {"CreateProject", "UpdateProject", "DeleteProject"} & set(fake.rpcs())


def test_deletes_project(run):
    fake = FakeZitadel([existing()])
    result = run(project.main, fake, name="homelab", state="absent")
    assert result["changed"]
    assert fake.projects == []


def test_absent_is_noop_when_missing(run):
    fake = FakeZitadel()
    assert not run(project.main, fake, name="homelab", state="absent")["changed"]


def test_ignores_projects_in_other_orgs(run):
    fake = FakeZitadel([existing(organizationId="org-other")])
    result = run(project.main, fake, name="homelab")
    assert result["changed"]
    assert len(fake.projects) == 2


def test_duplicate_names_fail(run_failing):
    fake = FakeZitadel([existing(), existing(projectId="p-2")])
    assert "names must be unique" in run_failing(project.main, fake, name="homelab")["msg"]
