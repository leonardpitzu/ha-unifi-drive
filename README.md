# UniFi Drive / UNAS for Home Assistant

A custom [Home Assistant](https://www.home-assistant.io/) integration for **local
monitoring and control of UniFi Drive / UNAS storage systems**. It talks directly
to the device on your LAN over the UniFi OS and UniFi Drive HTTP APIs — no
Ubiquiti cloud account, no remote polling.

This is a personal fork of [memphi2/ha-unifi-drive](https://github.com/memphi2/ha-unifi-drive),
maintained for my own UNAS 4. It keeps the `unifi_unas` domain (so it is a drop-in
replacement, entity IDs are preserved) and adds the changes listed below.

## What this fork adds

| Area | Change |
|------|--------|
| **API-key auth on UNAS 4** | UniFi API keys are scoped to the Drive app, so `/api/system` returns a reduced anonymous body and CPU/uptime/IP/version sensors stayed empty. System metadata is now sourced from `/proxy/drive/api/v2/systems/device-info`, which works with **both** API-key and username/password auth. |
| **SSD cache visibility** | `cacheSlots` is a top-level sibling of `disks`, not a pool member, so cache SSDs previously got no entities at all. They now appear under a synthetic **Cache** group. |
| **New sensors** | `cpu_percent`, `memory_percent`, `cache_status`, `ssd_wear`, `system_uptime_readable` (compact `3d 7h` form), plus per-drive `drive_life_span`, `drive_model`, `drive_capacity`, `drive_bad_sectors`, `drive_uncorrectable_sectors`. |
| **Per-drive naming** | Drive names are media-type aware (`SSD 1` / `HDD 1`) so HDD slots 1-4 and SSD slots 1-2 no longer collide as `Drive 1`. |
| **Pool rebuild/sync progress** | Populated from the UNAS RAID-group payload. |
| **Repo hygiene** | Single `pyproject.toml`, pinned test toolchain, `master`-only, no releases. Upstream's release/certification tooling was removed. |

## Requirements

- Home Assistant **2026.8.0** or newer.
- A UniFi Drive / UNAS device reachable on the local network.
- Either a local UniFi OS account (username/password) or a UniFi **API key**.

> **API keys are Drive-app scoped.** An API key authenticates `/proxy/drive/*`
> only. Username/password (cookie) auth additionally reads UniFi OS core
> endpoints. Both modes produce the full sensor set — the fork sources shared
> metadata from the Drive `device-info` endpoint precisely so API-key setups are
> not degraded.

## Supported devices

| Device | Firmware | Evidence |
|--------|----------|----------|
| UNAS 4 (UNAS4W) | UniFi OS `5.1.19`, Drive `4.3.6` | primary development target |
| UNAS 2 | UniFi OS `5.1.8` – `5.1.19` | inherited from upstream |
| Other UniFi Drive / UNAS models | unknown | expected to work where endpoint shape and permissions match |
| Non-UniFi NAS devices | any | unsupported |

## Installation

### HACS custom repository

1. Open HACS.
2. Three-dot menu → **Custom repositories**.
3. Add `https://github.com/leonardpitzu/homeassistant_unifi_unas` as category **Integration**.
4. Install **UniFi Drive / UNAS**, then restart Home Assistant.

### Manual

Copy `custom_components/unifi_unas/` into `/config/custom_components/` and restart
Home Assistant. The final path must be `/config/custom_components/unifi_unas/`.

## Setup

Add the integration from **Settings → Devices & services → Add integration →
UniFi Drive / UNAS**. Start from a discovery card, or enter the device manually —
manual setup stays available when mDNS is blocked by VLANs.

| Field | Notes |
|-------|-------|
| Host | IP address or DNS name. URLs with scheme/port are normalized. |
| Port | `443` with SSL, `80` without. |
| SSL / verify certificate | Match your local UniFi OS endpoint. |
| Username / password | Local account session auth. |
| API key | Local API-key auth. |

If both are supplied, the local account session is used first. A second step
selects which optional control surfaces to expose — leave them off for a
monitoring-only setup.

Discovery treats matches as hints, not trust: configured devices are hidden,
duplicate records are deduplicated via local identity hints, and conflicting
hints are recorded for diagnostics instead of forcing a risky automatic match.

## Entities

Eight platforms: `sensor`, `binary_sensor`, `button`, `switch`, `number`,
`select`, `time`, `update`.

**System** — `total_storage`, `used_storage`, `available_storage`,
`usage_percent`, `overall_status`, `system_status`, `pool_count`,
`degraded_pool_count`, `maintenance_pool_count`, `at_risk_disk_count`,
`average_disk_temperature`, `cpu_temperature`, `cpu_percent`, `memory_percent`,
`read_throughput`, `write_throughput`, `system_ip`, `system_uptime_readable`,
`unifi_os_version`, `drive_version`, `cache_status`, `ssd_wear`.

**Per pool** — `pool_status`, `pool_capacity`, `pool_used`, `pool_available`,
`pool_usage_percent`, `pool_raid_level`, `pool_drive_count`,
`pool_rebuild_progress`, `pool_sync_progress`, `pool_at_risk_drive_count`,
`pool_average_drive_temperature`.

**Per drive** (disabled by default — enable the ones you want) — `drive_status`,
`drive_temperature`, `drive_power_on_hours`, `drive_life_span`, `drive_model`,
`drive_capacity`, `drive_bad_sectors`, `drive_uncorrectable_sectors`. SMART and
identity fields that do not warrant their own entity are exposed as attributes.

**Binary sensors** — `device_online`, `storage_problem`, `maintenance_active`,
and per pool `pool_problem`, `pool_maintenance_active`.

**Controls** (opt-in) — Wake-on-LAN / restart / shutdown / backup / snapshot
buttons, fan-mode select, and snapshot limit/schedule number, select and time
entities. `update` entities appear when UniFi OS or Drive report an available
update.

## Options

Open the integration entry → **Configure**.

| Option | Purpose |
|--------|---------|
| `scan_interval` | Core polling interval. |
| `fan_control_enabled` | Expose fan-mode control. |
| `snapshot_buttons_enabled` | Expose snapshot inventory and controls. |
| `wol_enabled`, `wol_mac_address`, `wol_broadcast_address`, `wol_port` | Wake-on-LAN for a device that may be powered off. |
| `discovery_debug` | Extra discovery diagnostics while investigating. |

Reconfigure and reauth flows preserve the existing device identity where possible.

## Actions

```text
unifi_unas.wake_on_lan
unifi_unas.reboot
unifi_unas.shutdown
unifi_unas.set_fan_mode
unifi_unas.create_snapshot
unifi_unas.set_snapshot_limit
unifi_unas.set_snapshot_schedule
```

Pass `entry_id` to target a specific UNAS in a multi-device setup. Snapshot
delete and restore are intentionally not implemented.

## Automation examples

Alert when the pool degrades:

```yaml
automation:
  - alias: UNAS pool degraded
    triggers:
      - trigger: state
        entity_id: binary_sensor.unifi_drive_storage_problem
        to: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "UNAS storage problem - overall status is degraded."
```

Warn before the array fills up:

```yaml
automation:
  - alias: UNAS nearly full
    triggers:
      - trigger: numeric_state
        entity_id: sensor.unifi_drive_usage_percent
        above: 85
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "UNAS is {{ states('sensor.unifi_drive_usage_percent') }}% full."
```

Wake the NAS before a backup window:

```yaml
automation:
  - alias: Wake UNAS for backup
    triggers:
      - trigger: time
        at: "02:45:00"
    actions:
      - action: unifi_unas.wake_on_lan
```

## Diagnostics and privacy

Download diagnostics from the integration entry. Runtime state, capability flags,
monitoring/discovery health and payload-shape metadata are included. Credentials,
API keys, hostnames, IP and MAC addresses, serial-like identifiers, token-like
values, snapshot target names and raw payload values are redacted or reduced to
presence flags.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Setup cannot connect | Verify host, port, SSL and certificate settings from the Home Assistant host. |
| Authentication fails | Recheck local account permissions or API-key validity. |
| Discovery does not find the device | Use manual setup; mDNS rarely crosses VLANs without a relay. |
| Monitoring works but controls fail | The account may lack permission for the optional local endpoints. |
| Snapshot targets missing | Enable snapshot options and confirm endpoint support on this firmware. |
| CPU / uptime / IP sensors empty | Confirm the device exposes `systems/device-info`; older Drive builds may not. |
| Device is off | Expected — use Wake-on-LAN when configured. |

## Known limitations

- Unofficial and not vendor-supported; endpoint behaviour varies by firmware.
- Snapshot controls are opt-in and non-destructive; no delete or restore.
- No per-disk used-space — the API reports capacity and throughput only.
- HDD entries omit `lifeSpan`, so `drive_life_span` self-gates to SSDs.
- Wake-on-LAN may need directed-broadcast support on your network.

## Removal

1. **Settings → Devices & services**, open the **UniFi Drive / UNAS** entry, choose **Delete**.
2. Uninstall via HACS, or remove `/config/custom_components/unifi_unas/`.

Removing the files alone does not delete the config entry.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
ruff check .
mypy
pytest tests/ -q --cov=custom_components/unifi_unas
```

CI runs the same four gates plus HACS and hassfest validation on every push to
`master`. The test toolchain is pinned in `requirements_test.txt` so a new ruff
release cannot silently turn the build red.

## Legal notes

This is an unofficial community integration. It does not claim affiliation,
sponsorship, authorization, approval, or endorsement by Ubiquiti Inc., Home
Assistant, HACS, or their respective owners.

Product names such as UniFi, UniFi Drive, UniFi OS, Ubiquiti and UNAS are used
only as descriptive compatibility references. The repository does not include
official Ubiquiti logos, copied vendor web assets, or proprietary Ubiquiti source
code. Protocol and endpoint notes document observed interoperability behaviour
only.

## Credits

- [memphi2/ha-unifi-drive](https://github.com/memphi2/ha-unifi-drive) — the
  upstream integration this fork is based on. All of the original design work,
  the discovery/identity handling, the snapshot and diagnostics surfaces and the
  bulk of the code are theirs; this fork only adapts it to my UNAS 4 and adds the
  sensors listed above.

## License

MIT — see [LICENSE](LICENSE). The upstream copyright notice is retained, as
required.
