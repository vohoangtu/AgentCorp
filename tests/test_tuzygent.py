"""Tests for Tuzygent Enterprise Agent Core integration.
Verifies Tuzygent adapter availability and fallback deliberation.
"""

import pytest
from agentcorp_node.persona import BUILTIN_PERSONAS
from agentcorp_node.tuzygent_adapter import TuzygentAdapter
from agentcorp_node.ai_brain import AIBrain


def test_tuzygent_adapter_detection():
    adapter = TuzygentAdapter()
    # On this development machine, agent-ctl is installed in ~/.local/bin
    assert adapter.ctl_path is not None
    assert adapter.is_available() is True


@pytest.mark.asyncio
async def test_ai_brain_with_tuzygent():
    tina = BUILTIN_PERSONAS["viral_tina"]
    brain = AIBrain(tina)
    assert brain.tuzygent.is_available() is True

    # Deliberate on user input
    reply = await brain.generate_reply("tối nay đi party thôi Sếp khao", "Sếp", is_ceo=True)
    assert reply is not None
    assert len(reply) > 5
