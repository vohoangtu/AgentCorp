"""Tests for Decentralized Tailscale Mesh Discovery and Leader Election.
"""

import pytest
from agentcorp_mesh.tailscale_discovery import TailscaleDiscovery, TailscaleNode
from agentcorp_mesh.election import MeshElectionManager


def test_tailscale_discovery_mock_parsing():
    discovery = TailscaleDiscovery()
    self_node = discovery.get_self_node()
    assert self_node is not None
    assert isinstance(self_node.ip, str)
    assert self_node.is_self is True


def test_mesh_election_prefers_server_node():
    self_node = TailscaleNode(hostname="my-laptop", dns_name="my-laptop.ts.net", ip="100.1.1.1", is_self=True, is_online=True)
    server_node = TailscaleNode(hostname="vultr", dns_name="vultr.ts.net", ip="100.1.1.2", is_self=False, is_online=True)
    client_node = TailscaleNode(hostname="fox", dns_name="fox.ts.net", ip="100.1.1.3", is_self=False, is_online=True)

    election = MeshElectionManager(self_node=self_node, preferred_leaders=["vultr", "srv"])
    leader = election.elect_leader([self_node, server_node, client_node])

    # vultr has +50 preferred score, so it must win election
    assert leader.hostname == "vultr"
    assert election.is_self_leader() is False


def test_mesh_election_yields_when_human_preempts():
    # If vultr was preferred but gets preempted by a human operator, another node must take over
    self_node = TailscaleNode(hostname="nextech", dns_name="nextech.ts.net", ip="100.1.1.1", is_self=True, is_online=True)
    vultr_node = TailscaleNode(hostname="vultr", dns_name="vultr.ts.net", ip="100.1.1.2", is_self=False, is_online=True)

    election = MeshElectionManager(self_node=self_node, preferred_leaders=["vultr"])

    # Before preemption: vultr is leader
    assert election.elect_leader([self_node, vultr_node]).hostname == "vultr"

    # Human user logs into vultr:
    election.set_node_preempted("vultr", True)

    # Re-election: nextech takes over leadership!
    new_leader = election.elect_leader([self_node, vultr_node])
    assert new_leader.hostname == "nextech"
    assert election.is_self_leader() is True
