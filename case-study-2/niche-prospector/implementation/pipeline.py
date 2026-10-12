#!/usr/bin/env python3
"""
Orchestratore del cold outreach (v5, unione di RBI_V3_Test e RBI_Auto_Test):
    1. aziende:  discover_companies (Google -> LinkedIn) con parole chiave e regione della settimana,
                 saltando le aziende gia' viste (scheda "Aziende viste") e quelle gia' nel foglio
    2. persone:  find_leads (code_crafter, seconda linea, solo i siti trovati); per le aziende fino a 50
                 dipendenti ancora scoperte, il titolare (find_leads); per le altre scoperte,
                 find_people_linkedin; un contatto per azienda
    3. email:    write_emails (schema fisso + controlli di qualita')
    4. foglio:   sheet_export (mai invio)
Scrive SEMPRE una riga nella scheda Log del foglio. Usato dal giro automatico del lunedi' (modal_app.py)
e lanciabile a mano.

Usage:
    python implementation/pipeline.py [--count 5] [--region-index N] [--terms-index N] [--run-id 2026-W42]
                                      [--tag TEST] [--dry-run] [--reuse-leads]
                                      [--offer "..."] [--sender "Nome Cognome"]
    --dry-run      non scrive righe nel foglio dei lead (il Log si', con esito "prova")
    --reuse-leads  usa .tmp/leads.json gia' pagato invece di chiamare Apify
    --tag TEST     righe con Stato "TEST - Bozza - non inviata"; run id di prova separato

Exit codes:
    0 - Success (giro completo)
    1 - Invalid input / configurazione (OUTREACH_OFFER o OUTREACH_SENDER mancanti)
    2 - Missing or invalid credentials (Apify, Anthropic, Google)
    3 - External API error, o errore imprevisto
    4 - Giro vuoto, parziale o saltato (gia' eseguito, tetto mensile)

Prerequisites:
    .env (o Modal Secret) con APIFY_TOKEN, ANTHROPIC_API_KEY, GOOGLE_SHEET_ID, OUTREACH_OFFER, OUTREACH_SENDER;
    credentials.json (o GOOGLE_CREDENTIALS_JSON nel Secret)
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import discover_companies
import find_leads
import find_people_linkedin
import run_log
import sheet_export
import write_emails
from load_env import load_env
from run_state import TMP_DIR

# Hard stop: limiti per giro e per mese
MAX_LEADS_PER_RUN = 5
RUN_BUDGET_USD = write_emails.MAX_BUDGET_USD  # 0,50 $ (Apify + Claude), controllato in write_emails
MONTHLY_CAP_USD = 2.50  # 5 lunedi' x 0,50 $: oltre, il giro viene saltato prima di spendere
# Aziende controllate su LinkedIn per giro (0,004 $ l'una); spesa Apify massima del giro ~0,25 $:
# Google 4 pagine 0,011 + LinkedIn aziende 0,04 + code_crafter 0,04 + LinkedIn persone 0,14
MAX_COMPANIES_PER_RUN = 10
# Ruoli per la ricerca persone: seconda linea (decisione dell'utente, 2026-10-12)
JOB_TITLES = find_leads.DEFAULT_JOB_TITLES.split(",")
# Nelle aziende fino a 50 dipendenti la seconda linea spesso non esiste: se non si trova, si accetta il
# titolare (decisione dell'utente, 2026-10-12; giro reale: 0 contatti in tutte le aziende 2-50)
OWNER_OK_MAX_EMPLOYEES = 50
OWNER_TITLES = find_leads.DEFAULT_EXCLUDE_TITLES.split(",")
# Parole chiave scelte dall'utente, a coppie: una coppia a settimana, insieme alla regione.
# 4 coppie x 17 regioni: la stessa combinazione torna dopo 68 settimane.
TERM_PAIRS = [discover_companies.DEFAULT_TERMS[i:i + 2] for i in range(0, len(discover_companies.DEFAULT_TERMS), 2)]

# Rotazione settimanale (decisione dell'utente, 2026-10-12): una regione a settimana.
# Ogni voce: nome leggibile + alias accettati dall'actor (verificati nello schema il 2026-10-12).
ROTATION_START = date(2026, 10, 12)  # lunedi' della settimana 0 = Lombardia
REGIONS = [
    ("Lombardia", ["lombardy, italy", "lombardia, italy"]),
    ("Lazio", ["lazio, italy"]),
    ("Veneto", ["veneto, italy"]),
    ("Emilia-Romagna", ["emilia-romagna, italy"]),
    ("Piemonte", ["piedmont, italy", "piemonte, italy"]),
    ("Toscana", ["tuscany, italy", "toscana, italy"]),
    ("Campania", ["campania, italy"]),
    ("Puglia", ["apulia, italy", "puglia, italy"]),
    ("Friuli-Venezia Giulia", ["friuli-venezia giulia, italy"]),
    ("Trentino-Alto Adige", ["trentino-alto adige/south tyrol, italy", "trentino-alto adige, italy"]),
    ("Marche", ["marche, italy"]),
    ("Liguria", ["liguria, italy"]),
    ("Sicilia", ["sicily, italy", "sicilia, italy"]),
    ("Abruzzo", ["abruzzo, italy"]),
    ("Umbria", ["umbria, italy"]),
    ("Sardegna", ["sardinia, italy", "sardegna, italy"]),
    ("Calabria", ["calabria, italy"]),
]


def week_index(today: date) -> int:
    return (today - ROTATION_START).days // 7


def region_for(today: date, index: int | None = None) -> tuple[str, list[str]]:
    i = week_index(today) if index is None else index
    return REGIONS[i % len(REGIONS)]


def terms_for(today: date, index: int | None = None) -> list[str]:
    i = week_index(today) if index is None else index
    return TERM_PAIRS[i % len(TERM_PAIRS)]


def default_run_id(today: date, tag: str | None) -> str:
    """Un giro per settimana ISO; i giri di prova hanno un id a parte e non bloccano quello vero."""
    year, week, _ = today.isocalendar()
    rid = f"{year}-W{week:02d}"
    return f"{tag}-{rid}-{datetime.now(timezone.utc):%H%M%S}" if tag else rid


def call_step(fn, *args, **kwargs) -> tuple[int, dict]:
    """Esegue uno script in-process: intercetta sys.exit e l'errore JSON su stderr invece di fermarsi."""
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            return 0, fn(*args, **kwargs)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        lines = [ln for ln in err.getvalue().strip().splitlines() if ln.strip()]
        try:
            detail = json.loads(lines[-1])
        except (IndexError, ValueError):
            detail = {"error": err.getvalue()[-500:] or f"uscita {code}"}
        return code, detail
    except Exception as e:  # errore imprevisto: va comunque nel Log
        return 3, {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]}


