#!/usr/bin/env python3
"""
Controlla passo passo la configurazione Google e dice all'utente cosa manca.
Non scrive nulla nel foglio (sola lettura del titolo).

Usage:
    python implementation/check_google_setup.py

Exit codes:
    0 - Tutto pronto
    2 - Credenziali/ID foglio mancanti o foglio non condiviso
    3 - Errore API Google (es. Google Sheets API non abilitata)

Prerequisites:
    uv pip install --python .venv\\Scripts\\python.exe -r requirements.txt
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_auth import GoogleAuthError, credentials_path, get_credentials, read_credentials_file
from load_env import load_env


def fail(message: str, code: int, **extra) -> None:
    print(json.dumps({"error": message, **extra}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def run() -> dict:
    load_env()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        fail("GOOGLE_SHEET_ID mancante nel .env", 2)

    try:
        info = read_credentials_file()
    except GoogleAuthError as e:
        fail(str(e), 2, step="Passo 3: scarica la chiave JSON e salvala come credentials.json nella cartella del progetto")

    auth_type = "service_account" if info.get("type") == "service_account" else "oauth_client"
    share_with = info.get("client_email") if auth_type == "service_account" else None

    import gspread

    try:
        client = gspread.authorize(get_credentials())
        spreadsheet = client.open_by_key(sheet_id)
    except GoogleAuthError as e:
        fail(str(e), 2)
    except gspread.exceptions.SpreadsheetNotFound:
        fail("Foglio non raggiungibile: condividilo (ruolo Editor) con l'email del service account",
             2, share_with=share_with, step="Passo 4")
    except gspread.exceptions.APIError as e:
        status = e.response.status_code
        hint = "Abilita 'Google Sheets API' nel progetto Google Cloud (Passo 2)" if status == 403 else str(e)
        fail(f"Errore Google ({status}): {hint}", 3 if status != 403 else 2, share_with=share_with)

    return {
        "status": "success",
        "auth_type": auth_type,
        "credentials_file": credentials_path().name,
        "share_with": share_with,
        "spreadsheet_title": spreadsheet.title,
        "worksheets": [w.title for w in spreadsheet.worksheets()],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    print(json.dumps(run(), indent=2, ensure_ascii=False))
