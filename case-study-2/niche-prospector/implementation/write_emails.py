#!/usr/bin/env python3
"""
Scrive per ogni lead di .tmp/leads.json un'email di cold outreach in italiano e salva il risultato
in .tmp/emails.json. Le email NON vengono inviate. Schema fisso (oggetto, saluto, offerta, invito, firma);
Claude scrive solo due frasi personalizzate: apertura sull'azienda ed esempio (domanda).

Usage:
    python implementation/write_emails.py --offer "cosa proponi" --sender "Nome Cognome"
                                          [--input .tmp/leads.json]

Exit codes:
    0 - Success (tutte le email scritte)
    1 - Invalid input (leads.json mancante/invalido, argomenti)
    2 - Missing or invalid credentials (ANTHROPIC_API_KEY)
    3 - External API error (Claude, nessuna email prodotta)
    4 - Partial/empty result (budget esaurito o alcune email fallite o scartate dai controlli di
        qualita' dopo una rigenerazione; le riuscite sono salvate)

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
MAX_OUTPUT_TOKENS = 300  # solo due frasi
MAX_FIELD_CHARS = 400
MAX_ATTEMPTS = 2  # un'email che non passa i controlli di qualita' si rigenera una volta, poi si scarta
CLAUDE_TIMEOUT_SECS = 60

# Schema fisso dell'email (decisione dell'utente, 2026-10-12): Claude scrive solo {apertura} ed {esempio},
# il resto e' testo fisso. Gli errori visti in produzione erano tutti nelle parti che ora sono fisse.
#   Oggetto: Meno lavoro manuale in {Azienda}
#   Gentile {Nome Cognome},
#   {apertura}            <- 1 frase sull'azienda, solo dai dati
#   {offerta}             <- OUTREACH_OFFER, fissa
#   {esempio}             <- 1 domanda su un'attivita' concreta dell'azienda
#   {invito}              <- fisso
#   Cordiali saluti,
#   {mittente}
SUBJECT_TEMPLATE = "Meno lavoro manuale in {company}"
SUBJECT_FALLBACK = "Meno lavoro manuale nei reparti IT e operations"
# Invito leggero (decisione dell'utente, 2026-10-12): niente richiesta di chiamata a tempo fisso
CALL_TO_ACTION = "Se il tema Le interessa, mi risponda pure: ne parliamo quando Le è più comodo."
MAX_SLOT_WORDS = 35
LEGAL_SUFFIXES = re.compile(r"[\s,]+(s\.?r\.?l\.?s?|s\.?p\.?a\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|ltd\.?|ag|gmbh|"
                            r"inc\.?|group|spa|srl)\s*$", re.IGNORECASE)

SYSTEM_PROMPT = (
    "Scrivi due frasi in italiano per personalizzare un'email di primo contatto B2B. Il resto dell'email "
    "(saluto, offerta, invito finale, firma) e' gia' scritto: NON scriverlo.\n"
    "1. apertura: UNA frase affermativa (max 30 parole) su cosa fa l'azienda del destinatario o sul suo "
    "ruolo, usando SOLO fatti presenti nei dati forniti. Inizia con il nome dell'azienda o con 'In <Azienda>'. "
    "Niente complimenti generici, niente supposizioni sui problemi dell'azienda, non parlare del mittente "
    "ne' dell'offerta.\n"
    "2. esempio: UNA domanda (max 30 parole) su un'attivita' concreta di QUELL'azienda, presa dai dati, che "
    "potrebbe passare ancora da fogli Excel, email o passaggi manuali. Deve finire con '?'. Esempio: "
    "'In Neri Impianti i dati di collaudo e di assistenza passano ancora da fogli Excel ed email?'\n"
    "Regole per entrambe:\n"
    "- L'azienda sempre in terza persona; il destinatario, se citato, con il Lei maiuscolo (Lei, Le, Suo). "
    "Mai il 'voi': sbagliato 'gestite', 'Vostra', 'avete'; giusto 'gestiscono', 'Sua', 'hanno'.\n"
    "- Italiano corretto, senza anglicismi inutili, senza emoji. Nomi di prodotti e settori come nei dati.\n"
    "- Non inventare numeri, clienti, progetti o notizie che non sono nei dati.\n"
    'Rispondi SOLO con un oggetto JSON: {"apertura": "...", "esempio": "..."}'
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


def parse_slots(text: str) -> dict:
    """{"apertura": ..., "esempio": ...} dalla risposta di Claude (anche dentro un blocco di codice)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("nessun JSON nella risposta")
    data = json.loads(match.group(0))
    slots = {k: " ".join(str(data.get(k, "")).split()) for k in ("apertura", "esempio")}
    if not all(slots.values()):
        raise ValueError("apertura o esempio vuoti")
    return slots


