#!/usr/bin/env python3
"""Convenience launcher for AgentCorp P2P Mesh over Tailscale.
Simply run:
    python3 run_mesh.py
"""

from agentcorp_mesh.__main__ import main
import asyncio

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
