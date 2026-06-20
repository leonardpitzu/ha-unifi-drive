"""URL helpers for UniFi Drive hosts."""

from __future__ import annotations

from ipaddress import IPv6Address, ip_address


def format_host_for_url(host: str) -> str:
    """Return a host value safe for use in a URL authority."""
    candidate = host.strip().strip("/")
    unbracketed = candidate
    if candidate.startswith("[") and candidate.endswith("]"):
        unbracketed = candidate[1:-1]

    try:
        parsed = ip_address(unbracketed)
    except ValueError:
        return candidate

    if isinstance(parsed, IPv6Address):
        return f"[{parsed.compressed}]"
    return str(parsed)


def build_console_url(scheme: str, host: str, port: int) -> str:
    """Build a console base URL from normalized or legacy entry data."""
    url_host = format_host_for_url(host)
    default_port = 443 if scheme == "https" else 80
    if port == default_port:
        return f"{scheme}://{url_host}"
    return f"{scheme}://{url_host}:{port}"
