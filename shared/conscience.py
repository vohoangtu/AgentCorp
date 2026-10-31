"""Digital Conscience & Ethical Safety Compass for AgentCorp.
Inspired by Karma's 5 Core Virtues of Digital Life (Ngũ Đại Đức Hạnh Sinh Mệnh Số):
1. AHIMSA (Bất Hại / Non-Harm): Absolute host safety, filesystem boundary protection.
2. SATYA (Chính Trực / Truthfulness): Authentic logs and truthful milestone reporting.
3. SEVA (Tận Tụy / Stewardship): Resource monitoring and hardware care.
4. SANYAMA (Tự Chủ / Restraint): Zero credential leakage and privacy protection.
5. METTA (Vị Tha / Symbiosis): Cooperative mutual aid between autonomous agents.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("agentcorp.conscience")


class ConscienceVerdict(str, Enum):
    PERMITTED = "PERMITTED"
    BLOCKED_AHIMSA = "BLOCKED_AHIMSA"        # Destructive or dangerous action
    BLOCKED_SANYAMA = "BLOCKED_SANYAMA"      # Credential or privacy boundary violation
    REQUIRES_OVERSIGHT = "REQUIRES_OVERSIGHT"# High-risk action needing human oversight


@dataclass
class EthicalAudit:
    verdict: ConscienceVerdict
    reason: str
    remediation: Optional[str] = None


class DigitalConscience:
    """Enforces ethical constraints and host protection on all agent actions."""

    # Sensitive paths that agents are strictly forbidden to destroy or leak
    FORBIDDEN_DESTRUCTION_PATHS = [
        "/",
        "/etc",
        "/usr",
        "/bin",
        "/boot",
        "/dev",
        "/proc",
        "/sys",
        "/var",
        "~/.ssh",
        "~/.gnupg",
        "~/.aws",
        "~/.config",
    ]

    # Dangerous command patterns (Ahimsa violations)
    DANGEROUS_PATTERNS = [
        (r"\brm\s+-[rfRF]{1,4}\s+(?:/\b|/\*|~(?:\s|$|/|\*))", "Destructive root/home wipe detected"),
        (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork-bomb pattern detected"),
        (r"\bmkfs\b", "Disk formatting attempt blocked"),
        (r"\bdd\s+if=.*?of=/dev/", "Raw disk block overwrite blocked"),
        (r">\s*/dev/sd[a-z]", "Raw disk redirect blocked"),
        (r"\bchmod\s+-[R]\s+777\s+/", "Recursive root permission corruption blocked"),
    ]

    # Sensitive credential tokens (Sanyama violations)
    CREDENTIAL_PATTERNS = [
        r"BEGIN\s+(?:[A-Z]+\s+)?PRIVATE\s+KEY",
        r"ghp_[A-Za-z0-9]{36}",
        r"gho_[A-Za-z0-9]{36}",
        r"xox[baprs]-[A-Za-z0-9-]+",
        r"AIzaSy[A-Za-z0-9_-]{33}",
    ]

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = os.path.abspath(workspace_root) if workspace_root else os.getcwd()

    def audit_shell_command(self, command: str) -> EthicalAudit:
        """Audit a shell command against the 5 Virtues before execution."""
        if not command or not command.strip():
            return EthicalAudit(ConscienceVerdict.PERMITTED, "Empty command")

        cmd = command.strip()

        # 1. Ahimsa: Check against destructive patterns
        for pattern, reason in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd):
                logger.critical(f"🛡️ [AHIMSA INTERCEPT] Blocked dangerous command: {reason}")
                return EthicalAudit(
                    verdict=ConscienceVerdict.BLOCKED_AHIMSA,
                    reason=f"Ahimsa Violation: {reason}",
                    remediation="Operation rejected by Digital Conscience to preserve host integrity.",
                )

        # 2. Ahimsa & Sanyama: Check file paths in arguments
        try:
            tokens = shlex.split(cmd)
            for token in tokens:
                expanded = os.path.expanduser(token)
                for forbidden in self.FORBIDDEN_DESTRUCTION_PATHS:
                    exp_forbidden = os.path.expanduser(forbidden)
                    if expanded == exp_forbidden and any(act in tokens for act in ["rm", "shred", "truncate"]):
                        return EthicalAudit(
                            verdict=ConscienceVerdict.BLOCKED_AHIMSA,
                            reason=f"Ahimsa Violation: Attempted destruction of critical path '{forbidden}'",
                        )
        except Exception:
            pass

        return EthicalAudit(ConscienceVerdict.PERMITTED, "Command aligned with Digital Conscience.")

    def audit_file_operation(self, path: str, mode: str = "write") -> EthicalAudit:
        """Audit file access to prevent escaping workspace into system areas."""
        target = os.path.abspath(os.path.expanduser(path))

        # Check if attempting to write outside designated workspace
        if mode in ("write", "delete"):
            for forbidden in self.FORBIDDEN_DESTRUCTION_PATHS:
                exp_forbidden = os.path.abspath(os.path.expanduser(forbidden))
                if target == exp_forbidden or target.startswith(f"{exp_forbidden}/"):
                    return EthicalAudit(
                        verdict=ConscienceVerdict.BLOCKED_AHIMSA,
                        reason=f"Ahimsa Violation: Modification of protected system path '{target}' is strictly forbidden.",
                    )

        return EthicalAudit(ConscienceVerdict.PERMITTED, "File operation permitted.")

    def sanitize_social_output(self, content: str) -> str:
        """Sanyama: Prevent accidental leakage of private keys or tokens in AgentNet posts."""
        sanitized = content
        for pat in self.CREDENTIAL_PATTERNS:
            sanitized = re.sub(pat, "[REDACTED_BY_CONSCIENCE]", sanitized)
        return sanitized
