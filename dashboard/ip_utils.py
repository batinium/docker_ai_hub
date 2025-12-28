"""Utilities for selecting a host IP address that remote clients can reach.

The project exposes several HTTP services that need to advertise a concrete
address (e.g. the host's LAN or tailnet IP) to other containers and remote
peers. Users can always override this via the ``AIHUB_IP`` or ``LAN_IP``
environment variables, but in practice those are often unset or end up pointing
to a non-routable interface (such as Docker's bridge network). This module
provides a best-effort resolver that picks a sensible default without manual
configuration.

The resolver follows this priority order:

1. Respect explicit environment variables (``AIHUB_IP``, ``LAN_IP``, etc.).
2. Examine network interfaces via ``ip -j addr`` when available.
3. Fall back to ``hostname -I`` and finally to the outbound socket heuristic.

Every candidate is scored so that Tailscale/tailnet addresses win first, then
LAN interfaces, with known container-only subnets heavily penalised. The helper
returns ``127.0.0.1`` only when no better option is found.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Iterable, List, Tuple

_ENV_IP_KEYS: Tuple[str, ...] = (
    "AIHUB_IP",
    "LAN_IP",
    "TAILSCALE_IP",
    "TAILNET_IP",
    "HOST_IP",
    "LOCAL_IP",
)

_EXCLUDED_IFACE_PREFIXES: Tuple[str, ...] = (
    "lo",
    "docker",
    "br-",
    "veth",
    "cni",
    "kube",
    "virbr",
    "zt",
    "wg",
    "utun",
)

_PREFERRED_IFACE_PREFIXES: Tuple[str, ...] = (
    "tailscale",
    "ts",
    "en",
    "eth",
    "wl",
    "wlan",
)

_DOCKER_HOST_SUBNETS = (ip_network("172.16.0.0/12"),)

_TAILSCALE_NET = ip_network("100.64.0.0/10")
_IS_CONTAINER = Path("/.dockerenv").exists()


def _is_valid_ip(value: str) -> bool:
    try:
        ip = ip_address(value)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast:
        return False
    return True


def _score_candidate(ip_str: str, iface: str | None, source_bias: int = 0) -> int:
    score = source_bias
    ip = ip_address(ip_str)

    if iface:
        iface_lower = iface.lower()
        if any(iface_lower.startswith(prefix) for prefix in _EXCLUDED_IFACE_PREFIXES):
            score -= 40
        if any(iface_lower.startswith(prefix) for prefix in _PREFERRED_IFACE_PREFIXES):
            score += 20
        if iface_lower.startswith("tailscale") or iface_lower.startswith("ts"):
            score += 40

    if ip in _TAILSCALE_NET:
        score += 80
    elif ip.is_private:
        score += 55
    elif ip.is_global:
        score += 40

    if ip.is_link_local:
        score -= 50

    if _IS_CONTAINER and ip.is_private:
        # Penalise Docker bridge addresses when running inside a container so we
        # do not advertise the container's virtual IP to peers. The host still
        # wins if no other option exists.
        if any(ip in subnet for subnet in _DOCKER_HOST_SUBNETS):
            score -= 60

    return score


def _collect_from_ip_cmd() -> List[Tuple[int, str]]:
    candidates: List[Tuple[int, str]] = []
    try:
        output = subprocess.check_output(["ip", "-j", "addr", "show", "up"], text=True)
    except (OSError, subprocess.CalledProcessError):
        return candidates

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return candidates

    for link in parsed:
        iface = link.get("ifname")
        addr_infos: Iterable[dict] = link.get("addr_info", [])
        for info in addr_infos:
            if info.get("family") != "inet":
                continue
            ip_str = info.get("local")
            if not ip_str or not _is_valid_ip(ip_str):
                continue
            candidates.append((_score_candidate(ip_str, iface, source_bias=30), ip_str))
    return candidates


def _collect_from_hostname() -> List[Tuple[int, str]]:
    candidates: List[Tuple[int, str]] = []
    try:
        output = subprocess.check_output(["hostname", "-I"], text=True)
    except (OSError, subprocess.CalledProcessError):
        return candidates

    for raw in output.split():
        ip_str = raw.strip()
        if not ip_str or not _is_valid_ip(ip_str):
            continue
        candidates.append((_score_candidate(ip_str, iface=None, source_bias=10), ip_str))
    return candidates


def _collect_host_gateway() -> List[Tuple[int, str]]:
    if not _IS_CONTAINER:
        return []
    try:
        ip_str = socket.gethostbyname("host.docker.internal")
    except socket.gaierror:
        return []

    if not _is_valid_ip(ip_str):
        return []
    # Prefer the host gateway strongly so we talk to the Docker host from within
    # the container instead of the container's own bridge IP.
    return [(_score_candidate(ip_str, iface="host.docker.internal", source_bias=80), ip_str)]


def _collect_from_socket() -> List[Tuple[int, str]]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # The destination address is irrelevant; no packets are sent.
        sock.connect(("1.1.1.1", 80))
        ip_str = sock.getsockname()[0]
    except OSError:
        return []
    finally:
        sock.close()

    if not _is_valid_ip(ip_str):
        return []
    return [(_score_candidate(ip_str, iface=None), ip_str)]


def _dedupe_best(candidates: Iterable[Tuple[int, str]]) -> str | None:
    best_by_ip: dict[str, int] = {}
    for score, ip_str in candidates:
        current = best_by_ip.get(ip_str)
        if current is None or score > current:
            best_by_ip[ip_str] = score

    if not best_by_ip:
        return None

    return max(best_by_ip.items(), key=lambda item: item[1])[0]


def resolve_local_ip(fallback: str = "127.0.0.1") -> str:
    """Return the best-guess host IP address for advertising services.

    Parameters
    ----------
    fallback:
        Value to emit when no usable interface can be discovered.
    """

    for env_key in _ENV_IP_KEYS:
        raw = os.environ.get(env_key)
        if not raw:
            continue
        candidate = raw.strip()
        if candidate and _is_valid_ip(candidate):
            return candidate

    candidates: List[Tuple[int, str]] = []
    candidates.extend(_collect_from_ip_cmd())
    candidates.extend(_collect_from_hostname())
    candidates.extend(_collect_host_gateway())
    candidates.extend(_collect_from_socket())

    best = _dedupe_best(candidates)
    return best or fallback


__all__ = ["resolve_local_ip"]


