# Maintenance and LTS Policy

This document describes the maintenance policy for this custom integration. It is
not an official Home Assistant or vendor support promise; it defines how this
repository keeps a stable release line dependable for HACS users.

## Supported Home Assistant Versions

The minimum supported Home Assistant version is the version declared in
`hacs.json`. That version must also be tested in the validation workflow.

The validation workflow must cover:

- the Home Assistant minimum advertised in `hacs.json`
- the current Home Assistant target line used for forward compatibility checks
- the Python version required by each tested Home Assistant line

If the HACS minimum version is raised, the change must be made deliberately and
must be reflected in CI, release notes and user-facing documentation.

## Stable Patch Releases

Patch releases are intended for low-risk maintenance only:

- compatibility fixes for supported Home Assistant versions
- deprecation fixes before a future Home Assistant release turns them into errors
- privacy, security, diagnostics and repository hygiene fixes
- test, CI and documentation corrections
- bug fixes that preserve existing config entries and entity identities

Patch releases must not introduce intentional breaking changes. In particular,
they must not rename the integration domain, change entity unique ID formats,
drop config-entry compatibility, or remove documented working behavior.

## Minor Releases

Minor releases may include larger compatibility work when it is still safe for
existing users. Examples include new diagnostics fields, additional tests,
documentation restructuring, or opt-in controls.

Any behavior that may require users to reinstall, reconfigure, or manually clean
up entities must be treated as a breaking change and documented clearly.

## Breaking Changes

Breaking changes require a new minor or major release. The release notes must
state:

- what changed
- who is affected
- whether the integration must be removed and reinstalled
- how to preserve or recreate expected entities
- which old files or directories users may need to remove

Breaking changes must not be hidden in patch releases.

## Backport Rules

If a dedicated maintenance branch is used later, only targeted changes should be
backported:

- confirmed bug fixes
- Home Assistant compatibility fixes
- privacy or security hardening
- CI and release validation fixes
- documentation corrections for the maintained line

New feature work, large refactors and entity model changes should remain on the
development line unless they are required to fix a supported regression.

## Deprecation Handling

Known Home Assistant deprecations should be fixed before they become hard
errors. Repository checks should guard against repeating known unsafe patterns
when practical.

Current examples include:

- config flows must not call config-entry reload methods when the integration
  also registers a config-entry update listener
- the advertised HACS minimum must remain covered by CI
- workflow Python versions must cover both the minimum and current Home
  Assistant test lines

## Firmware and Device Scope

Firmware-specific behavior must be documented in the firmware matrix when it is
confirmed by live testing or user evidence. A throughput limitation or endpoint
variation on one firmware/device combination should not be generalized to all
UNAS models unless the evidence supports that.

Optional local controls remain experimental when they depend on undocumented
local endpoints, firmware behavior or account permissions.