def summarize_discards(discarded: list[dict]) -> str:
    """'ruolo diverso x3; titolare o socio x1' (motivo senza il dettaglio dopo i due punti)."""
    counts: dict[str, int] = {}
    for d in discarded:
        key = d.get("reason", "?").split(":")[0]
        counts[key] = counts.get(key, 0) + 1
    return "; ".join(f"{k} x{v}" for k, v in counts.items())


def is_small(company: dict) -> bool:
    """Fascia LinkedIn dei dipendenti entro OWNER_OK_MAX_EMPLOYEES; dimensione sconosciuta = non piccola."""
    end = (company.get("employee_range") or {}).get("end")
    return isinstance(end, int) and end <= OWNER_OK_MAX_EMPLOYEES


def company_outcome(company: dict, leads: list[dict]) -> str:
    lead = next((l for l in leads if find_leads.domain_of(l.get("company_domain") or l.get("company_website"))
                 == company.get("domain")), None)
    if not lead:
        return "nessun contatto"
    return f"contatto: {lead.get('job_title')} ({lead.get('source') or 'code_crafter'})"


def collect_leads(count: int, region: str, terms: list[str], known_emails: set[str], known_domains: set[str],
                  seen: set[str]) -> tuple[int, dict]:
    """Step 1-2: aziende -> persone. Ritorna (codice, dati); codice 0 se c'e' almeno un lead.

    I dati contengono sempre il costo speso e le aziende controllate (anche se il giro e' vuoto o fallito).
    """
    out: dict = {"apify_cost_usd": 0.0, "leads": [], "discarded": [], "checked": [], "errors": {}}
    code, disc = call_step(discover_companies.run, terms, MAX_COMPANIES_PER_RUN, seen, place=region,
                           known_domains=known_domains)
    out["apify_cost_usd"] += float(disc.get("cost_usd", 0))
    out["slugs_found"] = disc.get("slugs_found", "")
    companies = disc.get("companies", []) if code == 0 else []
    out["companies"] = companies
    out["discarded"] += disc.get("discarded", [])
    out["checked"] = ([{**c, "esito": f"scartata: {c['reason']}"} for c in disc.get("discarded", [])]
                      + [dict(c) for c in companies])
    if code:
        out["errors"]["discover_companies"] = disc.get("error")
        return code, out

    # Persone: prima code_crafter sui siti trovati (economico), poi LinkedIn per le aziende scoperte
    code, found = call_step(find_leads.run, count, JOB_TITLES, find_leads.DEFAULT_LOCATION,
                            domains=[c["domain"] for c in companies], known_emails=known_emails,
                            known_domains=known_domains)
    out["apify_cost_usd"] += float(found.get("apify_cost_usd", 0))
    out["returned_by_actor"] = found.get("returned_by_actor", 0)
    out["discarded"] += found.get("discarded", [])
    if code not in (0, 4):
        out["errors"]["find_leads"] = found.get("error")
    leads = list(found.get("leads", [])) if code == 0 else []

    def uncovered() -> list[dict]:
        covered = {find_leads.domain_of(l.get("company_domain") or l.get("company_website")) for l in leads}
        return [c for c in companies if c["domain"] not in covered]

    # Piccole aziende senza seconda linea: il titolare, solo dopo aver cercato la seconda linea
    small = [c for c in uncovered() if is_small(c)]
    if len(leads) < count and small:
        code_ow, ow = call_step(find_leads.run, min(count - len(leads), find_leads.MAX_LEADS_LIMIT), OWNER_TITLES,
                                find_leads.DEFAULT_LOCATION, domains=[c["domain"] for c in small],
                                exclude_titles=[], known_emails=known_emails, known_domains=known_domains)
        out["apify_cost_usd"] += float(ow.get("apify_cost_usd", 0))
        out["owners_returned"] = ow.get("returned_by_actor", 0)
        out["discarded"] += ow.get("discarded", [])
        if code_ow not in (0, 4):
            out["errors"]["find_leads_titolari"] = ow.get("error")
        leads += ow.get("leads", []) if code_ow == 0 else []

    missing = uncovered()
    if len(leads) < count and missing:
        code_li, li = call_step(find_people_linkedin.run, missing, JOB_TITLES, known_emails=known_emails)
        out["apify_cost_usd"] += float(li.get("apify_cost_usd", 0))
        out["linkedin_returned"] = li.get("returned_by_actor", 0)
        out["discarded"] += li.get("discarded", [])
        if code_li not in (0, 4):
            out["errors"]["find_people_linkedin"] = li.get("error")
        leads += li.get("leads", []) if code_li == 0 else []
        if not leads and code_li not in (0, 4):
            code = code_li
    out["leads"] = leads[:count]
    out["apify_cost_usd"] = round(out["apify_cost_usd"], 4)
    for c in out["checked"]:
        c.setdefault("esito", company_outcome(c, out["leads"]))
    if out["leads"]:
        return 0, out
    return (code if code not in (0, 4) else 4), out