def short_company(lead: dict) -> str:
    """'Blu Consulting S.p.a.' -> 'Blu Consulting'; vuoto se manca."""
    name = (lead.get("company_name") or "").strip()
    while True:
        shorter = LEGAL_SUFFIXES.sub("", name).strip()
        if shorter == name:
            return name
        name = shorter


def full_name(lead: dict) -> str:
    first, last = (lead.get("first_name") or "").strip(), (lead.get("last_name") or "").strip()
    return f"{first} {last}".strip() or (lead.get("full_name") or "").strip()


def build_email(slots: dict, lead: dict, offer: str, sender: str) -> dict:
    """Monta l'email dallo schema fisso e dalle due frasi."""
    company = short_company(lead)
    subject = SUBJECT_TEMPLATE.format(company=company) if company else SUBJECT_FALLBACK
    body = (f"Gentile {full_name(lead)},\n\n{slots['apertura']}\n\n{offer.strip()}\n\n"
            f"{slots['esempio']}\n\n{CALL_TO_ACTION}\n\nCordiali saluti,\n{sender}")
    return {"subject": subject, "body": body}


def slot_problems(slots: dict, lead: dict) -> list[str]:
    """Controlli sulle due frasi scritte da Claude (forma, non senso)."""
    problems = []
    for key, text in slots.items():
        words = len(text.split())
        if words > MAX_SLOT_WORDS:
            problems.append(f"{key} troppo lunga ({words} parole, max {MAX_SLOT_WORDS})")
        # una sola frase: fine frase dopo una parola vera (non sigle come "S.p.A." o "Inc.") e poi maiuscola
        if re.search(r"[a-zà-ù]{3}[.!?]\s+[A-ZÀ-Ù]", text):
            problems.append(f"{key}: piu' di una frase")
    if not slots["esempio"].endswith("?"):
        problems.append("esempio: deve essere una domanda")
    if slots["apertura"].endswith("?"):
        problems.append("apertura: deve essere un'affermazione, non una domanda")
    # solo frasi in prima persona o il prodotto offerto: "sviluppo software" dell'azienda e' lecito
    # (falso positivo reale 2026-10-12)
    if re.search(r"power platform|\b(?:propongo|offro|mi occupo|ho|sviluppo app|le scrivo|la contatto)\b",
                 slots["apertura"], re.IGNORECASE):
        problems.append("apertura: parla del mittente o dell'offerta")
    first = short_company(lead).split()[0] if short_company(lead) else ""
    if first and not has_word(slots["apertura"], first):
        problems.append(f"apertura: non cita l'azienda ({short_company(lead)})")
    return problems


def call_cost(usage) -> float:
    return usage.input_tokens * PRICE_IN + usage.output_tokens * PRICE_OUT


# Controlli di qualita' (v3): sostituiscono la rilettura del Brain nel giro automatico.
# Ogni errore nuovo trovato in produzione va aggiunto qui e in un test.
MAX_BODY_WORDS = 150  # il prompt chiede 120: margine per saluto e firma
MAX_SUBJECT_CHARS = 90
FOREIGN_CLOSINGS = ["cordialement", "best regards", "kind regards", "regards", "saludos", "mit freundlichen"]
INVENTED_CLAIMS = ["ho aiutato", "abbiamo aiutato", "aziende simili", "realtà simili", "realta' simili",
                   "nostri clienti", "lavoro con aziende", "lavoriamo con aziende", "aziende come la sua",
                   # errore reale 2026-10-12: "Ho sviluppato soluzioni ... che aiutano reparti IT"
                   "ho sviluppato", "abbiamo sviluppato", "ho realizzato", "abbiamo realizzato",
                   "ho implementato", "abbiamo implementato", "ho già", "abbiamo già"]
