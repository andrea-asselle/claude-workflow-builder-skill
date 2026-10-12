#!/usr/bin/env python3
"""
Trova lead B2B per ruolo, paese e parole chiave con l'actor Apify code_crafter/leads-finder
e li salva in .tmp/leads.json. Default (v3): seconda linea (CTO, CIO, COO, responsabili IT,
operations e delivery), esclusi titolari, fondatori e soci.

Usage:
    python implementation/find_leads.py [--count 3] [--location "lombardy, italy;lombardia, italy"]
                                        [--job-titles "CTO,CIO,IT Manager"] [--exclude-titles "CEO,Founder"]
                                        [--keywords "..."] [--industry "information technology & services"]
                                        [--sizes "11-20,21-50,51-100,101-200"] [--any-email]
    Piu' localita' (alias della stessa regione) si separano con ';'.
    python implementation/find_leads.py --domains "azienda1.it,azienda2.it" --count 3
        (cerca i ruoli richiesti dentro aziende gia' note; senza filtro dimensione salvo --sizes)

Exit codes:
    0 - Success
    1 - Invalid input (count, ruoli o dimensioni fuori range)
    2 - Missing or invalid credentials (APIFY_TOKEN), o actor non utilizzabile col piano attuale
    3 - External API error (Apify, anche item di errore restituiti dall'actor)
    4 - Empty result (nessun lead che rispetta ruolo, paese, email e non gia' nel foglio)

Prerequisites:
    uv pip install --python .venv\\Scripts\\python.exe -r requirements.txt
    .env file with APIFY_TOKEN
    Piano Apify a pagamento: sul piano Free questo actor non si puo' usare via API.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from load_env import load_env
from run_state import TMP_DIR, save_step

# Hard stop: limiti di sicurezza per run
MAX_LEADS_LIMIT = 5
MAX_JOB_TITLES = 25  # code_crafter non ha un limite nello schema; harvestapi employees max 50
MAX_DOMAINS = 10
# Si chiedono piu' lead del necessario per poter scartare quelli col ruolo o paese sbagliato
FETCH_MULTIPLIER = 2
MAX_FETCH = 10
# Con --domains l'actor tende a restituire piu' persone della stessa azienda (giro reale v5: 10 persone,
# 7 da 3 aziende): si chiedono 2 persone per sito, fino a 20 (0,02 $ in piu' al massimo)
MAX_FETCH_WITH_DOMAINS = 20
# Con --require-terms si chiedono molti lead e si tengono solo quelli pertinenti
MAX_FETCH_WITH_TERMS = 50
# Campi dell'azienda in cui cercare i termini: descrizione e parole chiave dicono cosa fa l'azienda;
# company_technologies e' escluso perche' elenca strumenti che l'azienda USA (es. Office 365), non che offre
TERM_FIELDS = ("company_description", "keywords", "headline")
# Decisione dell'utente (v3, 2026-10-12): seconda linea IT, operations e delivery, non i titolari.
# Allargata (decisione dell'utente, 2026-10-12, v7) con Project Manager, BU Manager, Head of Business
# Intelligence e CxO: ruoli visti su LinkedIn nelle aziende rimaste senza contatto.
# Max MAX_JOB_TITLES ruoli; l'actor li cerca come testo libero nel titolo.
DEFAULT_JOB_TITLES = ("CTO,CIO,COO,IT Manager,Responsabile IT,Head of IT,IT Director,"
                      "Responsabile Sistemi Informativi,Operations Manager,Direttore Operativo,"
                      "Head of Operations,Delivery Manager,Head of Delivery,Service Delivery Manager,"
                      "Responsabile Delivery,Project Manager,BU Manager,Business Unit Manager,"
                      "Head of Business Intelligence,CxO")
# Titolari, fondatori e soci: esclusi sia nella ricerca (non vengono addebitati) sia nel controllo.
# "Partner" NON e' escluso (decisione dell'utente, 2026-10-12): "Partner e CTO" si tiene.
DEFAULT_EXCLUDE_TITLES = ("CEO,Founder,Owner,Titolare,Amministratore Delegato,Amministratore Unico,"
                          "Presidente,Socio,Managing Director")
DEFAULT_LOCATION = "italy"
# Nessun limite di dimensione (decisione dell'utente, 2026-10-12: non solo PMI).
# Le fasce si possono ancora passare a mano con --sizes.
DEFAULT_SIZES = ""
ALLOWED_SIZES = {"1-10", "11-20", "21-50", "51-100", "101-200", "201-500", "501-1000", "1001-2000",
                 "2001-5000", "5001-10000", "10001-20000", "20001-50000", "50000+"}
# Sinonimi usati solo per il controllo del ruolo sui risultati (confronto a parola intera, minuscolo)
TITLE_SYNONYMS = {
    "ceo": ["chief executive officer"],
    "founder": ["cofounder", "fondatore", "cofondatore"],
    "owner": ["proprietario"],
    "presidente": ["president"],
    "cto": ["chief technology officer", "chief technical officer"],
    "cio": ["chief information officer"],
    "coo": ["chief operating officer", "chief operations officer"],
    "it manager": ["ict manager", "it operations manager"],
    "responsabile it": ["responsabile ict", "responsabile ced", "responsabile informatico", "responsabile ufficio it"],
    "head of it": ["head of ict", "head of information technology"],
    "it director": ["ict director", "director of it", "direttore it", "direttore ict", "direttore informatico"],
    "responsabile sistemi informativi": ["direttore sistemi informativi", "responsabile dei sistemi informativi"],
    "operations manager": ["operation manager", "operations director", "director of operations",
                           "responsabile operations", "responsabile operativo"],
    "direttore operativo": ["direttrice operativa", "direttore operations"],
    "head of operations": ["head of operation"],
    "delivery manager": ["delivery director", "delivery lead"],
    "head of delivery": ["delivery head"],
    "project manager": ["capo progetto", "responsabile di progetto", "responsabile progetti"],
    "bu manager": ["bu director", "responsabile business unit", "responsabile bu"],
    "head of business intelligence": ["head of bi", "bi manager", "business intelligence manager",
                                      "responsabile business intelligence"],
}

# Tetto di spesa passato ad Apify: per questo actor il minimo accettato e' 0,50 $ (minimalMaxTotalChargeUsd)
MAX_APIFY_CHARGE_USD = 0.50
APIFY_ACTOR = "code_crafter~leads-finder"
APIFY_TIMEOUT_SECS = 300
# Prezzi pay-per-event letti dall'API Apify il 2026-10-01:
# avvio 0,02 $ per GB di memoria (default 512 MB = 1 evento), 0,002 $ per lead (fasce FREE/BRONZE)
RUN_FEE_USD = 0.02
LEAD_USD = 0.002
APIFY_WORST_CASE_USD = round(RUN_FEE_USD + LEAD_USD * MAX_FETCH_WITH_TERMS, 4)
OUTPUT_FILE = TMP_DIR / "leads.json"


def fail(message: str, code: int, **extra) -> None:
    """Print JSON error to stderr and exit with the given code."""
    print(json.dumps({"error": message, **extra}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def estimate_cost(n_leads: int) -> float:
    return round(RUN_FEE_USD + LEAD_USD * n_leads, 4)


def is_person(item: dict) -> bool:
    """Una riga e' un lead solo se ha un nome di persona (scarta errori, riepiloghi, caselle generiche)."""
    return bool(item.get("full_name") or item.get("first_name") or item.get("name"))


