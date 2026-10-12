#!/usr/bin/env python3
"""
Scopre aziende italiane specializzate in tecnologie Microsoft, in due passi:
    1. Google (apify/google-search-scraper): `site:linkedin.com/company "<termine>" <Regione>`
       -> pagine LinkedIn di aziende che citano la tecnologia nel testo (2 pagine di risultati per query)
    2. LinkedIn (harvestapi/linkedin-company): sito, sede, specializzazioni
       -> tiene solo aziende con sede in Italia, con sito, con termini Microsoft nella descrizione
          e non gia' presenti nel foglio
Salva il risultato in .tmp/companies.json.

Perche' cosi': i database di aziende (code_crafter, LinkedIn company search) cercano per nome, settore e
dimensione, non per "di cosa si occupa". Google cerca nel testo. Vedi rules/cold_outreach.md (v5).
Portato da RBI_Auto_Test (2026-10-12) con: regione nella query, piu' pagine, aziende gia' nel foglio scartate.

Usage:
    python implementation/discover_companies.py --terms "Business Central,Power Platform" [--place Lombardia]
        [--max-companies 10] [--pages 2] [--exclude-slugs "slug1,slug2"]

Exit codes:
    0 - Success
    1 - Invalid input
    2 - Missing or invalid credentials (APIFY_TOKEN)
    3 - External API error
    4 - Nessuna azienda valida
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
from find_leads import domain_of
from load_env import load_env
from run_state import TMP_DIR, save_step

GOOGLE_ACTOR = "apify~google-search-scraper"
COMPANY_ACTOR = "harvestapi~linkedin-company"
APIFY_TIMEOUT_SECS = 300
# Tetto per singolo run Apify (Google accetta minimo 0,50 $); la spesa reale e' molto piu' bassa
MAX_CHARGE_USD = 0.50
# Prezzi letti dall'API Apify il 2026-10-05 (fascia BRONZE)
GOOGLE_START_USD = 0.001
GOOGLE_PAGE_USD = 0.0025
COMPANY_USD = 0.004

MAX_TERMS = 4
MAX_COMPANIES_LIMIT = 10
# Con una sola pagina Google le aziende si ripetevano presto (RBI_Auto_Test, 2026-10-12)
GOOGLE_PAGES = 2
MAX_GOOGLE_PAGES = 3
# Parole chiave scelte dall'utente (2026-10-05); usate a coppie, a rotazione tra un giro e l'altro
DEFAULT_TERMS = ["Business Central", "Power Platform", "Dynamics 365", "Power Apps", "Microsoft Azure",
                 "Copilot Studio", "Power Automate", "Power BI"]
COUNTRY = "IT"
# Termini che indicano un'azienda che LAVORA sulle tecnologie Microsoft (cercati in descrizione,
# specializzazioni e tagline; non nelle tecnologie usate)
MICROSOFT_TERMS = re.compile(r"(?i)business central|dynamics(?: 365| nav| crm)?|navision|power platform|"
                             r"power apps|power automate|power bi|azure|copilot studio|microsoft 365|"
                             r"microsoft partner|partner microsoft")
# Tipi LinkedIn da escludere, confrontati come parti del testo: LinkedIn usa varianti
# ("Educational Institution", "Government Agency", "Self-Employed"...)
EXCLUDED_COMPANY_TYPE_WORDS = ("nonprofit", "non-profit", "educational", "government", "self-employed", "self-owned")
# "Siti" che sono solo raccolte di link, profili social o pagine di eventi
LINK_PAGE_DOMAINS = {"linktr.ee", "bit.ly", "linkedin.com", "facebook.com", "instagram.com", "sites.google.com",
                     "meetup.com", "eventbrite.com", "eventbrite.it"}
SLUG_RE = re.compile(r"linkedin\.com/company/([^/?#]+)")
# Community, gruppi ed eventi riconoscibili gia' da slug o titolo Google: scartati PRIMA di pagare LinkedIn
# (giro reale v7, 2026-10-12: 4 su 10 con "Azure" — meetup, podcast, Startup Grind, user group)
COMMUNITY_RE = re.compile(r"(?i)meetup|user[\s_-]?group|podcast|communit[yi]|startup[\s_-]?grind")
OUTPUT_FILE = TMP_DIR / "companies.json"


def fail(message: str, code: int, **extra) -> None:
    print(json.dumps({"error": message, **extra}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def run_actor(actor: str, body: dict, token: str) -> list:
    """Esegue un actor Apify in modo sincrono e ritorna gli item del dataset."""
    try:
        resp = requests.post(
            f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
            headers={"Authorization": f"Bearer {token}"},
            params={"timeout": APIFY_TIMEOUT_SECS, "maxTotalChargeUsd": MAX_CHARGE_USD},
            json=body,
            timeout=APIFY_TIMEOUT_SECS + 30,
        )
    except requests.RequestException as e:
        fail(f"Errore di rete verso Apify ({actor}): {e}", 3)
    if resp.status_code in (401, 403):
        fail(f"Apify ha rifiutato la richiesta a {actor} ({resp.status_code})", 2)
    if resp.status_code >= 400:
        fail(f"Apify {actor} ha risposto {resp.status_code}", 3, body=resp.text[:300])
    try:
        items = resp.json()
    except ValueError:
        fail(f"Risposta di {actor} non e' JSON", 3)
    if not isinstance(items, list):
        fail(f"Risposta di {actor} inattesa: non e' una lista", 3)
    return [i for i in items if isinstance(i, dict)]


def google_queries(terms: list[str], place: str = "Italia") -> list[str]:
    return [f'site:linkedin.com/company "{t}" {place}' for t in terms]


def extract_slugs(pages: list) -> list[str]:
    """Slug delle pagine aziendali LinkedIn trovate da Google, senza doppioni (it., ca., dk.linkedin.com...)."""
    slugs = []
    for page in pages:
        for result in page.get("organicResults") or []:
            m = SLUG_RE.search(result.get("url") or "")
            if m and m.group(1) not in slugs:
                slugs.append(m.group(1))
    return slugs


def community_slugs(pages: list) -> set[str]:
    """Slug il cui indirizzo o titolo Google indica una community, un gruppo o un evento."""
    found = set()
    for page in pages:
        for result in page.get("organicResults") or []:
            m = SLUG_RE.search(result.get("url") or "")
            if m and COMMUNITY_RE.search(f"{m.group(1)} {result.get('title') or ''}"):
                found.add(m.group(1))
    return found


def headquarter(company: dict) -> dict:
    locs = company.get("locations") or []
    return next((l for l in locs if l.get("headquarter")), locs[0] if locs else {})


def microsoft_terms(company: dict) -> list[str]:
    text = " ".join([company.get("description") or "", company.get("tagline") or "",
                     " ".join(company.get("specialities") or [])])
    return sorted({m.group(0).lower() for m in MICROSOFT_TERMS.finditer(text)})


def qualify(company: dict, known_domains: set[str] | None = None) -> str | None:
    """Motivo per cui l'azienda non va bene, o None se va bene."""
    country = (headquarter(company).get("country") or "").upper()
    if country != COUNTRY:
        return f"sede non in Italia: {country or 'sconosciuta'}"
    # User group, community, scuole, enti: non sono clienti
    ctype = (company.get("companyType") or "").lower()
    if any(w in ctype for w in EXCLUDED_COMPANY_TYPE_WORDS):
        return f"non e' un'azienda: {company.get('companyType')}"
    domain = domain_of(company.get("website"))
    if not domain or domain in LINK_PAGE_DOMAINS:
        return "sito assente" if not domain else f"sito non aziendale: {domain}"
    if known_domains and domain in known_domains:
        return f"azienda gia' nel foglio: {domain}"
    if not microsoft_terms(company):
        return "nessuna specializzazione Microsoft"
    return None


