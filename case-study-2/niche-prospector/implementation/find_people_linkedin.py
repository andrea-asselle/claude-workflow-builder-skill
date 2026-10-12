#!/usr/bin/env python3
"""
Ripiego per le aziende in cui code_crafter non trova nessuno: cerca i dipendenti dalla pagina LinkedIn
dell'azienda (harvestapi/linkedin-company-employees, con ricerca email) e tiene solo chi rispetta i filtri:
    - lavora ORA in quell'azienda (slug LinkedIn della posizione attuale)
    - ruolo di seconda linea, non titolare/fondatore/socio (stessi filtri di find_leads)
    - email consegnabile, non su dominio catch-all, sul dominio dell'azienda, non gia' nel foglio
Al massimo un contatto per azienda.

Il filtro sui ruoli dell'actor e' approssimativo (nella prova ha restituito un membro del consiglio e un VP):
per questo i controlli sono rifatti qui. Portato da RBI_Auto_Test (2026-10-12).

Usage:
    python implementation/find_people_linkedin.py --companies "slug1=dominio1.it,slug2=dominio2.it"
        [--max-profiles 10]

Exit codes:
    0 - Success
    1 - Invalid input
    2 - Missing or invalid credentials
    3 - External API error
    4 - Nessuna persona valida
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from discover_companies import run_actor
from find_leads import DEFAULT_EXCLUDE_TITLES, DEFAULT_JOB_TITLES, domain_of, same_company_domain, title_matches
from load_env import load_env

ACTOR = "harvestapi~linkedin-company-employees"
# Prezzi letti dall'API Apify il 2026-10-05: avvio 0,02 $ (uno solo in modalita' all_at_once),
# profilo completo con email 0,012 $
START_USD = 0.02
PROFILE_USD = 0.012
MAX_COMPANIES = 10
MAX_PROFILES = 10


def fail(message: str, code: int, **extra) -> None:
    print(json.dumps({"error": message, **extra}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def estimate_cost(n_profiles: int) -> float:
    return round(START_USD + PROFILE_USD * n_profiles, 4)


def position_at(profile: dict, slug: str) -> dict | None:
    """Posizione attuale del profilo nell'azienda indicata, se c'e'."""
    for pos in profile.get("currentPosition") or []:
        if (pos.get("companyUniversalName") or "").lower() == slug.lower():
            return pos
    return None


def best_email(profile: dict, domain: str) -> dict | None:
    """Email consegnabile, non catch-all, sul dominio dell'azienda (o un suo sottodominio)."""
    for e in profile.get("emails") or []:
        addr = (e.get("email") or "").lower()
        edomain = addr.split("@")[-1]
        if (e.get("deliverable") and e.get("status") == "valid" and not e.get("catchAllDomain")
                and same_company_domain(edomain, domain)):
            return e
    return None


def to_lead(profile: dict, position: dict, email: dict, company: dict) -> dict:
    """Lead nello stesso formato di code_crafter, cosi' il resto della pipeline non cambia."""
    loc = (profile.get("location") or {}).get("parsed") or {}
    first, last = profile.get("firstName") or "", profile.get("lastName") or ""
    return {
        "first_name": first, "last_name": last, "full_name": f"{first} {last}".strip(),
        "job_title": position.get("position"), "headline": profile.get("headline"),
        "email": email["email"], "email_status": f"{email.get('status')} ({email.get('qualityScore')})",
        "company_name": position.get("companyName") or company.get("name"),
        "company_domain": company["domain"], "company_website": company["domain"],
        "linkedin": profile.get("linkedinUrl"), "country": loc.get("country"), "city": loc.get("text"),
        "source": "linkedin-employees",
    }


def filter_people(profiles: list, companies: list[dict], job_titles: list[str],
                  exclude_titles: list[str] | None = None,
                  known_emails: set[str] | None = None) -> tuple[list, list]:
    """Ritorna (lead validi, scartati con motivo). Al massimo un lead per azienda."""
    leads, discarded, covered = [], [], set()
    for p in profiles:
        name = f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()
        match = next(((c, pos) for c in companies if (pos := position_at(p, c["slug"]))), None)
        if not match:
            discarded.append({"name": name, "reason": "non lavora in una delle aziende cercate"})
            continue
        company, position = match
        title = position.get("position") or ""
        if company["slug"] in covered:
            discarded.append({"name": name, "reason": "azienda gia' presa in questo giro"})
            continue
        if exclude_titles and title_matches(title, exclude_titles):
            discarded.append({"name": name, "reason": f"titolare o socio: {title}"})
            continue
        if not title_matches(title, job_titles):
            discarded.append({"name": name, "reason": f"ruolo diverso: {title or 'assente'}"})
            continue
        email = best_email(p, company["domain"])
        if not email:
            discarded.append({"name": name, "reason": "nessuna email valida sul dominio aziendale"})
            continue
        if known_emails and email["email"].lower() in known_emails:
            discarded.append({"name": name, "reason": "gia' nel foglio (stessa email)"})
            continue
        leads.append(to_lead(p, position, email, company))
        covered.add(company["slug"])
    return leads, discarded


def run(companies: list[dict], job_titles: list[str] | None = None, max_profiles: int | None = None,
        exclude_titles: list[str] | None = None, known_emails: set[str] | None = None) -> dict:
    """companies: [{"slug": ..., "domain": ..., "name": ...}]"""
    job_titles = job_titles or DEFAULT_JOB_TITLES.split(",")
    exclude_titles = DEFAULT_EXCLUDE_TITLES.split(",") if exclude_titles is None else exclude_titles
    companies = [c for c in companies if c.get("slug") and domain_of(c.get("domain"))]
    if not 1 <= len(companies) <= MAX_COMPANIES:
        fail(f"Servono da 1 a {MAX_COMPANIES} aziende con slug LinkedIn e dominio", 1)
    max_profiles = min(max_profiles or 2 * len(companies), MAX_PROFILES)

    load_env()
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        fail("APIFY_TOKEN mancante. Aggiungilo al file .env", 2)

    profiles = run_actor(ACTOR, {
        "companies": [f"https://www.linkedin.com/company/{c['slug']}/" for c in companies],
        "jobTitles": job_titles,
        "profileScraperMode": "Full + email search ($12 per 1k)",
        # Un solo avvio per tutte le aziende (one_by_one ne pagava uno per azienda, 2026-10-05)
        "companyBatchMode": "all_at_once",
        "maxItems": max_profiles,
    }, token)
    leads, discarded = filter_people(profiles, companies, job_titles, exclude_titles, known_emails)
    result = {
        "status": "success",
        "count": len(leads),
        "returned_by_actor": len(profiles),
        "discarded": discarded,
        "apify_cost_usd": estimate_cost(len(profiles)),
        "leads": leads,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not leads:
        fail("Nessuna persona valida trovata su LinkedIn", 4, returned_by_actor=len(profiles),
             discarded=discarded, apify_cost_usd=result["apify_cost_usd"])
    return result


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Trova la seconda linea dalla pagina LinkedIn dell'azienda")
    parser.add_argument("--companies", required=True, help="slug=dominio separati da virgola")
    parser.add_argument("--max-profiles", type=int, default=None)
    args = parser.parse_args()
    companies = []
    for pair in [p.strip() for p in args.companies.split(",") if p.strip()]:
        slug, _, domain = pair.partition("=")
        companies.append({"slug": slug.strip(), "domain": domain_of(domain), "name": slug.strip()})
    print(json.dumps(run(companies, max_profiles=args.max_profiles), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