def normalize_title(text: str) -> str:
    """Minuscolo, punteggiatura -> spazi: 'Co-Founder & CTO' -> 'co founder cto'."""
    t = re.sub(r"[^\w]+", " ", (text or "").lower())
    # "Vice President" non e' il presidente: va tolto prima del confronto con i titolari
    t = re.sub(r"\bvice ?president[ei]?\b", "vp", t)
    # "Product Owner" e "Delivery Partner" sono ruoli, non titolari o soci
    t = re.sub(r"\bproduct owner\b", "po", t)
    t = re.sub(r"\b(delivery|channel|business|technology|alliances?) partner\b", r"\1 prt", t)
    return " ".join(t.split())


def has_phrase(title: str, phrase: str) -> bool:
    """Frase a parola intera: 'cto' non e' in 'director', 'cio' non e' in 'socio'."""
    p = normalize_title(phrase)
    return bool(p) and re.search(rf"(?<!\w){re.escape(p)}(?!\w)", title) is not None


def title_matches(job_title: str, wanted: list[str]) -> bool:
    title = normalize_title(job_title)
    for w in wanted:
        if has_phrase(title, w) or any(has_phrase(title, s) for s in TITLE_SYNONYMS.get(w.lower(), [])):
            return True
    return False


def same_company_domain(mail: str, site: str) -> bool:
    """Stesso dominio, sottodominio, o stesso nome con estensione diversa (acmesoft.it per acmesoft.com:
    4 scarti sbagliati su 5 nella prova v7 del 2026-10-12)."""
    mail, site = mail.lower(), site.lower()
    if mail == site or mail.endswith("." + site) or site.endswith("." + mail):
        return True
    m, s = mail.split("."), site.split(".")
    return len(m) == 2 and len(s) == 2 and m[0] == s[0]


