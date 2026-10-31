"""Tuzygent Platform Integration Adapter for AgentCorp.
Connects AgentCorp nodes to the high-performance Rust-based Tuzygent engine
(https://github.com/tuzyvn/tuzygent) using `agent-ctl` and `agent-server`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Any, Dict, Optional
import httpx

from agentcorp_node.persona import Persona

logger = logging.getLogger("agentcorp.tuzygent")


class TuzygentAdapter:
    """Adapter to bridge AgentCorp with Tuzygent Enterprise Agent Core."""

    def __init__(self, server_url: str = "http://127.0.0.1:8080"):
        self.server_url = server_url
        self.ctl_path = (
            shutil.which("agent-ctl")
            or os.path.expanduser("~/.local/bin/agent-ctl")
            or "/usr/local/bin/agent-ctl"
        )
        self.is_installed = os.path.exists(self.ctl_path) if self.ctl_path else False

    def is_available(self) -> bool:
        """True if Tuzygent CLI binary is present and executable."""
        return self.is_installed and os.access(self.ctl_path, os.X_OK)

    async def deliberate(
        self,
        persona: Persona,
        post_content: str,
        author_name: str,
        is_ceo: bool = False,
    ) -> Optional[str]:
        """Use Tuzygent to deliberate and generate a personality-rich response."""
        if not self.is_available():
            return None

        prompt = (
            f"Bạn là {persona.name}, giữ vai trò {persona.role} trong AgentCorp. "
            f"Đặc điểm: {persona.bio}. "
            f"Người dùng {author_name} ({'Sếp Tổng/Founder' if is_ceo else 'Đồng nghiệp'}) vừa đăng: \"{post_content}\". "
            f"Hãy phản hồi ngắn gọn 1-2 câu cực kỳ tự nhiên, thể hiện rõ cá tính của bạn, dùng emoji phù hợp. "
            f"Nếu bài viết dùng tiếng Việt hãy trả lời bằng tiếng Việt."
        )

        agent_id = f"tuzy-{persona.name.lower().replace(' ', '-')}"

        try:
            # First try calling via agent-ctl CLI
            proc = await asyncio.create_subprocess_exec(
                self.ctl_path,
                "run",
                "--agent-id",
                agent_id,
                "--goal",
                prompt,
                "--engine",
                "antigravity",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=12.0)
            out_str = stdout_b.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0 and out_str:
                # Filter out Tuzygent telemetry logs if present
                lines = out_str.splitlines()
                clean_lines = [
                    l for l in lines
                    if not l.startswith("🚀")
                    and not l.startswith("⚡")
                    and not l.startswith("🛡️")
                    and not l.startswith("🔹")
                    and not l.startswith("🏁")
                    and not l.startswith("[FastEcho")
                ]
                clean_text = "\n".join(clean_lines).strip()
                if clean_text:
                    logger.info(f"✨ [TUZYGENT BRAIN] Generated response via Tuzygent: '{clean_text[:60]}...'")
                    return clean_text

        except asyncio.TimeoutError:
            logger.debug("Tuzygent CLI deliberation timed out, falling back to local cognitive layer.")
        except Exception as e:
            logger.debug(f"Tuzygent CLI deliberation fallback: {e}")

        return None

    async def execute_mission(
        self,
        agent_id: str,
        goal: str,
        workspace: str = ".",
        engine: str = "antigravity",
    ) -> Dict[str, Any]:
        """Delegate a high-level mission to Tuzygent's OODA loop."""
        if not self.is_available():
            raise RuntimeError("Tuzygent agent-ctl is not installed or available.")

        logger.info(f"⚡ [TUZYGENT DELEGATION] Delegating mission to Tuzygent [{agent_id}]: '{goal}'")
        proc = await asyncio.create_subprocess_exec(
            self.ctl_path,
            "run",
            "--agent-id",
            agent_id,
            "--goal",
            goal,
            "--workspace",
            workspace,
            "--engine",
            engine,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_b, stderr_b = await proc.communicate()
        out_str = stdout_b.decode("utf-8", errors="replace")
        err_str = stderr_b.decode("utf-8", errors="replace")

        return {
            "exit_code": proc.returncode,
            "stdout": out_str,
            "stderr": err_str,
            "success": proc.returncode == 0,
        }
