# CLAUDE.md

Progetto RBI (Rules-Brain-Implementation).

- `rules/` = SOP in Markdown, `implementation/` = script Python deterministici, `.tmp/` = stato delle esecuzioni
- Usa sempre `.venv\Scripts\python.exe` (Python 3.11). Installa i pacchetti con `uv`, non con `pip`.
- `uv` si trova in `%USERPROFILE%\.local\bin\uv.exe`
- Non leggere cartelle fuori da questo progetto.

## Workflow disponibili

| Workflow | Rule | Script |
|----------|------|--------|
| Cold outreach v5 (unione di V3 e Auto_Test: aziende di nicchia Microsoft da Google → LinkedIn, parole chiave × regione a rotazione settimanale, aziende gia' viste saltate → seconda linea IT/operations/delivery con code_crafter e ripiego LinkedIn, titolari esclusi, un contatto per azienda → email Claude a schema fisso con controlli di qualita' → Google Sheet + schede "Log outreach" e "Aziende viste", MAI invio; automatico il lunedi' 8:00 su Modal app `rbi-outreach-unico`, trigger spento finche' non lo si accende; 0,50 $ a giro, 2,50 $ al mese; richiede piano Apify a pagamento) | `rules/cold_outreach.md` | `pipeline.py`, `discover_companies.py`, `find_people_linkedin.py`, `find_leads.py`, `write_emails.py`, `sheet_export.py`, `run_log.py`, `modal_app.py`, `modal_secrets.py`, `check_google_setup.py` |
