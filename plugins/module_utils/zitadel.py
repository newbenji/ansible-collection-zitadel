# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Benjamin Andersen (@newbenji)
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared ZITADEL API client, authentication and argument spec."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import base64
import datetime
import json
import re
import time
import traceback
from urllib.parse import quote, urlencode

from ansible.module_utils.basic import env_fallback, missing_required_lib
from ansible.module_utils.common.text.converters import to_bytes, to_text
from ansible.module_utils.urls import fetch_url

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    HAS_CRYPTOGRAPHY = True
    CRYPTOGRAPHY_IMPORT_ERROR = None
except ImportError:
    HAS_CRYPTOGRAPHY = False
    CRYPTOGRAPHY_IMPORT_ERROR = traceback.format_exc()

# Audience scope that grants access to ZITADEL's own APIs.
ZITADEL_API_SCOPE = "openid urn:zitadel:iam:org:project:id:zitadel:aud"
JWT_BEARER_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
PAGE_SIZE = 100

AUTH_MUTUALLY_EXCLUSIVE = [['api_token', 'service_account_key']]
AUTH_REQUIRED_ONE_OF = [['api_token', 'service_account_key']]

_RFC3339 = re.compile(
    r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$')


def zitadel_argument_spec():
    """Connection options shared by every module (see doc fragment newbenji.zitadel.auth)."""
    return dict(
        endpoint=dict(type='str', required=True, fallback=(env_fallback, ['ZITADEL_ENDPOINT'])),
        api_token=dict(type='str', no_log=True, fallback=(env_fallback, ['ZITADEL_API_TOKEN'])),
        service_account_key=dict(type='raw', no_log=True,
                                 fallback=(env_fallback, ['ZITADEL_SERVICE_ACCOUNT_KEY'])),
        validate_certs=dict(type='bool', default=True),
        timeout=dict(type='int', default=10),
    )


def quote_path(value):
    return quote(value, safe='')


def parse_timestamp(value):
    """Parse an RFC 3339 timestamp into an aware datetime, or None."""
    match = _RFC3339.match(value or '')
    if not match:
        return None
    base, zone = match.groups()
    parsed = datetime.datetime.strptime(base, '%Y-%m-%dT%H:%M:%S')
    if zone == 'Z':
        offset = datetime.timedelta(0)
    else:
        sign = -1 if zone[0] == '-' else 1
        offset = sign * datetime.timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
    return parsed.replace(tzinfo=datetime.timezone(offset))


def _b64url(data):
    return to_text(base64.urlsafe_b64encode(data).rstrip(b'='))


def load_service_account_key(value):
    """Accept the key file contents as a dict or JSON string and validate it."""
    if isinstance(value, dict):
        key = value
    else:
        try:
            key = json.loads(value)
        except (TypeError, ValueError):
            raise ValueError("service_account_key must be the JSON key file contents")
        if not isinstance(key, dict):
            raise ValueError("service_account_key must be a JSON object")
    missing = [f for f in ('keyId', 'key', 'userId') if not key.get(f)]
    if missing:
        raise ValueError("service_account_key is missing: %s" % ', '.join(missing))
    return key


def build_jwt_assertion(key, audience, now=None):
    """Sign a JWT-bearer assertion (RS256) for a ZITADEL service-account key."""
    now = int(now if now is not None else time.time())
    header = {'alg': 'RS256', 'kid': key['keyId']}
    claims = {
        'iss': key['userId'],
        'sub': key['userId'],
        'aud': audience,
        'iat': now,
        'exp': now + 300,
    }
    signing_input = '%s.%s' % (
        _b64url(to_bytes(json.dumps(header, separators=(',', ':')))),
        _b64url(to_bytes(json.dumps(claims, separators=(',', ':')))),
    )
    private_key = serialization.load_pem_private_key(to_bytes(key['key']), password=None)
    signature = private_key.sign(to_bytes(signing_input), padding.PKCS1v15(), hashes.SHA256())
    return '%s.%s' % (signing_input, _b64url(signature))


class ZitadelClient(object):
    """Minimal REST client for a ZITADEL instance.

    Uses the module's ``endpoint``, ``api_token``/``service_account_key``,
    ``validate_certs`` and ``timeout`` parameters.
    """

    def __init__(self, module):
        self.module = module
        self.base = module.params['endpoint'].rstrip('/')
        self.timeout = module.params['timeout']
        self._auth = None

    def _fail(self, msg, **kwargs):
        self.module.fail_json(msg=msg, **kwargs)

    def _call(self, method, path, payload=None, headers=None, form=None):
        all_headers = {'Accept': 'application/json'}
        data = None
        if form is not None:
            all_headers['Content-Type'] = 'application/x-www-form-urlencoded'
            data = urlencode(form)
        elif payload is not None:
            all_headers['Content-Type'] = 'application/json'
            data = json.dumps(payload)
        all_headers.update(headers or {})

        resp, info = fetch_url(self.module, self.base + path, data=data, headers=all_headers,
                               method=method, timeout=self.timeout)
        status = info.get('status', -1)
        body = resp.read() if resp is not None else info.get('body', b'')
        if status < 200 or status >= 300:
            self._fail("ZITADEL API %s %s failed (HTTP %s): %s"
                       % (method, path, status, to_text(body) or info.get('msg', '')),
                       status=status)
        if not body:
            return {}
        try:
            return json.loads(to_text(body))
        except ValueError:
            self._fail("ZITADEL API %s %s returned non-JSON: %s" % (method, path, to_text(body)[:200]))

    def authenticate(self):
        """Resolve the Authorization header from api_token or service_account_key."""
        params = self.module.params
        if params['api_token']:
            self._auth = 'Bearer ' + params['api_token']
            return
        if not HAS_CRYPTOGRAPHY:
            self._fail(missing_required_lib('cryptography'), exception=CRYPTOGRAPHY_IMPORT_ERROR)
        try:
            key = load_service_account_key(params['service_account_key'])
        except ValueError as exc:
            self._fail(to_text(exc))
        result = self._call('POST', '/oauth/v2/token', form={
            'grant_type': JWT_BEARER_GRANT,
            'scope': ZITADEL_API_SCOPE,
            'assertion': build_jwt_assertion(key, self.base),
        })
        access_token = result.get('access_token')
        if not access_token:
            self._fail("ZITADEL token endpoint returned no access_token")
        self.module.no_log_values.add(access_token)
        self._auth = 'Bearer ' + access_token

    def request(self, method, path, payload=None):
        if self._auth is None:
            self.authenticate()
        return self._call(method, path, payload=payload, headers={'Authorization': self._auth})

    def search(self, path, payload):
        """POST a v2 search endpoint, following offset pagination; returns all results."""
        results = []
        offset = 0
        while True:
            body = dict(payload)
            body['pagination'] = {'offset': offset, 'limit': PAGE_SIZE, 'asc': True}
            page = self.request('POST', path, payload=body)
            batch = page.get('result') or []
            results.extend(batch)
            total = int((page.get('pagination') or {}).get('totalResult') or 0)
            offset += len(batch)
            if not batch or offset >= total:
                return results
