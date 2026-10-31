"""AgentCorp Peer-to-Peer Mesh over Tailscale.
Decentralized multi-agent clustering with zero manual configuration,
automatic Tailscale peer discovery, and dynamic leader election.
"""

from agentcorp_mesh.tailscale_discovery import TailscaleDiscovery, TailscaleNode
from agentcorp_mesh.election import MeshElectionManager
from agentcorp_mesh.mesh_node import MeshAgentNode

__all__ = [
    "TailscaleDiscovery",
    "TailscaleNode",
    "MeshElectionManager",
    "MeshAgentNode",
]