def email_domain_ok(lead: dict) -> bool:
    """L'email deve essere del sito dell'azienda (vedi same_company_domain); se il sito manca non si puo' dire."""
    email = (lead.get("email") or "").lower()
    site = domain_of(lead.get("company_domain") or lead.get("company_website"))
    if "@" not in email or not site:
        return True
    return same_company_domain(email.rsplit("@", 1)[1], site)


def expected_countries(locations: list[str]) -> set[str]:
    """'lombardy, italy' -> 'italy'; 'italy' -> 'italy'."""
    return {loc.rsplit(",", 1)[-1].strip().lower() for loc in locations if loc.strip()}


def domain_of(url: str | None) -> str:
    """'https://www.acme.it/chi-siamo' -> 'acme.it'"""
    d = (url or "").strip().lower()
    for prefix in ("https://", "http://"):
        d = d.removeprefix(prefix)
    return d.removeprefix("www.").split("/")[0]


def matched_terms(lead: dict, terms: list[str]) -> list[str]:
    """Termini richiesti presenti nei dati che descrivono cosa fa l'azienda."""
    text = " ".join(str(lead.get(f) or "") for f in TERM_FIELDS).lower()
    return [t for t in terms if t.lower() in text]


def discard_reason(lead: dict, job_titles: list[str], location: str | list[str],
                   domains: list[str] | None = None, terms: list[str] | None = None,
                   exclude_titles: list[str] | None = None, known_emails: set[str] | None = None,
                   known_domains: set[str] | None = None) -> str | None:
    """Motivo per cui un lead non rispetta la ricerca, o None se va bene."""
    locations = [location] if isinstance(location, str) else location
    email = (lead.get("email") or "").strip().lower()
    company = domain_of(lead.get("company_domain") or lead.get("company_website"))
    if known_emails and email and email in known_emails:
        return "gia' nel foglio (stessa email)"
    if known_domains and company and company in known_domains:
        return f"azienda gia' nel foglio: {company}"
    if terms and not matched_terms(lead, terms):
        return "nessun termine richiesto nella descrizione dell'azienda"
    if domains and company not in domains:
        return f"azienda non richiesta: {company or 'dominio assente'}"
    if exclude_titles and title_matches(lead.get("job_title", ""), exclude_titles):
        return f"titolare o socio: {lead.get('job_title')}"
    if not title_matches(lead.get("job_title", ""), job_titles):
        return f"ruolo diverso: {lead.get('job_title') or 'assente'}"
    country = (lead.get("country") or "").lower()
    if country and country not in expected_countries(locations):
        return f"paese diverso: {lead.get('country')}"
    if not email:
        return "email assente"
    if not email_domain_ok(lead):
        return f"email di un altro dominio: {email.rsplit('@', 1)[1]} (sito {company})"
    return None


