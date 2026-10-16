# Ansible Collection: newbenji.zitadel

[![CI](https://github.com/newbenji/ansible-collection-zitadel/actions/workflows/ci.yml/badge.svg)](https://github.com/newbenji/ansible-collection-zitadel/actions/workflows/ci.yml)
[![Integration](https://github.com/newbenji/ansible-collection-zitadel/actions/workflows/integration.yml/badge.svg)](https://github.com/newbenji/ansible-collection-zitadel/actions/workflows/integration.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)

Ansible modules for managing a [ZITADEL](https://zitadel.com) identity and access
management instance through its REST API.

> **Status: early (0.x).** The API of the collection may still change between minor
> versions. Every change is tested against a real ZITADEL in CI.

## Modules

| Module | Description |
|---|---|
| [`newbenji.zitadel.api_token`](plugins/modules/api_token.py) | Create or remove personal access tokens (PATs) of a machine user |
| [`newbenji.zitadel.project`](plugins/modules/project.py) | Create, update or delete projects |
| [`newbenji.zitadel.oidc_app`](plugins/modules/oidc_app.py) | Create, update or delete OIDC applications (OAuth2 clients) and rotate their secrets |

Planned: organizations, users, roles and API applications. Contributions welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## Requirements

- ansible-core 2.19 or newer
- ZITADEL v4 (tested with v4.16.0). The modules use the v2 APIs (REST and Connect JSON).
- Python `cryptography` on the host that runs the modules, only for
  `service_account_key` authentication. ansible-core already depends on it.

## Installation

From GitHub:

```bash
ansible-galaxy collection install git+https://github.com/newbenji/ansible-collection-zitadel.git
```

or in a `requirements.yml`:

```yaml
collections:
  - name: https://github.com/newbenji/ansible-collection-zitadel.git
    type: git
    version: main
```

## Authentication

Every module takes the same connection options:

| Option | Environment variable | Description |
|---|---|---|
| `endpoint` | `ZITADEL_ENDPOINT` | Base URL, e.g. `https://zitadel.example.com` |
| `api_token` | `ZITADEL_API_TOKEN` | PAT of a machine user with the needed permissions |
| `service_account_key` | `ZITADEL_SERVICE_ACCOUNT_KEY` | Contents of a service-account key JSON file |
| `validate_certs` | | Verify TLS (default `true`) |

Use exactly one of `api_token` and `service_account_key`. With a key file, the module
signs a JWT and exchanges it for a short-lived access token
([private key JWT](https://zitadel.com/docs/guides/integrate/service-accounts/private-key-jwt)).

Set the options once for a whole play with the `newbenji.zitadel.zitadel` module defaults group:

```yaml
- hosts: localhost
  module_defaults:
    group/newbenji.zitadel.zitadel:
      endpoint: https://zitadel.example.com
      api_token: "{{ vault_zitadel_admin_token }}"
  tasks:
    - name: Ensure the CI machine user has a token
      newbenji.zitadel.api_token:
        user_id: "302815613184245764"
        expiration_date: "2027-01-01T00:00:00Z"
        token_path: "{{ playbook_dir }}/.secrets/ci.pat"
```

## Example: an OIDC client for an app on Kubernetes

Create a project and a client, and put the credentials in a Kubernetes Secret
the app reads. The client secret is only returned when the client is created
(or rotated), so the Secret is only written then:

```yaml
- hosts: localhost
  module_defaults:
    group/newbenji.zitadel.zitadel:
      endpoint: https://zitadel.example.com
      api_token: "{{ vault_zitadel_admin_token }}"
  tasks:
    - name: Ensure the homelab project
      newbenji.zitadel.project:
        name: homelab
      register: project

    - name: Ensure the Grafana client
      newbenji.zitadel.oidc_app:
        project_id: "{{ project.project_id }}"
        name: grafana
        redirect_uris: [https://grafana.example.com/login/generic_oauth]
        grant_types: [authorization_code, refresh_token]
      register: grafana
      no_log: true

    - name: Store the credentials for Grafana
      kubernetes.core.k8s:
        definition:
          apiVersion: v1
          kind: Secret
          metadata: { name: grafana-oidc, namespace: monitoring }
          stringData:
            client-id: "{{ grafana.client_id }}"
            client-secret: "{{ grafana.client_secret }}"
      when: grafana.client_secret is defined
      no_log: true
```

If the Secret is lost, rotate with `regenerate_secret: true` on the next run.

## Handling secrets

ZITADEL returns PATs and client secrets **only once**, when they are created. For `api_token`, either:

- set `token_path` so the module writes it to a `0600` file (and never returns it), or
- `register` the result and put `no_log: true` on the task.

If an active token exists but `token_path` is missing, the module warns you. Remove the
token with `state: absent` and run again to rotate it.

## Development

```bash
# The collection must live at .../ansible_collections/newbenji/zitadel
git clone https://github.com/newbenji/ansible-collection-zitadel.git ansible_collections/newbenji/zitadel
cd ansible_collections/newbenji/zitadel

ansible-test sanity --docker
ansible-test units --docker
```

The integration tests need a running ZITADEL. See
[.github/workflows/integration.yml](.github/workflows/integration.yml) for how CI
starts one.

## License

[GPL-3.0-or-later](LICENSE).
