"""Compatibility entrypoint for UniFi Drive sensor platform.

The implementation is split across:
- sensor_descriptions.py
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
