"""Device Task Executor for AgentCorp Node.
Provides full autonomous control (shell execution, file operations, web/browser requests, GUI automation hooks)
with strict preemption guards that yield immediately when a human is present.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional
import httpx

from shared.conscience import ConscienceVerdict, DigitalConscience
from shared.models import Task, TaskActionType
from agentcorp_node.preemption import PreemptionMonitor

logger = logging.getLogger("agentcorp.executor")


class PreemptionInterruptedError(Exception):
    """Raised when an operation is interrupted or blocked due to human preemption."""
    pass


class TaskExecutor:
    """Executes actions on the local device under the supervision of the preemption monitor."""

    def __init__(self, monitor: PreemptionMonitor, workspace_dir: str = "./workspace"):
        self.monitor = monitor
        self.workspace_dir = os.path.abspath(workspace_dir)
        os.makedirs(self.workspace_dir, exist_ok=True)
        self.conscience = DigitalConscience(workspace_root=self.workspace_dir)

        self.current_task: Optional[Task] = None
        self.active_process: Optional[asyncio.subprocess.Process] = None
        self._is_paused: bool = False
        self._resume_event = asyncio.Event()
        self._resume_event.set()

        # Connect to preemption callbacks
        self.monitor.register_on_preempt(self._on_preempted)
        self.monitor.register_on_reclaim(self._on_reclaimed)

    def _on_preempted(self, sig):
        logger.warning(f"Executor received preemption signal. Pausing active operations.")
        self._is_paused = True
        self._resume_event.clear()

        # If a subprocess is actively running, suspend the process group with SIGSTOP
        if self.active_process and self.active_process.pid:
            try:
                pgid = os.getpgid(self.active_process.pid)
                os.killpg(pgid, signal.SIGSTOP)
                logger.info(f"Suspended active subprocess group PGID {pgid} (SIGSTOP).")
            except Exception:
                try:
                    os.kill(self.active_process.pid, signal.SIGSTOP)
                    logger.info(f"Suspended active subprocess PID {self.active_process.pid} (SIGSTOP).")
                except Exception as e:
                    logger.debug(f"Could not send SIGSTOP to pid: {e}")

    def _on_reclaimed(self, sig):
        logger.info(f"Executor received control reclaim signal. Resuming operations.")
        self._is_paused = False
        self._resume_event.set()

        # Resume suspended subprocess group with SIGCONT
        if self.active_process and self.active_process.pid:
            try:
                pgid = os.getpgid(self.active_process.pid)
                os.killpg(pgid, signal.SIGCONT)
                logger.info(f"Resumed active subprocess group PGID {pgid} (SIGCONT).")
            except Exception:
                try:
                    os.kill(self.active_process.pid, signal.SIGCONT)
                    logger.info(f"Resumed active subprocess PID {self.active_process.pid} (SIGCONT).")
                except Exception as e:
                    logger.debug(f"Could not send SIGCONT to pid: {e}")

    async def execute_task(
        self,
        task: Task,
        progress_cb: Optional[Callable[[float], None]] = None,
    ) -> Dict[str, Any]:
        """Execute a task, checking preemption guards before and during execution."""
        self.current_task = task
        action = task.action

        try:
            # Check preemption guard before starting
            if not self.monitor.is_autonomous_allowed():
                if action.action_type == TaskActionType.GUI:
                    raise PreemptionInterruptedError("GUI automation blocked: human user has physical control!")
                logger.info(f"Device preempted. Waiting for human to finish before starting task {task.id}...")
                timeout = task.action.params.get("preemption_wait_timeout", 5.0)
                try:
                    await asyncio.wait_for(self._resume_event.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    raise PreemptionInterruptedError("Timed out waiting for human user to yield workstation.")

            if progress_cb:
                progress_cb(10.0)

            result = {}

            if action.action_type == TaskActionType.SHELL:
                result = await self._run_shell_task(action.command, progress_cb)

            elif action.action_type == TaskActionType.FILE_WRITE:
                result = await self._run_file_write(action.params)

            elif action.action_type == TaskActionType.FILE_READ:
                result = await self._run_file_read(action.params)

            elif action.action_type == TaskActionType.BROWSER:
                result = await self._run_browser_task(action.params, progress_cb)

            elif action.action_type == TaskActionType.GUI:
                result = await self._run_gui_task(action.params, progress_cb)

            elif action.action_type == TaskActionType.SYNTHETIC:
                result = await self._run_synthetic_task(action.params, progress_cb)

            else:
                raise ValueError(f"Unknown action type: {action.action_type}")

            if progress_cb:
                progress_cb(100.0)

            return result

        finally:
            self.current_task = None
            self.active_process = None

    async def _run_shell_task(
        self, command: Optional[str], progress_cb: Optional[Callable[[float], None]]
    ) -> Dict[str, Any]:
        if not command:
            return {"output": "No command specified"}

        # Digital Conscience Audit (Ahimsa Virtue)
        audit = self.conscience.audit_shell_command(command)
        if audit.verdict != ConscienceVerdict.PERMITTED:
            logger.critical(f"🛡️ [CONSCIENCE REJECTION] {audit.reason}")
            raise ValueError(f"Action blocked by Digital Conscience (Ahimsa Virtue): {audit.reason}")

        logger.info(f"Executing shell command: {command}")
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=self.workspace_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )
        self.active_process = proc

        # Monitor execution while respecting pause events
        stdout_data, stderr_data = await proc.communicate()
        exit_code = proc.returncode

        out_str = stdout_data.decode("utf-8", errors="replace")
        err_str = stderr_data.decode("utf-8", errors="replace")

        if exit_code != 0:
            raise RuntimeError(f"Command failed (exit {exit_code}): {err_str or out_str}")

        return {
            "exit_code": exit_code,
            "stdout": out_str.strip(),
            "stderr": err_str.strip(),
        }

    async def _run_file_write(self, params: Dict[str, Any]) -> Dict[str, Any]:
        rel_path = params.get("path", "output.txt")
        content = params.get("content", "")

        # Digital Conscience Audit (Ahimsa Boundary Protection)
        audit = self.conscience.audit_file_operation(rel_path, mode="write")
        if audit.verdict != ConscienceVerdict.PERMITTED:
            raise ValueError(f"Action blocked by Digital Conscience (Ahimsa Virtue): {audit.reason}")

        target_file = os.path.normpath(os.path.join(self.workspace_dir, rel_path))
        os.makedirs(os.path.dirname(target_file), exist_ok=True)

        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Wrote file {target_file} ({len(content)} chars)")
        return {
            "path": target_file,
            "bytes_written": len(content.encode("utf-8")),
            "artifacts": [target_file],
        }

    async def _run_file_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        rel_path = params.get("path", "")
        target_file = os.path.normpath(os.path.join(self.workspace_dir, rel_path))

        if not os.path.exists(target_file):
            raise FileNotFoundError(f"File {target_file} does not exist.")

        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        return {"path": target_file, "content": content}

    async def _run_browser_task(
        self, params: Dict[str, Any], progress_cb: Optional[Callable[[float], None]]
    ) -> Dict[str, Any]:
        """Perform automated web fetch or simulated browser interaction."""
        url = params.get("url", "https://httpbin.org/get")
        method = params.get("method", "GET").upper()
        logger.info(f"Executing browser/HTTP request: {method} {url}")

        if progress_cb:
            progress_cb(50.0)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(method, url)
            return {
                "url": url,
                "status_code": resp.status_code,
                "text_snippet": resp.text[:500],
            }

    async def _run_gui_task(
        self, params: Dict[str, Any], progress_cb: Optional[Callable[[float], None]]
    ) -> Dict[str, Any]:
        """Execute desktop GUI automation actions (click, type, keypress) with safety interlocks."""
        steps = params.get("steps", [{"action": "click", "x": 100, "y": 200}])
        total_steps = len(steps)

        executed_steps = []
        for idx, step in enumerate(steps):
            # STRICT INTERLOCK: Check if human is present before ANY physical/virtual input
            if not self.monitor.is_autonomous_allowed():
                raise PreemptionInterruptedError("GUI automation blocked: human user has physical control!")

            action_name = step.get("action")
            logger.info(f"[GUI Automation Hook] Dispatching GUI event: {step}")

            # Simulated GUI execution with short safety pacing
            await asyncio.sleep(0.05)

            # Check again right after sleep
            if not self.monitor.is_autonomous_allowed():
                raise PreemptionInterruptedError("GUI automation interrupted mid-action by human takeover!")

            executed_steps.append(step)
            if progress_cb:
                progress_cb(float((idx + 1) / total_steps * 90.0))

        return {"executed_steps": executed_steps, "status": "gui_completed"}

    async def _run_synthetic_task(
        self, params: Dict[str, Any], progress_cb: Optional[Callable[[float], None]]
    ) -> Dict[str, Any]:
        steps = params.get("steps", 3)
        for i in range(steps):
            if not self.monitor.is_autonomous_allowed():
                await self._resume_event.wait()
            await asyncio.sleep(0.1)
            if progress_cb:
                progress_cb(float((i + 1) / steps * 90.0))

        return {"status": "synthetic_computation_done", "params": params}
