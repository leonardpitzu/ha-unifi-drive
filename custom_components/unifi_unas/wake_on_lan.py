"""Wake-on-LAN helpers for the UniFi Drive integration."""

from __future__ import annotations

import asyncio
import re
import socket
from ipaddress import IPv4Address

from .security import safe_error_text

_HEX_RE = re.compile(r"^[0-9a-fA-F]{12}$")


class WakeOnLanError(Exception):
    """Raised when the Wake-on-LAN packet cannot be sent."""


class _WakeOnLanProtocol(asyncio.DatagramProtocol):
    """No-op datagram protocol used for sending magic packets."""


def normalize_mac_address(mac_address: str) -> str:
    """Normalize a MAC address to colon-separated lower-case hex.

    Accepts common formats such as aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff,
    aabb.ccdd.eeff and aabbccddeeff.
    """
    compact = re.sub(r"[^0-9a-fA-F]", "", mac_address.strip())
    if not _HEX_RE.fullmatch(compact):
        raise ValueError("Invalid MAC address")
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2)).lower()


def mask_mac_address(mac_address: str | None) -> str | None:
    """Return a masked MAC address showing only the last two bytes.

    Example: aa:bb:cc:dd:ee:ff -> **:**:**:**:ee:ff
    """
    if mac_address is None:
        return None
    value = str(mac_address).strip()
    if not value:
        return None
    try:
        normalized = normalize_mac_address(value)
    except ValueError:
        return "REDACTED"
    parts = normalized.split(":")
    if len(parts) != 6:
        return "REDACTED"
    return f"**:**:**:**:{parts[4]}:{parts[5]}"


def validate_ipv4_address(address: str) -> str:
    """Validate and return an IPv4 address string."""
    value = address.strip()
    IPv4Address(value)
    return value


async def async_send_magic_packet(
    mac_address: str,
    *,
    broadcast_address: str,
    port: int,
    packets: int = 3,
    packet_interval: float = 0.05,
) -> None:
    """Send Wake-on-LAN magic packets using an asyncio UDP transport."""
    normalized_mac = normalize_mac_address(mac_address)
    validate_ipv4_address(broadcast_address)

    if port < 1 or port > 65535:
        raise ValueError("Invalid Wake-on-LAN UDP port")
    if packets < 1:
        raise ValueError("packets must be at least 1")

    mac_bytes = bytes.fromhex(normalized_mac.replace(":", ""))
    magic_packet = b"\xff" * 6 + mac_bytes * 16

    loop = asyncio.get_running_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            _WakeOnLanProtocol,
            family=socket.AF_INET,
            allow_broadcast=True,
        )
    except OSError as err:
        raise WakeOnLanError(
            f"Could not open UDP socket for Wake-on-LAN: {safe_error_text(err)}"
        ) from err

    try:
        for _ in range(packets):
            try:
                transport.sendto(magic_packet, (broadcast_address, port))
            except OSError as err:
                raise WakeOnLanError(
                    f"Could not send Wake-on-LAN packet to {broadcast_address}:{port}: "
                    f"{safe_error_text(err)}"
                ) from err
            await asyncio.sleep(packet_interval)
    finally:
        transport.close()
