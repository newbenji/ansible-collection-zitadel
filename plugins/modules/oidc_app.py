#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Benjamin Andersen (@newbenji)
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
module: oidc_app
short_description: Manage OIDC applications (clients) in a ZITADEL project
version_added: "0.2.0"
description:
  - Create, update or delete an OpenID Connect application (OAuth2 client) in a
    ZITADEL project through the ZITADEL v2 Application service.
  - Applications are matched by O(name) within the project. Options that are not
    set keep their current value on existing applications. When creating, unset
    options use the defaults listed for each option.
  - "The client secret is returned by ZITADEL only once: when the application is
    created, or when O(regenerate_secret=true). Register the result with
    C(no_log: true) and store the secret right away, for example in a Kubernetes
    Secret or a vault."
author:
  - Benjamin Andersen (@newbenji)
extends_documentation_fragment:
  - newbenji.zitadel.auth
  - ansible.builtin.action_common_attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
  platform:
    platforms: all
options:
  project_id:
    description:
      - ID of the project the application belongs to, for example the
        RV(newbenji.zitadel.project#module:project_id) of M(newbenji.zitadel.project).
    required: true
    type: str
  name:
    description:
      - Name of the application. Users may see it during sign-in.
    required: true
    type: str
  app_type:
    description:
      - OAuth2 client type. V(web) is a server-side app that can keep a secret,
        V(user_agent) a browser single-page app, V(native) a mobile or desktop app.
      - Defaults to V(web) when creating.
    type: str
    choices: [web, user_agent, native]
  auth_method:
    description:
      - How the client authenticates at the token endpoint.
      - V(basic) and V(post) use a client secret, V(private_key_jwt) a key,
        V(none) nothing (public client, use PKCE).
      - Defaults to V(basic) for O(app_type=web) and V(none) otherwise when creating.
    type: str
    choices: [basic, post, none, private_key_jwt]
  redirect_uris:
    description:
      - Allowed callback URIs. The list replaces the current one.
      - ZITADEL cannot clear this list through the API, so an empty list is rejected.
    type: list
    elements: str
  post_logout_redirect_uris:
    description:
      - Allowed redirect URIs after logout. The list replaces the current one.
    type: list
    elements: str
  response_types:
    description:
      - Allowed OIDC response types. Defaults to V(code) when creating.
    type: list
    elements: str
    choices: [code, id_token, id_token_token]
  grant_types:
    description:
      - Allowed grant types. Defaults to V(authorization_code) when creating.
    type: list
    elements: str
    choices: [authorization_code, implicit, refresh_token, device_code, token_exchange]
  access_token_type:
    description:
      - V(bearer) issues opaque tokens that must be introspected, V(jwt) self-contained JWTs.
      - Defaults to V(bearer) when creating.
    type: str
    choices: [bearer, jwt]
  access_token_role_assertion:
    description:
      - Add the user's roles to the access token (needs O(access_token_type=jwt)).
    type: bool
  id_token_role_assertion:
    description:
      - Add the user's roles to the ID token.
    type: bool
  id_token_userinfo_assertion:
    description:
      - Add profile, email, address and phone claims to the ID token. Not OIDC compliant,
        but some applications need it.
    type: bool
  development_mode:
    description:
      - Allow non-compliant settings such as C(http://) redirect URIs. Do not use in production.
    type: bool
  additional_origins:
    description:
      - Extra origins (scheme, host and port) allowed to use the app, besides the
        redirect URI origins.
    type: list
    elements: str
  back_channel_logout_uri:
    description:
      - URI that ZITADEL calls to tell the app a session ended (OIDC back-channel logout).
    type: str
  clock_skew:
    description:
      - Seconds (0 to 5) to tolerate clock differences between ZITADEL and the app.
    type: int
  skip_native_app_success_page:
    description:
      - For native apps, skip the success page and open the app right after login.
    type: bool
  regenerate_secret:
    description:
      - Generate a new client secret for an existing application and return it.
        The old secret stops working. Always reports a change.
      - Only for applications that use a client secret (O(auth_method=basic) or V(post)).
    type: bool
    default: false
  state:
    description:
      - Whether the application should exist.
    type: str
    choices: [present, absent]
    default: present
seealso:
  - module: newbenji.zitadel.project
  - name: ZITADEL OIDC applications
    description: Configuration options for OIDC applications in ZITADEL.
    link: https://zitadel.com/docs/guides/manage/console/applications
'''

EXAMPLES = r'''
- name: Ensure the homelab project exists
  newbenji.zitadel.project:
    name: homelab
  register: project

- name: Ensure an OIDC client for Grafana
  newbenji.zitadel.oidc_app:
    project_id: "{{ project.project_id }}"
    name: grafana
    app_type: web
    auth_method: basic
    redirect_uris:
      - https://grafana.example.com/login/generic_oauth
    post_logout_redirect_uris:
      - https://grafana.example.com/login
    grant_types: [authorization_code, refresh_token]
  register: grafana
  no_log: true  # the result holds the client secret on creation

- name: Store the client credentials in Kubernetes (only when a new secret was issued)
  kubernetes.core.k8s:
    state: present
    definition:
      apiVersion: v1
      kind: Secret
      metadata:
        name: grafana-oidc
        namespace: monitoring
      stringData:
        client-id: "{{ grafana.client_id }}"
        client-secret: "{{ grafana.client_secret }}"
  when: grafana.client_secret is defined
  no_log: true

- name: Single-page app with PKCE (public client, no secret)
  newbenji.zitadel.oidc_app:
    project_id: "{{ project.project_id }}"
    name: dashboard
    app_type: user_agent
    redirect_uris: [https://dash.example.com/callback]

- name: Rotate the Grafana client secret
  newbenji.zitadel.oidc_app:
    project_id: "{{ project.project_id }}"
    name: grafana
    regenerate_secret: true
  register: grafana
  no_log: true
'''

RETURN = r'''
application_id:
  description: ID of the application.
  returned: when the application exists, unless it would only be created in check mode
  type: str
  sample: "302815613184377092"
client_id:
  description: OAuth2 client ID to configure in the application.
  returned: when the application exists, unless it would only be created in check mode
  type: str
  sample: "302815613184377092@homelab"
client_secret:
  description:
    - OAuth2 client secret.
    - Only returned when the application was created with a secret-based O(auth_method),
      or with O(regenerate_secret=true).
  returned: when a secret was issued
  type: str
non_compliant:
  description: Whether ZITADEL considers the configuration not OIDC compliant.
  returned: when the application was created
  type: bool
compliance_problems:
  description: ZITADEL's explanation of why the configuration is not compliant.
  returned: when the application was created
  type: list
  elements: dict
app:
  description: The application's OIDC settings after the module ran, as ZITADEL names them.
  returned: when O(state=present)
  type: dict
  sample:
    applicationType: OIDC_APP_TYPE_WEB
    authMethodType: OIDC_AUTH_METHOD_TYPE_BASIC
    redirectUris: [https://grafana.example.com/login/generic_oauth]
    grantTypes: [OIDC_GRANT_TYPE_AUTHORIZATION_CODE]
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

SERVICE = 'zitadel.application.v2.ApplicationService'

# Enum names in protobuf order (the index is the wire number; index 0 is the default).
APP_TYPES = ['OIDC_APP_TYPE_WEB', 'OIDC_APP_TYPE_USER_AGENT', 'OIDC_APP_TYPE_NATIVE']
AUTH_METHODS = ['OIDC_AUTH_METHOD_TYPE_BASIC', 'OIDC_AUTH_METHOD_TYPE_POST',
                'OIDC_AUTH_METHOD_TYPE_NONE', 'OIDC_AUTH_METHOD_TYPE_PRIVATE_KEY_JWT']
RESPONSE_TYPES = ['OIDC_RESPONSE_TYPE_UNSPECIFIED', 'OIDC_RESPONSE_TYPE_CODE',
                  'OIDC_RESPONSE_TYPE_ID_TOKEN', 'OIDC_RESPONSE_TYPE_ID_TOKEN_TOKEN']
GRANT_TYPES = ['OIDC_GRANT_TYPE_AUTHORIZATION_CODE', 'OIDC_GRANT_TYPE_IMPLICIT',
               'OIDC_GRANT_TYPE_REFRESH_TOKEN', 'OIDC_GRANT_TYPE_DEVICE_CODE',
               'OIDC_GRANT_TYPE_TOKEN_EXCHANGE']
TOKEN_TYPES = ['OIDC_TOKEN_TYPE_BEARER', 'OIDC_TOKEN_TYPE_JWT']
SECRET_AUTH_METHODS = ('OIDC_AUTH_METHOD_TYPE_BASIC', 'OIDC_AUTH_METHOD_TYPE_POST')

# module option -> (API field, enum names or None, enum prefix)
ENUM_FIELDS = {
    'app_type': ('applicationType', APP_TYPES, 'OIDC_APP_TYPE_'),
    'auth_method': ('authMethodType', AUTH_METHODS, 'OIDC_AUTH_METHOD_TYPE_'),
    'access_token_type': ('accessTokenType', TOKEN_TYPES, 'OIDC_TOKEN_TYPE_'),
}
ENUM_LIST_FIELDS = {
    'response_types': ('responseTypes', RESPONSE_TYPES, 'OIDC_RESPONSE_TYPE_'),
    'grant_types': ('grantTypes', GRANT_TYPES, 'OIDC_GRANT_TYPE_'),
}
LIST_FIELDS = {
    'redirect_uris': 'redirectUris',
    'post_logout_redirect_uris': 'postLogoutRedirectUris',
    'additional_origins': 'additionalOrigins',
}
BOOL_FIELDS = {
    'access_token_role_assertion': 'accessTokenRoleAssertion',
    'id_token_role_assertion': 'idTokenRoleAssertion',
    'id_token_userinfo_assertion': 'idTokenUserinfoAssertion',
    'development_mode': 'developmentMode',
    'skip_native_app_success_page': 'skipNativeAppSuccessPage',
}


def duration(seconds):
    """Format seconds as a protobuf JSON Duration (e.g. '2s', '0.5s')."""
    return '%gs' % float(seconds)


def normalize(config):
    """Fill in the defaults protojson leaves out, so settings compare correctly."""
    current = {}
    for api, names, dummy in ENUM_FIELDS.values():
        current[api] = enum_value(config.get(api), names)
    for api, names, dummy in ENUM_LIST_FIELDS.values():
        current[api] = [enum_value(v, names) for v in config.get(api) or []]
    for api in LIST_FIELDS.values():
        current[api] = list(config.get(api) or [])
    for api in BOOL_FIELDS.values():
        current[api] = bool(config.get(api))
    current['backChannelLogoutUri'] = config.get('backChannelLogoutUri') or ''
    current['clockSkew'] = duration(str(config.get('clockSkew') or '0s').rstrip('s') or 0)
    return current


def desired_settings(params):
    """API fields for every option the user set."""
    desired = {}
    for opt, (api, dummy, prefix) in ENUM_FIELDS.items():
        if params[opt] is not None:
            desired[api] = prefix + params[opt].upper()
    for opt, (api, dummy, prefix) in ENUM_LIST_FIELDS.items():
        if params[opt] is not None:
            desired[api] = [prefix + v.upper() for v in params[opt]]
    for opt, api in LIST_FIELDS.items():
        if params[opt] is not None:
            desired[api] = list(params[opt])
    for opt, api in BOOL_FIELDS.items():
        if params[opt] is not None:
            desired[api] = params[opt]
    if params['back_channel_logout_uri'] is not None:
        desired['backChannelLogoutUri'] = params['back_channel_logout_uri']
    if params['clock_skew'] is not None:
        desired['clockSkew'] = duration(params['clock_skew'])
    return desired


def creation_settings(desired):
    """Desired settings plus the defaults this module documents for new applications."""
    settings = dict(desired)
    settings.setdefault('applicationType', APP_TYPES[0])
    if 'authMethodType' not in settings:
        web = settings['applicationType'] == 'OIDC_APP_TYPE_WEB'
        settings['authMethodType'] = 'OIDC_AUTH_METHOD_TYPE_BASIC' if web else 'OIDC_AUTH_METHOD_TYPE_NONE'
    settings.setdefault('responseTypes', ['OIDC_RESPONSE_TYPE_CODE'])
    settings.setdefault('grantTypes', ['OIDC_GRANT_TYPE_AUTHORIZATION_CODE'])
    return settings


def find_app(client, project_id, name):
    apps = client.search('ListApplications', {'filters': [
        {'projectIdFilter': {'projectId': project_id}},
        {'nameFilter': {'name': name, 'method': 'TEXT_FILTER_METHOD_EQUALS'}},
    ]}, result_key='applications', service=SERVICE)
    matches = [a for a in apps if a.get('name') == name
               and a.get('projectId', project_id) == project_id
               and a.get('state') != 'APPLICATION_STATE_REMOVED']
    if len(matches) > 1:
        client.module.fail_json(msg="Found %d applications named %r in project %s; names must be unique"
                                % (len(matches), name, project_id))
    if matches and 'oidcConfiguration' not in matches[0]:
        client.module.fail_json(msg="Application %r exists but is not an OIDC application" % name)
    return matches[0] if matches else None


def main():
    argument_spec = zitadel_argument_spec()
    argument_spec.update(
        project_id=dict(type='str', required=True),
        name=dict(type='str', required=True),
        app_type=dict(type='str', choices=['web', 'user_agent', 'native']),
        auth_method=dict(type='str', choices=['basic', 'post', 'none', 'private_key_jwt']),
        redirect_uris=dict(type='list', elements='str'),
        post_logout_redirect_uris=dict(type='list', elements='str'),
        response_types=dict(type='list', elements='str', choices=['code', 'id_token', 'id_token_token']),
        grant_types=dict(type='list', elements='str', choices=[
            'authorization_code', 'implicit', 'refresh_token', 'device_code', 'token_exchange']),
        access_token_type=dict(type='str', choices=['bearer', 'jwt']),
        access_token_role_assertion=dict(type='bool'),
        id_token_role_assertion=dict(type='bool'),
        id_token_userinfo_assertion=dict(type='bool'),
        development_mode=dict(type='bool'),
        additional_origins=dict(type='list', elements='str'),
        back_channel_logout_uri=dict(type='str'),
        clock_skew=dict(type='int'),
        skip_native_app_success_page=dict(type='bool'),
        regenerate_secret=dict(type='bool', default=False, no_log=False),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
    )
    module = AnsibleModule(
        argument_spec=argument_spec,
        required_one_of=AUTH_REQUIRED_ONE_OF,
        mutually_exclusive=AUTH_MUTUALLY_EXCLUSIVE,
        supports_check_mode=True,
    )
    params = module.params
    if params['clock_skew'] is not None and not 0 <= params['clock_skew'] <= 5:
        module.fail_json(msg="clock_skew must be between 0 and 5 seconds")
    if params['redirect_uris'] == []:
        module.fail_json(msg="redirect_uris cannot be emptied through the ZITADEL API; omit it instead")

    client = ZitadelClient(module)
    project_id = params['project_id']
    name = params['name']
    existing = find_app(client, project_id, name)
    result = dict(changed=False)

    if params['state'] == 'absent':
        if existing:
            result.update(changed=True, application_id=existing['applicationId'])
            if module._diff:
                result['diff'] = dict(before=dict(name=name, **normalize(existing['oidcConfiguration'])), after={})
            if not module.check_mode:
                client.rpc(SERVICE, 'DeleteApplication',
                           {'applicationId': existing['applicationId'], 'projectId': project_id})
        module.exit_json(**result)

    desired = desired_settings(params)

    if existing is None:
        settings = creation_settings(desired)
        result.update(changed=True, app=settings)
        if module._diff:
            result['diff'] = dict(before={}, after=dict(name=name, **settings))
        if not module.check_mode:
            created = client.rpc(SERVICE, 'CreateApplication',
                                 {'projectId': project_id, 'name': name, 'oidcConfiguration': settings})
            oidc = created.get('oidcConfiguration') or {}
            result.update(application_id=created.get('applicationId'), client_id=oidc.get('clientId'),
                          non_compliant=bool(oidc.get('nonCompliant')),
                          compliance_problems=oidc.get('complianceProblems') or [])
            if oidc.get('clientSecret'):
                result['client_secret'] = oidc['clientSecret']
        module.exit_json(**result)

    config = existing['oidcConfiguration']
    current = normalize(config)
    before, changes = compare_fields(current, desired)
    app = dict(current)
    app.update(changes)
    result.update(application_id=existing['applicationId'], client_id=config.get('clientId'),
                  app=app, changed=bool(changes))

    if changes:
        if module._diff:
            result['diff'] = dict(before=before, after=changes)
        if not module.check_mode:
            client.rpc(SERVICE, 'UpdateApplication', {
                'applicationId': existing['applicationId'], 'projectId': project_id,
                'oidcConfiguration': changes})

    if params['regenerate_secret']:
        if app['authMethodType'] not in SECRET_AUTH_METHODS:
            module.fail_json(msg="regenerate_secret needs auth_method basic or post, not %s"
                             % app['authMethodType'])
        result['changed'] = True
        if not module.check_mode:
            generated = client.rpc(SERVICE, 'GenerateClientSecret',
                                   {'applicationId': existing['applicationId'], 'projectId': project_id})
            result['client_secret'] = generated.get('clientSecret')

    module.exit_json(**result)


if __name__ == '__main__':
    main()
