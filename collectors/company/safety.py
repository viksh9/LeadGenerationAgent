"""URL / SSRF safety controls for the career-page collector (§45, §46).

Blocks requests to non-public destinations (loopback, private ranges,
link-local, cloud metadata) and non-http(s) schemes. Hostname resolution is
best-effort and only performed when explicitly requested, so unit tests stay
fully offline.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")

# Hostnames that are never public, independent of DNS.
_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
}
_BLOCKED_HOSTNAME_SUFFIXES = (".localhost", ".local", ".internal")

# Cloud metadata endpoints (link-local) — explicitly denied.
_METADATA_IPS = {"169.254.169.254", "100.100.100.200"}


class SafetyError(ValueError):
    """A URL failed a safety check and must not be requested."""


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def is_public_ip(value: str) -> bool:
    """True only for a routable public IP literal."""
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    if str(ip) in _METADATA_IPS:
        return False
    return _ip_is_public(ip)


def validate_public_url(
    url: str,
    *,
    resolve: bool = False,
    allow_private: bool = False,
    allowlisted_hosts: tuple[str, ...] = (),
) -> str:
    """Validate a URL is safe to request; return the normalized host.

    Raises SafetyError for unsupported schemes, missing hosts, and any host that
    is (or resolves to) a non-public address. `resolve=True` performs a DNS
    lookup (network) — leave it False in offline tests. `allow_private` /
    `allowlisted_hosts` permit controlled local testing only.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise SafetyError(f"unsupported URL scheme: {parts.scheme or '(none)'}")
    host = parts.hostname
    if not host:
        raise SafetyError("URL has no host")
    host_l = host.lower()

    if allowlisted_hosts and host_l in allowlisted_hosts:
        return host_l
    if allow_private:
        return host_l

    # Literal IP host → check directly. (Detect first, then decide — SafetyError
    # subclasses ValueError, so it must not be raised inside the parse try/except.)
    try:
        ipaddress.ip_address(host)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False
    if is_ip_literal:
        if not is_public_ip(host):
            raise SafetyError(f"non-public IP address blocked: {host}")
        return host_l

    if host_l in _BLOCKED_HOSTNAMES or host_l.endswith(_BLOCKED_HOSTNAME_SUFFIXES):
        raise SafetyError(f"non-public host blocked: {host}")

    if resolve:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise SafetyError(f"host resolution failed: {host}") from exc
        for info in infos:
            addr = info[4][0]
            if not is_public_ip(addr):
                raise SafetyError(f"host {host} resolves to non-public address {addr}")
    return host_l