def slug_of(company: dict) -> str | None:
    m = SLUG_RE.search(company.get("linkedinUrl") or "")
    return m.group(1) if m else None


def summarize_company(company: dict) -> dict:
    hq = headquarter(company)
    return {"name": company.get("name"), "domain": domain_of(company.get("website")),
            "linkedin": company.get("linkedinUrl"), "slug": slug_of(company),
            "city": hq.get("city"),
            "employee_range": company.get("employeeCountRange"), "microsoft_terms": microsoft_terms(company)}


def estimate_cost(n_pages: int, n_companies: int) -> float:
    return round(GOOGLE_START_USD + GOOGLE_PAGE_USD * n_pages + COMPANY_USD * n_companies, 4)


def run(terms: list[str], max_companies: int = MAX_COMPANIES_LIMIT, exclude_slugs: set | None = None,
        place: str = "Italia", pages: int = GOOGLE_PAGES, known_domains: set[str] | None = None) -> dict:
    """Core logic. Returns a JSON-serializable dict.

    exclude_slugs: aziende gia' viste nei giri precedenti, saltate PRIMA di pagare LinkedIn.
    known_domains: aziende gia' nel foglio, scartate prima di cercare le persone.
    """
    exclude_slugs = {s.lower() for s in exclude_slugs or set()}
    if not 1 <= len(terms) <= MAX_TERMS:
        fail(f"--terms: da 1 a {MAX_TERMS} termini", 1, terms=terms)
    if not 1 <= max_companies <= MAX_COMPANIES_LIMIT:
        fail(f"--max-companies tra 1 e {MAX_COMPANIES_LIMIT}", 1, max_companies=max_companies)
    if not 1 <= pages <= MAX_GOOGLE_PAGES:
        fail(f"--pages tra 1 e {MAX_GOOGLE_PAGES}", 1, pages=pages)

    load_env()
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        fail("APIFY_TOKEN mancante. Aggiungilo al file .env", 2)

    queries = google_queries(terms, place)
    results = run_actor(GOOGLE_ACTOR, {"queries": "\n".join(queries), "maxPagesPerQuery": pages,
                                       "countryCode": "it", "searchLanguage": "it", "languageCode": "it"}, token)
    found = extract_slugs(results)
    communities = community_slugs(results)
    unseen = [s for s in found if s.lower() not in exclude_slugs and s not in communities]
    new_slugs = unseen[:max_companies]

    companies = []
    if new_slugs:
        companies = run_actor(COMPANY_ACTOR,
                              {"companies": [f"https://www.linkedin.com/company/{s}/" for s in new_slugs]}, token)

    valid, discarded = [], []
    for c in companies:
        reason = qualify(c, known_domains)
        if reason:
            discarded.append({"name": c.get("name"), "slug": slug_of(c), "domain": domain_of(c.get("website")),
                              "reason": reason})
        else:
            valid.append(summarize_company(c))

    result = {
        "status": "success",
        "terms": terms,
        "queries": queries,
        "google_pages": len(results),
        "slugs_found": len(found),
        "slugs_already_seen": len([s for s in found if s.lower() in exclude_slugs]),
        "slugs_community": sorted(communities),
        "slugs_checked": new_slugs,
        "companies": valid,
        "discarded": discarded,
        "cost_usd": estimate_cost(len(results), len(companies)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    TMP_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    save_step("discover_companies", "done", companies=len(valid), cost_usd=result["cost_usd"])
    if not valid:
        fail("Nessuna azienda valida trovata", 4, slugs_found=len(found), slugs_checked=new_slugs,
             discarded=discarded, cost_usd=result["cost_usd"])
    return result


def split_list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Scopre aziende italiane specializzate in tecnologie Microsoft")
    parser.add_argument("--terms", default=",".join(DEFAULT_TERMS[:2]), help="Termini separati da virgola (max 4)")
    parser.add_argument("--place", default="Italia", help="Regione o paese aggiunto alla query Google")
    parser.add_argument("--max-companies", type=int, default=MAX_COMPANIES_LIMIT)
    parser.add_argument("--pages", type=int, default=GOOGLE_PAGES, help=f"Pagine Google per query (max {MAX_GOOGLE_PAGES})")
    parser.add_argument("--exclude-slugs", default="", help="Slug LinkedIn gia' visti da saltare")
    args = parser.parse_args()
    result = run(split_list(args.terms), args.max_companies, set(split_list(args.exclude_slugs)),
                 args.place, args.pages)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
