"""Compatibility entrypoint for UniFi Drive sensor platform.

The implementation is split across:
- sensor_descriptions.py
- storage_helpers.py
- entities.py
"""

from __future__ import annotations

from .entities import (
    UnifiUnasAggregateSensor,
    UnifiUnasBaseSensor,
    UnifiUnasCacheDriveSensor,
    UnifiUnasDriveSensor,
    UnifiUnasPoolSensor,
    UnifiUnasSnapshotInventorySensor,
    async_setup_entry,
)
from .sensor_descriptions import (
    AGGREGATE_SENSOR_TYPES,
    DRIVE_SENSOR_TYPES,
    POOL_SENSOR_TYPES,
    AggregateSensorDescription,
    DriveSensorDescription,
    PoolSensorDescription,
)

# Keeps every storage helper reachable as `sensor.<helper>`.
# storage_helpers.__all__ is the single source of truth for that list.
from .storage_helpers import *  # noqa: F403

PARALLEL_UPDATES = 0

__all__ = [
    "AGGREGATE_SENSOR_TYPES",
    "DRIVE_SENSOR_TYPES",
    "POOL_SENSOR_TYPES",
    "AggregateSensorDescription",
    "DriveSensorDescription",
    "PoolSensorDescription",
    "UnifiUnasAggregateSensor",
    "UnifiUnasBaseSensor",
    "UnifiUnasCacheDriveSensor",
    "UnifiUnasDriveSensor",
    "UnifiUnasPoolSensor",
    "UnifiUnasSnapshotInventorySensor",
    "async_setup_entry",
]
