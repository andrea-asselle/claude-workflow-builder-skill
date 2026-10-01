#!/usr/bin/env python3
"""
<Una riga: cosa fa questo script (una sola responsabilita').>

Usage:
    python3 implementation/<nome_script>.py --<arg> <valore>

Exit codes:
    0 - Success
    1 - Invalid input (missing args, bad JSON)
    2 - Missing or invalid credentials
    3 - External API error
    4 - Empty or partial result

Prerequisites:
    pip3 install -r requirements.txt
    .env file with <VARIABILE>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add implementation/ to path for local imports
sys.path.insert(0, str(Path(__file__).parent))
from load_env import load_env

# Hard stop: limite di sicurezza per run
MAX_ITEMS_LIMIT = 10


def fail(message: str, code: int, **extra) -> None:
    """Print JSON error to stderr and exit with the given code."""
    print(json.dumps({"error": message, **extra}), file=sys.stderr)
    sys.exit(code)


def run(arg: str) -> dict:
    """Core logic. Returns a JSON-serializable dict."""
    load_env()

    secret = os.environ.get("<VARIABILE>", "").strip()
    if not secret:
        fail("<VARIABILE> mancante. Aggiungila al file .env", 2)

    try:
        result = ...  # chiamata esterna
    except Exception as e:
        fail(f"Errore API: {e}", 3)

    if not result:
        fail("Risultato vuoto. Verifica gli input.", 4)

    return {
        "status": "success",
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="<descrizione>")
    parser.add_argument("--arg", required=True, help="<help>")
    args = parser.parse_args()

    print(json.dumps(run(args.arg), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
