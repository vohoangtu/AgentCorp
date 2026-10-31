"""Tests for Session Preemption Monitor and human activity interlocks.
"""

import os
import tempfile
import time
import pytest
from shared.models import ControlMode, PreemptionSignalType
from agentcorp_node.preemption import PreemptionMonitor


def test_preemption_initial_state():
    monitor = PreemptionMonitor(node_id="test-node-1", inactivity_threshold_seconds=1.0)
    assert monitor.control_mode == ControlMode.FULL_CONTROL
    assert monitor.is_autonomous_allowed() is True
    assert monitor.active_human_user is None


def test_user_detected_and_yield():
    monitor = PreemptionMonitor(node_id="test-node-1", inactivity_threshold_seconds=1.0)

    preempted_signals = []
    monitor.register_on_preempt(lambda s: preempted_signals.append(s))

    sig = monitor.trigger_user_detected(username="bob", details="Mouse move")

    assert sig is not None
    assert sig.signal_type == PreemptionSignalType.USER_DETECTED
    assert sig.username == "bob"
    assert monitor.control_mode == ControlMode.YIELDED_PASSIVE
    assert monitor.is_autonomous_allowed() is False
    assert len(preempted_signals) == 1


def test_user_idle_and_reclaim():
    monitor = PreemptionMonitor(node_id="test-node-1", inactivity_threshold_seconds=1.0)

    reclaim_signals = []
    monitor.register_on_reclaim(lambda s: reclaim_signals.append(s))

    # First preempt
    monitor.trigger_user_detected("bob")
    assert monitor.control_mode == ControlMode.YIELDED_PASSIVE

    # Then human goes idle
    sig = monitor.trigger_user_idle("Operator idle")
    assert sig is not None
    assert sig.signal_type == PreemptionSignalType.USER_IDLE
    assert monitor.control_mode == ControlMode.FULL_CONTROL
    assert monitor.is_autonomous_allowed() is True
    assert len(reclaim_signals) == 1


@pytest.mark.asyncio
async def test_watchdog_flag_file_preemption():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        flag_path = tmp.name

    try:
        monitor = PreemptionMonitor(
            node_id="test-node-file",
            inactivity_threshold_seconds=0.5,
            poll_interval=0.1,
            flag_file_path=flag_path,
        )

        preempted = []
        reclaimed = []
        monitor.register_on_preempt(lambda s: preempted.append(s))
        monitor.register_on_reclaim(lambda s: reclaimed.append(s))

        await monitor.start()

        # Touch flag file to simulate human interaction
        with open(flag_path, "w") as f:
            f.write("human_tester")

        # Allow watchdog to tick
        import asyncio
        await asyncio.sleep(0.3)

        assert monitor.control_mode == ControlMode.YIELDED_PASSIVE
        assert len(preempted) >= 1

        # Now remove flag file to simulate human leaving
        if os.path.exists(flag_path):
            os.remove(flag_path)

        # Wait for inactivity threshold (0.5s) to trigger reclaim
        await asyncio.sleep(0.7)

        assert monitor.control_mode == ControlMode.FULL_CONTROL
        assert len(reclaimed) >= 1

        await monitor.stop()
    finally:
        if os.path.exists(flag_path):
            os.remove(flag_path)