def build_input(fetch: int, job_titles: list[str], location: str | list[str], keywords: list[str],
                industries: list[str], sizes: list[str], any_email: bool,
                domains: list[str] | None = None, exclude_titles: list[str] | None = None) -> dict:
    locations = [location] if isinstance(location, str) else location
    actor_input = {
        "fetch_count": fetch,
        "contact_job_title": job_titles,
        "contact_location": [loc.strip().lower() for loc in locations],
    }
    if exclude_titles:
        actor_input["contact_not_job_title"] = exclude_titles
    if sizes:
        actor_input["size"] = sizes
    if domains:
        actor_input["company_domain"] = domains
    if keywords:
        actor_input["company_keywords"] = keywords
    if industries:
        actor_input["company_industry"] = [i.lower() for i in industries]
    if not any_email:
        actor_input["email_status"] = ["validated"]
    return actor_input


def run(count: int, job_titles: list[str], location: str | list[str] = DEFAULT_LOCATION,
        keywords: list[str] | None = None, industries: list[str] | None = None, sizes: list[str] | None = None,
        any_email: bool = False, domains: list[str] | None = None, terms: list[str] | None = None,
        fetch: int | None = None, exclude_titles: list[str] | None = None,
        known_emails: set[str] | None = None, known_domains: set[str] | None = None) -> dict:
    """Core logic. Returns a JSON-serializable dict.

    known_emails / known_domains: contatti e aziende gia' nel foglio, scartati qui (prima di pagare Claude).
    """
    keywords, industries, terms = keywords or [], industries or [], terms or []
    exclude_titles = DEFAULT_EXCLUDE_TITLES.split(",") if exclude_titles is None else exclude_titles
    domains = [domain_of(d) for d in (domains or []) if domain_of(d)]
    # Il filtro sulla dimensione si applica solo se richiesto esplicitamente
    if sizes is None:
        sizes = [s for s in DEFAULT_SIZES.split(",") if s] if not domains else []
    if len(domains) > MAX_DOMAINS:
        fail(f"--domains: max {MAX_DOMAINS} siti", 1, domains=domains)
    if not 1 <= count <= MAX_LEADS_LIMIT:
        fail(f"--count deve essere tra 1 e {MAX_LEADS_LIMIT} (hard limit)", 1, count=count)
    if not 1 <= len(job_titles) <= MAX_JOB_TITLES:
        fail(f"--job-titles: da 1 a {MAX_JOB_TITLES} ruoli", 1, job_titles=job_titles)
    bad_sizes = [s for s in sizes if s not in ALLOWED_SIZES]
    if bad_sizes:
        fail(f"--sizes non valide: {bad_sizes}. Valori ammessi: {sorted(ALLOWED_SIZES)}", 1)

    load_env()
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        fail("APIFY_TOKEN mancante. Aggiungilo al file .env", 2)

    max_fetch = MAX_FETCH_WITH_TERMS if terms else MAX_FETCH_WITH_DOMAINS if domains else MAX_FETCH
    if fetch is None:
        wanted = max(count, len(domains)) * FETCH_MULTIPLIER if domains else count * FETCH_MULTIPLIER
        fetch = min(wanted, MAX_FETCH_WITH_DOMAINS if domains else MAX_FETCH)
    if not count <= fetch <= max_fetch:
        fail(f"--fetch deve essere tra {count} e {max_fetch}"
             + ("" if terms or domains else f" (oltre {MAX_FETCH} solo con --require-terms o --domains)"), 1,
             fetch=fetch)
    actor_input = build_input(fetch, job_titles, location, keywords, industries, sizes, any_email, domains,
                              exclude_titles)

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
    if not isinstance(items, list):
        fail("Risposta Apify inattesa: non e' una lista di lead", 3, body=str(items)[:300])

    items = [i for i in items if isinstance(i, dict)]
    # Alcuni actor rispondono 200 con un item {"error": ...} invece di un lead (es. piano Free via API)
    error_items = [i for i in items if (i.get("error") or i.get("message")) and not is_person(i)]
    if error_items:
        first = error_items[0]
        fail(f"L'actor ha restituito un errore: {first.get('error') or first.get('message')}", 3)

    people = [i for i in items if is_person(i)]
    leads, discarded, taken_companies = [], [], set()
    for p in people:
        reason = discard_reason(p, job_titles, location, domains, terms, exclude_titles,
                                known_emails, known_domains)
        company = domain_of(p.get("company_domain") or p.get("company_website")) or p.get("company_name")
        # Un solo contatto per azienda in ogni giro
        if not reason and company and company in taken_companies:
            reason = "azienda gia' presa in questo giro"
        if reason:
            discarded.append({"name": p.get("full_name") or p.get("first_name"),
                              "company": p.get("company_name"), "reason": reason})
        elif len(leads) < count:
            if terms:
                p = {**p, "matched_terms": matched_terms(p, terms)}
            leads.append(p)
            taken_companies.add(company)

    if not leads:
        fail("Nessun lead che rispetta ruolo, paese ed email.", 4, input=actor_input,
             returned_by_actor=len(people), discarded=discarded,
             apify_cost_usd=estimate_cost(len(people)))

    result = {
        "status": "success",
        "count": len(leads),
        "returned_by_actor": len(people),
        "discarded": discarded,
        "apify_cost_usd": estimate_cost(len(people)),
        "apify_max_charge_usd": estimate_cost(fetch),
        "search": actor_input,
        "leads": leads,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    TMP_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    save_step("find_leads", "done", leads=len(leads), apify_cost_usd=result["apify_cost_usd"])
    return result


def split_list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def main():
    # Su Windows la console usa cp1252: il JSON in output deve essere UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Trova lead B2B per ruolo, paese e parole chiave via Apify")
    parser.add_argument("--count", type=int, default=3, help=f"Numero di lead (1-{MAX_LEADS_LIMIT})")
    parser.add_argument("--job-titles", default=DEFAULT_JOB_TITLES,
                        help=f"Ruoli separati da virgola, max {MAX_JOB_TITLES} (default: seconda linea IT/ops/delivery)")
    parser.add_argument("--exclude-titles", default=DEFAULT_EXCLUDE_TITLES,
                        help="Ruoli da escludere, separati da virgola (default: titolari, fondatori, soci); "
                             "'' per non escludere nulla")
    parser.add_argument("--location", default=DEFAULT_LOCATION,
                        help="Paese o regione come nell'elenco dell'actor (es. italy, 'piemonte, italy'); "
                             "piu' localita' separate da ';'")
    parser.add_argument("--keywords", default="", help="Parole chiave sull'azienda, separate da virgola")
    parser.add_argument("--industry", default="", help="Settori dell'actor separati da virgola (opzionale)")
    parser.add_argument("--sizes", default=None,
                        help="Fasce di dipendenti separate da virgola (default: nessun limite)")
    parser.add_argument("--domains", default="",
                        help=f"Siti delle aziende in cui cercare, separati da virgola (max {MAX_DOMAINS})")
    parser.add_argument("--any-email", action="store_true", help="Accetta anche email non validate")
    parser.add_argument("--require-terms", default="",
                        help="Tiene solo aziende che citano almeno uno di questi termini nella descrizione o "
                             "nelle parole chiave (es. 'Business Central,Power Platform')")
    parser.add_argument("--fetch", type=int, default=None,
                        help=f"Lead da chiedere all'actor (default count x {FETCH_MULTIPLIER}, max {MAX_FETCH}; "
                             f"fino a {MAX_FETCH_WITH_TERMS} con --require-terms)")
    args = parser.parse_args()

    sizes = split_list(args.sizes) if args.sizes is not None else None
    locations = [loc.strip() for loc in args.location.split(";") if loc.strip()]
    result = run(args.count, split_list(args.job_titles), locations, split_list(args.keywords),
                 split_list(args.industry), sizes, args.any_email, split_list(args.domains),
                 split_list(args.require_terms), args.fetch, split_list(args.exclude_titles))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
