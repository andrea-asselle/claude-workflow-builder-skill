# Rule: Cold Outreach (v1)

## Obiettivo

Dato un elenco di aziende (max 5 siti), trovarne i contatti con il ruolo richiesto (default CEO, max 5 lead), scrivere per ognuno una email di primo contatto personalizzata in italiano con Claude e salvarla in un Google Sheet come bozza. **Le email non vengono mai inviate.**

## Trigger

L'utente dice qualcosa come:

- "Fai il cold outreach sui CEO di azienda1.it, azienda2.it, azienda3.it"
- "Trova i contatti di queste aziende e scrivi le email nel foglio"

## Input Richiesti

- `companies` (obbligatorio) — siti delle aziende (es. `azienda.it`), 1-5; con il solo nome l'actor non costruisce l'email
- `count` (opzionale) — numero di lead, 1-5, default 3
- `offer` (obbligatorio) — cosa proponi ai lead, 1-2 frasi
- `sender` (obbligatorio) — nome e cognome che firma le email
- `job_titles` (opzionale) — max 3 ruoli, default `CEO,Amministratore Delegato,Founder`

## Prerequisiti

- File `.env` con: `APIFY_TOKEN`, `ANTHROPIC_API_KEY`, `GOOGLE_SHEET_ID` (vedi `.env.example`)
- `credentials.json` nella root: chiave del service account Google (o OAuth client desktop). Verifica con `python implementation/check_google_setup.py`
- Il foglio Google condiviso (ruolo Editor) con l'email `client_email` del service account
- Google Sheets API abilitata nel progetto Google Cloud
- Actor Apify `themineworks/b2b-leads-finder` (permessi limitati, funziona via API anche sul piano Free)
- Dipendenze: `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`

## Pipeline

### Step 0 (una tantum): Verifica Google

```bash
.venv\Scripts\python.exe implementation/check_google_setup.py
```

**Validazione:**
- Exit code 0 e `spreadsheet_title` valorizzato

### Step 1: Trova i lead

```bash
.venv\Scripts\python.exe implementation/find_leads.py --companies "azienda1.it,azienda2.it,azienda3.it" --count 3 --job-titles "CEO,Amministratore Delegato,Founder"
```

**Validazione:**
- Exit code 0
- `count` >= 1 e `apify_cost_usd` <= 0.20
- Controllare i lead: nome, ruolo, azienda ed email valorizzati; `email_confidence` (found / pattern_matched / guessed) indica quanto l'email e' affidabile

**Dopo il successo:**
- Output in `.tmp/leads.json`
- `.tmp/run_state.json` aggiornato (`find_leads`)

### Step 2: Scrivi le email

```bash
.venv\Scripts\python.exe implementation/write_emails.py --offer "<offerta>" --sender "<Nome Cognome>"
```

**Validazione:**
- Exit code 0, `status` = `success`
- `total_cost_usd` <= 0.50
- Rileggere almeno un'email: italiano, "Lei", nessun fatto inventato

**Dopo il successo:**
- Output in `.tmp/emails.json`
- `.tmp/run_state.json` aggiornato (`write_emails`)

### Step 3: Scrivi nel Google Sheet

```bash
.venv\Scripts\python.exe implementation/sheet_export.py [--tag TEST]
```

`--tag TEST` per le righe di prova: lo Stato diventa "TEST - Bozza - non inviata".

**Validazione:**
- Exit code 0, `rows_written` = numero di email
- Le righe hanno `Stato` = "Bozza - non inviata" (con prefisso se `--tag`)
- Rileggere il foglio: intestazione = `HEADERS`, nessuna colonna vuota tranne quelle che l'actor non fornisce (es. Telefono)

**Dopo il successo:**
- `.tmp/run_state.json` aggiornato (`sheet_export`)
- `.venv\Scripts\python.exe implementation/alert_user.py success`

## Limiti di Sicurezza

