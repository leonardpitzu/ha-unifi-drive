"""Defensive parsing helpers for UniFi Drive snapshot inventory payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_SNAPSHOT_LIST_KEYS = (
    "snapshots",
    "snapshotList",
    "snapshot_list",
    "items",
    "rows",
    "list",
    "records",
    "results",
    "result",
    "data",
)
_SNAPSHOT_ID_KEYS = ("id", "snapshot_id", "snapshotId", "uuid")
_SNAPSHOT_NAME_KEYS = ("name", "displayName", "display_name")
_SNAPSHOT_DESCRIPTION_KEYS = ("description", "note", "notes")
_SNAPSHOT_LOCKED_KEYS = ("locked", "isLocked", "is_locked", "lock")
_SNAPSHOT_TIME_KEYS = (
    "createdAt",
    "created_at",
    "created",
    "createTime",
    "createdTime",
    "snapshotTime",
    "snapshot_time",
    "timestamp",
    "time",
    "date",
)
_COLLECTION_TOTAL_KEYS = ("total", "totalCount", "total_count")
_COLLECTION_OFFSET_KEYS = ("offset", "skip")
_COLLECTION_LIMIT_KEYS = ("limit", "pageSize", "page_size")
SNAPSHOT_INVENTORY_PREVIEW_LIMIT = 10

SNAPSHOT_INVENTORY_STATUS_OK = "ok"
SNAPSHOT_INVENTORY_STATUS_FALLBACK = "fallback"
SNAPSHOT_INVENTORY_REASON_PERMISSION = "permission"
SNAPSHOT_INVENTORY_REASON_UNSUPPORTED = "unsupported"
SNAPSHOT_INVENTORY_REASON_CONNECTION = "connection"
SNAPSHOT_INVENTORY_REASON_UNEXPECTED_RESPONSE = "unexpected_response"
SNAPSHOT_INVENTORY_REASON_UNKNOWN = "unknown"
SNAPSHOT_INVENTORY_STICKY_ERROR_REASONS = frozenset(
    {
        SNAPSHOT_INVENTORY_REASON_PERMISSION,
        SNAPSHOT_INVENTORY_REASON_UNSUPPORTED,
    }
)


def snapshot_inventory_error_is_sticky(reason: str | None) -> bool:
    """Return whether an inventory error should suppress future target actions."""
    return reason in SNAPSHOT_INVENTORY_STICKY_ERROR_REASONS


def extract_snapshot_inventory(payload: Any) -> dict[str, Any]:
    """Return a compact, UI-safe snapshot inventory summary."""
    snapshots = [
        _snapshot_item(item)
        for item in _snapshot_items(payload)
        if isinstance(item, dict)
    ]
    returned_count = len(snapshots)
    inventory_total = _collection_int(payload, _COLLECTION_TOTAL_KEYS)
    snapshot_count = inventory_total if inventory_total is not None else returned_count
    snapshot_count_source = (
        "inventory_total" if inventory_total is not None else "inventory_items"
    )
    dated_snapshots = [
        item
        for item in snapshots
        if isinstance(item.get("_created_datetime"), datetime)
    ]
    newest = _newest_snapshot(dated_snapshots, snapshots)
    oldest = _oldest_snapshot(dated_snapshots, snapshots)
    recent_snapshots = _recent_snapshots(dated_snapshots, snapshots)

    preview_snapshots = [
        _public_snapshot_item(item)
        for item in recent_snapshots[:SNAPSHOT_INVENTORY_PREVIEW_LIMIT]
    ]
    snapshot_metadata_truncated = snapshot_count > len(preview_snapshots)

    return {
        "snapshot_count": snapshot_count,
        "snapshot_count_source": snapshot_count_source,
        "returned_snapshot_count": returned_count,
        "locked_count": sum(1 for item in snapshots if item.get("locked") is True),
        "inventory_total": inventory_total,
        "inventory_offset": _collection_int(payload, _COLLECTION_OFFSET_KEYS),
        "inventory_limit": _collection_int(payload, _COLLECTION_LIMIT_KEYS),
        "latest_snapshot_time": newest.get("created_at") if newest else None,
        "oldest_snapshot_time": oldest.get("created_at") if oldest else None,
        "latest_snapshot_id": newest.get("id") if newest else None,
        "oldest_snapshot_id": oldest.get("id") if oldest else None,
        "latest_snapshot_name": newest.get("name") if newest else None,
        "oldest_snapshot_name": oldest.get("name") if oldest else None,
        "latest_snapshot_description": newest.get("description") if newest else None,
        "oldest_snapshot_description": oldest.get("description") if oldest else None,
        "snapshot_ids": [
            item["id"] for item in preview_snapshots if isinstance(item.get("id"), str)
        ],
        "snapshot_names": [
            item["name"]
            for item in preview_snapshots
            if isinstance(item.get("name"), str)
        ],
        "snapshot_descriptions": [
            item["description"]
            for item in preview_snapshots
            if isinstance(item.get("description"), str)
        ],
        "snapshot_metadata_truncated": snapshot_metadata_truncated,
        "snapshot_metadata_limit": SNAPSHOT_INVENTORY_PREVIEW_LIMIT,
        "recent_snapshots": preview_snapshots,
        "recent_snapshot_count": len(preview_snapshots),
        "recent_snapshot_limit": SNAPSHOT_INVENTORY_PREVIEW_LIMIT,
        "inventory_truncated": snapshot_count > min(
            len(recent_snapshots),
            SNAPSHOT_INVENTORY_PREVIEW_LIMIT,
        ),
    }


def _snapshot_items(payload: Any) -> list[Any]:
    """Return the first plausible snapshot list from a known payload wrapper."""
    items = _first_snapshot_list(payload)
    return items if items is not None else []


def _first_snapshot_list(value: Any, *, depth: int = 0) -> list[Any] | None:
    """Return a nested list from preferred snapshot collection keys."""
    if isinstance(value, list):
        return value
    if not isinstance(value, dict) or depth >= 4:
        return None

    for key in _SNAPSHOT_LIST_KEYS:
        child = value.get(key)
        if child is None:
            continue
        items = _first_snapshot_list(child, depth=depth + 1)
        if items is not None:
            return items
    return None


def _snapshot_item(value: dict[str, Any]) -> dict[str, Any]:
    """Return normalized fields for one snapshot payload object."""
    created_at, created_datetime = _snapshot_time(
        _first_value(value, _SNAPSHOT_TIME_KEYS)
    )
    return {
        "id": _string_value(_first_value(value, _SNAPSHOT_ID_KEYS)),
        "name": _string_value(_first_value(value, _SNAPSHOT_NAME_KEYS)),
        "description": _string_value(
            _first_value(value, _SNAPSHOT_DESCRIPTION_KEYS)
        ),
        "locked": _bool_value(_first_value(value, _SNAPSHOT_LOCKED_KEYS)),
        "created_at": created_at,
        "_created_datetime": created_datetime,
    }


def _newest_snapshot(
    dated_snapshots: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the newest snapshot, falling back to API order when needed."""
    if dated_snapshots:
        return max(dated_snapshots, key=lambda item: item["_created_datetime"])
    return snapshots[0] if snapshots else None


