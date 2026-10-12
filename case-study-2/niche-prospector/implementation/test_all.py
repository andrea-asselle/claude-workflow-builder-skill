"""Test di tutti gli script RBI. API esterne sempre mockate.

Esecuzione: .venv\\Scripts\\python.exe -m pytest implementation/test_all.py -v
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import discover_companies
import find_leads
import find_people_linkedin
import google_auth
import pipeline
import run_log
import run_state
import sheet_export
import write_emails
from load_env import load_env

LEAD = {
    "first_name": "Mario", "last_name": "Rossi", "job_title": "CTO",
    "company_name": "Acme Srl", "email": "mario@acme.it", "industry": "software",
    "city": "Milano", "linkedin": "https://linkedin.com/in/mrossi", "company_website": "acme.it",
}


def _blocked(*a, **k):
    raise RuntimeError("Test non isolato: tentata chiamata a un servizio reale")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Sposta .tmp in una cartella temporanea, imposta env finto e blocca i client reali."""
    tmp = tmp_path / ".tmp"
    tmp.mkdir()
    for mod in (find_leads, write_emails, sheet_export, pipeline, discover_companies):
        monkeypatch.setattr(mod, "TMP_DIR", tmp)
    monkeypatch.setattr(find_leads, "OUTPUT_FILE", tmp / "leads.json")
    monkeypatch.setattr(discover_companies, "OUTPUT_FILE", tmp / "companies.json")
    monkeypatch.setattr(run_state, "TMP_DIR", tmp)
    monkeypatch.setattr(run_state, "STATE_FILE", tmp / "run_state.json")
    monkeypatch.setattr("load_env.load_env", lambda *a, **k: None)
    for mod in (find_leads, write_emails, sheet_export, pipeline, run_log, discover_companies, find_people_linkedin):
        monkeypatch.setattr(mod, "load_env", lambda *a, **k: None)
    # Il codice ricarica il .env: togliere le variabili non basta, i client vanno bloccati (script-rules §9)
    monkeypatch.setattr("gspread.authorize", _blocked)
    monkeypatch.setattr("find_leads.requests.post", _blocked)
    monkeypatch.setattr("anthropic.Anthropic", _blocked)
    monkeypatch.setenv("APIFY_TOKEN", "test-apify")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")
    monkeypatch.setenv("OUTREACH_OFFER", "Sviluppiamo automazioni su Power Platform.")
    monkeypatch.setenv("OUTREACH_SENDER", "Andrea")
    return tmp


def exit_code(fn, *args, **kwargs) -> int:
    with pytest.raises(SystemExit) as exc:
        fn(*args, **kwargs)
    return exc.value.code


# ---------- load_env ----------

class TestLoadEnv:
    def test_loads_without_overriding(self, tmp_path, monkeypatch):
        f = tmp_path / ".env"
        f.write_text('# c\nAAA_TEST="uno"\nBBB_TEST=due\n', encoding="utf-8")
        monkeypatch.setenv("BBB_TEST", "gia")
        monkeypatch.delenv("AAA_TEST", raising=False)
        load_env(f)
        import os
        assert os.environ["AAA_TEST"] == "uno"
        assert os.environ["BBB_TEST"] == "gia"

    def test_missing_file_is_noop(self, tmp_path):
        load_env(tmp_path / "nope.env")


# ---------- find_leads ----------

