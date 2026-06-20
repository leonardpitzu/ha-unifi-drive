# Entity Overview

The integration exposes one Home Assistant device per configured UniFi Drive /
UNAS entry.

## Core Monitoring Entities

| Platform | Examples |
| --- | --- |
| `sensor` | capacity, used/available, usage %, pool health, drive health, temperatures |
| `sensor` | throughput, uptime, system status, UniFi OS version, Drive version |
| `binary_sensor` | storage problem, maintenance states |

## Optional Control Entities

| Platform | Examples | Notes |
| --- | --- | --- |
| `button` | Wake-on-LAN, restart, shutdown | local action endpoints |
| `select` | fan mode | permission-dependent |
| `update` | UniFi OS / Drive updates | uses HA update semantics |
| `button` | backup task actions | shown when task metadata is available |
| `switch`/`number`/`select`/`time` | snapshot per-target controls | opt-in and endpoint-dependent |

## Availability Model

- Coordinator-backed entities become unavailable when the device is unreachable.
- Optional feature entities can stay unavailable when endpoints are unsupported
  or blocked by permissions.
- No direct API calls happen from entity properties.
