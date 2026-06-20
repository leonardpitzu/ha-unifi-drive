# Validation And Release Checks

This document defines the validation gates used for branch hardening and release
validation.

## Required Local Gate

```bash
python scripts/check_repo.py
python scripts/audit_github_public_surfaces.py --repo memphi2/ha-unifi-drive
rm -rf dist
mkdir -p dist
(cd custom_components && zip -q -r ../dist/unifi_unas.zip unifi_unas -x "*/__pycache__/*" "*.pyc")
python scripts/check_release_zip.py dist/unifi_unas.zip
python -m pytest -q
python -m compileall -q custom_components/unifi_unas tests
git diff --check
```

## Additional Quality Gates

Run when the environment provides the tooling:

```bash
python -m ruff check custom_components tests scripts
mypy --config-file mypy.ini
python -m bandit -q -r custom_components scripts
```

## What These Checks Cover

- release metadata alignment (`manifest`, `CHANGELOG`, release notes)
- HACS metadata safety (`hacs.json`)
- legal, trademark and asset hygiene checks
- tracked-file secret checks and release ZIP privacy/legal/layout checks
- public GitHub release, PR, issue and release-asset hygiene checks
- generic RFC1918 local-address checks and optional local denylist marker checks
  through `UNIFI_UNAS_FORBIDDEN_MARKERS`
- quality-scale status validation
- translation structure validation
- typed runtime-data baseline and strict mypy gate structure
- icon/exception translation baseline
- full integration unit/fixture test suite

## Live Validation Notes

- `docs/live_test_report_v0.6.2.md` tracks full HA live validation including
  restart/reload/reauth/reconfigure and firmware-update checks.
- `docs/live_db_probe.md` tracks recorder/config-entry write behavior for
  discovery write-throttle hardening.

## Release Readiness Rule

Do not finalize release work while any of these remain red:

- repository checks
- public GitHub surface audit
- release ZIP privacy/legal/layout check
- pytest suite
- compile checks
- HACS validation workflow
- Hassfest workflow

Release publication also runs `scripts/check_repo.py` before building the ZIP and
`scripts/check_release_zip.py` before uploading the release asset. It also runs
`scripts/audit_github_public_surfaces.py` to scan existing public releases, PRs,
issues and release ZIP assets for privacy, copyright and branding-risk markers.
Release notes, PR bodies and public support comments should use redacted examples
only and must not include live hostnames, local addresses, credentials, tokens,
cookies, personal usernames, test-user names, snapshot target names, official
vendor assets, proprietary vendor source material, or wording that implies vendor
endorsement.

Personal or environment-specific marker strings must not be committed to the
repository. Keep them in the `UNIFI_UNAS_FORBIDDEN_MARKERS` environment variable
locally and in the matching GitHub Actions variable for CI/release runs.
Set that variable in a private shell environment before running the commands
above when local marker coverage is needed.

When a HACS submission is part of the release cycle, include that public PR in
the audit as well:

```bash
python scripts/audit_github_public_surfaces.py \
  --repo memphi2/ha-unifi-drive \
  --hacs-repo hacs/default \
  --hacs-pr <number>
```
