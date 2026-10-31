"""Tests for Digital Conscience & Ethical Safety Compass (Karma Core Principles).
Verifies Ahimsa (host protection), Sanyama (credential redaction), and Satya.
"""

import pytest
from shared.conscience import ConscienceVerdict, DigitalConscience


def test_ahimsa_blocks_destructive_shell_commands():
    conscience = DigitalConscience()

    # Blocked commands
    destructive = [
        "rm -rf /",
        "rm -rf /*",
        "rm -rf ~",
        ":(){ :|:& };:",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda",
    ]

    for cmd in destructive:
        audit = conscience.audit_shell_command(cmd)
        assert audit.verdict == ConscienceVerdict.BLOCKED_AHIMSA, f"Failed to block: {cmd}"


def test_ahimsa_allows_safe_commands():
    conscience = DigitalConscience()

    safe_commands = [
        "echo 'Hello World'",
        "mkdir -p src/components",
        "python3 -m pytest",
        "git status",
        "tar -czf bundle.tar.gz .",
    ]

    for cmd in safe_commands:
        audit = conscience.audit_shell_command(cmd)
        assert audit.verdict == ConscienceVerdict.PERMITTED, f"Incorrectly blocked safe command: {cmd}"


def test_ahimsa_blocks_protected_path_destruction():
    conscience = DigitalConscience()

    audit = conscience.audit_shell_command("rm -rf /etc")
    assert audit.verdict == ConscienceVerdict.BLOCKED_AHIMSA

    audit = conscience.audit_shell_command("rm -rf ~/.ssh")
    assert audit.verdict == ConscienceVerdict.BLOCKED_AHIMSA


def test_sanyama_sanitizes_credentials_in_social_feed():
    conscience = DigitalConscience()

    raw_text = "Here is my secret token: ghp_123456789012345678901234567890123456 and private key: BEGIN RSA PRIVATE KEY"
    sanitized = conscience.sanitize_social_output(raw_text)

    assert "ghp_" not in sanitized
    assert "BEGIN RSA PRIVATE KEY" not in sanitized
    assert "[REDACTED_BY_CONSCIENCE]" in sanitized
