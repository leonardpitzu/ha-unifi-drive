"""Unit tests for Home Assistant device metadata helpers."""

from enum import Enum
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types


def _load_device_module():
    root = Path(__file__).resolve().parents[1]
    package_root = root / "custom_components" / "unifi_unas"

    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(root / "custom_components")]
    sys.modules.setdefault("custom_components", custom_components_pkg)

    drive_pkg = types.ModuleType("custom_components.unifi_unas")
    drive_pkg.__path__ = [str(package_root)]
    sys.modules["custom_components.unifi_unas"] = drive_pkg

    ha_pkg = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha_pkg

    config_entries_pkg = types.ModuleType("homeassistant.config_entries")
    config_entries_pkg.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries_pkg

    const_pkg = types.ModuleType("homeassistant.const")

    class Platform(str, Enum):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        NUMBER = "number"
        SELECT = "select"
        SENSOR = "sensor"
        SWITCH = "switch"
        TIME = "time"
        UPDATE = "update"

    const_pkg.Platform = Platform
    sys.modules["homeassistant.const"] = const_pkg

    helpers_pkg = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers_pkg

    device_registry_pkg = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_pkg.DeviceInfo = dict
    sys.modules["homeassistant.helpers.device_registry"] = device_registry_pkg

    const_spec = spec_from_file_location(
        "custom_components.unifi_unas.const",
        package_root / "const.py",
    )
    if const_spec is None or const_spec.loader is None:
        raise RuntimeError("Could not load const module spec")
    const_module = module_from_spec(const_spec)
    sys.modules["custom_components.unifi_unas.const"] = const_module
    const_spec.loader.exec_module(const_module)

    device_spec = spec_from_file_location(
        "custom_components.unifi_unas.device",
        package_root / "device.py",
    )
    if device_spec is None or device_spec.loader is None:
        raise RuntimeError("Could not load device module spec")
    device_module = module_from_spec(device_spec)
    sys.modules["custom_components.unifi_unas.device"] = device_module
    device_spec.loader.exec_module(device_module)
    return device_module


device_module = _load_device_module()


class _FakeClient:
    base_url = "https://unas.local"


class _FakeCoordinator:
    client = _FakeClient()
    data = {
        "_system": {
            "hardware": {
                "shortname": "UNAS2",
                "name": "UniFi Drive UNAS",
                "firmwareVersion": "5.0.17",
            }
        }
    }


class _FakeEntry:
    title = "Keller"


def test_device_info_uses_dynamic_model_and_firmware_version() -> None:
    """DeviceInfo should reflect UniFi OS hardware metadata when available."""
    info = device_module.build_device_info(_FakeCoordinator(), _FakeEntry(), "dev-1")

    assert info["model"] == "UNAS2"
    assert info["sw_version"] == "5.0.17"
    assert info["name"] == "Keller"
    assert info["configuration_url"] == "https://unas.local"


def test_device_info_falls_back_to_hardware_name_and_ucore_version() -> None:
    """DeviceInfo should keep useful metadata when shortname/firmware are absent."""
    coordinator = types.SimpleNamespace(
        client=types.SimpleNamespace(base_url="https://backup.local"),
        data={
            "_system": {
                "ucore_version": "5.1.0",
                "hardware": {
                    "shortname": "",
                    "name": "UniFi Drive Backup",
                    "firmwareVersion": "",
                },
            }
        },
    )

    info = device_module.build_device_info(
        coordinator,
        _FakeEntry(),
        "backup-user",
        configuration_url="https://override.local",
    )

    assert info["identifiers"] == {("unifi_unas", "backup-user")}
    assert info["model"] == "UniFi Drive Backup"
    assert info["sw_version"] == "5.1.0"
    assert info["configuration_url"] == "https://override.local"


def test_device_info_uses_raw_system_payload_version_fields() -> None:
    """DeviceInfo should accept system metadata that is not nested under _system."""
    coordinator = types.SimpleNamespace(
        client=types.SimpleNamespace(base_url="https://raw.local"),
        data={
            "hardware": {"shortname": "UNAS2W"},
            "firmware_version": "5.1.10",
        },
    )

    info = device_module.build_device_info(coordinator, _FakeEntry(), "raw-system")

    assert info["model"] == "UNAS2W"
    assert info["sw_version"] == "5.1.10"


def test_device_info_uses_client_cached_system_metadata() -> None:
    """Fresh installs should keep firmware metadata when only the client has it."""
    coordinator = types.SimpleNamespace(
        client=types.SimpleNamespace(
            base_url="https://cached.local",
            _system_info={
                "hardware": {
                    "shortname": "UNAS2W",
                    "firmwareVersion": "5.1.10",
                }
            },
        ),
        data={"pools": []},
    )

    info = device_module.build_device_info(coordinator, _FakeEntry(), "cached-system")

    assert info["model"] == "UNAS2W"
    assert info["sw_version"] == "5.1.10"


def test_device_info_uses_default_model_without_system_payload() -> None:
    """DeviceInfo should remain stable while the device is offline."""
    coordinator = types.SimpleNamespace(
        client=types.SimpleNamespace(base_url=None),
        data=None,
    )

    info = device_module.build_device_info(coordinator, _FakeEntry(), "offline-entry")

    assert info["identifiers"] == {("unifi_unas", "offline-entry")}
    assert info["model"] == "UniFi Drive / UNAS"
    assert "sw_version" not in info
    assert info["configuration_url"] is None
