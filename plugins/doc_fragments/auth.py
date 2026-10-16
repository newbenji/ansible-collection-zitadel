# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Benjamin Andersen (@newbenji)
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type


class ModuleDocFragment(object):

    DOCUMENTATION = r'''
options:
  endpoint:
    description:
      - Base URL of the ZITADEL instance, for example V(https://zitadel.example.com).
      - Also used as the JWT audience when authenticating with O(service_account_key).
      - If not set, the E(ZITADEL_ENDPOINT) environment variable is used.
    required: true
    type: str
  api_token:
    description:
      - Personal access token (PAT) of an administrative machine user, sent as a Bearer token.
      - If not set, the E(ZITADEL_API_TOKEN) environment variable is used.
      - Exactly one of O(api_token) and O(service_account_key) is required.
    type: str
  service_account_key:
    description:
      - Contents of a ZITADEL service-account key file (the JSON with C(type),
        C(keyId), C(key) and C(userId)), as a dict or a JSON string.
      - The module signs a JWT with it and exchanges it at C(/oauth/v2/token)
        for an access token. Requires the C(cryptography) Python library.
      - If not set, the E(ZITADEL_SERVICE_ACCOUNT_KEY) environment variable is used.
    type: raw
  validate_certs:
    description:
      - Whether to validate the TLS certificate of O(endpoint).
      - Only disable this for a self-signed endpoint you control.
    type: bool
    default: true
  timeout:
    description:
      - HTTP request timeout, in seconds.
    type: int
    default: 10
requirements:
  - cryptography (only for O(service_account_key))
'''

    ORGANIZATION = r'''
options:
  organization_id:
    description:
      - ID of the organization that owns the resource.
      - Defaults to the organization of the authenticated user.
    type: str
'''
