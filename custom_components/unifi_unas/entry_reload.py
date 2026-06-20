"""Helpers for deciding whether config-entry updates need a reload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from .const import (
    CONF_DISCOVERY_CONFIDENCE,
    CONF_DISCOVERY_HOST_ALIASES,
    CONF_DISCOVERY_IDENTITY_CONFLICTS,
    CONF_DISCOVERY_IDENTITY_SOURCE,
    CONF_DISCOVERY_LAST_SEEN,
    CONF_DISCOVERY_MAC_ADDRESS,
)

if TYPE_CHECKING:
    from .runtime import UnifiDriveConfigEntry

EntryReloadSignature = tuple[object, object]

_METADATA_ONLY_DATA_KEYS = frozenset(
    {
        CONF_DISCOVERY_CONFIDENCE,
        CONF_DISCOVERY_HOST_ALIASES,
        CONF_DISCOVERY_IDENTITY_CONFLICTS,
        CONF_DISCOVERY_IDENTITY_SOURCE,
        CONF_DISCOVERY_LAST_SEEN,
        CONF_DISCOVERY_MAC_ADDRESS,
    }
)


def entry_reload_signature(entry: UnifiDriveConfigEntry) -> EntryReloadSignature:
    """Return the config-entry parts that require a runtime reload."""
    return (
        _freeze_config_value(_runtime_entry_data(entry)),
        _freeze_config_value(dict(getattr(entry, "options", {}) or {})),
    )


def _runtime_entry_data(entry: UnifiDriveConfigEntry) -> dict[str, object]:
    """Return entry data with metadata-only keys removed."""
    return {
        key: value
        for key, value in dict(getattr(entry, "data", {}) or {}).items()
        if key not in _METADATA_ONLY_DATA_KEYS
    }


def _freeze_config_value(value: object) -> object:
    """Convert config data into a stable comparable structure."""
    if isinstance(value, Mapping):
        return tuple(
            sorted(
                (
                    (str(key), _freeze_config_value(item))
                    for key, item in value.items()
                ),
                key=repr,
            )
        )
    if isinstance(value, set):
        return tuple(sorted((_freeze_config_value(item) for item in value), key=repr))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_config_value(item) for item in value)
    return value
