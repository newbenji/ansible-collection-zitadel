#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Benjamin Andersen (@newbenji)
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
module: project
short_description: Manage ZITADEL projects
version_added: "0.2.0"
description:
  - Create, update or delete a project in a ZITADEL organization through the
    ZITADEL v2 Project service.
  - Projects are matched by O(name) within the organization, so the name must be
    unique there. Options that are not set are left unchanged on existing projects.
author:
  - Benjamin Andersen (@newbenji)
extends_documentation_fragment:
  - newbenji.zitadel.auth
  - newbenji.zitadel.auth.ORGANIZATION
  - ansible.builtin.action_common_attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
  platform:
    platforms: all
options:
  name:
    description:
      - Name of the project. Users may see it, for example during sign-in.
    required: true
    type: str
  project_role_assertion:
    description:
      - Add the user's roles in this project to the userinfo endpoint (and tokens,
        if the application asks for it).
    type: bool
  authorization_required:
    description:
      - Only let users sign in to the project's applications if they have a role
        (authorization) in this project.
    type: bool
  project_access_required:
    description:
      - Only let users sign in if their organization owns or was granted this project.
    type: bool
  private_labeling_setting:
    description:
      - Which organization's branding the login page shows for this project.
    type: str
    choices:
      - unspecified
      - enforce_project_resource_owner_policy
      - allow_login_user_resource_owner_policy
  state:
    description:
      - Whether the project should exist.
      - V(absent) also deletes the project's applications and roles.
    type: str
    choices:
      - present
      - absent
    default: present
seealso:
  - module: newbenji.zitadel.oidc_app
'''

EXAMPLES = r'''
- name: Ensure the homelab project exists
  newbenji.zitadel.project:
    endpoint: https://zitadel.example.com
    api_token: "{{ zitadel_admin_token }}"
    name: homelab
    project_role_assertion: true
  register: homelab

- name: Use the project ID
  ansible.builtin.debug:
    msg: "Project ID is {{ homelab.project_id }}"

- name: Delete a project (and its applications)
  newbenji.zitadel.project:
    endpoint: https://zitadel.example.com
    api_token: "{{ zitadel_admin_token }}"
    name: old-project
    state: absent
'''

RETURN = r'''
project_id:
  description: ID of the project.
  returned: when the project exists, unless it would only be created in check mode
  type: str
  sample: "302815613184311300"
organization_id:
  description: ID of the organization the project belongs to.
  returned: always
  type: str
project:
  description: The project's settings after the module ran.
  returned: when O(state=present)
  type: dict
  sample:
    projectId: "302815613184311300"
    name: homelab
    projectRoleAssertion: true
    authorizationRequired: false
    projectAccessRequired: false
    privateLabelingSetting: PRIVATE_LABELING_SETTING_UNSPECIFIED
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.newbenji.zitadel.plugins.module_utils.zitadel import (
    AUTH_MUTUALLY_EXCLUSIVE,
    AUTH_REQUIRED_ONE_OF,
    ZitadelClient,
    compare_fields,
    enum_value,
    zitadel_argument_spec,
)

SERVICE = 'zitadel.project.v2.ProjectService'

PRIVATE_LABELING = [
    'PRIVATE_LABELING_SETTING_UNSPECIFIED',
    'PRIVATE_LABELING_SETTING_ENFORCE_PROJECT_RESOURCE_OWNER_POLICY',
    'PRIVATE_LABELING_SETTING_ALLOW_LOGIN_USER_RESOURCE_OWNER_POLICY',
]

# module option -> API field
BOOL_FIELDS = {
    'project_role_assertion': 'projectRoleAssertion',
    'authorization_required': 'authorizationRequired',
    'project_access_required': 'projectAccessRequired',
}


def find_project(client, organization_id, name):
    projects = client.search('ListProjects', {'filters': [
        {'projectNameFilter': {'projectName': name, 'method': 'TEXT_FILTER_METHOD_EQUALS'}},
        {'organizationIdFilter': {'organizationId': organization_id, 'type': 'OWNED'}},
    ]}, result_key='projects', service=SERVICE)
    matches = [p for p in projects
               if p.get('name') == name and p.get('organizationId', organization_id) == organization_id]
    if len(matches) > 1:
        client.module.fail_json(msg="Found %d projects named %r; names must be unique to manage them"
                                % (len(matches), name))
    return matches[0] if matches else None


def normalize(project):
    """Fill in the defaults protojson leaves out, so settings compare correctly."""
    current = dict((api, bool(project.get(api))) for api in BOOL_FIELDS.values())
    current['privateLabelingSetting'] = enum_value(project.get('privateLabelingSetting'), PRIVATE_LABELING)
    return current


def desired_settings(params):
    desired = dict((api, params[opt]) for opt, api in BOOL_FIELDS.items() if params[opt] is not None)
    if params['private_labeling_setting'] is not None:
        desired['privateLabelingSetting'] = 'PRIVATE_LABELING_SETTING_' + params['private_labeling_setting'].upper()
    return desired


def main():
    argument_spec = zitadel_argument_spec()
    argument_spec.update(
        organization_id=dict(type='str'),
        name=dict(type='str', required=True),
        project_role_assertion=dict(type='bool'),
        authorization_required=dict(type='bool'),
        project_access_required=dict(type='bool'),
        private_labeling_setting=dict(type='str', choices=[
            'unspecified', 'enforce_project_resource_owner_policy', 'allow_login_user_resource_owner_policy']),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
    )
    module = AnsibleModule(
        argument_spec=argument_spec,
        required_one_of=AUTH_REQUIRED_ONE_OF,
        mutually_exclusive=AUTH_MUTUALLY_EXCLUSIVE,
        supports_check_mode=True,
    )
    params = module.params
    client = ZitadelClient(module)
    org_id = params['organization_id'] or client.own_organization_id()
    name = params['name']

    existing = find_project(client, org_id, name)
    result = dict(changed=False, organization_id=org_id)

    if params['state'] == 'absent':
        if existing:
            result.update(changed=True, project_id=existing.get('projectId'))
            if module._diff:
                result['diff'] = dict(before=dict(name=name, **normalize(existing)), after={})
            if not module.check_mode:
                client.rpc(SERVICE, 'DeleteProject', {'projectId': existing['projectId']})
        module.exit_json(**result)

    desired = desired_settings(params)
    if existing is None:
        after = dict(name=name, **normalize({}))
        after.update(desired)
        result.update(changed=True, project=after)
        if module._diff:
            result['diff'] = dict(before={}, after=after)
        if not module.check_mode:
            payload = dict(organizationId=org_id, name=name, **desired)
            created = client.rpc(SERVICE, 'CreateProject', payload)
            result['project_id'] = created.get('projectId')
            after['projectId'] = result['project_id']
        module.exit_json(**result)

    current = normalize(existing)
    before, changes = compare_fields(current, desired)
    project = dict(projectId=existing['projectId'], name=name, **current)
    project.update(changes)
    result.update(project_id=existing['projectId'], project=project, changed=bool(changes))
    if changes:
        if module._diff:
            result['diff'] = dict(before=before, after=changes)
        if not module.check_mode:
            client.rpc(SERVICE, 'UpdateProject', dict(projectId=existing['projectId'], **changes))
    module.exit_json(**result)


if __name__ == '__main__':
    main()