def run(count: int = MAX_LEADS_PER_RUN, region_index: int | None = None, run_id: str | None = None,
        tag: str | None = None, dry_run: bool = False, reuse_leads: bool = False,
        offer: str | None = None, sender: str | None = None, trigger: str = "manuale",
        leads_data: dict | None = None, today: date | None = None,
        terms_index: int | None = None) -> tuple[int, dict]:
    """Core logic. Ritorna (exit code, riepilogo). Scrive sempre una riga di Log, salvo errori del foglio."""
    today = today or datetime.now(timezone.utc).date()
    region, _ = region_for(today, region_index)
    terms = terms_for(today, terms_index)
    run_id = run_id or default_run_id(today, tag)
    entry = {"Data": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "Run id": run_id,
             "Avvio": trigger, "Regione": region, "Parole chiave": ", ".join(terms),
             "Costo Apify $": 0, "Costo Claude $": 0, "Costo totale $": 0}
    details: dict = {"tag": tag, "dry_run": dry_run, "reuse_leads": reuse_leads}

    def finish(code: int, outcome: str, ws=None) -> tuple[int, dict]:
        entry["Esito"] = "prova" if dry_run and code == 0 else outcome
        entry["Costo totale $"] = round(float(entry["Costo Apify $"]) + float(entry["Costo Claude $"]), 4)
        entry["Dettagli"] = details
        if ws is not None:
            try:
                run_log.append_log(ws, entry)
            except Exception as e:  # il Log non scritto va segnalato, non nascosto
                details["log_error"] = f"{type(e).__name__}: {e}"
                code = code or 3
        return code, {"status": "success" if code == 0 else entry["Esito"], "exit_code": code, **entry,
                      "timestamp": datetime.now(timezone.utc).isoformat()}

    if not 1 <= count <= MAX_LEADS_PER_RUN:
        details["error"] = f"count deve essere tra 1 e {MAX_LEADS_PER_RUN}"
        return finish(1, "errore")

    load_env()
    # Foglio e Log per primi: senza di loro non si spende nulla (non si saprebbe cosa e' gia' stato fatto)
    try:
        spreadsheet = run_log.open_spreadsheet()
        log_ws = run_log.log_worksheet(spreadsheet)
        log_values = log_ws.get_all_values()
        seen_ws = run_log.seen_worksheet(spreadsheet)
        seen = run_log.seen_slugs(seen_ws.get_all_values())
        known_emails, known_domains = sheet_export.known_contacts(spreadsheet.sheet1.get_all_values())
    except run_log.SheetError as e:
        details["error"] = str(e)
        return finish(e.code, "errore")
    except Exception as e:
        details["error"] = f"Google Sheets: {type(e).__name__}: {e}"
        return finish(3, "errore")

    offer = (offer or os.environ.get("OUTREACH_OFFER", "")).strip()
    sender = (sender or os.environ.get("OUTREACH_SENDER", "")).strip()
    if not offer or not sender:
        details["error"] = "OUTREACH_OFFER o OUTREACH_SENDER mancanti (nel .env o nel Modal Secret)"
        return finish(1, "errore", log_ws)
    if run_log.run_already_done(log_values, run_id):
        details["error"] = f"giro {run_id} gia' eseguito: nessuna nuova spesa"
        return finish(4, "saltato", log_ws)
    month = today.strftime("%Y-%m")
    spent_month = run_log.month_spend(log_values, month)
    details["spesa_mese_prima_usd"] = spent_month
    if not reuse_leads and spent_month + RUN_BUDGET_USD > MONTHLY_CAP_USD:
        details["error"] = f"tetto mensile: {spent_month} $ spesi a {month}, tetto {MONTHLY_CAP_USD} $"
        return finish(4, "saltato", log_ws)

    # Step 1-2: aziende e persone (Apify), scartando prima della spesa su Claude chi e' gia' nel foglio
    leads_file = TMP_DIR / "leads.json"
    if reuse_leads or leads_data is not None:
        if leads_data is not None:
            TMP_DIR.mkdir(exist_ok=True)
            leads_file.write_text(json.dumps(leads_data, ensure_ascii=False), encoding="utf-8")
        if not leads_file.exists():
            details["error"] = f"{leads_file} non trovato: niente da riusare"
            return finish(1, "errore", log_ws)
        leads_result = json.loads(leads_file.read_text(encoding="utf-8"))
        details["leads"] = "riusati (gia' pagati)"
    else:
        code, collected = collect_leads(count, region, terms, known_emails, known_domains, seen)
        entry["Costo Apify $"] = collected["apify_cost_usd"]
        entry["Aziende trovate"] = collected.get("slugs_found", "")
        entry["Aziende valide"] = len(collected.get("companies", []))
        entry["Lead da Apify"] = collected.get("returned_by_actor", "")
        entry["Lead da LinkedIn"] = collected.get("linkedin_returned", "")
        entry["Scarti"] = summarize_discards(collected["discarded"])
        if collected["errors"]:
            details["errori_step"] = collected["errors"]
        if "owners_returned" in collected:
            details["titolari_piccole_aziende"] = collected["owners_returned"]
        # Le aziende controllate si registrano subito: sono gia' pagate, il prossimo giro le salta
        if not dry_run:
            try:
                run_log.append_seen(seen_ws, [
                    {"Data": entry["Data"], "Run id": run_id, "Slug LinkedIn": c.get("slug") or "",
                     "Azienda": c.get("name") or "", "Sito": c.get("domain") or "", "Esito": c["esito"]}
                    for c in collected["checked"]])
            except Exception as e:  # non blocca il giro, ma va visto
                details["aziende_viste_error"] = f"{type(e).__name__}: {e}"
        if code:
            return finish(code, "vuoto" if code == 4 else "errore", log_ws)
        leads_result = {"status": "success", "count": len(collected["leads"]), "leads": collected["leads"],
                        "apify_cost_usd": collected["apify_cost_usd"],
                        "apify_max_charge_usd": collected["apify_cost_usd"]}
        TMP_DIR.mkdir(exist_ok=True)
        leads_file.write_text(json.dumps(leads_result, indent=2, ensure_ascii=False), encoding="utf-8")
    entry["Lead tenuti"] = len(leads_result.get("leads", []))

    # Step 2: email (Claude) con controlli di qualita' nel codice
    code, emails_result = call_step(write_emails.run, leads_file, offer, sender)
    entry["Costo Claude $"] = emails_result.get("claude_cost_usd", 0)
    if code:
        details["write_emails"] = emails_result.get("errors") or emails_result.get("error")
        entry["Email scartate"] = len(emails_result.get("errors", []))
        return finish(code, "vuoto" if code == 4 else "errore", log_ws)
    entry["Email scritte"] = emails_result["count"]
    entry["Email scartate"] = len(emails_result["errors"])
    if emails_result["errors"]:
        details["write_emails"] = emails_result["errors"]
    if emails_result.get("stopped_for_budget"):
        details["budget"] = f"fermato al tetto di {RUN_BUDGET_USD} $"

    # Step 3: foglio (mai invio)
    if dry_run:
        details["sheet_export"] = "saltato (dry-run)"
        return finish(0, "prova", log_ws)
    code, sheet_result = call_step(sheet_export.run, TMP_DIR / "emails.json", None, tag)
    if code:
        details["sheet_export"] = sheet_result.get("error")
        return finish(code, "vuoto" if code == 4 else "errore", log_ws)
    entry["Righe scritte"] = sheet_result["rows_written"]
    complete = (emails_result["status"] == "success" and sheet_result["skipped_duplicates"] == 0
                and entry["Lead tenuti"] == count)
    if not complete:
        details["nota"] = f"{sheet_result['rows_written']} righe su {count} richieste"
    return finish(0 if complete else 4, "ok" if complete else "parziale", log_ws)


