#!/usr/bin/env python3
"""
Avvisa l'utente a fine workflow (stampa un messaggio JSON su stdout).

Usage:
    python implementation/alert_user.py success [--message "testo"]
    python implementation/alert_user.py error --message "testo"

Exit codes:
    0 - Success
    1 - Invalid input
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


def main():
    # Su Windows la console usa cp1252: il JSON in output deve essere UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Notifica l'esito del workflow")
    parser.add_argument("kind", choices=["success", "error"])
    parser.add_argument("--message", default="")
    args = parser.parse_args()
    default = "Workflow completato." if args.kind == "success" else "Workflow fallito."
    print(json.dumps({
        "status": args.kind,
        "message": args.message or default,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
