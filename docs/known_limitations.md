# Known Limitations

- This is an unofficial community integration and not vendor-supported.
- Only local UniFi OS / Drive endpoint behavior is covered; no cloud control
  path is implemented.
- Endpoint behavior and permission requirements can vary by firmware.
- Snapshot controls are intentionally opt-in and non-destructive.
- Snapshot delete/restore actions are intentionally not provided.
- Discovery quality depends on local network metadata quality (mDNS/zeroconf,
  MAC hints, aliases, VLAN routing behavior).
- Wake-on-LAN uses IPv4 UDP broadcast and may need directed-broadcast support.
- Real-device lifecycle validation is strongest on the tested UNAS2 target.
  Throughput has been confirmed for the UNAS2 and UNAS4 firmware combinations
  listed in the firmware matrix, but other feature/model/firmware combinations
  should still be verified before being treated as equivalent.
