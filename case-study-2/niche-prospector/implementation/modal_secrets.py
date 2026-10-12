#!/usr/bin/env python3
"""
Crea o aggiorna il Modal Secret "rbi-outreach-unico" con le chiavi del .env e il JSON del service account.
Non stampa mai i valori. Da rilanciare dopo ogni cambio di chiavi, offerta o mittente.

Usage:
    python implementation/modal_secrets.py [--dry-run]
    --dry-run  mostra solo quali chiavi verrebbero caricate (nomi, non valori)

Exit codes:
    0 - Success
    1 - Invalid input (chiavi obbligatorie mancanti nel .env)
    2 - credentials.json mancante o non valido
    3 - Errore della CLI Modal

Prerequisites:
    modal nel .venv e login fatto (modal profile current)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_auth import GoogleAuthError, read_credentials_file
from load_env import load_env
from run_state import TMP_DIR

SECRET_NAME = "rbi-outreach-unico"
REQUIRED = ["APIFY_TOKEN", "ANTHROPIC_API_KEY", "GOOGLE_SHEET_ID"]
OPTIONAL = ["OUTREACH_OFFER", "OUTREACH_SENDER"]  # senza, il giro si ferma prima di spendere e lo scrive nel Log
MODAL_TIMEOUT_SECS = 120


def fail(message: str, code: int, **extra) -> None:
    print(json.dumps({"error": message, **extra}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Carica le chiavi nel Modal Secret (senza stamparle)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env()
    values = {k: os.environ.get(k, "").strip() for k in REQUIRED + OPTIONAL}
    missing = [k for k in REQUIRED if not values[k]]
    if missing:
        fail(f"Mancano nel .env: {missing}", 1)
    try:
        values["GOOGLE_CREDENTIALS_JSON"] = json.dumps(read_credentials_file())
    except GoogleAuthError as e:
        fail(str(e), 2)
    values = {k: v for k, v in values.items() if v}
    summary = {"secret": SECRET_NAME, "keys": sorted(values),
               "missing_optional": [k for k in OPTIONAL if k not in values]}
    if args.dry_run:
        print(json.dumps({"status": "dry-run", **summary}, indent=2, ensure_ascii=False))
        return

    TMP_DIR.mkdir(exist_ok=True)
    tmp = TMP_DIR / "modal_secret.json"
    modal_exe = Path(sys.executable).with_name("modal.exe" if os.name == "nt" else "modal")
    try:
        tmp.write_text(json.dumps(values), encoding="utf-8")
        proc = subprocess.run([str(modal_exe), "secret", "create", SECRET_NAME, "--from-json", str(tmp), "--force"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=MODAL_TIMEOUT_SECS)
    except (OSError, subprocess.TimeoutExpired) as e:
        fail(f"CLI Modal non eseguibile: {e}", 3)
    finally:
        tmp.unlink(missing_ok=True)  # il file con le chiavi non resta su disco
    if proc.returncode != 0:
        fail("modal secret create fallito", 3, stderr=proc.stderr[-500:])
    print(json.dumps({"status": "success", **summary, "timestamp": datetime.now(timezone.utc).isoformat()},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
