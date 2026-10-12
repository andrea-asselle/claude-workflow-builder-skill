#!/usr/bin/env python3
"""
Autenticazione Google Sheets. Supporta due tipi di file credenziali:
  - service account (campo "type": "service_account") -> nessun login nel browser
  - OAuth client desktop (campo "installed")           -> login nel browser, salva token.json

Usage:
    from google_auth import get_credentials, GoogleAuthError
    creds = get_credentials()

Prerequisites:
    File credenziali in GOOGLE_CREDENTIALS_FILE (default credentials.json nella root)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from load_env import PROJECT_ROOT, load_env

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleAuthError(Exception):
    """Credenziali Google mancanti o non valide."""


def credentials_path() -> Path:
    load_env()
    p = Path(os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json"))
    return p if p.is_absolute() else PROJECT_ROOT / p


def read_credentials_file() -> dict:
    path = credentials_path()
    if not path.exists():
        raise GoogleAuthError(f"File credenziali Google non trovato: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise GoogleAuthError(f"{path.name} non e' un JSON valido: {e}")


def get_credentials():
    """Ritorna credenziali google-auth pronte per gspread."""
    info = read_credentials_file()
    if info.get("type") == "service_account":
        from google.oauth2.service_account import Credentials
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    if "installed" in info:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        token_path = PROJECT_ROOT / "token.json"
        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path()), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds
    raise GoogleAuthError("Formato credenziali non riconosciuto (atteso service account o OAuth 'installed').")
