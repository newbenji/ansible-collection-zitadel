#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Benjamin Andersen (@newbenji)
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
module: api_token
short_description: Manage personal access tokens (PATs) of a ZITADEL machine user
version_added: "0.1.0"
description:
  - Create or remove personal access tokens (PATs) for a ZITADEL machine user
    (service account) through the ZITADEL User v2 REST API.
  - "ZITADEL PATs have no name or label, so idempotency is defined per user.
    With O(state=present) a new token is created only when the user has no
    active (non-expired) token. With O(state=absent) the token given in
    O(token_id) is removed, or every token of the user if O(token_id) is omitted."
  - "The token secret is returned by ZITADEL only once, at creation. Either set
    O(token_path) so the module writes it to a file, or register the result and
    put C(no_log: true) on the task so the secret does not end up in logs."
author:
  - Benjamin Andersen (@newbenji)
extends_documentation_fragment:
  - newbenji.zitadel.auth
  - ansible.builtin.action_common_attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: none
  platform:
    platforms: all
options:
  user_id:
    description:
      - ID of the machine user that owns the tokens.
    required: true
    type: str
  token_id:
    description:
      - ID of a single token to remove. Only valid with O(state=absent).
    type: str
  expiration_date:
    description:
      - Expiry of a newly created token as an RFC 3339 timestamp, for example
        V(2027-01-01T00:00:00Z). If omitted the token does not expire.
      - Existing tokens are not changed when this value changes.
    type: str
  token_path:
    description:
      - When a token is created, write its secret to this file with mode C(0600)
        instead of returning it in the result. The file is written on the host the
        module runs on.
      - If an active token already exists but this file is missing, the module
        warns, because the secret cannot be read back from ZITADEL.
    type: path
  state:
    description:
      - Whether the user should have an active token (V(present)) or none (V(absent)).
    type: str
    choices:
      - present
      - absent
    default: present
seealso:
  - name: ZITADEL personal access tokens
    description: How PATs work for ZITADEL service accounts.
    link: https://zitadel.com/docs/guides/integrate/service-accounts/personal-access-token
'''

EXAMPLES = r'''
- name: Ensure the ci-deploy machine user has a token, stored on disk
  newbenji.zitadel.api_token:
    endpoint: https://zitadel.example.com
    api_token: "{{ zitadel_admin_token }}"
    user_id: "{{ ci_user_id }}"
    expiration_date: "2027-01-01T00:00:00Z"
    token_path: "{{ playbook_dir }}/.secrets/ci-deploy.pat"

- name: Same, authenticating with a service-account key file
  newbenji.zitadel.api_token:
    endpoint: https://zitadel.example.com
    service_account_key: "{{ lookup('ansible.builtin.file', 'zitadel-admin-key.json') }}"
    user_id: "{{ ci_user_id }}"
    token_path: "{{ playbook_dir }}/.secrets/ci-deploy.pat"

- name: Create a token and keep the secret in a variable
  newbenji.zitadel.api_token:
    user_id: "{{ ci_user_id }}"  # endpoint and api_token from ZITADEL_* environment variables
  register: ci_pat
  no_log: true

- name: Remove every token of the user
  newbenji.zitadel.api_token:
    endpoint: https://zitadel.example.com
    api_token: "{{ zitadel_admin_token }}"
    user_id: "{{ ci_user_id }}"
    state: absent
'''

RETURN = r'''
token_id:
  description: ID of the created token, or of the active token that already existed.
  returned: when O(state=present) and not in check mode with no active token
  type: str
  sample: "302815613184311300"
token:
  description:
    - Secret of the newly created token.
    - Only returned on creation, and only when O(token_path) is not set.
  returned: when a token was created
  type: str
tokens:
  description: Metadata (no secrets) of the user's tokens before the module acted.
  returned: always
  type: list
  elements: dict
  sample:
    - id: "302815613184311300"
      userId: "302815613184245764"
      organizationId: "302815613184180228"
      creationDate: "2026-10-16T09:00:00Z"
      changeDate: "2026-10-16T09:00:00Z"
      expirationDate: "2027-01-01T00:00:00Z"
removed:
  description: IDs of the tokens that were removed (or would be, in check mode).
  returned: when O(state=absent)
  type: list
  elements: str
'''

import datetime
import os

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.newbenji.zitadel.plugins.module_utils.zitadel import (
    AUTH_MUTUALLY_EXCLUSIVE,
    AUTH_REQUIRED_ONE_OF,
    ZitadelClient,
    parse_timestamp,
    quote_path,
    zitadel_argument_spec,
)


def is_active(token, now):
    """A token without (or with an unparseable) expiry counts as active."""
    expires = parse_timestamp(token.get('expirationDate'))
    return expires is None or expires > now


def list_tokens(client, user_id):
    return client.search('/v2/users/pats/search', {'filters': [{'userIdFilter': {'id': user_id}}]})


def write_secret(path, secret):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(secret)
    # O_CREAT's mode is ignored when the file already exists.
    os.chmod(path, 0o600)


def ensure_present(module, client, user_id, tokens):
    params = module.params
    now = datetime.datetime.now(datetime.timezone.utc)
    active = [t for t in tokens if is_active(t, now)]
    if active:
        token_path = params['token_path']
        if token_path and not os.path.exists(token_path):
            module.warn("An active token already exists for user %s but %s is missing; ZITADEL "
                        "cannot return the secret again. Remove the token (state=absent) to rotate it."
                        % (user_id, token_path))
        return dict(changed=False, token_id=active[0].get('id'))

    if module.check_mode:
        return dict(changed=True)

    payload = {}
    if params['expiration_date']:
        payload['expirationDate'] = params['expiration_date']
    created = client.request('POST', '/v2/users/%s/pats' % quote_path(user_id), payload=payload)
    secret = created.get('token')
    result = dict(changed=True, token_id=created.get('tokenId'))
    if params['token_path']:
        write_secret(params['token_path'], secret)
    else:
        result['token'] = secret
    return result


def ensure_absent(module, client, user_id, tokens):
    token_id = module.params['token_id']
    targets = [t.get('id') for t in tokens if token_id is None or t.get('id') == token_id]
    if not module.check_mode:
        for target in targets:
            client.request('DELETE', '/v2/users/%s/pats/%s' % (quote_path(user_id), quote_path(target)))
    return dict(changed=bool(targets), removed=targets)


def main():
    argument_spec = zitadel_argument_spec()
    argument_spec.update(
        user_id=dict(type='str', required=True),
        token_id=dict(type='str'),
        expiration_date=dict(type='str'),
        token_path=dict(type='path'),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
    )
    module = AnsibleModule(
        argument_spec=argument_spec,
        required_one_of=AUTH_REQUIRED_ONE_OF,
        mutually_exclusive=AUTH_MUTUALLY_EXCLUSIVE,
        supports_check_mode=True,
    )
    params = module.params

    if params['token_id'] and params['state'] == 'present':
        module.fail_json(msg="token_id is only valid with state=absent")
    if params['expiration_date'] and parse_timestamp(params['expiration_date']) is None:
        module.fail_json(msg="expiration_date must be an RFC 3339 timestamp, e.g. 2027-01-01T00:00:00Z")

    client = ZitadelClient(module)
    user_id = params['user_id']
    tokens = list_tokens(client, user_id)
    if params['state'] == 'present':
        result = ensure_present(module, client, user_id, tokens)
    else:
        result = ensure_absent(module, client, user_id, tokens)

    module.exit_json(tokens=tokens, **result)


if __name__ == '__main__':
    main()
