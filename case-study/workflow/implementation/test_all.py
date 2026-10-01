"""Test di tutti gli script RBI. API esterne sempre mockate.

Esecuzione: .venv\\Scripts\\python.exe -m pytest implementation/test_all.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import find_leads
import google_auth
import run_state
import sheet_export
import write_emails
from load_env import load_env

LEAD = {
    "first_name": "Mario", "last_name": "Rossi", "job_title": "CEO",
    "company_name": "Acme Srl", "email": "mario@acme.it", "industry": "software",
    "city": "Milano", "linkedin": "https://linkedin.com/in/mrossi", "company_website": "acme.it",
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Sposta .tmp in una cartella temporanea e imposta env finto."""
    tmp = tmp_path / ".tmp"
    tmp.mkdir()
    for mod in (find_leads, write_emails, sheet_export):
        monkeypatch.setattr(mod, "TMP_DIR", tmp)
    monkeypatch.setattr(find_leads, "OUTPUT_FILE", tmp / "leads.json")
    monkeypatch.setattr(run_state, "TMP_DIR", tmp)
    monkeypatch.setattr(run_state, "STATE_FILE", tmp / "run_state.json")
    monkeypatch.setattr("load_env.load_env", lambda *a, **k: None)
    for mod in (find_leads, write_emails, sheet_export):
        monkeypatch.setattr(mod, "load_env", lambda *a, **k: None)
    monkeypatch.setenv("APIFY_TOKEN", "test-apify")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")
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


PERSON = {"full_name": "Mario Rossi", "job_title": "CEO", "company": "Acme", "domain": "acme.it",
          "email": "mario@acme.it", "title_match": True, "charged": True}
C3 = ["a.it", "b.it", "c.it"]


class TestFindLeads:
    @patch("find_leads.requests.post")
    def test_success(self, post, isolated):
        post.return_value = apify_response(payload=[PERSON, PERSON, PERSON, {"_type": "summary"}])
        result = find_leads.run(C3, 3, ["CEO"])
        assert result["count"] == 3
        assert result["apify_cost_usd"] == pytest.approx(0.005 + 3 * 0.0075)
        assert json.loads((isolated / "leads.json").read_text(encoding="utf-8"))["count"] == 3
        assert post.call_args.kwargs["json"] == {"companies": C3, "jobTitles": ["CEO"], "maxLeadsPerCompany": 1}
        assert post.call_args.kwargs["params"]["maxTotalChargeUsd"] == find_leads.MAX_APIFY_CHARGE_USD

    @patch("find_leads.requests.post")
    def test_keeps_only_matching_roles(self, post, isolated):
        other = {**PERSON, "full_name": "Anna Bianchi", "job_title": "Engineer", "title_match": False}
        post.return_value = apify_response(payload=[other, other, PERSON, PERSON])
        result = find_leads.run(["a.it"], 1, ["CEO"])
        assert [l["full_name"] for l in result["leads"]] == ["Mario Rossi"]
        assert result["returned_by_actor"] == 4 and result["discarded_other_roles"] == 2
        assert result["apify_cost_usd"] == pytest.approx(0.005 + 4 * 0.0075)

    @patch("find_leads.requests.post")
    def test_only_other_roles_exit_4(self, post, isolated):
        post.return_value = apify_response(payload=[{**PERSON, "title_match": False}])
        assert exit_code(find_leads.run, C3, 3, ["CEO"]) == 4

    def test_too_many_job_titles(self):
        assert exit_code(find_leads.run, C3, 1, ["a", "b", "c", "d"]) == 1

    @patch("find_leads.requests.post")
    def test_company_inbox_not_a_lead(self, post, isolated):
        post.return_value = apify_response(payload=[{"email": "info@acme.it", "charged": False}])
        assert exit_code(find_leads.run, C3, 3, ["CEO"]) == 4

    @pytest.mark.parametrize("count", [0, 6, -1])
    def test_count_out_of_range(self, count):
        assert exit_code(find_leads.run, C3, count, ["CEO"]) == 1

    @pytest.mark.parametrize("companies", [[], ["x.it"] * 6])
    def test_companies_out_of_range(self, companies):
        assert exit_code(find_leads.run, companies, 1, ["CEO"]) == 1

    def test_missing_token(self, monkeypatch):
        monkeypatch.delenv("APIFY_TOKEN")
        assert exit_code(find_leads.run, C3, 1, ["CEO"]) == 2

    @patch("find_leads.requests.post")
    def test_forbidden(self, post):
        post.return_value = apify_response(403, {"error": {"message": "no"}})
        assert exit_code(find_leads.run, C3, 1, ["CEO"]) == 2

    @patch("find_leads.requests.post")
    def test_api_error(self, post):
        post.return_value = apify_response(500, text="boom")
        assert exit_code(find_leads.run, C3, 1, ["CEO"]) == 3

    @patch("find_leads.requests.post")
    def test_error_item_is_not_a_lead(self, post, isolated):
        post.return_value = apify_response(payload=[{"error": "free plan cannot run via API"}])
        assert exit_code(find_leads.run, C3, 3, ["CEO"]) == 3
        assert not (isolated / "leads.json").exists()

    @patch("find_leads.requests.post")
    def test_network_error(self, post):
        post.side_effect = find_leads.requests.ConnectionError("down")
        assert exit_code(find_leads.run, C3, 1, ["CEO"]) == 3

    @patch("find_leads.requests.post")
    def test_empty_result(self, post):
        post.return_value = apify_response(payload=[])
        assert exit_code(find_leads.run, C3, 2, ["CEO"]) == 4


