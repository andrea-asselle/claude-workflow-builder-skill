#!/usr/bin/env python3
"""
Carica le variabili del file .env (root progetto) in os.environ.

Usage:
    from load_env import load_env
    load_env()
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> None:
    """Legge KEY=VALUE dal .env senza sovrascrivere variabili gia' presenti."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