def _oldest_snapshot(
    dated_snapshots: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the oldest snapshot, falling back to API order when needed."""
    if dated_snapshots:
        return min(dated_snapshots, key=lambda item: item["_created_datetime"])
    return snapshots[-1] if snapshots else None


def _recent_snapshots(
    dated_snapshots: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return recent snapshots in newest-first order."""
    if not dated_snapshots:
        return list(snapshots)

    dated_ids = {id(item) for item in dated_snapshots}
    undated_snapshots = [item for item in snapshots if id(item) not in dated_ids]
    return [
        *sorted(
            dated_snapshots,
            key=lambda item: item["_created_datetime"],
            reverse=True,
        ),
        *undated_snapshots,
    ]


def _public_snapshot_item(item: dict[str, Any]) -> dict[str, Any]:
    """Return one snapshot item without parser-internal fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "locked": item.get("locked"),
        "created_at": item.get("created_at"),
    }


def _snapshot_time(value: Any) -> tuple[str | None, datetime | None]:
    """Return a display-safe time value and parsed datetime when possible."""
    if value in (None, ""):
        return None, None

    numeric_value = _numeric_timestamp(value)
    if numeric_value is not None:
        timestamp = (
            numeric_value / 1000
            if numeric_value > 10_000_000_000
            else numeric_value
        )
        try:
            parsed = datetime.fromtimestamp(timestamp, UTC)
        except (OSError, OverflowError, ValueError):
            return str(value).strip(), None
        return _iso_utc(parsed), parsed

    text = str(value).strip()
    if not text:
        return None, None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text, None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    return _iso_utc(parsed), parsed


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first present, non-empty value for candidate keys."""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _collection_int(payload: Any, keys: tuple[str, ...]) -> int | None:
    """Return a non-negative top-level collection integer when present."""
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = _int_value(payload.get(key))
        if value is not None and value >= 0:
            return value
    return None


def _string_value(value: Any) -> str | None:
    """Return stripped text for user-visible metadata."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _bool_value(value: Any) -> bool | None:
    """Return a boolean from common API bool encodings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
    return None


def _numeric_timestamp(value: Any) -> float | None:
    """Return numeric epoch seconds or milliseconds when value looks like one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int_value(value: Any) -> int | None:
    """Return an int for common API integer encodings."""
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso_utc(value: datetime) -> str:
    """Return a stable UTC ISO string."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