def apify_response(status=200, payload=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else []
    r.text = text
    return r


# Forma reale di un lead code_crafter (nomi dei campi verificati), con dati inventati
PERSON = {
    "first_name": "Mario", "last_name": "Rossi", "full_name": "Mario Rossi", "job_title": "CTO",
    "email": "mario.rossi@example.com", "mobile_number": "+39 000 000 0000",
    "linkedin": "https://linkedin.com/in/example", "company_name": "Example Srl",
    "company_website": "https://example.com", "industry": "information technology & services",
    "company_size": 30, "country": "Italy", "city": "Torino",
    "company_technologies": "microsoft azure, microsoft power apps",
}
KW = ["Power Apps", "Azure"]


def person(i: int, **kw) -> dict:
    """Lead di un'azienda diversa per ogni i (un solo contatto per azienda)."""
    return {**PERSON, "full_name": f"Persona {i}", "email": f"p{i}@azienda{i}.it",
            "company_website": f"https://azienda{i}.it", "company_name": f"Azienda {i}", **kw}


class TestFindLeads:
    @patch("find_leads.requests.post")
    def test_success(self, post, isolated):
        post.return_value = apify_response(payload=[person(1), person(2), person(3)])
        result = find_leads.run(3, ["CTO"], "italy", KW)
        assert result["count"] == 3
        assert result["apify_cost_usd"] == pytest.approx(0.02 + 3 * 0.002)
        assert json.loads((isolated / "leads.json").read_text(encoding="utf-8"))["count"] == 3
        assert post.call_args.kwargs["params"]["maxTotalChargeUsd"] == find_leads.MAX_APIFY_CHARGE_USD

    @patch("find_leads.requests.post")
    def test_actor_input(self, post, isolated):
        post.return_value = apify_response(payload=[PERSON])
        find_leads.run(2, ["CTO", "CIO"], "Italy", KW, ["Computer Software"])
        sent = post.call_args.kwargs["json"]
        assert sent["fetch_count"] == 4  # count * 2 per poter scartare
        assert sent["contact_job_title"] == ["CTO", "CIO"]
        assert sent["contact_location"] == ["italy"]
        assert sent["company_keywords"] == KW
        assert sent["company_industry"] == ["computer software"]
        assert "size" not in sent  # nessun limite di dimensione (decisione dell'utente)
        assert sent["email_status"] == ["validated"]
        assert sent["contact_not_job_title"] == find_leads.DEFAULT_EXCLUDE_TITLES.split(",")

    @patch("find_leads.requests.post")
    def test_fetch_capped_and_any_email(self, post, isolated):
        post.return_value = apify_response(payload=[PERSON])
        find_leads.run(5, ["CTO"], any_email=True)
        sent = post.call_args.kwargs["json"]
        assert sent["fetch_count"] == find_leads.MAX_FETCH
        assert "email_status" not in sent and "company_keywords" not in sent

    @patch("find_leads.requests.post")
    def test_discards_with_reason(self, post, isolated):
        engineer = {**PERSON, "full_name": "Anna Bianchi", "job_title": "Software Engineer"}
        abroad = {**PERSON, "full_name": "John Smith", "country": "Germany"}
        no_mail = {**PERSON, "full_name": "Luca Verdi", "email": ""}
        post.return_value = apify_response(payload=[engineer, abroad, no_mail, PERSON])
        result = find_leads.run(1, ["CTO"], "italy", KW)
        assert [l["full_name"] for l in result["leads"]] == ["Mario Rossi"]
        reasons = [d["reason"] for d in result["discarded"]]
        assert reasons[0].startswith("ruolo diverso") and reasons[1].startswith("paese diverso")
        assert reasons[2] == "email assente"
        assert result["apify_cost_usd"] == pytest.approx(0.02 + 4 * 0.002)

    @patch("find_leads.requests.post")
    def test_domains_input_and_filter(self, post, isolated):
        other = {**PERSON, "full_name": "Anna Bianchi", "company_domain": "altra.it",
                 "company_website": "https://altra.it"}
        mine = {**PERSON, "company_domain": "example.com"}
        post.return_value = apify_response(payload=[other, mine])
        result = find_leads.run(1, ["CTO"], domains=["https://www.Example.com/chi-siamo", "beta.it"])
        sent = post.call_args.kwargs["json"]
        assert sent["company_domain"] == ["example.com", "beta.it"]
        assert "size" not in sent  # niente filtro dimensione se si cerca per sito
        assert [l["full_name"] for l in result["leads"]] == ["Mario Rossi"]
        assert result["discarded"][0]["reason"] == "azienda non richiesta: altra.it"

    @patch("find_leads.requests.post")
    def test_domains_with_explicit_sizes(self, post, isolated):
        post.return_value = apify_response(payload=[{**PERSON, "company_domain": "example.com"}])
        find_leads.run(1, ["CTO"], sizes=["1-10"], domains=["example.com"])
        assert post.call_args.kwargs["json"]["size"] == ["1-10"]

    @patch("find_leads.requests.post")
    def test_require_terms_filters_on_description(self, post, isolated):
        uses_office = {**PERSON, "full_name": "Anna Bianchi", "company_description": "Agenzia di marketing",
                       "company_technologies": "office 365, microsoft dynamics"}  # strumenti usati: non contano
        partner = {**PERSON, "company_description": "Partner per Dynamics 365 Business Central",
                   "keywords": "erp, crm"}
        post.return_value = apify_response(payload=[uses_office, partner])
        result = find_leads.run(1, ["CTO"], terms=["Business Central", "Power Platform"], fetch=40)
        assert post.call_args.kwargs["json"]["fetch_count"] == 40
        assert [l["full_name"] for l in result["leads"]] == ["Mario Rossi"]
        assert result["leads"][0]["matched_terms"] == ["Business Central"]
        assert result["discarded"][0]["reason"].startswith("nessun termine")
        assert result["apify_max_charge_usd"] == pytest.approx(0.02 + 40 * 0.002)

    def test_fetch_limits(self):
        assert exit_code(find_leads.run, 1, ["CTO"], fetch=20) == 1  # oltre 10 serve --require-terms
        assert exit_code(find_leads.run, 1, ["CTO"], terms=["x"], fetch=51) == 1
        assert exit_code(find_leads.run, 3, ["CTO"], fetch=2) == 1  # meno di count

    def test_too_many_domains(self):
        assert exit_code(find_leads.run, 1, ["CTO"], domains=[f"d{i}.it" for i in range(11)]) == 1

    @pytest.mark.parametrize("title", ["Chief Executive Officer", "Co-Founder & CTO", "CEO & Founder"])
    def test_title_synonyms(self, title):
        assert find_leads.title_matches(title, ["CEO", "Founder"])

    def test_region_skips_country_check(self):
        assert find_leads.discard_reason({**PERSON, "country": ""}, ["CTO"], "piemonte, italy") is None

    @patch("find_leads.requests.post")
    def test_only_discarded_exit_4(self, post, isolated):
        post.return_value = apify_response(payload=[{**PERSON, "job_title": "Engineer"}])
        assert exit_code(find_leads.run, 3, ["CTO"]) == 4

    def test_too_many_job_titles(self):
        assert exit_code(find_leads.run, 1, [f"r{i}" for i in range(find_leads.MAX_JOB_TITLES + 1)]) == 1

    def test_invalid_size(self):
        assert exit_code(find_leads.run, 1, ["CTO"], sizes=["1-1000"]) == 1

    @patch("find_leads.requests.post")
    def test_company_inbox_not_a_lead(self, post, isolated):
        post.return_value = apify_response(payload=[{"email": "info@example.com"}])
        assert exit_code(find_leads.run, 3, ["CTO"]) == 4

    @pytest.mark.parametrize("count", [0, 6, -1])
    def test_count_out_of_range(self, count):
        assert exit_code(find_leads.run, count, ["CTO"]) == 1

    def test_missing_token(self, monkeypatch):
        monkeypatch.delenv("APIFY_TOKEN")
        assert exit_code(find_leads.run, 1, ["CTO"]) == 2

    @patch("find_leads.requests.post")
    def test_forbidden(self, post):
        post.return_value = apify_response(403, {"error": {"message": "no"}})
        assert exit_code(find_leads.run, 1, ["CTO"]) == 2

    @patch("find_leads.requests.post")
    def test_api_error(self, post):
        post.return_value = apify_response(500, text="boom")
        assert exit_code(find_leads.run, 1, ["CTO"]) == 3

    @patch("find_leads.requests.post")
    def test_not_a_list(self, post, isolated):
        post.return_value = apify_response(payload={"error": {"message": "strano"}})
        assert exit_code(find_leads.run, 1, ["CTO"]) == 3
        assert not (isolated / "leads.json").exists()

    @patch("find_leads.requests.post")
    @pytest.mark.parametrize("item", [{"error": "free plan cannot run via API"},
                                      {"message": "Users on the free Apify plan can run the actor through the UI"}])
    def test_error_item_is_not_a_lead(self, post, item, isolated):
        post.return_value = apify_response(payload=[item])
        assert exit_code(find_leads.run, 3, ["CTO"]) == 3
        assert not (isolated / "leads.json").exists()

    @patch("find_leads.requests.post")
    def test_network_error(self, post):
        post.side_effect = find_leads.requests.ConnectionError("down")
        assert exit_code(find_leads.run, 1, ["CTO"]) == 3

    @patch("find_leads.requests.post")
    def test_empty_result(self, post):
        post.return_value = apify_response(payload=[])
        assert exit_code(find_leads.run, 2, ["CTO"]) == 4


# ---------- find_leads v3: seconda linea (decisioni dell'utente, 2026-10-12) ----------

SECOND_LINE = find_leads.DEFAULT_JOB_TITLES.split(",")
OWNERS = find_leads.DEFAULT_EXCLUDE_TITLES.split(",")


def reason_for(title: str) -> str | None:
    lead = {**PERSON, "job_title": title}
    return find_leads.discard_reason(lead, SECOND_LINE, ["lombardy, italy"], exclude_titles=OWNERS)


class TestSecondLine:
    @pytest.mark.parametrize("title", [
        "CTO", "Chief Technology Officer", "CIO", "Chief Information Officer", "COO", "Chief Operating Officer",
        "IT Manager", "Responsabile IT", "Responsabile Sistemi Informativi", "Direttore Sistemi Informativi",
        "IT & Operations Manager", "Head of IT Operations", "Operations Manager", "Direttore Operativo",
        "Delivery Manager", "Head of Delivery", "Service Delivery Manager",
        "Head Of International Business Development & CIO",  # titolo reale dalla scoperta
        # Decisione dell'utente (2026-10-12): "Partner e CTO" si tiene
        "Partner e CTO", "Partner & CTO", "Company Partner & Chief Operating Officer",
        # v7, decisione dell'utente (2026-10-12): ruoli allargati, titoli reali visti su LinkedIn
        "Project Manager", "Project Manager and Senior Consultant SAP", "Capo Progetto",
        "BU Manager, Developer Lead - Prompt Engineer, Business Central, .NET, SQL Server, BI, ARXivar",
        "Business Unit Manager", "Head Of Business Intelligence", "BI Manager", "CxO",
    ])
    def test_second_line_kept(self, title):
        assert reason_for(title) is None

    @pytest.mark.parametrize("title", [
        "CEO", "Founder & CTO", "Co-Founder & CTO", "Titolare", "Amministratore Delegato", "Presidente e CTO",
        "Socio e Responsabile IT", "Managing Director & COO", "Founder & Project Manager",
    ])
    def test_owners_excluded(self, title):
        assert reason_for(title).startswith("titolare o socio")

    @pytest.mark.parametrize("title", [
        "Director of Sales",  # contiene "cto" ma non a parola intera
        "Sales Director", "Chief Strategy Officer", "Product Owner", "Delivery Partner", "Vice President IT",
        "Direttore Tecnico", "Software Engineer",
        "Responsabile tecnico", "Responsabile Tecnico",  # decisione dell'utente (2026-10-12): si esclude
    ])
    def test_other_roles_not_target(self, title):
        assert reason_for(title).startswith("ruolo diverso")

    def test_socio_does_not_contain_cio(self):
        assert not find_leads.title_matches("Socio", ["CIO"])

    def test_defaults_within_limits(self):
        assert len(SECOND_LINE) <= find_leads.MAX_JOB_TITLES

    def test_no_company_size_limit_by_default(self):
        # Decisione dell'utente (2026-10-12): nessun limite di dimensione, non solo PMI
        assert find_leads.DEFAULT_SIZES == ""

    @patch("find_leads.requests.post")
    def test_explicit_sizes_still_supported(self, post, isolated):
        post.return_value = apify_response(payload=[PERSON])
        find_leads.run(1, ["CTO"], sizes=["51-100"])
        assert post.call_args.kwargs["json"]["size"] == ["51-100"]

    @pytest.mark.parametrize("email,site,ok", [
        ("a@gruppoalfa.it", "https://www.gruppoalfa.it", True),
        ("a@mail.acme.it", "acme.it", True),
        ("m.verdi@altrogruppo.it", "https://www.gruppoalfa.it", False),  # caso reale dalla scoperta
        ("info@betaservizi.com", None, True),  # sito assente: non si puo' controllare
        ("a@acmesoft.it", "https://acmesoft.com", True),  # stesso nome, estensione diversa (prova v7, caso reale)
        ("a@omegadocs.it", "omegadocs.com", True),  # caso reale v7
        ("a@gmail.com", "https://acmesoft.com", False),
        ("a@acmesoft.co.uk", "acmesoft.com", False),  # nomi a piu' livelli: non si indovina
    ])
    def test_email_domain(self, email, site, ok):
        lead = {**PERSON, "email": email, "company_website": site}
        assert find_leads.email_domain_ok(lead) is ok
        reason = find_leads.discard_reason(lead, SECOND_LINE, "italy", exclude_titles=OWNERS)
        assert (reason is None) is ok

    @patch("find_leads.requests.post")
    def test_known_contacts_and_one_per_company(self, post, isolated):
        same_company = {**person(1), "full_name": "Collega", "email": "c@azienda1.it"}
        post.return_value = apify_response(payload=[person(0), person(1), same_company, person(2), person(3)])
        result = find_leads.run(5, SECOND_LINE, ["lombardy, italy", "lombardia, italy"],
                                known_emails={"p0@azienda0.it"}, known_domains={"azienda2.it"})
        assert [l["full_name"] for l in result["leads"]] == ["Persona 1", "Persona 3"]
        reasons = [d["reason"] for d in result["discarded"]]
        assert reasons == ["gia' nel foglio (stessa email)", "azienda gia' presa in questo giro",
                           "azienda gia' nel foglio: azienda2.it"]
        sent = post.call_args.kwargs["json"]
        assert sent["contact_location"] == ["lombardy, italy", "lombardia, italy"]

    @patch("find_leads.requests.post")
    def test_empty_reports_cost(self, post, isolated, capsys):
        post.return_value = apify_response(payload=[person(1, job_title="CEO")])
        assert exit_code(find_leads.run, 1, SECOND_LINE) == 4
        err = json.loads(capsys.readouterr().err)
        assert err["apify_cost_usd"] == pytest.approx(0.022)

    @pytest.mark.parametrize("n_domains,expected", [(8, 16), (10, 20), (2, 10)])
    @patch("find_leads.requests.post")
    def test_fetch_with_domains_two_per_site(self, post, isolated, n_domains, expected):
        """Giro reale v5: con 10 persone l'actor ne ha date 7 da 3 aziende; ora 2 per sito, max 20."""
        post.return_value = apify_response(payload=[person(0)])
        find_leads.run(5, SECOND_LINE, "italy", domains=[f"azienda{i}.it" for i in range(n_domains)])
        assert post.call_args.kwargs["json"]["fetch_count"] == expected

    def test_fetch_over_10_without_domains_refused(self):
        assert exit_code(find_leads.run, 5, SECOND_LINE, fetch=20) == 1

    def test_country_from_region(self):
        assert find_leads.discard_reason({**PERSON, "country": "Switzerland"}, ["CTO"],
                                         ["lombardy, italy"]).startswith("paese diverso")


# ---------- write_emails ----------

def claude_reply(text, inp=500, out=300):
    return SimpleNamespace(content=[SimpleNamespace(text=text)],
                           usage=SimpleNamespace(input_tokens=inp, output_tokens=out))


def write_leads_file(tmp, n=2, cost=0.024):
    f = tmp / "leads.json"
    f.write_text(json.dumps({"leads": [LEAD] * n, "apify_cost_usd": cost}), encoding="utf-8")
    return f


def email_json(body: str, subject: str = "Automazioni per l'IT di Acme") -> str:
    return json.dumps({"subject": subject, "body": body}, ensure_ascii=False)


GOOD_BODY = ("Gentile Mario Rossi,\n\nLe scrivo perche' Acme Srl potrebbe ridurre il lavoro manuale con "
             "automazioni su misura. Avrebbe 15 minuti per una breve chiamata?\n\nCordiali saluti,\nAndrea")
def slots_json(apertura: str = "Acme sviluppa software gestionale per aziende manifatturiere di Milano.",
               esempio: str = "In Acme le richieste di assistenza passano ancora da fogli Excel ed email?") -> str:
    """Risposta di Claude nello schema fisso: solo le due frasi."""
    return json.dumps({"apertura": apertura, "esempio": esempio}, ensure_ascii=False)


GOOD = slots_json()
BAD_SLOTS = slots_json(esempio="Nella Vostra azienda le richieste passano da fogli Excel?")  # 'voi'


class TestWriteEmails:
    @patch("anthropic.Anthropic")
    def test_success(self, anth, isolated):
        anth.return_value.messages.create.return_value = claude_reply(GOOD)
        result = write_emails.run(write_leads_file(isolated), "consulenza", "Andrea")
        assert result["status"] == "success" and result["count"] == 2
        assert 0.024 < result["total_cost_usd"] < write_emails.MAX_BUDGET_USD
        assert result["claude_cost_usd"] == pytest.approx(result["total_cost_usd"] - 0.024)
        assert (isolated / "emails.json").exists()
        assert anth.return_value.messages.create.call_args.kwargs["timeout"] == write_emails.CLAUDE_TIMEOUT_SECS

    @patch("anthropic.Anthropic")
    def test_json_wrapped_in_code_fence(self, anth, isolated):
        anth.return_value.messages.create.return_value = claude_reply("```json\n" + GOOD + "\n```")
        assert write_emails.run(write_leads_file(isolated, 1), "x", "Andrea")["count"] == 1

    def test_missing_input_file(self, isolated):
        assert exit_code(write_emails.run, isolated / "none.json", "x", "y") == 1

    def test_invalid_input_file(self, isolated):
        f = isolated / "leads.json"
        f.write_text("not json", encoding="utf-8")
        assert exit_code(write_emails.run, f, "x", "y") == 1

    def test_too_many_leads(self, isolated):
        assert exit_code(write_emails.run, write_leads_file(isolated, 6), "x", "y") == 1

    def test_missing_api_key(self, isolated, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY")
        assert exit_code(write_emails.run, write_leads_file(isolated), "x", "y") == 2

    def test_empty_leads(self, isolated):
        f = isolated / "leads.json"
        f.write_text(json.dumps({"leads": []}), encoding="utf-8")
        assert exit_code(write_emails.run, f, "x", "y") == 4

    @patch("anthropic.Anthropic")
    def test_api_error_all_fail(self, anth, isolated):
        import anthropic
        anth.return_value.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())
        assert exit_code(write_emails.run, write_leads_file(isolated, 1), "x", "Andrea") == 3

    @patch("anthropic.Anthropic")
    def test_bad_response_is_partial(self, anth, isolated):
        anth.return_value.messages.create.side_effect = [
            claude_reply(GOOD), claude_reply("niente json"), claude_reply("ancora niente")]
        result = write_emails.run(write_leads_file(isolated), "x", "Andrea")
        assert result["status"] == "partial" and result["count"] == 1 and len(result["errors"]) == 1
        assert result["errors"][0]["error"].startswith("risposta non valida")

    @patch("anthropic.Anthropic")
    def test_budget_stop(self, anth, isolated):
        anth.return_value.messages.create.return_value = claude_reply(GOOD)
        assert exit_code(write_emails.run, write_leads_file(isolated, 2, cost=0.499), "x", "Andrea") == 3
        anth.return_value.messages.create.assert_not_called()

    @patch("anthropic.Anthropic")
    def test_budget_counts_apify_cap(self, anth, isolated):
        f = isolated / "leads.json"
        f.write_text(json.dumps({"leads": [LEAD], "apify_cost_usd": 0.01, "apify_max_charge_usd": 0.4999}), encoding="utf-8")
        assert exit_code(write_emails.run, f, "x", "Andrea") == 3
        anth.return_value.messages.create.assert_not_called()

    def test_compact_lead_drops_empty_and_truncates(self):
        out = write_emails.compact_lead({"a": "", "b": None, "c": "x" * 1000, "d": 5})
        assert "a" not in out and "b" not in out
        assert len(out["c"]) == write_emails.MAX_FIELD_CHARS and out["d"] == 5


# ---------- write_emails v3: controlli di qualita' nel codice ----------

def problems(body: str, subject: str = "Oggetto", offer: str = "consulenza") -> list[str]:
    return write_emails.quality_problems({"subject": subject, "body": body}, LEAD, "Andrea", offer)


class TestQuality:
    def test_good_email_passes(self):
        assert problems(GOOD_BODY) == []

    @pytest.mark.parametrize("bad,expected", [
        (GOOD_BODY.replace("Cordiali saluti,", "Cordialement,"), "manca la chiusura"),  # errore reale v2
        (GOOD_BODY.replace("Cordiali saluti,", "Cordiali saluti, Best regards"), "chiusura non italiana"),
        (GOOD_BODY.replace("Le scrivo", "Ho aiutato aziende simili e Le scrivo"), "esperienza del mittente"),  # errore reale v2
        (GOOD_BODY.replace("Le scrivo", "Ho sviluppato soluzioni che aiutano reparti IT. Le scrivo"),
         "esperienza del mittente"),  # errore reale v3
        (GOOD_BODY.replace("Le scrivo", "Develuppo app. Le scrivo"), "storpiata"),  # errore reale v3
        (GOOD_BODY.replace("Le scrivo", "Spesso in realtà come la Sua, i team perdono tempo. Le scrivo"),
         "supposizione"),  # errore reale v3
        (GOOD_BODY.replace("Le scrivo", "In organizzazioni come Acme i team perdono tempo. Le scrivo"),
         "supposizione"),  # errore reale v3
        (GOOD_BODY.replace("chiamata", "call"), "anglicismo: 'call'"),
        (GOOD_BODY.replace("Le scrivo", "Ti scrivo"), "tono informale"),
        (GOOD_BODY.replace("Avrebbe", "Potrebbe interessarVi? Avrebbe"), "'voi' mescolato"),  # errore reale v3
        (GOOD_BODY.replace("Le scrivo", "Nella Vostra azienda Le scrivo"), "'voi' mescolato"),
        (GOOD_BODY.replace("Le scrivo", "Se avete tempo Le scrivo"), "'voi' mescolato"),
        (GOOD_BODY.replace("Avrebbe", "Potremmo supportarvi? Avrebbe"), "'voi' mescolato"),  # errore reale v3
        (GOOD_BODY.replace("Le scrivo", "In Acme gestite processi complessi. Le scrivo"), "rivolto all'azienda"),  # reale
        (GOOD_BODY.replace("Avrebbe", "\U0001F600 Avrebbe"), "emoji"),
        (GOOD_BODY.replace("Gentile Mario Rossi", "Buongiorno"), "saluto non inizia"),
        (GOOD_BODY.replace("Gentile Mario Rossi", "Gentile Luigi"), "nome del destinatario"),
        (GOOD_BODY.replace("\nAndrea", "\nIl team"), "firma finale"),
        (GOOD_BODY.replace("Le scrivo", "parola " * 160 + "Le scrivo"), "troppo lungo"),
        (GOOD_BODY.replace("Le scrivo", "Nel coordinar dei progetti i report passano da Excel? Le scrivo"),
         "infinito troncato"),  # errore reale v5
        (GOOD_BODY.replace("Le scrivo", "Sul gestir delle commesse Le scrivo"), "infinito troncato"),
    ])
    def test_problems_detected(self, bad, expected):
        assert any(expected in p for p in problems(bad)), problems(bad)

    @pytest.mark.parametrize("text", ["Nel server aziendale", "Nel webinar di giugno", "Nel coordinamento dei progetti",
                                      "Al partner Microsoft", "Nel provider cloud"])
    def test_truncated_infinitive_no_false_positives(self, text):
        assert not any("infinito troncato" in p for p in problems(GOOD_BODY.replace("Le scrivo", f"{text}. Le scrivo")))

    def test_lei_forms_not_flagged(self):
        assert problems(GOOD_BODY.replace("Le scrivo", "Le scrivo per la Sua azienda e vi")) == []
        # terza persona e participi plurali non sono "voi"
        ok = GOOD_BODY.replace("Le scrivo", "In Acme gestiscono attivita' automatizzate. Le scrivo")
        assert problems(ok) == []
        assert problems(GOOD_BODY.replace("Avrebbe", "Potrei supportarLa? Avrebbe")) == []

    @pytest.mark.parametrize("body,company,verb", [
        ("In Deltasoft gestite processi complessi", "Deltasoft", "gestite"),  # email reale 2026-10-12
        ("In Blu Consulting gestite i servizi", "Blu Consulting S.p.a.", "gestite"),
        ("Ho notato che in Blu Consulting gestiscono servizi IT", "Blu Consulting S.p.a.", None),
        ("In Acme gestiscono attivita' automatizzate", "Acme Srl", None),
    ])
    def test_company_plural_verb(self, body, company, verb):
        assert write_emails.company_plural_verb(body, company) == verb

    def test_long_subject(self):
        assert any("oggetto" in p for p in problems(GOOD_BODY, subject="x" * 120))

    def test_anglicism_allowed_when_in_offer(self):
        body = GOOD_BODY.replace("automazioni su misura", "Business Central")
        assert problems(body, offer="Implementiamo Business Central") == []
        assert any("business" in p for p in problems(body, offer="consulenza"))

    @patch("anthropic.Anthropic")
    def test_regenerates_once_then_ok(self, anth, isolated):
        anth.return_value.messages.create.side_effect = [claude_reply(BAD_SLOTS), claude_reply(GOOD)]
        result = write_emails.run(write_leads_file(isolated, 1), "consulenza", "Andrea")
        assert result["status"] == "success" and result["emails"][0]["attempts"] == 2
        second_prompt = anth.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "evitali" in second_prompt and "Vostra" in second_prompt

    @patch("anthropic.Anthropic")
    def test_discarded_after_two_bad(self, anth, isolated):
        bad = BAD_SLOTS
        anth.return_value.messages.create.side_effect = [claude_reply(GOOD), claude_reply(bad), claude_reply(bad)]
        result = write_emails.run(write_leads_file(isolated, 2), "consulenza", "Andrea")
        assert result["status"] == "partial" and result["count"] == 1
        assert result["errors"][0]["error"].startswith("controllo qualita'")
        assert anth.return_value.messages.create.call_count == 3  # mai piu' di 2 tentativi per lead

    @patch("anthropic.Anthropic")
    def test_all_discarded_exit_4(self, anth, isolated):
        anth.return_value.messages.create.return_value = claude_reply(BAD_SLOTS)
        assert exit_code(write_emails.run, write_leads_file(isolated, 1), "consulenza", "Andrea") == 4


# ---------- write_emails: schema fisso (decisione dell'utente, 2026-10-12) ----------

OFFER = "Sviluppo app e automazioni su Microsoft Power Platform per ridurre il lavoro manuale nei reparti IT."
LEAD_ESEMPIO = {"first_name": "Paolo", "last_name": "Bianchi", "company_name": "Neri Impianti Ltd"}
APERTURA = "Neri Impianti progetta impianti di climatizzazione marina con tecnologia inverter per yacht."
ESEMPIO = "In Neri Impianti i dati di collaudo passano ancora da fogli Excel ed email?"


class TestTemplate:
    def test_fixed_parts_and_slots(self):
        e = write_emails.build_email({"apertura": APERTURA, "esempio": ESEMPIO}, LEAD_ESEMPIO, OFFER, "Andrea Asselle")
        assert e["subject"] == "Meno lavoro manuale in Neri Impianti"
        assert e["body"] == (f"Gentile Paolo Bianchi,\n\n{APERTURA}\n\n{OFFER}\n\n{ESEMPIO}\n\n"
                             f"{write_emails.CALL_TO_ACTION}\n\nCordiali saluti,\nAndrea Asselle")
        assert write_emails.quality_problems(e, LEAD_ESEMPIO, "Andrea Asselle", OFFER) == []

    def test_subject_without_company(self):
        e = write_emails.build_email({"apertura": "x", "esempio": "y?"}, {"full_name": "Luca Neri"}, OFFER, "A")
        assert e["subject"] == write_emails.SUBJECT_FALLBACK and e["body"].startswith("Gentile Luca Neri,")

    @pytest.mark.parametrize("name,short", [("Blu Consulting S.p.a.", "Blu Consulting"),
                                            ("Gamma Soft S.r.l.", "Gamma Soft"), ("Omega Spa", "Omega"),
                                            ("Neri Impianti Ltd", "Neri Impianti"), ("Deltasoft", "Deltasoft")])
    def test_short_company(self, name, short):
        assert write_emails.short_company({"company_name": name}) == short

    def test_good_slots(self):
        assert write_emails.slot_problems({"apertura": APERTURA, "esempio": ESEMPIO}, LEAD_ESEMPIO) == []

    @pytest.mark.parametrize("apertura,esempio,expected", [
        (APERTURA, "In Neri Impianti i dati passano da Excel.", "deve essere una domanda"),
        ("Neri Impianti fa impianti?", ESEMPIO, "deve essere un'affermazione"),
        ("Neri Impianti fa impianti. Ha 40 dipendenti.", ESEMPIO, "piu' di una frase"),
        ("Sviluppo app su Power Platform per Neri Impianti.", ESEMPIO, "parla del mittente"),
        ("Un'azienda di Varese progetta impianti marini.", ESEMPIO, "non cita l'azienda"),
        (APERTURA + " parola" * 30, ESEMPIO, "troppo lunga"),
    ])
    def test_slot_problems(self, apertura, esempio, expected):
        probs = write_emails.slot_problems({"apertura": apertura, "esempio": esempio}, LEAD_ESEMPIO)
        assert any(expected in p for p in probs), probs

    @pytest.mark.parametrize("apertura", [
        "Softlab si occupa di sviluppo software e consulenza IT per le aziende di Reggio Emilia.",  # falso positivo reale
        "Neri Impianti S.p.A. progetta impianti di climatizzazione marina per yacht.",  # sigla con punti
    ])
    def test_slot_false_positives(self, apertura):
        lead = {**LEAD_ESEMPIO, "company_name": apertura.split()[0]}
        assert write_emails.slot_problems({"apertura": apertura, "esempio": ESEMPIO}, lead) == []

    @patch("anthropic.Anthropic")
    def test_rejected_slots_reported(self, anth, isolated):
        anth.return_value.messages.create.return_value = claude_reply(BAD_SLOTS)
        f = write_leads_file(isolated, 2)
        anth.return_value.messages.create.side_effect = [claude_reply(GOOD), claude_reply(BAD_SLOTS),
                                                         claude_reply(BAD_SLOTS)]
        result = write_emails.run(f, "consulenza", "Andrea")
        assert result["errors"][0]["frasi_scartate"]["esempio"].startswith("Nella Vostra")

    def test_slot_errors_still_caught_by_text_checks(self):
        """Il 'voi' e le esperienze inventate nelle frasi vengono presi dai controlli sull'email montata."""
        for esempio in ["In Neri Impianti gestite i collaudi su Excel?", "Ho sviluppato app simili, Le servono?"]:
            e = write_emails.build_email({"apertura": APERTURA, "esempio": esempio}, LEAD_ESEMPIO, OFFER, "A")
            assert write_emails.quality_problems(e, LEAD_ESEMPIO, "A", OFFER)

    def test_parse_slots(self):
        assert write_emails.parse_slots("```json\n" + slots_json("a  b", "c?") + "\n```") == {"apertura": "a b",
                                                                                             "esempio": "c?"}
        with pytest.raises(ValueError):
            write_emails.parse_slots('{"apertura": "x"}')


# ---------- sheet_export ----------

def write_emails_file(tmp, n=2):
    f = tmp / "emails.json"
    items = [{"lead": {**LEAD, "email": f"m{i}@acme.it"}, "subject": "S", "body": "B"} for i in range(n)]
    f.write_text(json.dumps({"emails": items}), encoding="utf-8")
    return f


def fake_worksheet(values):
    ws = MagicMock()
    ws.title = "Foglio1"
    ws.get_all_values.return_value = values
    return ws


class TestSheetExport:
    @patch("sheet_export.open_worksheet")
    def test_success_writes_header_and_rows(self, opener, isolated):
        ws = fake_worksheet([])
        opener.return_value = ws
        result = sheet_export.run(write_emails_file(isolated), None)
        assert result["rows_written"] == 2
        ws.update.assert_called_once()
        rows = ws.append_rows.call_args.args[0]
        assert rows[0][sheet_export.HEADERS.index("Stato")] == sheet_export.STATUS_DRAFT
        assert rows[0][sheet_export.HEADERS.index("Email lead")] == "m0@acme.it"

    @patch("sheet_export.open_worksheet")
    def test_skips_duplicates(self, opener, isolated):
        ws = fake_worksheet([sheet_export.HEADERS, ["", "", "", "", "", "", "M0@acme.it"]])
        opener.return_value = ws
        result = sheet_export.run(write_emails_file(isolated), None)
        assert result["rows_written"] == 1 and result["skipped_duplicates"] == 1
        ws.update.assert_not_called()

    @patch("sheet_export.open_worksheet")
    def test_all_duplicates_exit_4(self, opener, isolated):
        ws = fake_worksheet([sheet_export.HEADERS, ["", "", "", "", "", "", "m0@acme.it"]])
        opener.return_value = ws
        assert exit_code(sheet_export.run, write_emails_file(isolated, 1), None) == 4

    def test_missing_input(self, isolated):
        assert exit_code(sheet_export.run, isolated / "none.json", None) == 1

    def test_too_many_rows(self, isolated):
        assert exit_code(sheet_export.run, write_emails_file(isolated, 6), None) == 1

    def test_missing_sheet_id(self, isolated, monkeypatch):
        monkeypatch.delenv("GOOGLE_SHEET_ID")
        assert exit_code(sheet_export.run, write_emails_file(isolated), None) == 2

    @patch("sheet_export.get_credentials", side_effect=google_auth.GoogleAuthError("manca"))
    def test_missing_credentials(self, _creds, isolated):
        assert exit_code(sheet_export.run, write_emails_file(isolated), None) == 2

    @patch("sheet_export.open_worksheet")
    def test_api_error_on_write(self, opener, isolated):
        import gspread
        ws = fake_worksheet([sheet_export.HEADERS])
        resp = MagicMock(status_code=500, text="err")
        resp.json.return_value = {"error": {"code": 500, "message": "err", "status": "X"}}
        ws.append_rows.side_effect = gspread.exceptions.APIError(resp)
        opener.return_value = ws
        assert exit_code(sheet_export.run, write_emails_file(isolated), None) == 3

    def test_pick_fallback_keys(self):
        assert sheet_export.pick({"title": "CTO"}, "job_title", "title") == "CTO"
        assert sheet_export.pick({}, "a", "b") == ""

    def test_full_name_split_and_mapping(self):
        lead = {"full_name": "Mario Rossi", "company": "Acme", "domain": "acme.it", "email": "mario@acme.it"}
        row = sheet_export.to_row({"lead": lead, "subject": "S", "body": "B"}, "2026-09-30")
        h = sheet_export.HEADERS
        assert row[h.index("Nome")] == "Mario" and row[h.index("Cognome")] == "Rossi"
        assert row[h.index("Azienda")] == "Acme" and row[h.index("Sito")] == "acme.it"

    def test_invisible_chars_removed_from_title(self):
        # caso reale 2026-10-12
        assert sheet_export.clean_title("​group Chief Information Officer") == "group Chief Information Officer"

    def test_tag_prefixes_status(self):
        row = sheet_export.to_row({"lead": PERSON, "subject": "S", "body": "B"}, "2026-09-30", "TEST")
        assert row[sheet_export.HEADERS.index("Stato")] == "TEST - " + sheet_export.STATUS_DRAFT

    def test_real_themineworks_fields(self):
        lead = {"company": "Example Spa", "domain": "example.com", "name": "Jane Doe Smith",
                "job_title": "Logistic&Planning Manager at ...", "email": "j@example.com",
                "email_confidence": "guessed", "linkedin_url": "https://linkedin.com/in/x"}
        row = sheet_export.to_row({"lead": lead, "subject": "S", "body": "B"}, "2026-09-30")
        h = sheet_export.HEADERS
        assert row[h.index("Nome")] == "Jane" and row[h.index("Cognome")] == "Doe Smith"
        assert row[h.index("Ruolo")] == "Logistic&Planning Manager"
        assert row[h.index("Origine email")] == "guessed"
        assert row[h.index("LinkedIn")] == "https://linkedin.com/in/x"

    def test_code_crafter_fields(self):
        row = sheet_export.to_row({"lead": PERSON, "subject": "S", "body": "B"}, "2026-10-01")
        h = sheet_export.HEADERS
        assert row[h.index("Nome")] == "Mario" and row[h.index("Cognome")] == "Rossi"
        assert row[h.index("Ruolo")] == "CTO"
        assert row[h.index("Azienda")] == "Example Srl"
        assert row[h.index("Sito")] == "https://example.com"
        assert row[h.index("Email lead")] == "mario.rossi@example.com"
        assert row[h.index("Telefono")] == "+39 000 000 0000"
        assert row[h.index("LinkedIn")] == "https://linkedin.com/in/example"
        # code_crafter non restituisce un campo di affidabilita' dell'email
        assert row[h.index("Origine email")] == ""

    def test_known_contacts(self):
        h = sheet_export.HEADERS
        row = [""] * len(h)
        row[h.index("Email lead")], row[h.index("Sito")] = " Mario@Acme.it ", "https://www.acme.it/chi-siamo"
        emails, domains = sheet_export.known_contacts([h, row, ["solo data"]])
        assert emails == {"mario@acme.it"} and domains == {"acme.it"}
        assert sheet_export.known_contacts([]) == (set(), set())


# ---------- run_log ----------

def log_values(*rows: dict) -> list[list[str]]:
    return [run_log.LOG_HEADERS] + [[str(r.get(h, "")) for h in run_log.LOG_HEADERS] for r in rows]


class TestRunLog:
    def test_month_spend(self):
        values = log_values({"Data": "2026-10-05 06:00 UTC", "Costo totale $": "0.05"},
                            {"Data": "2026-10-12 06:00 UTC", "Costo totale $": "0,04"},
                            {"Data": "2026-09-28 06:00 UTC", "Costo totale $": "0.5"})
        assert run_log.month_spend(values, "2026-10") == pytest.approx(0.09)
        assert run_log.month_spend([], "2026-10") == 0

    @pytest.mark.parametrize("esito,costo,done", [("ok", "0.05", True), ("vuoto", "0.03", True),
                                                  ("errore", "0", False), ("errore", "0.03", True),
                                                  ("saltato", "0", False)])
    def test_run_already_done(self, esito, costo, done):
        values = log_values({"Run id": "2026-W42", "Esito": esito, "Costo totale $": costo})
        assert run_log.run_already_done(values, "2026-W42") is done
        assert run_log.run_already_done(values, "2026-W43") is False

    def test_append_log_order_and_json(self):
        ws = MagicMock()
        run_log.append_log(ws, {"Esito": "ok", "Dettagli": {"a": 1}, "Run id": "x", "Scarti": "y" * 5000})
        row = ws.append_rows.call_args.args[0][0]
        h = run_log.LOG_HEADERS
        assert row[h.index("Esito")] == "ok" and row[h.index("Run id")] == "x"
        assert json.loads(row[h.index("Dettagli")]) == {"a": 1}
        assert len(row[h.index("Scarti")]) == run_log.MAX_CELL_CHARS

    def test_log_worksheet_created_with_header(self):
        import gspread
        sp = MagicMock()
        sp.worksheet.side_effect = gspread.exceptions.WorksheetNotFound("Log")
        run_log.log_worksheet(sp)
        sp.add_worksheet.assert_called_once()
        sp.add_worksheet.return_value.update.assert_called_once_with(range_name="A1", values=[run_log.LOG_HEADERS])

    def test_existing_log_with_other_columns_is_refused(self):
        """Caso reale 2026-10-12: la scheda Log della vecchia automazione ha colonne diverse."""
        sp = MagicMock()
        sp.worksheet.return_value.row_values.return_value = ["Data", "Run Apify", "Esito", "Lead ricevuti"]
        with pytest.raises(run_log.SheetError):
            run_log.log_worksheet(sp)
        sp.worksheet.return_value.append_rows.assert_not_called()
        assert run_log.LOG_TITLE != "Log"

    def test_existing_empty_log_gets_header(self):
        sp = MagicMock()
        sp.worksheet.return_value.row_values.return_value = []
        sp.worksheet.return_value.col_count = 26
        ws = run_log.log_worksheet(sp)
        ws.update.assert_called_once_with(range_name="A1", values=[run_log.LOG_HEADERS])

    def test_v4_log_gets_new_columns_at_the_end(self):
        """La scheda "Log outreach" della v4 ha 15 colonne: le nuove si aggiungono in coda, i dati restano."""
        sp = MagicMock()
        ws = sp.worksheet.return_value
        ws.row_values.return_value = run_log.LOG_HEADERS[:15]
        ws.col_count = 15
        run_log.log_worksheet(sp)
        ws.add_cols.assert_called_once_with(len(run_log.LOG_HEADERS) - 15)
        ws.update.assert_called_once_with(range_name="A1", values=[run_log.LOG_HEADERS])
        assert run_log.LOG_HEADERS[14] == "Dettagli"  # le colonne vecchie non si spostano

    def test_seen_slugs_and_append(self):
        values = [run_log.SEEN_HEADERS, ["2026-10-12", "W42", "Acme-Srl", "Acme", "acme.it", "nessun contatto"],
                  ["2026-10-12", "W42", "", "Senza slug", "", ""]]
        assert run_log.seen_slugs(values) == {"acme-srl"}
        assert run_log.seen_slugs([]) == set()
        ws = MagicMock()
        run_log.append_seen(ws, [{"Slug LinkedIn": "beta", "Esito": "scartata: sito assente"}])
        row = ws.append_rows.call_args.args[0][0]
        assert row[run_log.SEEN_HEADERS.index("Slug LinkedIn")] == "beta"
        run_log.append_seen(ws, [])
        assert ws.append_rows.call_count == 1

    def test_missing_sheet_id(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_SHEET_ID")
        with pytest.raises(run_log.SheetError) as e:
            run_log.open_spreadsheet()
        assert e.value.code == 2


# ---------- pipeline (orchestratore del giro automatico) ----------

MONDAY = date(2026, 10, 12)


def company_row(i: int) -> dict:
    """Azienda valida come la restituisce discover_companies (dominio uguale a quello di person(i))."""
    return {"name": f"Azienda {i}", "domain": f"azienda{i}.it", "slug": f"azienda-{i}",
            "linkedin": f"https://www.linkedin.com/company/azienda-{i}/", "microsoft_terms": ["business central"]}


def fake_discover(n=5, cost=0.03):
    def _run(terms, max_companies, seen, place="Italia", known_domains=None, **kw):
        fake_discover.kwargs = {"terms": terms, "max_companies": max_companies, "seen": seen, "place": place,
                                "known_domains": known_domains}
        return {"status": "success", "slugs_found": n + 3, "companies": [company_row(i) for i in range(n)],
                "discarded": [{"name": "Estera", "slug": "estera", "domain": "estera.si",
                               "reason": "sede non in Italia: SI"}],
                "cost_usd": cost}
    return _run


@pytest.fixture
def sheet(monkeypatch):
    """Foglio finto: sheet1 con un lead gia' presente, scheda Log e scheda Aziende viste vuote.
    Scoperta aziende finta (5 aziende); ripiego LinkedIn finto che non trova nessuno."""
    h = sheet_export.HEADERS
    existing = [""] * len(h)
    existing[h.index("Email lead")], existing[h.index("Sito")] = "old@vecchia.it", "vecchia.it"
    sp = MagicMock()
    sp.sheet1.get_all_values.return_value = [h, existing]
    log_ws = MagicMock()
    log_ws.get_all_values.return_value = [run_log.LOG_HEADERS]
    seen_ws = MagicMock()
    seen_ws.get_all_values.return_value = [run_log.SEEN_HEADERS]
    monkeypatch.setattr(run_log, "open_spreadsheet", lambda: sp)
    monkeypatch.setattr(run_log, "log_worksheet", lambda _sp: log_ws)
    monkeypatch.setattr(run_log, "seen_worksheet", lambda _sp: seen_ws)
    monkeypatch.setattr(discover_companies, "run", fake_discover())
    monkeypatch.setattr(find_people_linkedin, "run", fake_linkedin())
    return SimpleNamespace(sp=sp, log=log_ws, seen=seen_ws)


def logged(sheet) -> dict:
    """Ultima riga scritta nel Log come dizionario."""
    row = sheet.log.append_rows.call_args.args[0][0]
    return dict(zip(run_log.LOG_HEADERS, row))


def seen_rows(sheet) -> list[dict]:
    rows = sheet.seen.append_rows.call_args.args[0]
    return [dict(zip(run_log.SEEN_HEADERS, r)) for r in rows]


def fake_find(isolated, n=5, cost=0.04, returned=10):
    def _run(count, job_titles, locations, **kw):
        fake_find.kwargs = {"count": count, "job_titles": job_titles, "locations": locations, **kw}
        data = {"status": "success", "count": n, "returned_by_actor": returned, "apify_cost_usd": cost,
                "apify_max_charge_usd": cost, "discarded": [{"reason": "ruolo diverso: X"}] * (returned - n),
                "leads": [person(i) for i in range(n)]}
        (isolated / "leads.json").write_text(json.dumps(data), encoding="utf-8")
        return data
    return _run


def fake_linkedin(found: tuple[int, ...] = (), cost=0.02):
    """Ripiego LinkedIn finto: trova un contatto per le aziende con indice in found."""
    def _run(companies, job_titles, max_profiles=None, **kw):
        fake_linkedin.companies = [c["domain"] for c in companies]
        leads = [{**person(i), "source": "linkedin-employees", "company_domain": f"azienda{i}.it"}
                 for i in found if f"azienda{i}.it" in fake_linkedin.companies]
        if not leads:
            find_leads.fail("Nessuna persona valida trovata su LinkedIn", 4, returned_by_actor=2,
                            discarded=[{"reason": "ruolo diverso: Sales"}], apify_cost_usd=cost)
        return {"status": "success", "count": len(leads), "returned_by_actor": len(leads), "discarded": [],
                "apify_cost_usd": cost, "leads": leads}
    fake_linkedin.companies = None
    return _run


def fake_write(isolated, n=5, claude=0.01, errors=None):
    def _run(leads_file, offer, sender):
        fake_write.args = (offer, sender)
        fake_write.leads = json.loads(Path(leads_file).read_text(encoding="utf-8"))
        data = {"status": "partial" if errors else "success", "count": n, "errors": errors or [],
                "stopped_for_budget": False, "claude_cost_usd": claude,
                "emails": [{"lead": person(i), "subject": "S", "body": "B"} for i in range(n)]}
        (isolated / "emails.json").write_text(json.dumps(data), encoding="utf-8")
        return data
    return _run


def fake_export(n=5, skipped=0):
    def _run(input_file, worksheet, tag=None):
        fake_export.tag = tag
        return {"status": "success", "rows_written": n, "skipped_duplicates": skipped}
    return _run


def failing(code: int, **extra):
    def _run(*a, **k):
        find_leads.fail("errore finto", code, **extra)
    return _run


class TestPipeline:
    def test_full_run_ok(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(find_leads, "run", fake_find(isolated))
        monkeypatch.setattr(find_people_linkedin, "run", _blocked)  # 5 lead su 5: niente ripiego
        monkeypatch.setattr(write_emails, "run", fake_write(isolated))
        monkeypatch.setattr(sheet_export, "run", fake_export())
        code, summary = pipeline.run(today=MONDAY, trigger="cron")
        assert code == 0 and summary["Esito"] == "ok"
        row = logged(sheet)
        assert row["Run id"] == "2026-W42" and row["Regione"] == "Lombardia" and row["Avvio"] == "cron"
        assert row["Parole chiave"] == "Business Central, Power Platform"
        assert float(row["Costo Apify $"]) == pytest.approx(0.07)  # scoperta 0,03 + code_crafter 0,04
        assert float(row["Costo totale $"]) == pytest.approx(0.08)
        assert row["Aziende trovate"] == "8" and row["Aziende valide"] == "5"
        assert row["Scarti"] == "sede non in Italia x1; ruolo diverso x5"
        # scoperta: parole chiave e regione della settimana, aziende gia' viste e gia' nel foglio
        assert fake_discover.kwargs["terms"] == ["Business Central", "Power Platform"]
        assert fake_discover.kwargs["place"] == "Lombardia"
        assert fake_discover.kwargs["known_domains"] == {"vecchia.it"}
        # persone: solo nei siti trovati, seconda linea, contatti gia' nel foglio scartati prima di Claude
        assert fake_find.kwargs["domains"] == [f"azienda{i}.it" for i in range(5)]
        assert fake_find.kwargs["locations"] == "italy"
        assert fake_find.kwargs["known_emails"] == {"old@vecchia.it"}
        assert fake_find.kwargs["known_domains"] == {"vecchia.it"}
        assert fake_find.kwargs["job_titles"] == SECOND_LINE
        assert fake_write.args == ("Sviluppiamo automazioni su Power Platform.", "Andrea")
        # il budget di write_emails vede la spesa Apify di tutti gli step
        assert fake_write.leads["apify_cost_usd"] == pytest.approx(0.07)
        assert fake_export.tag is None

    def test_linkedin_only_for_uncovered_companies(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(find_leads, "run", fake_find(isolated, n=2))
        monkeypatch.setattr(find_people_linkedin, "run", fake_linkedin(found=(3,)))
        monkeypatch.setattr(write_emails, "run", fake_write(isolated, n=3))
        monkeypatch.setattr(sheet_export, "run", fake_export(n=3))
        code, _ = pipeline.run(today=MONDAY)
        assert fake_linkedin.companies == ["azienda2.it", "azienda3.it", "azienda4.it"]
        assert [l["email"] for l in fake_write.leads["leads"]] == ["p0@azienda0.it", "p1@azienda1.it",
                                                                  "p3@azienda3.it"]
        row = logged(sheet)
        assert code == 4 and row["Esito"] == "parziale" and row["Lead tenuti"] == "3"
        assert float(row["Costo Apify $"]) == pytest.approx(0.03 + 0.04 + 0.02)
        esiti = {r["Sito"]: r["Esito"] for r in seen_rows(sheet)}
        assert esiti["azienda0.it"] == "contatto: CTO (code_crafter)"
        assert esiti["azienda3.it"] == "contatto: CTO (linkedin-employees)"
        assert esiti["azienda2.it"] == "nessun contatto"
        assert esiti["estera.si"] == "scartata: sede non in Italia: SI"

    def test_owner_only_in_small_uncovered_companies(self, isolated, sheet, monkeypatch):
        """Decisione dell'utente (2026-10-12): titolare solo nelle aziende fino a 50 dipendenti e solo se la
        seconda linea non si trova; nelle altre aziende mai."""
        sizes = {0: 10, 1: 200, 2: 10, 3: 50, 4: 51}
        companies = [{**company_row(i), "employee_range": {"start": 1, "end": e}} for i, e in sizes.items()]
        monkeypatch.setattr(discover_companies, "run", lambda *a, **k: {
            "status": "success", "slugs_found": 5, "companies": companies, "discarded": [], "cost_usd": 0.03})
        calls = []

        def find(count, job_titles, location, domains=None, exclude_titles=None, **kw):
            calls.append({"titles": job_titles, "domains": domains, "exclude": exclude_titles})
            owner_call = job_titles == pipeline.OWNER_TITLES
            wanted = ["azienda2.it"] if owner_call else ["azienda0.it"]  # azienda0: seconda linea trovata
            leads = [{**person(int(d[7])), "job_title": "CEO" if owner_call else "CTO"} for d in wanted]
            return {"status": "success", "count": len(leads), "returned_by_actor": 2, "apify_cost_usd": 0.022,
                    "discarded": [], "leads": leads}
        monkeypatch.setattr(find_leads, "run", find)
        monkeypatch.setattr(find_people_linkedin, "run", fake_linkedin())
        monkeypatch.setattr(write_emails, "run", fake_write(isolated, n=2))
        monkeypatch.setattr(sheet_export, "run", fake_export(n=2))
        pipeline.run(today=MONDAY)
        assert len(calls) == 2
        assert calls[0]["titles"] == SECOND_LINE and calls[0]["exclude"] is None  # prima sempre la seconda linea
        assert calls[1]["titles"] == pipeline.OWNER_TITLES and calls[1]["exclude"] == []
        assert calls[1]["domains"] == ["azienda2.it", "azienda3.it"]  # piccole e ancora scoperte (0 ha il CTO)
        assert fake_linkedin.companies == ["azienda1.it", "azienda3.it", "azienda4.it"]
        esiti = {r["Sito"]: r["Esito"] for r in seen_rows(sheet)}
        assert esiti["azienda0.it"] == "contatto: CTO (code_crafter)"
        assert esiti["azienda2.it"] == "contatto: CEO (code_crafter)"
        assert logged(sheet)["Lead tenuti"] == "2"

    def test_no_owner_search_without_small_companies(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(find_leads, "run", fake_find(isolated, n=2))  # company_row: dimensione sconosciuta
        monkeypatch.setattr(write_emails, "run", fake_write(isolated, n=2))
        monkeypatch.setattr(sheet_export, "run", fake_export(n=2))
        pipeline.run(today=MONDAY)
        assert fake_find.kwargs["job_titles"] == SECOND_LINE  # unica chiamata: nessuna ricerca titolari

    def test_is_small(self):
        assert pipeline.is_small({"employee_range": {"start": 11, "end": 50}})
        assert not pipeline.is_small({"employee_range": {"start": 51, "end": 200}})
        assert not pipeline.is_small({"employee_range": None}) and not pipeline.is_small({})

    def test_seen_companies_passed_to_discovery(self, isolated, sheet, monkeypatch):
        sheet.seen.get_all_values.return_value = [run_log.SEEN_HEADERS,
                                                  ["2026-10-05", "W41", "Vista-Srl", "Vista", "vista.it", "x"]]
        monkeypatch.setattr(find_leads, "run", fake_find(isolated))
        monkeypatch.setattr(write_emails, "run", fake_write(isolated))
        monkeypatch.setattr(sheet_export, "run", fake_export())
        pipeline.run(today=MONDAY)
        assert fake_discover.kwargs["seen"] == {"vista-srl"}
        assert len(seen_rows(sheet)) == 6 and seen_rows(sheet)[0]["Run id"] == "2026-W42"

    def test_no_companies_stops_before_people_search(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(discover_companies, "run", failing(
            4, cost_usd=0.015, slugs_found=2,
            discarded=[{"name": "Podcast", "slug": "podcast", "domain": "", "reason": "sito assente"}]))
        monkeypatch.setattr(find_leads, "run", _blocked)
        monkeypatch.setattr(find_people_linkedin, "run", _blocked)
        code, _ = pipeline.run(today=MONDAY)
        row = logged(sheet)
        assert code == 4 and row["Esito"] == "vuoto" and float(row["Costo Apify $"]) == pytest.approx(0.015)
        # anche le aziende scartate sono pagate: il prossimo giro non le ricontrolla
        assert seen_rows(sheet)[0]["Slug LinkedIn"] == "podcast"

    def test_no_leads_logs_apify_cost(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(find_leads, "run", failing(4, apify_cost_usd=0.04, returned_by_actor=10,
                                                       discarded=[{"reason": "titolare o socio: CEO"}]))
        monkeypatch.setattr(write_emails, "run", _blocked)
        code, _ = pipeline.run(today=MONDAY)
        row = logged(sheet)
        assert code == 4 and row["Esito"] == "vuoto"
        assert fake_linkedin.companies == [f"azienda{i}.it" for i in range(5)]  # ripiego su tutte
        assert float(row["Costo Apify $"]) == pytest.approx(0.03 + 0.04 + 0.02)
        assert row["Scarti"] == "sede non in Italia x1; titolare o socio x1; ruolo diverso x1"

    def test_code_crafter_error_linkedin_still_tried(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(find_leads, "run", failing(3))
        monkeypatch.setattr(find_people_linkedin, "run", fake_linkedin(found=(0, 1)))
        monkeypatch.setattr(write_emails, "run", fake_write(isolated, n=2))
        monkeypatch.setattr(sheet_export, "run", fake_export(n=2))
        code, summary = pipeline.run(today=MONDAY)
        assert code == 4 and summary["Esito"] == "parziale"
        assert "find_leads" in logged(sheet)["Dettagli"]

    def test_missing_offer_stops_before_spending(self, isolated, sheet, monkeypatch):
        monkeypatch.delenv("OUTREACH_OFFER")
        monkeypatch.setattr(discover_companies, "run", _blocked)
        code, summary = pipeline.run(today=MONDAY)
        assert code == 1 and logged(sheet)["Esito"] == "errore"
        assert "OUTREACH_OFFER" in logged(sheet)["Dettagli"]

    def test_same_week_not_repeated(self, isolated, sheet, monkeypatch):
        sheet.log.get_all_values.return_value = log_values({"Run id": "2026-W42", "Esito": "ok",
                                                            "Costo totale $": "0.05"})
        monkeypatch.setattr(discover_companies, "run", _blocked)
        code, _ = pipeline.run(today=MONDAY)
        assert code == 4 and logged(sheet)["Esito"] == "saltato"

    def test_monthly_cap(self, isolated, sheet, monkeypatch):
        sheet.log.get_all_values.return_value = log_values({"Data": "2026-10-05 06:00 UTC", "Run id": "x",
                                                            "Esito": "ok", "Costo totale $": "2.10"})
        monkeypatch.setattr(discover_companies, "run", _blocked)
        code, _ = pipeline.run(today=MONDAY)
        assert code == 4 and "tetto mensile" in logged(sheet)["Dettagli"]

    def test_unexpected_error_still_logged(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(find_leads, "run", fake_find(isolated))
        monkeypatch.setattr(write_emails, "run", lambda *a, **k: 1 / 0)
        code, _ = pipeline.run(today=MONDAY)
        row = logged(sheet)
        assert code == 3 and row["Esito"] == "errore" and "ZeroDivisionError" in row["Dettagli"]
        assert float(row["Costo Apify $"]) == pytest.approx(0.07)  # il costo gia' speso resta nel riepilogo

    def test_partial(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(find_leads, "run", fake_find(isolated, n=3))
        monkeypatch.setattr(write_emails, "run", fake_write(isolated, n=2, errors=[{"lead": "x", "error": "q"}]))
        monkeypatch.setattr(sheet_export, "run", fake_export(n=2))
        code, _ = pipeline.run(today=MONDAY)
        row = logged(sheet)
        assert code == 4 and row["Esito"] == "parziale"
        assert row["Lead tenuti"] == "3" and row["Email scartate"] == "1" and row["Righe scritte"] == "2"

    def test_dry_run_writes_no_rows(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(find_leads, "run", fake_find(isolated))
        monkeypatch.setattr(write_emails, "run", fake_write(isolated))
        monkeypatch.setattr(sheet_export, "run", _blocked)
        code, _ = pipeline.run(today=MONDAY, dry_run=True, tag="TEST")
        row = logged(sheet)
        assert code == 0 and row["Esito"] == "prova" and row["Run id"].startswith("TEST-2026-W42")
        # in prova le aziende non si segnano come viste: il giro vero deve poterle usare
        sheet.seen.append_rows.assert_not_called()

    def test_reuse_leads_skips_apify(self, isolated, sheet, monkeypatch):
        fake_find(isolated)(5, [], [])  # leads.json gia' pagato
        monkeypatch.setattr(discover_companies, "run", _blocked)
        monkeypatch.setattr(find_leads, "run", _blocked)
        monkeypatch.setattr(write_emails, "run", fake_write(isolated))
        monkeypatch.setattr(sheet_export, "run", fake_export())
        code, _ = pipeline.run(today=MONDAY, reuse_leads=True, tag="TEST")
        assert code == 0 and float(logged(sheet)["Costo Apify $"]) == 0 and fake_export.tag == "TEST"

    def test_seen_write_failure_reported_not_fatal(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(find_leads, "run", fake_find(isolated))
        monkeypatch.setattr(write_emails, "run", fake_write(isolated))
        monkeypatch.setattr(sheet_export, "run", fake_export())
        sheet.seen.append_rows.side_effect = RuntimeError("quota")
        code, summary = pipeline.run(today=MONDAY)
        assert code == 0 and "quota" in summary["Dettagli"]["aziende_viste_error"]

    def test_sheet_unreachable_no_spend(self, isolated, monkeypatch):
        def no_sheet():
            raise run_log.SheetError("foglio non condiviso", 2)
        monkeypatch.setattr(run_log, "open_spreadsheet", no_sheet)
        monkeypatch.setattr(discover_companies, "run", _blocked)
        code, summary = pipeline.run(today=MONDAY)
        assert code == 2 and summary["Esito"] == "errore"

    def test_log_write_failure_reported(self, isolated, sheet, monkeypatch):
        monkeypatch.setattr(find_leads, "run", fake_find(isolated))
        monkeypatch.setattr(write_emails, "run", fake_write(isolated))
        monkeypatch.setattr(sheet_export, "run", fake_export())
        sheet.log.append_rows.side_effect = RuntimeError("quota")
        code, summary = pipeline.run(today=MONDAY)
        assert code == 3 and "quota" in summary["Dettagli"]["log_error"]

    def test_count_limit(self, isolated):
        assert pipeline.run(count=6, today=MONDAY)[0] == 1

    def test_region_rotation(self):
        assert pipeline.region_for(MONDAY)[0] == "Lombardia"
        assert pipeline.region_for(date(2026, 10, 19))[0] == "Lazio"
        assert pipeline.region_for(date(2026, 10, 18))[0] == "Lombardia"  # stessa settimana
        assert pipeline.region_for(MONDAY, index=len(pipeline.REGIONS))[0] == "Lombardia"

    def test_terms_rotation_with_region(self):
        assert pipeline.terms_for(MONDAY) == ["Business Central", "Power Platform"]
        assert pipeline.terms_for(date(2026, 10, 19)) == ["Dynamics 365", "Power Apps"]
        # tutte le parole chiave dell'utente, a coppie
        assert sorted(t for p in pipeline.TERM_PAIRS for t in p) == sorted(discover_companies.DEFAULT_TERMS)
        # combinazioni regione x coppia tutte diverse per 68 settimane
        combos = {(pipeline.region_for(MONDAY, i)[0], tuple(pipeline.terms_for(MONDAY, i))) for i in range(68)}
        assert len(combos) == 68

    def test_region_aliases_exist_in_actor_schema(self):
        # alias copiati dall'elenco contact_location dell'actor (2026-10-12): tutti "regione, italy"
        for _, aliases in pipeline.REGIONS:
            assert aliases and all(a.endswith(", italy") and a == a.lower() for a in aliases)

    def test_worst_case_apify_spend_within_run_budget(self):
        dc, fpl = discover_companies, find_people_linkedin
        google = dc.estimate_cost(len(pipeline.TERM_PAIRS[0]) * dc.GOOGLE_PAGES, pipeline.MAX_COMPANIES_PER_RUN)
        # code_crafter due volte: seconda linea + titolari delle piccole aziende
        worst = (google + 2 * find_leads.estimate_cost(find_leads.MAX_FETCH_WITH_DOMAINS)
                 + fpl.estimate_cost(fpl.MAX_PROFILES))
        assert worst < 0.32 and worst + 0.05 < pipeline.RUN_BUDGET_USD  # 0,05 $ = margine Claude per 5 email

    def test_call_step_captures_exit_and_json(self):
        code, detail = pipeline.call_step(failing(3, foo=1))
        assert code == 3 and detail == {"error": "errore finto", "foo": 1}


# ---------- discover_companies (Google -> LinkedIn) ----------

def google_page(*urls):
    return {"searchQuery": {"term": "q"}, "organicResults": [{"url": u, "title": "t"} for u in urls]}


def li_company(slug, country="IT", website="https://www.acme.it", description="Partner Business Central",
               specialities=None):
    return {"name": slug.title(), "linkedinUrl": f"https://www.linkedin.com/company/{slug}/", "website": website,
            "description": description, "specialities": specialities or [], "tagline": "",
            "locations": [{"country": country, "city": "Milano", "headquarter": True}],
            "employeeCountRange": {"start": 11, "end": 50}}


class TestDiscoverCompanies:
    def test_slugs_deduplicated_across_country_subdomains(self):
        pages = [google_page("https://ca.linkedin.com/company/acme", "https://it.linkedin.com/company/acme/about",
                             "https://www.microsoft.com/partner", "https://www.linkedin.com/company/beta?x=1")]
        assert discover_companies.extract_slugs(pages) == ["acme", "beta"]

    @pytest.mark.parametrize("changes,reason", [
        ({"locations": [{"country": "SI", "headquarter": True}]}, "sede non in Italia"),
        ({"website": ""}, "sito assente"),
        ({"description": "Agenzia di marketing"}, "nessuna specializzazione"),
        ({"companyType": "Educational Institution"}, "non e' un'azienda"),  # caso reale: un podcast
        ({"companyType": "Nonprofit"}, "non e' un'azienda"),
        ({"website": "https://www.meetup.com/it-IT/Azure-Meetup-Milano/"}, "sito non aziendale"),
    ])
    def test_qualify_rejects(self, changes, reason):
        assert discover_companies.qualify({**li_company("a"), **changes}).startswith(reason)

    def test_company_already_in_sheet_rejected(self):
        assert discover_companies.qualify(li_company("a"), {"acme.it"}).startswith("azienda gia' nel foglio")

    def test_qualify_accepts_specialities_and_copilot(self):
        assert discover_companies.qualify(li_company("a", description="ERP",
                                                     specialities=["Microsoft Dynamics NAV"])) is None
        assert discover_companies.qualify(li_company("a", description="Agenti con Copilot Studio")) is None

    def test_region_in_google_query(self):
        assert discover_companies.google_queries(["Power BI"], "Lombardia") == [
            'site:linkedin.com/company "Power BI" Lombardia']

    @patch("discover_companies.requests.post")
    def test_seen_slugs_skipped_before_paying_linkedin(self, post, isolated):
        post.side_effect = [
            apify_response(payload=[google_page("https://it.linkedin.com/company/Vista",
                                                "https://it.linkedin.com/company/nuova")] * 2),
            apify_response(payload=[li_company("nuova")]),
        ]
        result = discover_companies.run(["Business Central"], 10, {"vista"}, place="Lombardia")
        google_body = post.call_args_list[0].kwargs["json"]
        assert google_body["maxPagesPerQuery"] == discover_companies.GOOGLE_PAGES == 2
        assert google_body["queries"] == 'site:linkedin.com/company "Business Central" Lombardia'
        assert post.call_args_list[1].kwargs["json"]["companies"] == ["https://www.linkedin.com/company/nuova/"]
        assert result["slugs_already_seen"] == 1 and [c["slug"] for c in result["companies"]] == ["nuova"]
        assert result["cost_usd"] == pytest.approx(0.001 + 2 * 0.0025 + 0.004)

    def test_community_slugs(self):
        # casi reali v5/v7 (2026-10-12): riconosciuti da slug o titolo Google
        page = {"organicResults": [
            {"url": "https://it.linkedin.com/company/azure-meetup-esempio", "title": "Azure Meetup Esempio"},
            {"url": "https://it.linkedin.com/company/cloud-podcast-esempio", "title": "Cloud Podcast Esempio"},
            {"url": "https://it.linkedin.com/company/powerbi-group-esempio", "title": "Power BI User Group Italy"},
            {"url": "https://it.linkedin.com/company/startup-grind-esempio", "title": "Startup Grind Esempio"},
            {"url": "https://it.linkedin.com/company/gamma-soft", "title": "Gamma Soft | LinkedIn"},
            {"url": "https://it.linkedin.com/company/acme-communications", "title": "Acme Communications"},
        ]}
        assert discover_companies.community_slugs([page]) == {
            "azure-meetup-esempio", "cloud-podcast-esempio", "powerbi-group-esempio", "startup-grind-esempio"}

    @patch("discover_companies.requests.post")
    def test_communities_skipped_before_paying_linkedin(self, post, isolated):
        post.side_effect = [
            apify_response(payload=[{"organicResults": [
                {"url": "https://it.linkedin.com/company/azure-meetup-esempio", "title": "Azure Meetup Esempio"},
                {"url": "https://it.linkedin.com/company/nuova", "title": "Nuova Srl"}]}]),
            apify_response(payload=[li_company("nuova")]),
        ]
        result = discover_companies.run(["Microsoft Azure"], 10)
        assert post.call_args_list[1].kwargs["json"]["companies"] == ["https://www.linkedin.com/company/nuova/"]
        assert result["slugs_community"] == ["azure-meetup-esempio"]

    @patch("discover_companies.requests.post")
    def test_all_seen_no_linkedin_call(self, post, isolated):
        post.side_effect = [apify_response(payload=[google_page("https://it.linkedin.com/company/vista")])]
        assert exit_code(discover_companies.run, ["Business Central"], 10, {"vista"}) == 4
        assert post.call_count == 1

    @patch("discover_companies.requests.post")
    def test_discarded_have_slug_for_seen_tab(self, post, isolated, capsys):
        post.side_effect = [apify_response(payload=[google_page("https://it.linkedin.com/company/estera")]),
                            apify_response(payload=[li_company("estera", country="SI")])]
        assert exit_code(discover_companies.run, ["Power BI"], 10) == 4
        err = json.loads(capsys.readouterr().err)
        assert err["discarded"][0]["slug"] == "estera" and err["cost_usd"] > 0

    @patch("discover_companies.requests.post")
    def test_google_error(self, post, isolated):
        post.return_value = apify_response(status=500, text="x")
        assert exit_code(discover_companies.run, ["Business Central"], 10) == 3

    @pytest.mark.parametrize("args", [([], 10), (["a"], 11), (["a", "b", "c", "d", "e"], 5)])
    def test_invalid_input(self, args):
        assert exit_code(discover_companies.run, *args) == 1

    def test_invalid_pages(self):
        assert exit_code(discover_companies.run, ["a"], 5, pages=4) == 1


# ---------- find_people_linkedin (ripiego per le aziende scoperte) ----------

LI_COMPANIES = [{"slug": "acme-srl", "domain": "acme.it", "name": "Acme"},
                {"slug": "beta", "domain": "beta.it", "name": "Beta"}]


def li_profile(first="Mario", position="CTO", slug="acme-srl", email="mario@acme.it", **email_kw):
    em = {"email": email, "deliverable": True, "status": "valid", "catchAllDomain": False, "qualityScore": 90,
          **email_kw}
    return {"firstName": first, "lastName": "Rossi", "headline": position,
            "linkedinUrl": f"https://www.linkedin.com/in/{first.lower()}",
            "currentPosition": [{"position": position, "companyName": slug.title(), "companyUniversalName": slug}],
            "emails": [em] if email else [],
            "location": {"parsed": {"country": "Italy", "text": "Milano, Italy"}}}


def li_filter(profiles, **kw):
    return find_people_linkedin.filter_people(profiles, LI_COMPANIES, SECOND_LINE, OWNERS, **kw)


class TestFindPeopleLinkedin:
    def test_valid_profile_becomes_lead(self):
        leads, discarded = li_filter([li_profile()])
        assert discarded == [] and len(leads) == 1
        assert leads[0]["company_domain"] == "acme.it" and leads[0]["source"] == "linkedin-employees"

    @pytest.mark.parametrize("p,reason", [
        (li_profile(slug="altra-azienda"), "non lavora"),
        (li_profile(position="Founder & CEO"), "titolare o socio"),
        (li_profile(position="Responsabile tecnico"), "ruolo diverso"),  # decisione dell'utente
        (li_profile(position="Vice President Sales"), "ruolo diverso"),
        (li_profile(email=None), "nessuna email"),
        (li_profile(email="mario@bssrl.it"), "nessuna email"),
        (li_profile(email="mario@acme.com", slug="beta"), "nessuna email"),  # email di Acme, lavora in Beta
        (li_profile(deliverable=False), "nessuna email"),
        (li_profile(catchAllDomain=True), "nessuna email"),
    ])
    def test_rejections(self, p, reason):
        leads, discarded = li_filter([p])
        assert leads == [] and discarded[0]["reason"].startswith(reason)

    def test_same_name_other_extension_accepted(self):
        leads, _ = li_filter([li_profile(email="mario@acme.com")])  # sito acme.it (caso reale v7: stesso nome .it/.com)
        assert len(leads) == 1

    def test_partner_e_cto_kept(self):
        """Decisione dell'utente (2026-10-12): "Partner e CTO" si tiene anche dal ripiego LinkedIn."""
        leads, _ = li_filter([li_profile(position="Partner e CTO")])
        assert len(leads) == 1

    def test_one_lead_per_company_and_known_email(self):
        leads, discarded = li_filter([li_profile(), li_profile(first="Luca", email="luca@acme.it"),
                                      li_profile(first="Anna", slug="beta", email="anna@beta.it")],
                                     known_emails={"anna@beta.it"})
        assert [l["full_name"] for l in leads] == ["Mario Rossi"]
        assert [d["reason"] for d in discarded] == ["azienda gia' presa in questo giro",
                                                    "gia' nel foglio (stessa email)"]

    @patch("discover_companies.requests.post")
    def test_actor_input_and_cost(self, post, isolated):
        post.return_value = apify_response(payload=[
            li_profile(position="CEO"), li_profile(first="Anna", slug="beta", email="anna@beta.it")])
        result = find_people_linkedin.run(LI_COMPANIES)
        body = post.call_args.kwargs["json"]
        assert body["companyBatchMode"] == "all_at_once"  # un solo avvio pagato
        assert body["maxItems"] == 4 and body["jobTitles"] == SECOND_LINE
        assert result["count"] == 1 and result["apify_cost_usd"] == pytest.approx(0.02 + 2 * 0.012)

    def test_needs_slug_and_domain(self):
        assert exit_code(find_people_linkedin.run, [{"slug": None, "domain": "acme.it"}]) == 1


# ---------- decisioni dell'utente: mai invio, trigger spento di default ----------

class TestUserDecisions:
    def test_no_script_sends_email(self):
        """Le email non vanno mai inviate (decisione dell'utente)."""
        import re
        forbidden = re.compile(r"smtplib|sendmail|send_message|gmail|sendgrid|mailgun|/send\b|messages/send")
        for f in Path(__file__).parent.glob("*.py"):
            if f.name == "test_all.py":
                continue
            assert not forbidden.search(f.read_text(encoding="utf-8").lower()), f.name

    def test_schedule_off_unless_explicit(self, monkeypatch):
        monkeypatch.delenv("OUTREACH_SCHEDULE", raising=False)
        monkeypatch.delenv("OUTREACH_RUN_ID_SUFFIX", raising=False)
        import modal_app
        assert importlib.reload(modal_app).SCHEDULE_ON is False
        assert modal_app.RUN_ID_SUFFIX == ""  # un deploy normale usa il run id della settimana
        monkeypatch.setenv("OUTREACH_SCHEDULE", "on")
        assert importlib.reload(modal_app).SCHEDULE_ON is True
        assert modal_app.CRON == "0 8 * * 1" and modal_app.TIMEZONE == "Europe/Rome"
        monkeypatch.delenv("OUTREACH_SCHEDULE")
        importlib.reload(modal_app)

    def test_light_call_to_action(self):
        """Invito finale leggero (decisione dell'utente, 2026-10-12): niente "15 minuti" ne' chiamata fissata."""
        cta = write_emails.CALL_TO_ACTION.lower()
        assert "minuti" not in cta and "chiamata" not in cta
        assert write_emails.quality_problems(
            {"subject": "Oggetto", "body": f"Gentile Mario Rossi,\n\nTesto.\n\n{write_emails.CALL_TO_ACTION}"
                                           "\n\nCordiali saluti,\nAndrea"},
            LEAD, "Andrea") == []

    def test_partner_not_excluded_responsabile_tecnico_not_target(self):
        """Decisioni dell'utente (2026-10-12): "Partner e CTO" si tiene, "Responsabile tecnico" no."""
        assert "Partner" not in find_leads.DEFAULT_EXCLUDE_TITLES.split(",")
        assert find_leads.title_matches("Partner e CTO", SECOND_LINE)
        assert not find_leads.title_matches("Responsabile tecnico", SECOND_LINE)

    def test_owner_accepted_only_up_to_50_employees(self):
        """Decisione dell'utente (2026-10-12): titolare ammesso solo nelle aziende fino a 50 dipendenti."""
        assert pipeline.OWNER_OK_MAX_EMPLOYEES == 50
        assert pipeline.OWNER_TITLES == find_leads.DEFAULT_EXCLUDE_TITLES.split(",")

    def test_run_budget_and_monthly_cap(self):
        assert pipeline.RUN_BUDGET_USD == 0.50 and write_emails.MAX_BUDGET_USD == 0.50
        assert pipeline.MONTHLY_CAP_USD == 2.50


# ---------- google_auth ----------

class TestGoogleAuth:
    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", str(tmp_path / "nope.json"))
        with pytest.raises(google_auth.GoogleAuthError):
            google_auth.get_credentials()

    def test_invalid_json(self, tmp_path, monkeypatch):
        f = tmp_path / "c.json"
        f.write_text("{", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", str(f))
        with pytest.raises(google_auth.GoogleAuthError):
            google_auth.get_credentials()

    def test_unknown_format(self, tmp_path, monkeypatch):
        f = tmp_path / "c.json"
        f.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", str(f))
        with pytest.raises(google_auth.GoogleAuthError):
            google_auth.get_credentials()


# ---------- run_state ----------

class TestRunState:
    def test_save_and_load(self, isolated):
        run_state.save_step("a", "done", n=1)
        run_state.save_step("b", "partial")
        state = run_state.load_state()
        assert state["a"]["n"] == 1 and state["b"]["status"] == "partial"
