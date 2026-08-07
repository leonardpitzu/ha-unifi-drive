"""Entity description types for the UniFi Drive integration.

Kept free of any storage imports so the `storage_*` modules can declare their
own entity descriptions next to the helpers that produce the values.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.helpers.typing import StateType


@dataclass(frozen=True, kw_only=True)
class AggregateSensorDescription(SensorEntityDescription):
    """Description of an aggregate UNAS sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]


@dataclass(frozen=True, kw_only=True)
class PoolSensorDescription(SensorEntityDescription):
    """Description of a per-pool UNAS sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    entity_registry_enabled_default: bool = False


@dataclass(frozen=True, kw_only=True)
class DriveSensorDescription(SensorEntityDescription):
    """Description of a per-drive UNAS sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    entity_registry_enabled_default: bool = False


@dataclass(frozen=True, kw_only=True)
class AggregateBinarySensorDescription(BinarySensorEntityDescription):
    """Description of an aggregate UNAS binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool]


@dataclass(frozen=True, kw_only=True)
class PoolBinarySensorDescription(BinarySensorEntityDescription):
    """Description of a per-pool UNAS binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool]
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    entity_registry_enabled_default: bool = False
