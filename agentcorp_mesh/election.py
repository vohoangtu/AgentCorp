"""Decentralized Leader Election for Tailscale Peer Mesh.
Selects an Orchestrator Leader deterministically across all online tailnet nodes.
"""

from __future__ import annotations

import logging
import socket
from typing import Dict, List, Optional
from agentcorp_mesh.tailscale_discovery import TailscaleNode

logger = logging.getLogger("agentcorp.mesh.election")


def is_hub_port_open(ip: str, port: int = 8000, timeout: float = 0.4) -> bool:
    """Check if the Hub port is actively listening and reachable on the given IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        res = s.connect_ex((ip, port))
        s.close()
        return res == 0
    except Exception:
        return False


class MeshElectionManager:
    """Computes and coordinates the elected leader in the Tailscale Mesh."""

    def __init__(
        self,
        self_node: TailscaleNode,
        preferred_leaders: Optional[List[str]] = None,
        port: int = 8000,
        check_active_hub: bool = True,
    ):
        self.self_node = self_node
        self.port = port
        self.preferred_leaders = preferred_leaders or []
        self.check_active_hub = check_active_hub
        self.current_leader: Optional[TailscaleNode] = None
        self._preempted_nodes: Dict[str, bool] = {}

    def set_node_preempted(self, node_ip_or_name: str, is_preempted: bool):
        """Mark whether a node's physical workstation is currently occupied by a human."""
        self._preempted_nodes[node_ip_or_name] = is_preempted

    def is_node_preempted(self, node: TailscaleNode) -> bool:
        return self._preempted_nodes.get(node.ip, False) or self._preempted_nodes.get(node.hostname, False)

    def calculate_node_score(self, node: TailscaleNode) -> tuple:
        """Calculate election priority score. Higher is better.

        Returns tuple (score, ip) for deterministic comparison.
        """
        score = 100

        # If this node ALREADY has an active Hub listening on port 8000, prioritize it so nodes converge!
        if self.check_active_hub:
            target_check_ip = "127.0.0.1" if node.is_self else node.ip
            if is_hub_port_open(target_check_ip, self.port):
                score += 1000

        # If a human user is physically operating this machine, penalize heavily so it yields leadership
        if self.is_node_preempted(node):
            score -= 500

        # Preferred hostnames if specified by user
        for pref in self.preferred_leaders:
            if pref and pref.lower() in node.hostname.lower():
                score += 50
                break

        # Ties broken deterministically by IP string (stable order)
        return (score, node.ip)

    def elect_leader(self, online_nodes: List[TailscaleNode]) -> TailscaleNode:
        """Deterministically elect the leader among all reachable nodes."""
        if not online_nodes:
            self.current_leader = self.self_node
            return self.self_node

        # Filter only reachable nodes
        candidates = [n for n in online_nodes if n.is_online]
        if not candidates:
            candidates = [self.self_node]

        # Pick candidate with highest score
        best_candidate = max(candidates, key=self.calculate_node_score)
        self.current_leader = best_candidate
        return best_candidate

    def is_self_leader(self) -> bool:
        """True if the current node is the elected leader."""
        if not self.current_leader:
            return False
        return self.current_leader.ip == self.self_node.ip or self.current_leader.hostname == self.self_node.hostname
