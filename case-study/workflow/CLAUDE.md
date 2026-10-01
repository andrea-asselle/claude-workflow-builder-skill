# CLAUDE.md

Progetto RBI (Rules-Brain-Implementation).

- `rules/` = SOP in Markdown, `implementation/` = script Python deterministici, `.tmp/` = stato delle esecuzioni
- Usa sempre `.venv\Scripts\python.exe` (Python 3.11). Installa i pacchetti con `uv`, non con `pip`.
- `uv` deve essere installato e nel PATH
- Non leggere cartelle fuori da questo progetto.

## Workflow disponibili

| Workflow | Rule | Script |
|----------|------|--------|
| Cold outreach (aziende → contatti Apify → email Claude → Google Sheet, senza invio) | `rules/cold_outreach.md` | `find_leads.py`, `write_emails.py`, `sheet_export.py`, `check_google_setup.py` |
