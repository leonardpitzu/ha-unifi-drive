"""Shared API test helpers."""

from tests.module_stubs import load_api_module


def _load_api_client_class():
    api_module = load_api_module()
    api_snapshot_module = __import__(
        "custom_components.unifi_unas.api_snapshot",
        fromlist=["ApiSnapshotMixin"],
    )
    snapshot_schedule_module = __import__(
        "custom_components.unifi_unas.snapshot_schedule",
        fromlist=["_snapshot_schedule_days"],
    )
    return (
        api_module.UnifiUnasApiClient,
        api_snapshot_module,
        snapshot_schedule_module,
    )


(
    UnifiUnasApiClient,
    api_snapshot_module,
    snapshot_schedule_module,
) = _load_api_client_class()


class SnapshotWriteClient(api_snapshot_module.ApiSnapshotMixin):
    """Small fake client for testing snapshot write routing."""

    def __init__(self) -> None:
        """Initialize the fake client."""
        self._snapshot_settings_write_supported = None
        self._snapshot_settings_write_supported_by_type = {}
        self._snapshot_create_supported = None
        self._snapshot_create_supported_by_type = {}
        self._snapshot_inventory_supported = None
        self._snapshot_inventory_supported_by_type = {}
        self.calls = []
        self.responses = [(200, {"data": "OK"})]

    async def _ensure_authenticated(self) -> None:
        """No-op authentication stub for this pure routing test client."""
        return None

    async def _request_raw(self, method, path, *, json_body=None):
        """Record the outgoing request and return success."""
        self.calls.append((method, path, json_body))
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


class SnapshotStatusClient(api_snapshot_module.ApiSnapshotMixin):
    """Small fake client for testing snapshot endpoint status handling."""

    def __init__(self, status: int) -> None:
        """Initialize the fake client."""
        self._snapshot_settings_read_supported = None
        self._snapshot_create_supported = None
        self._snapshot_create_supported_by_type = {}
        self._snapshot_inventory_supported = None
        self._snapshot_inventory_supported_by_type = {}
        self.status = status
        self.calls = []

    async def _request_raw(self, method, path, *, json_body=None):
        """Record the outgoing request and return the configured status."""
        self.calls.append((method, path, json_body))
        return self.status, {"error": "not found"}