| Limite | Valore | Dove |
|--------|--------|------|
| Tetto di spesa Apify per run | 0,50 $ (minimo accettato da Apify per questo actor) | `find_leads.py` (`MAX_APIFY_CHARGE_USD`, passato come `maxTotalChargeUsd`) |
| Caso peggiore Apify reale | ~0,19 $ (l'actor addebita max 25 lead/run) | `find_leads.py` (`APIFY_WORST_CASE_USD`), usato nel budget di `write_emails.py` |
| Max aziende per run | 5 | `find_leads.py` (`MAX_COMPANIES`) |
| Max lead per run | 5 | `find_leads.py` (`MAX_LEADS_LIMIT`), `write_emails.py`, `sheet_export.py` (`MAX_ROWS_LIMIT`) |
| Budget totale per run (Apify + Claude) | 0,50 $ | `write_emails.py` (`MAX_BUDGET_USD`), conta il caso peggiore Apify + ogni chiamata Claude |
| Invio email | Mai | Nessuno script invia email; lo stato e' sempre "Bozza - non inviata" |
| Duplicati nel foglio | Saltati per email | `sheet_export.py` |

## Casi Limite

| Situazione | Exit Code | Azione |
|------------|-----------|--------|
| `--count` o numero aziende fuori da 1-5, file input mancante/invalido | 1 | Correggere input; rieseguire lo step precedente |
| `APIFY_TOKEN` / `ANTHROPIC_API_KEY` / `GOOGLE_SHEET_ID` mancanti o rifiutati | 2 | Aggiungere/correggere nel `.env` |
| `credentials.json` mancante, foglio non condiviso, API Sheets non abilitata | 2 | Eseguire `check_google_setup.py` e seguire il messaggio |
| Errore Apify / Claude / Google (rete, 5xx) | 3 | Ritentare max 3 volte, poi chiedere all'utente |
| Nessun lead trovato | 4 | Verificare i siti (esistono? sono dell'azienda giusta?), provare altri ruoli (`Founder`, `Owner`, `Amministratore Delegato`) |
| Actor risponde 200 con item `{"error": ...}` | 3 | Leggere il messaggio: non e' un lead |
| Budget esaurito o alcune email fallite (`partial`) | 4 | Le email riuscite sono in `.tmp/emails.json`; scriverle con step 3 e segnalare le mancanti |
| Tutti i lead gia' nel foglio | 4 | Nessuna azione: il foglio e' gia' aggiornato |

## Recupero da Interruzione

Leggere `.tmp/run_state.json`:

- `find_leads` done → `.tmp/leads.json` esiste, saltare a step 2 (non rispendere Apify)
- `write_emails` done → `.tmp/emails.json` esiste, saltare a step 3
- `sheet_export` e' idempotente (salta le email gia' presenti), si puo' rilanciare

## Note

- Costi: Apify (piano Free) 0,005 $/lead, dal 2026-10-13 0,0075 $/lead + 0,005 $ a run; lo script stima gia' con i prezzi nuovi. Claude Haiku 4.5 ~0,003 $ per email.
- Aziende italiane: cercare solo "CEO" trova poco (run 2026-09-30 su 3 aziende italiane, 1 grande e 2 PMI: 1 lead, e non era CEO). Usare anche "Amministratore Delegato" e "Founder". Secondo run con i 3 ruoli: 0 lead, 52 profili scartati da `candidates_rejected_wrong_company` (l'actor non collega i profili LinkedIn al dominio). Con queste aziende l'actor non e' affidabile: leggere `report` nell'errore exit 4 prima di ritentare.
- Si tengono solo i lead con `title_match` true: gli altri ruoli vengono scartati (ma l'actor li addebita comunque).
- `job_title` di LinkedIn arriva troncato ("... at ..."): `sheet_export.py` toglie il suffisso.
- `maxTotalChargeUsd` sotto 0,50 $ viene rifiutato da Apify (400 `max-total-charge-usd-below-minimum`).
- L'actor puo' restituire piu' lead del richiesto (fino a 25, tutti addebitati): lo script tiene i primi `count` con `title_match`.
- Actor scartati (2026-09-30): `code_crafter/leads-finder` e' bloccato via API sul piano Free (risponde 200 con item di errore, 0,02 $ addebitati); `braveleads` e `olympus` addebitano minimo 100 lead per run; `atomus` sul Free ha 10 lead/mese e nessuna email.
- I lead contengono dati personali: trattarli nel rispetto del GDPR (informativa, opt-out) prima di inviare qualsiasi email reale.
- Prova end-to-end 2026-09-30 con lead fittizio (example.com, `--tag TEST`): step 2 e 3 ok, 13 colonne compilate, corpo email identico nel foglio. Costo Claude 0,0015 $/email.
- Prima versione del prompt produceva anglicismi ("una fit") e saluto informale: il prompt ora impone italiano senza anglicismi e "Gentile <Nome Cognome>".
- Su Windows gli script forzano stdout/stderr UTF-8 (prima il JSON usciva in cp1252 con le lettere accentate).
- Con `run-sync-get-dataset-items` Apify non restituisce il costo reale; controllarlo nella console Apify se serve.
