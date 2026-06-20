# Device And Firmware Matrix

This matrix tracks conservative compatibility evidence. Rows with a feature
scope document that specific feature only; they do not replace the broader
integration support statement.

## Status Meanings

| Status | Meaning |
| --- | --- |
| `tested` | validated with live Home Assistant integration flow |
| `community_confirmed` | validated by user feedback and privacy-safe diagnostics, not reproduced on the maintainer's local hardware |
| `partial` | basic behavior validated, feature groups still open |
| `planned` | expected support, no direct live evidence yet |

## Matrix

| Device scope | UniFi OS firmware | Feature scope | Status | Coverage notes |
| --- | --- | --- | --- | --- |
| UNAS2 | 5.1.8 | integration lifecycle | tested | setup/reload/reconfigure/reauth, offline/WOL recovery, diagnostics privacy |
| UNAS2 | 5.1.10 | integration lifecycle and optional controls | tested | update-entity flow, post-update recovery, diagnostics, optional feature checks |
| UNAS2 | 5.1.19, Drive 4.3.6 | throughput | tested | read/write throughput confirmed |
| UNAS4 | 5.1.16, Drive 4.3.6 | throughput | community_confirmed | throughput sensors were reported stuck at zero on 0.8.2 while the device UI showed SMB traffic; the 0.8.4 network I/O fallback was confirmed to restore read/write throughput |
| Other UniFi Drive / UNAS models | unknown | general compatibility | planned | expected when endpoint shape and permissions match |

## Evidence References

- [live_test_report_v0.6.2.md](live_test_report_v0.6.2.md)
- [live_db_probe.md](live_db_probe.md)
- Community feedback: UNAS4 throughput fallback confirmed on 0.8.4

## Evidence Template

Use this when adding a new row:

```text
Device scope:
Firmware:
Validation date:
Branch/tag:
Coverage:
- setup/discovery
- reload/restart/recovery
- diagnostics/privacy
- optional control paths
Result:
Notes:
```
