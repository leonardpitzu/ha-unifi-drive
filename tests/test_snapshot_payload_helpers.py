"""Unit tests for snapshot payload helpers."""

from typing import Any

from tests.module_stubs import (
    install_aiohttp_stub,
    install_package_stubs,
    load_const_module,
    load_integration_module,
)

def _load_snapshot_payload_module():
    """Load the snapshot payload module with integration stubs."""
    load_const_module()
    install_package_stubs()
    install_aiohttp_stub()
    return load_integration_module("snapshot_payload")

snapshot_payload_module = _load_snapshot_payload_module()


def test_snapshot_target_type_uses_aliases_and_shape_detection() -> None:
    """List payloads should resolve target type using aliases and key hints."""
    assert (
        snapshot_payload_module._snapshot_target_type(
            {"type": "personal", "id": "user-1"}
        )
        == "mydrive"
    )
    assert (
        snapshot_payload_module._snapshot_target_type(
            {"targetType": "shared_drive", "sharedDrive": {"id": "shared-1"}}
        )
        == "shared"
    )
    assert (
        snapshot_payload_module._snapshot_target_type(
            {"user": {"id": "user-1"}, "id": "user-1"}
        )
        == "mydrive"
    )


def test_snapshot_target_type_invalid_payload_returns_none() -> None:
    """Malformed payload entries should return no target type instead of raising."""
    assert snapshot_payload_module._snapshot_target_type("bad-entry") is None
    assert snapshot_payload_module._snapshot_target_type(None) is None


def test_snapshot_target_type_normalized_returns_empty_on_invalid_payload() -> None:
    """Normalization helper should stay robust on non-mapping target objects."""
    assert snapshot_payload_module._snapshot_target_type_normalized("bad-entry") == ""
    assert snapshot_payload_module._snapshot_target_type_normalized(None) == ""


def test_extract_snapshot_settings_skips_invalid_list_items() -> None:
    """Non-dict list entries in snapshot payloads must be ignored."""
    payload: dict[str, Any] = {
        "data": [
            None,
            "invalid",
            {"sharedDriveName": "Team", "type": "shared"},
            {"user": {"id": "user-1", "firstName": "Alex"}, "targetName": "Alex"},
            {"foo": 123, "type": "mydrive"},
        ]
    }

    settings = snapshot_payload_module.extract_snapshot_settings(payload)
    assert len(settings) == 2
    assert settings[0]["type"] == "shared"
    assert settings[0]["id"] == "Team"
    assert settings[0]["name"] == "Team"
    assert settings[1]["type"] == "mydrive"
    assert settings[1]["id"] == "user-1"
    assert settings[1]["name"] == "Alex"
