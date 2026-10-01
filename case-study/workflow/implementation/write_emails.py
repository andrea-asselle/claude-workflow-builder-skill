#!/usr/bin/env python3
"""
Scrive per ogni lead di .tmp/leads.json un'email di cold outreach in italiano con Claude
e salva il risultato in .tmp/emails.json. Le email NON vengono inviate.

Usage:
    python implementation/write_emails.py --offer "cosa proponi" --sender "Nome Cognome"
                                          [--input .tmp/leads.json]

Exit codes:
    0 - Success (tutte le email scritte)
    1 - Invalid input (leads.json mancante/invalido, argomenti)
    2 - Missing or invalid credentials (ANTHROPIC_API_KEY)
    3 - External API error (Claude, nessuna email prodotta)
    4 - Partial/empty result (budget esaurito o alcune email fallite; le riuscite sono salvate)

Prerequisites:
    uv pip install --python .venv\\Scripts\\python.exe -r requirements.txt
    .env file with ANTHROPIC_API_KEY
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
from load_env import load_env
from run_state import TMP_DIR, save_step

# Hard stop: limiti di sicurezza per run
MAX_LEADS_LIMIT = 5
MAX_BUDGET_USD = 0.50  # tetto totale per esecuzione (Apify + Claude)
MODEL = "claude-haiku-4-5-20251001"
# Prezzi USD per token di Haiku 4.5 ($1 / $5 per milione)
PRICE_IN = 1.0 / 1_000_000
PRICE_OUT = 5.0 / 1_000_000
MAX_OUTPUT_TOKENS = 700
MAX_FIELD_CHARS = 400

SYSTEM_PROMPT = (
    "Sei un copywriter B2B italiano. Scrivi email di primo contatto (cold outreach) brevi, "
    "professionali e umane, in italiano, con il 'Lei' formale.\n"
    "Regole:\n"
    "- Italiano corretto e naturale, senza anglicismi (niente 'fit', 'call', 'business').\n"
    "- Saluto formale: 'Gentile <Nome Cognome>,'. Pronomi di cortesia con la maiuscola (Lei, Le, Suo).\n"
    "- Massimo 120 parole nel corpo, un solo invito all'azione (una breve chiamata di 15 minuti).\n"
    "- Personalizza usando SOLO i dati forniti sul destinatario e sulla sua azienda. "
    "Non inventare fatti, numeri, notizie o progetti che non sono nei dati.\n"
    "- Se un dato manca, non citarlo.\n"
    "- Niente promesse esagerate, niente frasi da spam, niente emoji.\n"
    "- Chiudi con il nome del mittente.\n"
    'Rispondi SOLO con un oggetto JSON: {"subject": "...", "body": "..."}'
)


def fail(message: str, code: int, **extra) -> None:
    """Print JSON error to stderr and exit with the given code."""
    print(json.dumps({"error": message, **extra}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def compact_lead(lead: dict) -> dict:
    """Tiene solo i campi con valore e tronca quelli lunghi (meno token = meno costo)."""
    out = {}
    for k, v in lead.items():
        if v in (None, "", [], {}):
            continue
        out[k] = v[:MAX_FIELD_CHARS] if isinstance(v, str) else v
    return out


def parse_email_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("nessun JSON nella risposta")
    data = json.loads(match.group(0))
    subject, body = str(data.get("subject", "")).strip(), str(data.get("body", "")).strip()
    if not subject or not body:
        raise ValueError("subject o body vuoti")
    return {"subject": subject, "body": body}


def call_cost(usage) -> float:
    return usage.input_tokens * PRICE_IN + usage.output_tokens * PRICE_OUT


def run(input_file: Path, offer: str, sender: str) -> dict:
    """Core logic. Returns a JSON-serializable dict."""
    if not input_file.exists():
        fail(f"{input_file} non trovato. Esegui prima find_leads.py", 1)
    try:
        data = json.loads(input_file.read_text(encoding="utf-8"))
        leads = data["leads"]
        # Caso peggiore: il tetto di spesa Apify, se piu' alto della stima
        apify_cost = max(float(data.get("apify_cost_usd", 0)), float(data.get("apify_max_charge_usd", 0)))
    except (ValueError, KeyError, TypeError) as e:
        fail(f"{input_file.name} non valido: {e}", 1)
    if not leads:
        fail("Nessun lead in input", 4)
    if len(leads) > MAX_LEADS_LIMIT:
        fail(f"Troppi lead ({len(leads)}): hard limit {MAX_LEADS_LIMIT}", 1)

    load_env()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        fail("ANTHROPIC_API_KEY mancante. Aggiungila al file .env", 2)

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    spent = apify_cost
    emails, errors = [], []
    stopped_for_budget = False

    for lead in leads:
        prompt = (
            f"Mittente: {sender}\nCosa proponiamo: {offer}\n\n"
            f"Dati del destinatario (JSON):\n{json.dumps(compact_lead(lead), ensure_ascii=False)}"
        )
        # Stima prudente del costo massimo di questa chiamata prima di farla
        worst_case = (len(SYSTEM_PROMPT + prompt) / 3) * PRICE_IN + MAX_OUTPUT_TOKENS * PRICE_OUT
        if spent + worst_case > MAX_BUDGET_USD:
            stopped_for_budget = True
            break
        try:
            msg = client.messages.create(
                model=MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError:
            fail("ANTHROPIC_API_KEY rifiutata da Anthropic. Controlla la chiave nel .env", 2)
        except anthropic.APIError as e:
            errors.append({"lead": lead.get("email") or lead.get("full_name"), "error": f"API: {e}"})
            continue
        spent += call_cost(msg.usage)
        try:
            email = parse_email_json(msg.content[0].text)
        except (ValueError, IndexError) as e:
            errors.append({"lead": lead.get("email") or lead.get("full_name"), "error": f"risposta non valida: {e}"})
            continue
        emails.append({"lead": lead, **email})

    result = {
        "status": "success" if not errors and not stopped_for_budget else "partial",
        "count": len(emails),
        "errors": errors,
        "stopped_for_budget": stopped_for_budget,
        "total_cost_usd": round(spent, 4),
        "budget_usd": MAX_BUDGET_USD,
        "model": MODEL,
        "emails": emails,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not emails:
        fail("Nessuna email prodotta", 3, errors=errors)
    TMP_DIR.mkdir(exist_ok=True)
    (TMP_DIR / "emails.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    save_step("write_emails", "done" if result["status"] == "success" else "partial",
              emails=len(emails), total_cost_usd=result["total_cost_usd"])
    return result


def main():
    # Su Windows la console usa cp1252: il JSON in output deve essere UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Scrive email di cold outreach con Claude (non le invia)")
    parser.add_argument("--offer", required=True, help="Cosa proponi ai lead (1-2 frasi)")
    parser.add_argument("--sender", required=True, help="Nome e cognome del mittente")
    parser.add_argument("--input", default=str(TMP_DIR / "leads.json"), help="File leads.json")
    args = parser.parse_args()

    result = run(Path(args.input), args.offer, args.sender)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] == "partial":
        sys.exit(4)


if __name__ == "__main__":
    main()
