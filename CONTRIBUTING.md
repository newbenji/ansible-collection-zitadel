# Contributing

Thanks for helping. Bug reports, module ideas and pull requests are all welcome.

## Reporting

- **Bugs and feature requests:** open an issue using one of the templates.
- **Security issues:** do not open a public issue. See [SECURITY.md](SECURITY.md).

## Development setup

`ansible-test` needs the collection at a path ending in
`ansible_collections/<namespace>/<name>`:

```bash
git clone https://github.com/<you>/ansible-collection-zitadel.git ansible_collections/newbenji/zitadel
cd ansible_collections/newbenji/zitadel
python3 -m pip install ansible-core cryptography pytest
```

## Tests

| What | Command |
|---|---|
| Sanity (docs, imports, style) | `ansible-test sanity --docker` |
| Unit tests | `ansible-test units --docker` (or `PYTHONPATH=../../.. python3 -m pytest tests/unit`) |
| Integration (needs a ZITADEL) | write `tests/integration/integration_config.yml`, then `ansible-test integration --local --allow-unsupported` |

`integration_config.yml` looks like this. It is gitignored, so never commit it:

```yaml
zitadel_endpoint: http://localhost:8080
zitadel_admin_token: "<PAT of an IAM_OWNER machine user>"
zitadel_admin_key_file: /path/to/admin-key.json
```

[.github/workflows/integration.yml](.github/workflows/integration.yml) shows how to
start a throwaway ZITADEL with Docker that writes both files for you.

## Writing a module

- Put the shared connection logic in `plugins/module_utils/zitadel.py`; use
  `zitadel_argument_spec()`, `ZitadelClient` and the `newbenji.zitadel.auth`
  documentation fragment.
- Add the module to the `zitadel` action group in `meta/runtime.yml`.
- Use the ZITADEL **v2** REST API where it exists.
- Modules must be idempotent and support check mode.
- Mark secret options `no_log`. Never return a secret on a run that did not create it.
- Add unit tests (with `fetch_url` faked) and an integration target.

## Pull requests

1. Fork, create a branch, and make your change with tests.
2. Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
3. Open a PR. CI (sanity, units, ansible-lint and the live ZITADEL integration test)
   must pass before merging.

By contributing you agree that your contribution is licensed under
[GPL-3.0-or-later](LICENSE), and you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
