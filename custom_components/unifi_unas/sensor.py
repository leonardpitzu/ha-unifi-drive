"""Sensor platform entrypoint for the UniFi Drive integration.

Home Assistant loads the platform from here; the entity classes live in
entities.py and the description tables are assembled in sensor_descriptions.py.
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