ANGLICISMS = ["fit", "call", "business"]
# Parole storpiate viste in produzione (2026-10-12: "Develuppo" = develop + sviluppo, 2 email su 5)
MANGLED = re.compile(r"\bdevel\w*", re.IGNORECASE)
# Infinito troncato dopo una preposizione articolata (errore reale 2026-10-12:
# "Nel coordinar dei progetti"). Solo -ar/-ir: le parole in -er sono spesso inglesi ("nel server").
TRUNCATED_INFINITIVE = re.compile(r"\b(?:nel|nello|del|dello|al|allo|dal|dallo|sul|sullo|col)\s+([a-zà-ù]{3,}(?:ar|ir))\b",
                                  re.IGNORECASE)
NOT_TRUNCATED = {"webinar", "seminar", "radar", "calendar", "dollar", "solar", "sugar"}
# Supposizioni sul destinatario presentate come fatti (2026-10-12, 2 casi reali)
ASSUMED_FACTS = ["realtà come la sua", "realta' come la sua", "in organizzazioni come", "aziende come la vostra",
                 "in realtà come", "spesso i team", "i team it e operations spesso", "spesso dedicano"]
INFORMAL = ["ti", "tuo", "tua", "tuoi", "tue"]
# "voi" di cortesia mescolato al Lei (errore reale 2026-10-12: "interessarVi", "gestite")
# Forme sicure: "Vi" maiuscolo, infiniti con -vi in coda ("interessarVi", "supportarvi"), vostro/a/i/e,
# avete, siete. Errori reali 2026-10-12: "interessarVi", "supportarvi", "In Deltasoft gestite".
PLURAL_YOU = re.compile(r"\bVi\b|[a-zà-ù](?:ar|er|ir)[Vv]i\b|[a-zà-ù]Vi\b|\b[Vv]ostr[oaie]\b|\b(?:[Aa]vete|[Ss]iete)\b")


def company_plural_verb(body: str, company: str) -> str | None:
    """'In Deltasoft gestite ...': verbo alla seconda plurale subito dopo il nome dell'azienda."""
    first = (company or "").split()[0] if (company or "").split() else ""
    if len(first) < 2:
        return None
    # il verbo deve venire subito dopo il nome (che puo' avere altre parole maiuscole: "Blu Consulting")
    m = re.search(rf"\b[Ii]n\s+{re.escape(first)}(?:\s+[A-Z][\w&.'-]*)*\s+([a-zà-ù]+(?:ate|ete|ite))\b", body)
    return m.group(1) if m else None
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) is not None


