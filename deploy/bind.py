"""Dinlenecek adresler. Genel arayüz ve 0.0.0.0 kabul edilmez."""

from __future__ import annotations

import ipaddress

_ALLOWED = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
)


def listen_hosts(bind_ip: str | None) -> list[str]:
    """127.0.0.1 her zaman vardır. BIND_IP farklı ve özel bir adres ise ona da bağlanır."""
    raw = (bind_ip or "").strip() or "127.0.0.1"
    if raw.lower() == "localhost":
        raw = "127.0.0.1"
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise SystemExit("BIND_IP geçerli bir IPv4 adresi olmalı.") from exc
    if not isinstance(address, ipaddress.IPv4Address):
        raise SystemExit("BIND_IP IPv4 olmalı.")
    if address.is_unspecified or not _is_closed_network(address):
        raise SystemExit("BIND_IP yalnız loopback, özel ağ veya Tailscale adresi olabilir.")
    hosts = ["127.0.0.1"]
    if str(address) != "127.0.0.1":
        hosts.append(str(address))
    return hosts


def _is_closed_network(address: ipaddress.IPv4Address) -> bool:
    return any(address in network for network in _ALLOWED)