def main():
    # Su Windows la console usa cp1252: il JSON in output deve essere UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Giro completo del cold outreach (non invia email)")
    parser.add_argument("--count", type=int, default=MAX_LEADS_PER_RUN, help=f"Lead (1-{MAX_LEADS_PER_RUN})")
    parser.add_argument("--region-index", type=int, help=f"Regione (0-{len(REGIONS) - 1}); default: quella della settimana")
    parser.add_argument("--terms-index", type=int,
                        help=f"Coppia di parole chiave (0-{len(TERM_PAIRS) - 1}); default: quella della settimana")
    parser.add_argument("--run-id", help="Id del giro (default: settimana ISO, es. 2026-W42)")
    parser.add_argument("--tag", help="Etichetta delle righe di prova, es. TEST")
    parser.add_argument("--dry-run", action="store_true", help="Non scrive righe nel foglio dei lead")
    parser.add_argument("--reuse-leads", action="store_true", help="Usa .tmp/leads.json invece di Apify")
    parser.add_argument("--offer", help="Offerta (default OUTREACH_OFFER)")
    parser.add_argument("--sender", help="Mittente (default OUTREACH_SENDER)")
    args = parser.parse_args()

    code, summary = run(args.count, args.region_index, args.run_id, args.tag, args.dry_run, args.reuse_leads,
                        args.offer, args.sender, terms_index=args.terms_index)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.exit(code)


if __name__ == "__main__":
    main()
