#!/usr/bin/env python3
"""
Scrive le email di .tmp/emails.json nel Google Sheet (una riga per lead, stato "Bozza - non inviata").
Non invia nessuna email. Salta i lead gia' presenti nel foglio (stessa email).

Usage:
    python implementation/sheet_export.py [--input .tmp/emails.json] [--worksheet NOME] [--tag TEST]

Exit codes:
    0 - Success
    1 - Invalid input (emails.json mancante/invalido)
    2 - Missing or invalid credentials (credentials.json, GOOGLE_SHEET_ID, foglio non condiviso)
    3 - External API error (Google Sheets)
    4 - Nothing to write (tutti i lead erano gia' nel foglio)

Prerequisites:
    uv pip install --python .venv\\Scripts\\python.exe -r requirements.txt
    .env file with GOOGLE_SHEET_ID; credentials.json (vedi rules/cold_outreach.md)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_auth import GoogleAuthError, get_credentials
from load_env import load_env
from run_state import TMP_DIR, save_step

# Hard stop: mai piu' di 5 righe scritte per run
MAX_ROWS_LIMIT = 5
STATUS_DRAFT = "Bozza - non inviata"
HEADERS = [
    "Data", "Nome", "Cognome", "Ruolo", "Azienda", "Sito",
    "Email lead", "Origine email", "Telefono", "LinkedIn", "Oggetto", "Corpo email", "Stato",
]


def fail(message: str, code: int, **extra) -> None:
    """Print JSON error to stderr and exit with the given code."""
    print(json.dumps({"error": message, **extra}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def pick(lead: dict, *keys: str) -> str:
    """Primo valore non vuoto tra le chiavi candidate (i nomi campo di Apify possono variare)."""
    for k in keys:
        v = lead.get(k)
        if v not in (None, "", [], {}):
            return str(v)
    return ""


def split_name(lead: dict) -> tuple[str, str]:
    first, last = pick(lead, "first_name", "firstName"), pick(lead, "last_name", "lastName")
    if first or last:
        return first, last
    full = pick(lead, "full_name", "name").split()
    return (full[0], " ".join(full[1:])) if full else ("", "")


def clean_title(title: str) -> str:
    """Toglie il suffisso troncato di LinkedIn, es. "CEO at ..." -> "CEO"."""
    return re.sub(r"\s+(at|presso|@)\s+(\.\.\.|…)\s*$", "", title).strip()


def to_row(item: dict, today: str, tag: str | None = None) -> list[str]:
    lead = item["lead"]
    first, last = split_name(lead)
    return [
        today,
        first,
        last,
        clean_title(pick(lead, "job_title", "title", "position")),
        pick(lead, "company_name", "company", "organization_name"),
        pick(lead, "domain", "company_domain", "company_website", "website"),
        pick(lead, "email", "work_email"),
        pick(lead, "email_confidence", "email_status", "email_source"),
        pick(lead, "phone", "phone_number"),
        pick(lead, "linkedin_url", "linkedin", "linkedinUrl"),
        item["subject"],
        item["body"],
        f"{tag} - {STATUS_DRAFT}" if tag else STATUS_DRAFT,
    ]


def open_worksheet(sheet_id: str, worksheet: str | None):
    import gspread

    try:
        client = gspread.authorize(get_credentials())
    except GoogleAuthError as e:
        fail(str(e), 2)
    try:
        spreadsheet = client.open_by_key(sheet_id)
        return spreadsheet.worksheet(worksheet) if worksheet else spreadsheet.sheet1
    except gspread.exceptions.SpreadsheetNotFound:
        fail("Foglio non trovato: controlla GOOGLE_SHEET_ID e che il foglio sia condiviso "
             "con l'email del service account (ruolo Editor)", 2)
    except gspread.exceptions.WorksheetNotFound:
        fail(f"Scheda '{worksheet}' non trovata nel foglio", 1)
    except gspread.exceptions.APIError as e:
        code = 2 if e.response.status_code in (401, 403) else 3
        fail(f"Errore Google Sheets ({e.response.status_code}): {e}", code)


def run(input_file: Path, worksheet: str | None, tag: str | None = None) -> dict:
    """Core logic. Returns a JSON-serializable dict."""
    if not input_file.exists():
        fail(f"{input_file} non trovato. Esegui prima write_emails.py", 1)
    try:
        emails = json.loads(input_file.read_text(encoding="utf-8"))["emails"]
    except (ValueError, KeyError, TypeError) as e:
        fail(f"{input_file.name} non valido: {e}", 1)
    if not emails:
        fail("Nessuna email da scrivere", 4)
    if len(emails) > MAX_ROWS_LIMIT:
        fail(f"Troppe righe ({len(emails)}): hard limit {MAX_ROWS_LIMIT}", 1)

    load_env()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        fail("GOOGLE_SHEET_ID mancante. Aggiungilo al file .env", 2)

    import gspread

    ws = open_worksheet(sheet_id, worksheet)
    try:
        existing = ws.get_all_values()
        if not existing or not any(existing[0]):
            ws.update(range_name="A1", values=[HEADERS])
            existing = [HEADERS]
        email_col = existing[0].index("Email lead") if "Email lead" in existing[0] else HEADERS.index("Email lead")
        known = {r[email_col].strip().lower() for r in existing[1:] if len(r) > email_col and r[email_col].strip()}

        today = datetime.now().strftime("%Y-%m-%d")
        rows, skipped = [], 0
        for item in emails:
            row = to_row(item, today, tag)
            addr = row[HEADERS.index("Email lead")].strip().lower()
            if addr and addr in known:
                skipped += 1
                continue
            rows.append(row)
        if not rows:
            fail("Tutti i lead sono gia' presenti nel foglio", 4, skipped=skipped)
        ws.append_rows(rows, value_input_option="RAW")
    except gspread.exceptions.APIError as e:
        code = 2 if e.response.status_code in (401, 403) else 3
        fail(f"Errore Google Sheets ({e.response.status_code}): {e}", code)

    result = {
        "status": "success",
        "rows_written": len(rows),
        "skipped_duplicates": skipped,
        "sheet_id": sheet_id,
        "worksheet": ws.title,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    save_step("sheet_export", "done", rows_written=len(rows), skipped_duplicates=skipped)
    return result


def main():
    # Su Windows la console usa cp1252: il JSON in output deve essere UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Scrive le email nel Google Sheet (non le invia)")
    parser.add_argument("--input", default=str(TMP_DIR / "emails.json"), help="File emails.json")
    parser.add_argument("--worksheet", help="Nome della scheda (default: la prima)")
    parser.add_argument("--tag", help="Etichetta anteposta allo Stato, es. TEST per le righe di prova")
    args = parser.parse_args()

    print(json.dumps(run(Path(args.input), args.worksheet, args.tag), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
