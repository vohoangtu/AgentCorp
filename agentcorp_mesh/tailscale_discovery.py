"""Tailscale peer auto-discovery and network status parser.
Extracts local node Tailscale identity and peers in the tailnet.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("agentcorp.mesh.discovery")


@dataclass
class TailscaleNode:
    hostname: str
    dns_name: str
    ip: str
    ipv6: Optional[str] = None
    is_self: bool = False
    is_online: bool = False
    os: str = "linux"


class TailscaleDiscovery:
    """Discovers peer devices in the same Tailscale Tailnet."""

    def __init__(self, port: int = 8000):
        self.port = port
        self.tailscale_bin = shutil.which("tailscale")
        self._cached_self_node: Optional[TailscaleNode] = None

    def is_tailscale_installed(self) -> bool:
        return self.tailscale_bin is not None

    def query_tailscale_status(self) -> Optional[dict]:
        """Run `tailscale status --json` and parse output."""
        if not self.tailscale_bin:
            return None
        try:
            res = subprocess.run(
                [self.tailscale_bin, "status", "--json"],
                capture_output=True,
                text=True,
                timeout=4,
                check=True,
            )
            return json.loads(res.stdout)
        except Exception as e:
            logger.debug(f"Unable to query tailscale status: {e}")
            return None

    def get_self_node(self) -> TailscaleNode:
        """Get the identity of the current host."""
        data = self.query_tailscale_status()
        if data and "Self" in data:
            self_info = data["Self"]
            ips = self_info.get("TailscaleIPs", [])
            ipv4 = ips[0] if len(ips) > 0 else "127.0.0.1"
            ipv6 = ips[1] if len(ips) > 1 else None

            node = TailscaleNode(
                hostname=self_info.get("HostName", socket.gethostname()),
                dns_name=self_info.get("DNSName", f"{socket.gethostname()}.local"),
                ip=ipv4,
                ipv6=ipv6,
                is_self=True,
                is_online=True,
                os=self_info.get("OS", "linux"),
            )
            self._cached_self_node = node
            return node

        # Fallback to local machine hostname & interface
        fallback_host = socket.gethostname()
        return TailscaleNode(
            hostname=fallback_host,
            dns_name=f"{fallback_host}.local",
            ip="127.0.0.1",
            is_self=True,
            is_online=True,
            os="linux",
        )

    def get_online_peers(self, include_self: bool = True) -> List[TailscaleNode]:
        """Returns all reachable nodes in the tailnet."""
        nodes: List[TailscaleNode] = []
        data = self.query_tailscale_status()

        self_node = self.get_self_node()
        if include_self:
            nodes.append(self_node)

        if not data or "Peer" not in data:
            return nodes

        peers = data.get("Peer", {})
        for peer_id, p in peers.items():
            if not p.get("Online", False):
                continue

            ips = p.get("TailscaleIPs", [])
            if not ips:
                continue

            ipv4 = ips[0]
            ipv6 = ips[1] if len(ips) > 1 else None
            dns_name = p.get("DNSName", "")
            host_name = p.get("HostName", "peer")

            nodes.append(
                TailscaleNode(
                    hostname=host_name,
                    dns_name=dns_name,
                    ip=ipv4,
                    ipv6=ipv6,
                    is_self=False,
                    is_online=True,
                    os=p.get("OS", "linux"),
                )
            )

        return nodes
