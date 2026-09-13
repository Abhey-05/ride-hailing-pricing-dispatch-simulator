"""Minimal .env loader shared by every entry point that might need
ANTHROPIC_API_KEY / GROQ_API_KEY (ask_copilot.py, dashboard/app.py) -- no new
dependency. .env is gitignored; only ever read locally, never committed."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv() -> None:
    """Reads KEY=VALUE lines from .env at the project root into os.environ,
    without overriding already-set env vars. Safe to call multiple times."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
