"""System utility helpers for AgentCorp nodes and hub.
"""

from __future__ import annotations

import platform
import socket
import psutil
from typing import Dict, Any


def get_system_metrics() -> Dict[str, Any]:
    """Retrieve current system load, memory, and platform details."""
    cpu_pct = 0.0
    mem_pct = 0.0
    try:
        cpu_pct = float(psutil.cpu_percent(interval=None))
    except Exception:
        pass

    try:
        mem = psutil.virtual_memory()
        mem_pct = float(mem.percent)
    except Exception:
        pass

    hostname = socket.gethostname()
    try:
        ip = socket.gethostbyname(hostname)
    except Exception:
        ip = "127.0.0.1"

    return {
        "hostname": hostname,
        "ip": ip,
        "platform_name": platform.system().lower(),
        "cpu_percent": cpu_pct,
        "memory_percent": mem_pct,
    }
