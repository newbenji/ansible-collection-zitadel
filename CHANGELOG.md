# Changelog

All notable changes to this collection are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the collection uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0]

### Added

- `newbenji.zitadel.project` module: create, update and delete projects (v2 Project service),
  with check and diff mode.
- `newbenji.zitadel.oidc_app` module: create, update and delete OIDC applications, return the
  client ID and (on creation) client secret, and rotate the secret with `regenerate_secret`.
- `organization_id` documentation fragment; projects default to the caller's organization.

### Changed

- CI runs `ansible-test` directly and every GitHub Action is SHA-pinned and allow-listed.

## [0.1.0]

### Added

- `newbenji.zitadel.api_token` module: create and remove personal access tokens of
  ZITADEL machine users through the v2 REST API, with check mode, `token_path`
  secret storage, and pagination.
- Shared authentication by PAT (`api_token`) or service-account key JSON
  (`service_account_key`, private key JWT), with `ZITADEL_*` environment variable
  fallbacks and a `newbenji.zitadel.zitadel` module defaults group.
