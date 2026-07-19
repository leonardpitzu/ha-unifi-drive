"""Shared UniFi OS metadata helper functions."""

from __future__ import annotations

import re
from typing import Any


def normalized_token(value: str) -> str:
    """Normalize text for fuzzy comparisons."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def system_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return the nested UniFi OS system payload."""
    system = data.get("_system")
    return system if isinstance(system, dict) else {}


def core_metadata_available(data: Any) -> bool:
    """Return whether authenticated UniFi OS core metadata was retrieved.

    UniFi API keys authenticate the Drive application API (``/proxy/drive/*``)
    but not the UniFi OS core ``/api/system`` endpoint, which then answers with
    a reduced anonymous payload that omits ``cpu``, ``uptime``, ``apps`` and
    ``hardware.firmwareVersion``. The authenticated payload always carries a
    numeric ``uptime`` alongside the ``cpu`` and ``apps`` sections, so their
    absence is a reliable signal that core-only sensors cannot be populated.
    """
    if not isinstance(data, dict):
        return False
    system = system_payload(data)
    if not system:
        return False
    if isinstance(system.get("cpu"), dict) or isinstance(system.get("apps"), dict):
        return True
    uptime = system.get("uptime")
    if isinstance(uptime, bool):
        return False
    return isinstance(uptime, (int, float))


def unifi_os_version(data: dict[str, Any]) -> str | None:
    """Return UniFi OS firmware version."""
    system = system_payload(data)
    hardware = system.get("hardware")
    if isinstance(hardware, dict) and (version := _text(hardware.get("firmwareVersion"))):
        return version
    return (
        _text(system.get("firmwareVersion"))
        or _text(system.get("firmware_version"))
        or _text(system.get("ucore_version"))
        or _text(system.get("version"))
    )


def drive_version(data: dict[str, Any]) -> str | None:
    """Return installed UniFi Drive application version."""
    system = system_payload(data)
    apps = system.get("apps")
    if isinstance(apps, dict):
        for key in ("controllers", "apps", "applications"):
            if version := _drive_version_from_items(apps.get(key)):
                return version

    for key in ("controllers", "apps", "applications"):
        if version := _drive_version_from_items(system.get(key)):
            return version
    return None


def _drive_version_from_items(value: Any) -> str | None:
    """Return a Drive application version from a list-like payload."""
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        app_name = normalized_token(
            str(item.get("name") or item.get("id") or item.get("slug") or "")
        )
        if app_name not in {"drive", "unifidrive"}:
            continue
        version = (
            _text(item.get("versionRaw"))
            or _text(item.get("version"))
            or _text(item.get("uiVersion"))
            or _text(item.get("currentVersion"))
        )
        if version:
            return version
    return None


def _text(value: Any) -> str | None:
    """Return stripped text for non-empty non-boolean values."""
    if isinstance(value, bool) or value in (None, ""):
        return None
    text = str(value).strip()
    return text or None
