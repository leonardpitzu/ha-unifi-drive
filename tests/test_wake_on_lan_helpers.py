"""Unit tests for Wake-on-LAN helper utilities."""

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types

import pytest


def _load_wol_module():
    root = Path(__file__).resolve().parents[1]
    package_root = root / "custom_components" / "unifi_unas"
    wol_path = package_root / "wake_on_lan.py"

    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(root / "custom_components")]
    sys.modules.setdefault("custom_components", custom_components_pkg)

    unas_pkg = types.ModuleType("custom_components.unifi_unas")
    unas_pkg.__path__ = [str(package_root)]
    sys.modules["custom_components.unifi_unas"] = unas_pkg

    wol_spec = spec_from_file_location("custom_components.unifi_unas.wake_on_lan", wol_path)
    if wol_spec is None or wol_spec.loader is None:
        raise RuntimeError("Could not load wake_on_lan module spec")
    wol_module = module_from_spec(wol_spec)
    sys.modules["custom_components.unifi_unas.wake_on_lan"] = wol_module
    wol_spec.loader.exec_module(wol_module)
    return wol_module


wol_module = _load_wol_module()


def test_mask_mac_address_shows_only_last_two_bytes() -> None:
    """Masked MAC should reveal only the last two bytes."""
    assert wol_module.mask_mac_address("AA:BB:CC:DD:EE:FF") == "**:**:**:**:ee:ff"


def test_mask_mac_address_handles_empty_and_invalid_values() -> None:
    """Empty MAC values should return None, invalid values should be redacted."""
    assert wol_module.mask_mac_address("") is None
    assert wol_module.mask_mac_address(None) is None
    assert wol_module.mask_mac_address("not-a-mac") == "REDACTED"


def test_wol_validation_helpers_accept_and_reject_expected_values() -> None:
    """Wake-on-LAN validation should normalize common inputs."""
    assert wol_module.normalize_mac_address("AABB.CCDD.EEFF") == "aa:bb:cc:dd:ee:ff"
    assert wol_module.normalize_mac_address("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
    assert wol_module.validate_ipv4_address(" 192.0.2.255 ") == "192.0.2.255"

    with pytest.raises(ValueError):
        wol_module.normalize_mac_address("not-a-mac")
    with pytest.raises(ValueError):
        wol_module.validate_ipv4_address("not-an-ip")


def test_async_send_magic_packet_sends_repeated_packets(monkeypatch) -> None:
    """Magic packet sender should use broadcast UDP and close the transport."""

    class FakeTransport:
        def __init__(self) -> None:
            self.sent: list[tuple[bytes, tuple[str, int]]] = []
            self.closed = False

        def sendto(self, packet: bytes, address: tuple[str, int]) -> None:
            self.sent.append((packet, address))

        def close(self) -> None:
            self.closed = True

    transport = FakeTransport()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _create_datagram_endpoint(*args, **kwargs):
        assert kwargs["allow_broadcast"] is True
        return transport, object()

    monkeypatch.setattr(loop, "create_datagram_endpoint", _create_datagram_endpoint)
    try:
        loop.run_until_complete(
            wol_module.async_send_magic_packet(
                "aa:bb:cc:dd:ee:ff",
                broadcast_address="192.0.2.255",
                port=9,
                packets=2,
                packet_interval=0,
            )
        )
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    assert len(transport.sent) == 2
    assert transport.sent[0][1] == ("192.0.2.255", 9)
    assert transport.sent[0][0].startswith(b"\xff" * 6)
    assert transport.closed is True


def test_async_send_magic_packet_translates_socket_errors(monkeypatch) -> None:
    """Socket open and send failures should become WakeOnLanError."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _raise_on_open(*args, **kwargs):
        raise OSError("cannot bind")

    monkeypatch.setattr(loop, "create_datagram_endpoint", _raise_on_open)
    with pytest.raises(wol_module.WakeOnLanError):
        loop.run_until_complete(
            wol_module.async_send_magic_packet(
                "aa:bb:cc:dd:ee:ff",
                broadcast_address="192.0.2.255",
                port=9,
            )
        )

    class FailingTransport:
        def __init__(self) -> None:
            self.closed = False

        def sendto(self, packet: bytes, address: tuple[str, int]) -> None:
            raise OSError("cannot send")

        def close(self) -> None:
            self.closed = True

    transport = FailingTransport()

    async def _create_failing_transport(*args, **kwargs):
        return transport, object()

    monkeypatch.setattr(loop, "create_datagram_endpoint", _create_failing_transport)
    with pytest.raises(wol_module.WakeOnLanError):
        loop.run_until_complete(
            wol_module.async_send_magic_packet(
                "aa:bb:cc:dd:ee:ff",
                broadcast_address="192.0.2.255",
                port=9,
                packet_interval=0,
            )
        )
    assert transport.closed is True
    loop.close()
    asyncio.set_event_loop(None)


def test_async_send_magic_packet_rejects_invalid_arguments() -> None:
    """Invalid packet arguments should fail before opening a socket."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with pytest.raises(ValueError):
        loop.run_until_complete(
            wol_module.async_send_magic_packet(
                "aa:bb:cc:dd:ee:ff",
                broadcast_address="192.0.2.255",
                port=0,
            )
        )
    with pytest.raises(ValueError):
        loop.run_until_complete(
            wol_module.async_send_magic_packet(
                "aa:bb:cc:dd:ee:ff",
                broadcast_address="192.0.2.255",
                port=9,
                packets=0,
            )
        )
    loop.close()
    asyncio.set_event_loop(None)
