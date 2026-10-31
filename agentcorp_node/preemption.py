"""Session Preemption Monitor for AgentCorp Node.
Detects human user login / physical interaction and immediately yields device control.
Reclaims device control when the human user logs out or goes idle.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Callable, List, Optional
import psutil

from shared.models import ControlMode, PreemptionSignal, PreemptionSignalType

logger = logging.getLogger("agentcorp.preemption")


class PreemptionMonitor:
    """Monitors workstation interaction and enforces safe user preemption."""

    def __init__(
        self,
        node_id: str,
        inactivity_threshold_seconds: float = 8.0,
        poll_interval: float = 0.5,
        flag_file_path: Optional[str] = "/tmp/.agentcorp_user_active",
        enable_os_user_check: bool = False,
    ):
        self.node_id = node_id
        self.inactivity_threshold_seconds = inactivity_threshold_seconds
        self.poll_interval = poll_interval
        self.flag_file_path = flag_file_path
        self.enable_os_user_check = enable_os_user_check
        self.start_time = time.time()

        self.control_mode: ControlMode = ControlMode.FULL_CONTROL
        self.active_human_user: Optional[str] = None
        self.last_user_activity_time: float = 0.0
        self.is_monitoring: bool = False

        self._on_preempt_callbacks: List[Callable[[PreemptionSignal], None]] = []
        self._on_reclaim_callbacks: List[Callable[[PreemptionSignal], None]] = []
        self._monitor_task: Optional[asyncio.Task] = None

    def register_on_preempt(self, callback: Callable[[PreemptionSignal], None]):
        """Register callback when human takes over control."""
        self._on_preempt_callbacks.append(callback)

    def register_on_reclaim(self, callback: Callable[[PreemptionSignal], None]):
        """Register callback when agent reclaims control."""
        self._on_reclaim_callbacks.append(callback)

    def is_autonomous_allowed(self) -> bool:
        """True only if node has full autonomous device control."""
        return self.control_mode == ControlMode.FULL_CONTROL

    def check_human_activity(self) -> Optional[str]:
        """Check for active human interaction across multi-detection strategies.

        Returns username if human activity is detected, else None.
        """
        # Strategy 1: Check simulated/external flag file (global or node-specific)
        candidates = [self.flag_file_path, f"/tmp/.agentcorp_user_active_{self.node_id}"]
        for p in candidates:
            if p and os.path.exists(p):
                try:
                    stat = os.stat(p)
                    # If modified within the last threshold seconds
                    if time.time() - stat.st_mtime < self.inactivity_threshold_seconds:
                        with open(p, "r") as f:
                            content = f.read().strip()
                        return content or "local_human_operator"
                except Exception:
                    pass

        # Strategy 2: Check fresh interactive logins via psutil if enabled
        if self.enable_os_user_check:
            try:
                users = psutil.users()
                for u in users:
                    if u.terminal and (u.terminal.startswith("tty") or u.terminal.startswith(":")):
                        # Fresh user login detected
                        if u.started and (u.started > self.start_time or (time.time() - u.started < self.inactivity_threshold_seconds)):
                            return u.name
            except Exception:
                pass

        return None

    def trigger_user_detected(self, username: str = "human_user", details: str = "Human interaction detected"):
        """Explicitly notify of human user interaction."""
        self.last_user_activity_time = time.time()
        self.active_human_user = username

        if self.control_mode != ControlMode.YIELDED_PASSIVE:
            self.control_mode = ControlMode.YIELDED_PASSIVE
            logger.warning(
                f"🚨 [PREEMPTION] Human user '{username}' detected! Node '{self.node_id}' yielding full control."
            )
            signal = PreemptionSignal(
                signal_type=PreemptionSignalType.USER_DETECTED,
                node_id=self.node_id,
                username=username,
                details=details,
                timestamp=self.last_user_activity_time,
            )
            for cb in self._on_preempt_callbacks:
                try:
                    cb(signal)
                except Exception as e:
                    logger.error(f"Error in on_preempt callback: {e}")
            return signal
        return None

    def trigger_user_idle(self, details: str = "User idle timeout reached"):
        """Explicitly release control back to autonomous agent."""
        if self.control_mode != ControlMode.FULL_CONTROL:
            self.control_mode = ControlMode.FULL_CONTROL
            old_user = self.active_human_user
            self.active_human_user = None
            logger.info(
                f"🟢 [RECLAIM] Human '{old_user}' idle or logged out. Node '{self.node_id}' reclaiming full control."
            )
            # Remove flag files if present
            candidates = [self.flag_file_path, f"/tmp/.agentcorp_user_active_{self.node_id}"]
            for p in candidates:
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            signal = PreemptionSignal(
                signal_type=PreemptionSignalType.USER_IDLE,
                node_id=self.node_id,
                username=old_user,
                details=details,
                timestamp=time.time(),
            )
            for cb in self._on_reclaim_callbacks:
                try:
                    cb(signal)
                except Exception as e:
                    logger.error(f"Error in on_reclaim callback: {e}")
            return signal
        return None

    async def start(self):
        """Start the background preemption watchdog loop."""
        self.is_monitoring = True
        self._monitor_task = asyncio.create_task(self._watchdog_loop())

    async def stop(self):
        """Stop the background preemption watchdog."""
        self.is_monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def _watchdog_loop(self):
        while self.is_monitoring:
            try:
                active_user = self.check_human_activity()
                now = time.time()

                if active_user:
                    # User is currently active
                    self.trigger_user_detected(active_user, "Active user session or input detected")
                else:
                    # No active user detected right now
                    if self.control_mode == ControlMode.YIELDED_PASSIVE:
                        # Check if inactivity threshold has elapsed since last seen
                        if (now - self.last_user_activity_time) >= self.inactivity_threshold_seconds:
                            self.trigger_user_idle("Inactivity threshold reached; user left workstation")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in preemption watchdog: {e}")

            await asyncio.sleep(self.poll_interval)
