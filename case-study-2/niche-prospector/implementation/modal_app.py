#!/usr/bin/env python3
"""
Giro automatico del cold outreach su Modal: ogni lunedi' alle 8:00 (Europe/Rome) esegue pipeline.py.
Le email NON vengono mai inviate: finiscono nel Google Sheet come "Bozza - non inviata".

Usage:
    modal deploy implementation/modal_app.py                 # deploy SENZA orario (trigger spento, default)
    OUTREACH_SCHEDULE=on modal deploy implementation/modal_app.py      # accensione esplicita del lunedi'
    (PowerShell: $env:OUTREACH_SCHEDULE="on"; modal deploy implementation/modal_app.py; Remove-Item Env:OUTREACH_SCHEDULE)
    Prova del trigger: anche OUTREACH_CRON="<min> <ora> * * *" e OUTREACH_RUN_ID_SUFFIX="trigger" al deploy,
    poi un deploy normale per spegnere tutto
    modal run implementation/modal_app.py [--tag TEST] [--dry-run] [--reuse-leads] [--run-id ID]
                                          [--offer "..."] [--sender "..."] [--region-index N] [--terms-index N]
        (giro manuale nel cloud; --reuse-leads invia .tmp/leads.json locale, gia' pagato;
         --offer/--sender solo per le prove, il cron usa il Secret)

Exit codes (modal run):
    0 - Success
    1-4 - come pipeline.py (il dettaglio e' nella scheda Log del foglio)

Prerequisites:
    pip: modal (nel .venv); login Modal gia' fatto (modal profile current)
    Modal Secret "rbi-outreach-unico": python implementation/modal_secrets.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
REMOTE_DIR = "/root/project/implementation"
APP_NAME = "rbi-outreach-unico"
SECRET_NAME = "rbi-outreach-unico"
CRON = os.environ.get("OUTREACH_CRON", "0 8 * * 1")  # OUTREACH_CRON solo per la prova del trigger
TIMEZONE = "Europe/Rome"
# Il trigger si accende solo con OUTREACH_SCHEDULE=on al momento del deploy, mai per un deploy normale
SCHEDULE_ON = modal.is_local() and os.environ.get("OUTREACH_SCHEDULE") == "on"
# Solo per la prova del trigger: suffisso del run id del cron (es. "trigger" -> 2026-W42-trigger), cosi'
# la prova non usa il run id della settimana. Si passa al deploy e finisce nell'immagine; un deploy normale non lo ha.
RUN_ID_SUFFIX = os.environ.get("OUTREACH_RUN_ID_SUFFIX", "")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .uv_pip_install("anthropic==1.13.0", "requests==2.34.2", "gspread==6.2.1", "google-auth==2.61.0",
                    "google-auth-oauthlib==1.5.0")
    .env({"OUTREACH_RUN_ID_SUFFIX": RUN_ID_SUFFIX})
    .add_local_dir(HERE, REMOTE_DIR, ignore=["__pycache__", "test_*.py", "modal_*.py"])
)
app = modal.App(APP_NAME)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    schedule=modal.Cron(CRON, timezone=TIMEZONE) if SCHEDULE_ON else None,
    max_containers=1,  # mai due giri insieme
    retries=0,  # nessun nuovo tentativo automatico: rispenderebbe; l'esito e' nel Log
    timeout=1800,  # 4 actor Apify in sequenza, ognuno fino a 5 minuti
)
def weekly_run(tag: str = "", dry_run: bool = False, run_id: str = "", leads_json: str = "",
               trigger: str = "cron", offer: str = "", sender: str = "", region_index: int = -1,
               terms_index: int = -1) -> dict:
    """Il cron la chiama senza argomenti: offerta e mittente arrivano dal Secret (OUTREACH_OFFER/SENDER)."""
    # Il JSON del service account arriva dal Secret: va scritto su file per google_auth
    creds = os.environ.pop("GOOGLE_CREDENTIALS_JSON", "")
    if creds:
        Path("/tmp/credentials.json").write_text(creds, encoding="utf-8")
        os.environ["GOOGLE_CREDENTIALS_FILE"] = "/tmp/credentials.json"
    sys.path.insert(0, REMOTE_DIR)
    import pipeline

    if trigger == "cron" and not run_id and RUN_ID_SUFFIX:
        today = pipeline.datetime.now(pipeline.timezone.utc).date()
        run_id = f"{pipeline.default_run_id(today, None)}-{RUN_ID_SUFFIX}"
    code, summary = pipeline.run(tag=tag or None, dry_run=dry_run, run_id=run_id or None,
                                 leads_data=json.loads(leads_json) if leads_json else None, trigger=trigger,
                                 offer=offer or None, sender=sender or None,
                                 region_index=region_index if region_index >= 0 else None,
                                 terms_index=terms_index if terms_index >= 0 else None)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


@app.local_entrypoint()
def main(tag: str = "", dry_run: bool = False, reuse_leads: bool = False, run_id: str = "",
         offer: str = "", sender: str = "", region_index: int = -1, terms_index: int = -1):
    leads_json = ""
    if reuse_leads:
        leads_json = (HERE.parent / ".tmp" / "leads.json").read_text(encoding="utf-8")
    summary = weekly_run.remote(tag=tag, dry_run=dry_run, run_id=run_id, leads_json=leads_json,
                                trigger="manuale (cloud)", offer=offer, sender=sender, region_index=region_index,
                                terms_index=terms_index)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if summary.get("exit_code"):
        sys.exit(summary["exit_code"])
