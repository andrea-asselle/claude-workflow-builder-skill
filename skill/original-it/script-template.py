#!/usr/bin/env python3
"""
<Una riga: cosa fa questo script (una sola responsabilita').>

Usage:
    python implementation/<nome_script>.py --input-file .tmp/<input>.json [--dry-run]

Exit codes:
    0 - Success
    1 - Invalid input (missing args, bad JSON)
    2 - Missing or invalid credentials
    3 - External API error or unexpected response shape
    4 - Empty or partial result

Prerequisites:
    Dipendenze in requirements.txt (installate con l'interprete del progetto)
    .env file with <VARIABILE>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add implementation/ to path for local imports
sys.path.insert(0, str(Path(__file__).parent))
from load_env import load_env

# Hard stop: limiti di sicurezza per run
MAX_ITEMS_LIMIT = 10
MAX_COST_USD = 0.50
TIMEOUT_SECS = 30
MAX_RETRIES = 3


def fail(message: str, code: int, **extra) -> None:
    """Print JSON error to stderr and exit with the given code."""
    print(json.dumps({"error": message, **extra}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def call_with_retry(func, *args, **kwargs):
    """Ritenta solo errori temporanei, con attesa crescente (1s, 2s, 4s)."""
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, timeout=TIMEOUT_SECS, **kwargs)
        except TimeoutError:  # sostituire con gli errori temporanei del client (429, 5xx)
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt)


def is_valid_item(item: dict) -> bool:
    """Controlla la forma della risposta: un errore non deve diventare un dato."""
    return isinstance(item, dict) and "<campo_obbligatorio>" in item


def process(item: dict, done_keys: set, dry_run: bool) -> dict:
    """Elabora un elemento e ne restituisce l'esito."""
    key = item.get("<chiave_univoca>")
    if key in done_keys:
        return {"input": key, "status": "skipped", "reason": "gia' elaborato"}
    if dry_run:
        return {"input": key, "status": "dry_run"}

    try:
        result = ...  # call_with_retry(client.metodo, ...)
    except Exception as e:
        return {"input": key, "status": "failed", "reason": str(e)}

    if not is_valid_item(result):
        return {"input": key, "status": "failed", "reason": "risposta con forma inattesa"}
    return {"input": key, "status": "ok", "result": result}


def run(items: list[dict], dry_run: bool) -> dict:
    """Core logic. Returns a JSON-serializable dict."""
    load_env()

    secret = os.environ.get("<VARIABILE>", "").strip()
    if not secret:
        fail("<VARIABILE> mancante. Aggiungila al file .env", 2)

    if not items:
        fail("Nessun elemento in input", 4)
    if len(items) > MAX_ITEMS_LIMIT:
        fail(f"HARD STOP: {len(items)} elementi, limite {MAX_ITEMS_LIMIT}", 1)

    done_keys: set = set()  # leggere da .tmp/ o dalla destinazione per evitare duplicati
    outcomes = [process(item, done_keys, dry_run) for item in items]

    return {
        "status": "success",
        "dry_run": dry_run,
        "ok": sum(o["status"] == "ok" for o in outcomes),
        "skipped_duplicates": sum(o["status"] == "skipped" for o in outcomes),
        "failed": sum(o["status"] == "failed" for o in outcomes),
        "items": outcomes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    # Su Windows la console usa cp1252: l'output JSON deve essere UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="<descrizione>")
    parser.add_argument("--input-file", required=True, help="JSON con gli elementi da elaborare")
    parser.add_argument("--dry-run", action="store_true", help="Mostra cosa farebbe senza effetti esterni")
    args = parser.parse_args()

    try:
        items = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        fail(f"Input non leggibile: {e}", 1)

    result = run(items, args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Parziale: alcuni elementi falliti
    if result["failed"] and result["ok"]:
        sys.exit(4)
    if result["failed"] and not result["ok"]:
        sys.exit(3)


if __name__ == "__main__":
    main()