# ---------- write_emails ----------

def claude_reply(text, inp=500, out=300):
    return SimpleNamespace(content=[SimpleNamespace(text=text)],
                           usage=SimpleNamespace(input_tokens=inp, output_tokens=out))


def write_leads_file(tmp, n=2, cost=0.024):
    f = tmp / "leads.json"
    f.write_text(json.dumps({"leads": [LEAD] * n, "apify_cost_usd": cost}), encoding="utf-8")
    return f


GOOD = '{"subject": "Ciao Mario", "body": "Gentile Mario, ..."}'


class TestWriteEmails:
    @patch("anthropic.Anthropic")
    def test_success(self, anth, isolated):
        anth.return_value.messages.create.return_value = claude_reply(GOOD)
        result = write_emails.run(write_leads_file(isolated), "consulenza", "Andrea")
        assert result["status"] == "success" and result["count"] == 2
        assert 0.024 < result["total_cost_usd"] < write_emails.MAX_BUDGET_USD
        assert (isolated / "emails.json").exists()

    @patch("anthropic.Anthropic")
    def test_json_wrapped_in_code_fence(self, anth, isolated):
        anth.return_value.messages.create.return_value = claude_reply("```json\n" + GOOD + "\n```")
        assert write_emails.run(write_leads_file(isolated, 1), "x", "y")["count"] == 1

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
        assert exit_code(write_emails.run, write_leads_file(isolated, 1), "x", "y") == 3

    @patch("anthropic.Anthropic")
    def test_bad_response_is_partial(self, anth, isolated):
        anth.return_value.messages.create.side_effect = [claude_reply(GOOD), claude_reply("niente json")]
        result = write_emails.run(write_leads_file(isolated), "x", "y")
        assert result["status"] == "partial" and result["count"] == 1 and len(result["errors"]) == 1

    @patch("anthropic.Anthropic")
    def test_budget_stop(self, anth, isolated):
        anth.return_value.messages.create.return_value = claude_reply(GOOD)
        assert exit_code(write_emails.run, write_leads_file(isolated, 2, cost=0.499), "x", "y") == 3
        anth.return_value.messages.create.assert_not_called()

    @patch("anthropic.Anthropic")
    def test_budget_counts_apify_cap(self, anth, isolated):
        f = isolated / "leads.json"
        f.write_text(json.dumps({"leads": [LEAD], "apify_cost_usd": 0.01, "apify_max_charge_usd": 0.4999}), encoding="utf-8")
        assert exit_code(write_emails.run, f, "x", "y") == 3
        anth.return_value.messages.create.assert_not_called()

    def test_compact_lead_drops_empty_and_truncates(self):
        out = write_emails.compact_lead({"a": "", "b": None, "c": "x" * 1000, "d": 5})
        assert "a" not in out and "b" not in out
        assert len(out["c"]) == write_emails.MAX_FIELD_CHARS and out["d"] == 5


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
        row = sheet_export.to_row({"lead": PERSON, "subject": "S", "body": "B"}, "2026-09-30")
        h = sheet_export.HEADERS
        assert row[h.index("Nome")] == "Mario" and row[h.index("Cognome")] == "Rossi"
        assert row[h.index("Azienda")] == "Acme" and row[h.index("Sito")] == "acme.it"

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
