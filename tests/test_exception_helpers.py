"""Unit tests for translatable exception helpers."""

import sys
import types

from tests.module_stubs import (
    install_package_stubs,
    load_const_module,
    load_integration_module,
)


def _load_exceptions_module():
    install_package_stubs()
    ha_pkg = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    exceptions_pkg = types.ModuleType("homeassistant.exceptions")
    exceptions_pkg.HomeAssistantError = Exception
    exceptions_pkg.ServiceValidationError = Exception
    sys.modules["homeassistant.exceptions"] = exceptions_pkg
    ha_pkg.exceptions = exceptions_pkg
    load_const_module()
    return load_integration_module("exceptions")


exceptions_module = _load_exceptions_module()
DOMAIN = exceptions_module.DOMAIN


class _LegacyHomeAssistantError(Exception):
    """Stub that mimics older/lightweight HA exceptions without kwargs."""

    def __init__(self, message: str, **kwargs: object) -> None:
        if kwargs:
            raise TypeError("translation kwargs are unsupported")
        super().__init__(message)


def test_unifi_unas_error_preserves_translation_attributes_with_legacy_stubs(
    monkeypatch,
) -> None:
    """Fallback path should still expose HA translation metadata."""
    monkeypatch.setattr(exceptions_module, "HomeAssistantError", _LegacyHomeAssistantError)

    err = exceptions_module.unifi_unas_error(
        "Could not run action",
        "system_action_failed",
        action="restart",
    )

    assert isinstance(err, _LegacyHomeAssistantError)
    assert err.translation_domain == DOMAIN
    assert err.translation_key == "system_action_failed"
    assert err.translation_placeholders == {"action": "restart"}


def test_unifi_unas_validation_error_preserves_translation_attributes_with_legacy_stubs(
    monkeypatch,
) -> None:
    """Validation fallback path should preserve the same translation contract."""
    monkeypatch.setattr(
        exceptions_module,
        "ServiceValidationError",
        _LegacyHomeAssistantError,
    )

    err = exceptions_module.unifi_unas_validation_error(
        "Device is offline",
        "device_offline",
    )

    assert isinstance(err, _LegacyHomeAssistantError)
    assert err.translation_domain == DOMAIN
    assert err.translation_key == "device_offline"
    assert err.translation_placeholders is None
