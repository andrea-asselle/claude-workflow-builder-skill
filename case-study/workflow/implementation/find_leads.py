#!/usr/bin/env python3
"""
Trova i contatti (es. CEO) delle aziende indicate con l'actor Apify themineworks/b2b-leads-finder
e li salva in .tmp/leads.json.

Usage:
    python implementation/find_leads.py --companies "azienda1.it,azienda2.it,azienda3.it"
                                        [--count 3] [--job-titles "CEO,Amministratore Delegato,Founder"]

Exit codes:
    0 - Success
    1 - Invalid input (count o numero aziende fuori range)
    2 - Missing or invalid credentials (APIFY_TOKEN)
    3 - External API error (Apify, anche item di errore restituiti dall'actor)
    4 - Empty result (nessun lead con il ruolo richiesto)

Prerequisites:
    uv pip install --python .venv\\Scripts\\python.exe -r requirements.txt
    .env file with APIFY_TOKEN
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from load_env import load_env
from run_state import TMP_DIR, save_step

# Hard stop: limiti di sicurezza per run
MAX_LEADS_LIMIT = 5
MAX_COMPANIES = 5  # limite dell'actor per run
MAX_JOB_TITLES = 3  # l'actor cerca per nome solo i primi 3 ruoli
DEFAULT_JOB_TITLES = "CEO,Amministratore Delegato,Founder"
# Tetto di spesa passato ad Apify: per questo actor Apify non accetta valori sotto 0,50 $
# (errore max-total-charge-usd-below-minimum)
MAX_APIFY_CHARGE_USD = 0.50
APIFY_ACTOR = "themineworks~b2b-leads-finder"
APIFY_TIMEOUT_SECS = 300
# Prezzi piano Free (README 2026-09-30): 0,005 $/lead; dal 2026-10-13 0,0075 $/lead + 0,005 $ a run.
# Si usano gia' i prezzi piu' alti per stare larghi.
RUN_FEE_USD = 0.005
LEAD_USD = 0.0075
# L'actor restituisce (e addebita) al massimo 25 lead per run: e' il caso peggiore reale
ACTOR_MAX_LEADS_PER_RUN = 25
APIFY_WORST_CASE_USD = round(RUN_FEE_USD + LEAD_USD * ACTOR_MAX_LEADS_PER_RUN, 4)
OUTPUT_FILE = TMP_DIR / "leads.json"


def fail(message: str, code: int, **extra) -> None:
    """Print JSON error to stderr and exit with the given code."""
    print(json.dumps({"error": message, **extra}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def estimate_cost(n_charged: int) -> float:
    return round(RUN_FEE_USD + LEAD_USD * n_charged, 4)


def is_person(item: dict) -> bool:
    """Scarta le righe di report (_type summary/info), gli errori e le caselle generiche (info@)."""
    if item.get("_type") in ("summary", "info"):
        return False
    return bool(item.get("full_name") or item.get("name"))


def run(companies: list[str], count: int, job_titles: list[str]) -> dict:
    """Core logic. Returns a JSON-serializable dict."""
    if not 1 <= count <= MAX_LEADS_LIMIT:
        fail(f"--count deve essere tra 1 e {MAX_LEADS_LIMIT} (hard limit)", 1, count=count)
    if not 1 <= len(companies) <= MAX_COMPANIES:
        fail(f"--companies: da 1 a {MAX_COMPANIES} aziende", 1, companies=companies)
    if not 1 <= len(job_titles) <= MAX_JOB_TITLES:
        fail(f"--job-titles: da 1 a {MAX_JOB_TITLES} ruoli", 1, job_titles=job_titles)

    load_env()
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        fail("APIFY_TOKEN mancante. Aggiungilo al file .env", 2)

    actor_input = {
        "companies": companies,
        "jobTitles": job_titles,
        "maxLeadsPerCompany": max(1, math.ceil(count / len(companies))),
    }

    url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={"timeout": APIFY_TIMEOUT_SECS, "maxTotalChargeUsd": MAX_APIFY_CHARGE_USD},
            json=actor_input,
            timeout=APIFY_TIMEOUT_SECS + 30,
        )
    except requests.RequestException as e:
        fail(f"Errore di rete verso Apify: {e}", 3)

    if resp.status_code in (401, 403):
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        fail(f"Apify ha rifiutato la richiesta ({resp.status_code}): {err.get('message', 'controlla APIFY_TOKEN nel .env')}", 2)
    if resp.status_code >= 400:
        fail(f"Apify ha risposto {resp.status_code}", 3, body=resp.text[:500])

    try:
        items = resp.json()
    except ValueError:
        fail("Risposta Apify non e' JSON", 3, body=resp.text[:300])

    items = [i for i in items if isinstance(i, dict)]
    # Alcuni actor rispondono 200 con un item {"error": ...} invece di un lead
    error_items = [i for i in items if i.get("error") and not is_person(i)]
    if error_items:
        fail(f"L'actor ha restituito un errore: {error_items[0]['error']}", 3)

    people = [i for i in items if is_person(i)]
    # Si tengono solo i lead col ruolo richiesto; l'actor puo' restituirne piu' del necessario
    matching = [i for i in people if i.get("title_match")]
    leads = matching[:count]
    if not leads:
        fail("Nessun lead con il ruolo richiesto per le aziende indicate.", 4, input=actor_input,
             discarded_other_roles=len(people),
             report=[i for i in items if i.get("_type") in ("summary", "info")][:2])

    charged = sum(1 for i in people if i.get("charged", True))
    result = {
        "status": "success",
        "count": len(leads),
        "returned_by_actor": len(people),
        "discarded_other_roles": len(people) - len(matching),
        "apify_cost_usd": estimate_cost(charged),
        "apify_max_charge_usd": APIFY_WORST_CASE_USD,
        "search": actor_input,
        "leads": leads,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    TMP_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    save_step("find_leads", "done", leads=len(leads), apify_cost_usd=result["apify_cost_usd"])
    return result


def main():
    # Su Windows la console usa cp1252: il JSON in output deve essere UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Trova i contatti delle aziende indicate via Apify")
    parser.add_argument("--companies", required=True,
                        help=f"Siti delle aziende separati da virgola (max {MAX_COMPANIES})")
    parser.add_argument("--count", type=int, default=3, help=f"Numero di lead (1-{MAX_LEADS_LIMIT})")
    parser.add_argument("--job-titles", default=DEFAULT_JOB_TITLES,
                        help=f"Ruoli separati da virgola, max {MAX_JOB_TITLES} (default {DEFAULT_JOB_TITLES})")
    args = parser.parse_args()

    companies = [c.strip() for c in args.companies.split(",") if c.strip()]
    job_titles = [j.strip() for j in args.job_titles.split(",") if j.strip()]
    result = run(companies, args.count, job_titles)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