def quality_problems(email: dict, lead: dict, sender: str, offer: str = "") -> list[str]:
    """Errori di forma di un'email; lista vuota se va bene. Non vede gli errori di senso.

    Gli anglicismi presenti nell'offerta o nei dati del lead (es. "Business Central") sono ammessi.
    """
    subject, body = email["subject"], email["body"]
    problems = []
    first_line = body.strip().splitlines()[0] if body.strip() else ""
    first_name = (lead.get("first_name") or (lead.get("full_name") or "").split(" ")[0]).strip()
    if not first_line.startswith("Gentile"):
        problems.append("il saluto non inizia con 'Gentile'")
    elif first_name and first_name.lower() not in first_line.lower():
        problems.append(f"il saluto non contiene il nome del destinatario ({first_name})")
    if "Cordiali saluti," not in body:
        problems.append("manca la chiusura 'Cordiali saluti,'")
    if sender and not body.rstrip().endswith(sender):
        problems.append(f"la firma finale non e' '{sender}'")
    if len(body.split()) > MAX_BODY_WORDS:
        problems.append(f"corpo troppo lungo ({len(body.split())} parole, max {MAX_BODY_WORDS})")
    if len(subject) > MAX_SUBJECT_CHARS:
        problems.append(f"oggetto troppo lungo ({len(subject)} caratteri)")
    text = f"{subject}\n{body}"
    problems += [f"chiusura non italiana: '{w}'" for w in FOREIGN_CLOSINGS if has_word(text, w)]
    problems += [f"esperienza del mittente inventata: '{w}'" for w in INVENTED_CLAIMS if w in text.lower()]
    allowed = f"{offer} {json.dumps(lead, ensure_ascii=False)}"
    problems += [f"anglicismo: '{w}'" for w in ANGLICISMS if has_word(text, w) and not has_word(allowed, w)]
    problems += [f"tono informale: '{w}'" for w in INFORMAL if has_word(text, w)]
    mangled = MANGLED.search(text)
    if mangled:
        problems.append(f"parola inglese o storpiata: '{mangled.group(0)}'")
    problems += [f"infinito troncato: '{m.group(0)}'" for m in TRUNCATED_INFINITIVE.finditer(text)
                 if m.group(1).lower() not in NOT_TRUNCATED]
    problems += [f"supposizione presentata come fatto: '{w}' (usare una domanda)"
                 for w in ASSUMED_FACTS if w in text.lower()]
    plural = PLURAL_YOU.search(body)
    if plural:
        problems.append(f"'voi' mescolato al Lei: '{plural.group(0)}'")
    verb = company_plural_verb(body, lead.get("company_name", ""))
    if verb:
        problems.append(f"'voi' rivolto all'azienda: '{verb}' (usare la terza persona)")
    if EMOJI.search(text):
        problems.append("contiene emoji")
    return problems


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
        who = lead.get("email") or lead.get("full_name")
        base_prompt = (
            f"Mittente: {sender}\nCosa proponiamo: {offer}\n\n"
            f"Dati del destinatario (JSON):\n{json.dumps(compact_lead(lead), ensure_ascii=False)}"
        )
        prompt, problems, rejected = base_prompt, [], None
        # Al massimo 2 tentativi: se l'email non passa i controlli si rigenera una volta, poi si scarta
        for attempt in range(1, MAX_ATTEMPTS + 1):
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
                    timeout=CLAUDE_TIMEOUT_SECS,
                )
            except anthropic.AuthenticationError:
                fail("ANTHROPIC_API_KEY rifiutata da Anthropic. Controlla la chiave nel .env", 2)
            except anthropic.APIError as e:
                problems = [f"API: {e}"]
                break
            spent += call_cost(msg.usage)
            try:
                slots = parse_slots(msg.content[0].text)
            except (ValueError, IndexError) as e:
                problems = [f"risposta non valida: {e}"]
                continue
            email = build_email(slots, lead, offer, sender)
            # controlli sulle due frasi + controlli di sempre sull'email montata
            problems = slot_problems(slots, lead) + quality_problems(email, lead, sender, offer)
            rejected = slots  # per capire nel Log perche' una frase e' stata scartata
            if not problems:
                emails.append({"lead": lead, **email, "slots": slots, "attempts": attempt})
                break
            prompt = (f"{base_prompt}\n\nUna versione precedente aveva questi errori, evitali: "
                      + "; ".join(problems))
        if stopped_for_budget:
            break
        if problems:
            technical = problems[0].startswith(("API:", "risposta non valida"))
            errors.append({"lead": who, "error": problems[0] if technical
                           else "controllo qualita': " + "; ".join(problems),
                           **({"frasi_scartate": rejected} if rejected and not technical else {})})

    result = {
        "status": "success" if not errors and not stopped_for_budget else "partial",
        "count": len(emails),
        "errors": errors,
        "stopped_for_budget": stopped_for_budget,
        "total_cost_usd": round(spent, 4),
        "claude_cost_usd": round(spent - apify_cost, 4),
        "budget_usd": MAX_BUDGET_USD,
        "model": MODEL,
        "emails": emails,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not emails:
        only_quality = bool(errors) and all(e["error"].startswith("controllo qualita'") for e in errors)
        fail("Nessuna email prodotta", 4 if only_quality and not stopped_for_budget else 3,
             errors=errors, total_cost_usd=round(spent, 4), claude_cost_usd=round(spent - apify_cost, 4))
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
