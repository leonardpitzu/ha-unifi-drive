"""Shared import stubs for pure helper tests."""

from __future__ import annotations

import sys
import types
from enum import StrEnum
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "custom_components" / "unifi_unas"


class Platform(StrEnum):
    """Minimal Home Assistant Platform enum stub."""

    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    NUMBER = "number"
    SELECT = "select"
    SENSOR = "sensor"
    SWITCH = "switch"
    TIME = "time"
    UPDATE = "update"


def install_package_stubs() -> None:
    """Install lightweight package stubs for integration relative imports."""
    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(ROOT / "custom_components")]
    sys.modules.setdefault("custom_components", custom_components_pkg)

    drive_pkg = types.ModuleType("custom_components.unifi_unas")
    drive_pkg.__path__ = [str(PACKAGE_ROOT)]
    sys.modules["custom_components.unifi_unas"] = drive_pkg


def install_homeassistant_const_stub(**values: Any) -> types.ModuleType:
    """Install a minimal ``homeassistant.const`` module."""
    ha_pkg = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    const_pkg = types.ModuleType("homeassistant.const")
    const_pkg.Platform = Platform
    for key, value in values.items():
        setattr(const_pkg, key, value)
    sys.modules["homeassistant.const"] = const_pkg
    ha_pkg.const = const_pkg
    return const_pkg


def install_aiohttp_stub(*, include_cookie_jar: bool = False) -> types.ModuleType:
    """Install a minimal aiohttp module for API helper imports."""
    aiohttp_pkg = types.ModuleType("aiohttp")
    aiohttp_pkg.ClientSession = object

    class ClientError(Exception):
        """aiohttp client error stub."""

    class ClientConnectorError(ClientError):
        """aiohttp connector error stub."""

    aiohttp_pkg.ClientError = ClientError
    aiohttp_pkg.ClientConnectorError = ClientConnectorError
    aiohttp_pkg.ClientResponse = object
    if include_cookie_jar:
        aiohttp_pkg.CookieJar = lambda *args, **kwargs: object()
    sys.modules["aiohttp"] = aiohttp_pkg
    return aiohttp_pkg


def load_repo_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a repo module from an explicit file path."""
    spec = spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {module_name} module spec")
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_integration_module(name: str, filename: str | None = None) -> types.ModuleType:
    """Load a UniFi Drive integration module by short module name."""
    module_name = f"custom_components.unifi_unas.{name}"
    return load_repo_module(module_name, PACKAGE_ROOT / (filename or f"{name}.py"))


def load_const_module() -> types.ModuleType:
    """Load the integration constants module."""
    return load_integration_module("const")


def load_wake_on_lan_module() -> types.ModuleType:
    """Load the Wake-on-LAN helper module."""
    return load_integration_module("wake_on_lan")


def load_api_module() -> types.ModuleType:
    """Load the API client with common package, HA const and aiohttp stubs."""
    install_package_stubs()
    install_homeassistant_const_stub()
    install_aiohttp_stub()
    load_wake_on_lan_module()
    load_const_module()
    return load_integration_module("api")
