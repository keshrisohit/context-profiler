"""Formatting and lightweight estimation helpers."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime


def fmt_tokens(n: int | float | None) -> str:
    n = int(n or 0)
    return f"~{n//1000}k" if n >= 1000 else f"~{n}"


def fmt_bytes(n: int | float | None) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}MB"
    if n >= 1_000:
        return f"{n/1_000:.1f}KB"
    return f"{n}B"


def token_color(n: int) -> str:
    if n >= 20000:
        return "bright_red"
    if n >= 5000:
        return "red"
    if n >= 1000:
        return "yellow"
    return "green"


def ts_to_epoch(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def estimate_tokens(input_bytes: int, output_bytes: int, output_text: str = "") -> int:
    match = re.search(r"Original token count:\s*([0-9]+)", output_text or "")
    if match:
        return int(match.group(1)) + (input_bytes // 4)
    return (input_bytes + output_bytes) // 4


def git_branch_for(cwd: str) -> str:
    if not cwd:
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""

