#!/usr/bin/env python3
"""
Legge/scrive lo stato di esecuzione in .tmp/run_state.json.

Usage:
    from run_state import save_step
    save_step("find_leads", "done", leads=3)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
STATE_FILE = TMP_DIR / "run_state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_step(step: str, status: str, **info) -> None:
    TMP_DIR.mkdir(exist_ok=True)
    state = load_state()
    state[step] = {"status": status, "timestamp": datetime.now(timezone.utc).isoformat(), **info}
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
