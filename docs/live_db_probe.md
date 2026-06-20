# Live DB Write Probe

This report documents the live recorder/config-entry write probe performed
during discovery write-throttle hardening on the Home Assistant test instance.
It excludes credentials, tokens, private hostnames, and local network details.

## Scope

- integration under test: `custom_components/unifi_unas`
- action pattern: idle window + three explicit `reload_config_entry` cycles
- focus:
  - `states` growth
  - `state_attributes` growth
  - `events` growth
  - `unifi_unas` state row growth
  - config-entry storage touch (`.storage/core.config_entries`)

## Baseline Behavior Before Throttle Deployment

- repeated reloads updated `discovery_last_seen` each cycle
- `.storage/core.config_entries` changed on each reload cycle

Observed step deltas:

- `idle_30s`: `state+301`, `attr+0`, `event+398`, `unifi_rows+63`, `cfg_touch=yes`
- `reload_1_plus30s`: `state+157`, `attr+1`, `event+1`, `unifi_rows+120`, `cfg_touch=yes`
- `reload_2_plus30s`: `state+158`, `attr+0`, `event+1`, `unifi_rows+120`, `cfg_touch=yes`
- `reload_3_plus30s`: `state+160`, `attr+0`, `event+1`, `unifi_rows+120`, `cfg_touch=yes`

## Behavior After Throttle Deployment

- `discovery_last_seen` changed only once inside the short reload window
- `.storage/core.config_entries` changed on first reload only
- subsequent short-window reloads did not touch config-entry storage

Observed step deltas:

- `idle_30s`: `state+36`, `attr+0`, `event+0`, `unifi_rows+2`, `cfg_touch=no`
- `reload_1_plus30s`: `state+156`, `attr+0`, `event+1`, `unifi_rows+120`, `cfg_touch=yes`
- `reload_2_plus30s`: `state+160`, `attr+0`, `event+1`, `unifi_rows+120`, `cfg_touch=no`
- `reload_3_plus30s`: `state+159`, `attr+1`, `event+1`, `unifi_rows+120`, `cfg_touch=no`

## Interpretation

- The discovery write-throttle is effective for short-interval metadata-only
  discovery updates.
- Explicit reloads still generate normal recorder writes for entities; this is
  expected because entities are reloaded and state is republished.
- No sign of repeated config-entry write churn after the first reload within the
  throttle window.
