#!/usr/bin/env python3
"""
Schede di servizio del Google Sheet:
    "Log outreach"  una riga per ogni giro del workflow (anche se vuoto o fallito); e' anche lo stato
                    persistente del giro automatico: spesa del mese e giri gia' eseguiti.
    "Aziende viste" una riga per ogni azienda gia' controllata su LinkedIn (v5): non si ripaga.

Usage:
    from run_log import open_spreadsheet, log_worksheet, append_log, month_spend, run_already_done
    from run_log import seen_worksheet, seen_slugs, append_seen
    python implementation/run_log.py            # stampa le ultime righe del Log (sola lettura)

Exit codes:
    0 - Success
    2 - Missing or invalid credentials (credentials.json, GOOGLE_SHEET_ID, foglio non condiviso)
    3 - External API error (Google Sheets)

Prerequisites:
    .env file with GOOGLE_SHEET_ID; credentials.json (vedi rules/cold_outreach.md)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_auth import GoogleAuthError, get_credentials
from load_env import load_env

# Scheda dedicata: nel foglio esiste gia' una scheda "Log" della vecchia automazione (rbi-outreach-auto)
# con colonne diverse; scriverci per posizione mescolerebbe i dati (errore visto il 2026-10-12)
LOG_TITLE = "Log outreach"
LOG_HEADERS = [
    "Data", "Run id", "Avvio", "Esito", "Regione", "Lead da Apify", "Lead tenuti", "Scarti",
    "Email scritte", "Email scartate", "Righe scritte", "Costo Apify $", "Costo Claude $", "Costo totale $",
    "Dettagli",
    # v5 (unione con RBI_Auto_Test): colonne aggiunte in coda, la scheda esistente si aggiorna da sola
    "Parole chiave", "Aziende trovate", "Aziende valide", "Lead da LinkedIn",
]
# Aziende gia' controllate su LinkedIn: i giri successivi le saltano prima di pagare di nuovo
SEEN_TITLE = "Aziende viste"
SEEN_HEADERS = ["Data", "Run id", "Slug LinkedIn", "Azienda", "Sito", "Esito"]
# Esiti che contano come "giro gia' fatto": un secondo giro con lo stesso run id non deve rispendere
DONE_OUTCOMES = {"ok", "parziale", "vuoto"}
MAX_CELL_CHARS = 2000


class SheetError(Exception):
    """Errore Google Sheets; code = exit code (2 credenziali/permessi, 3 API)."""

    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


def open_spreadsheet():
    import gspread

    load_env()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        raise SheetError("GOOGLE_SHEET_ID mancante. Aggiungilo al file .env", 2)
    try:
        return gspread.authorize(get_credentials()).open_by_key(sheet_id)
    except GoogleAuthError as e:
        raise SheetError(str(e), 2)
    except gspread.exceptions.SpreadsheetNotFound:
        raise SheetError("Foglio non trovato: controlla GOOGLE_SHEET_ID e la condivisione col service account", 2)
    except gspread.exceptions.APIError as e:
        raise SheetError(f"Errore Google Sheets ({e.response.status_code}): {e}",
                         2 if e.response.status_code in (401, 403) else 3)


def _worksheet(spreadsheet, title: str, headers: list[str]):
    """Scheda con l'intestazione attesa, creata se manca. Colonne nuove in coda: aggiunte.
    Colonne diverse: errore, mai scritture."""
    import gspread

    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=200, cols=len(headers))
        ws.update(range_name="A1", values=[headers])
        return ws
    header = [h for h in ws.row_values(1) if h]
    if header == headers:
        return ws
    if header and header != headers[:len(header)]:
        raise SheetError(f"La scheda '{title}' ha colonne diverse da quelle attese: {header[:5]}...", 1)
    if ws.col_count < len(headers):
        ws.add_cols(len(headers) - ws.col_count)
    ws.update(range_name="A1", values=[headers])
    return ws


def log_worksheet(spreadsheet):
    """Scheda Log, creata con l'intestazione se manca."""
    return _worksheet(spreadsheet, LOG_TITLE, LOG_HEADERS)


def seen_worksheet(spreadsheet):
    """Scheda delle aziende gia' controllate, creata se manca."""
    return _worksheet(spreadsheet, SEEN_TITLE, SEEN_HEADERS)


def _rows(values: list[list[str]]) -> list[dict]:
    if not values:
        return []
    header = values[0]
    return [dict(zip(header, r)) for r in values[1:]]


def _num(value: str) -> float:
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return 0.0


def month_spend(values: list[list[str]], month: str) -> float:
    """Somma dei costi totali registrati nel mese 'YYYY-MM'."""
    return round(sum(_num(r.get("Costo totale $", "")) for r in _rows(values)
                     if r.get("Data", "").startswith(month)), 4)


def run_already_done(values: list[list[str]], run_id: str) -> bool:
    """True se il run id ha gia' un giro concluso o che ha speso."""
    return any(r.get("Run id") == run_id and (r.get("Esito") in DONE_OUTCOMES or _num(r.get("Costo totale $", "")) > 0)
               for r in _rows(values))


def seen_slugs(values: list[list[str]]) -> set[str]:
    """Slug LinkedIn gia' controllati nei giri precedenti."""
    return {r.get("Slug LinkedIn", "").strip().lower() for r in _rows(values) if r.get("Slug LinkedIn", "").strip()}


def append_seen(ws, rows: list[dict]) -> None:
    """Una riga per azienda controllata; le chiavi sono le intestazioni di SEEN_HEADERS."""
    if rows:
        ws.append_rows([[str(r.get(h, ""))[:MAX_CELL_CHARS] for h in SEEN_HEADERS] for r in rows],
                       value_input_option="RAW")


def append_log(ws, entry: dict) -> None:
    """Aggiunge una riga; le chiavi di entry sono le intestazioni di LOG_HEADERS."""
    row = []
    for h in LOG_HEADERS:
        v = entry.get(h, "")
        v = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)
        row.append(v[:MAX_CELL_CHARS])
    ws.append_rows([row], value_input_option="RAW")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        values = log_worksheet(open_spreadsheet()).get_all_values()
    except SheetError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(e.code)
    print(json.dumps({"status": "success", "rows": _rows(values)[-10:],
                      "timestamp": datetime.now(timezone.utc).isoformat()}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
