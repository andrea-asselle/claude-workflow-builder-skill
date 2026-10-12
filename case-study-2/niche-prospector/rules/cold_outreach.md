# Rule: Cold Outreach (v7)

v7 (2026-10-12), su richiesta dell'utente:
- **Ruoli allargati:** oltre alla seconda linea IT/operations/delivery anche Project Manager, BU Manager / Business Unit Manager, Head of Business Intelligence, CxO (20 ruoli, `MAX_JOB_TITLES` 25). Perche': nelle aziende senza contatto LinkedIn mostrava persone con questi ruoli e nessuno della lista v6.
- **Email con stesso nome e altra estensione accettate** (es. acmesoft.it per il sito acmesoft.com). Perche': nella prova mirata 4 scarti "email di un altro dominio" su 5 erano di questo tipo.
- **Community scartate prima di pagare LinkedIn** (meetup, user group, podcast, community, Startup Grind), riconosciute da slug o titolo Google (`discover_companies.COMMUNITY_RE`). Perche': nel giro v7 4 aziende controllate su 10 erano community.
- La v6 e' in `cold_outreach.v6.md`.

v6 (2026-10-12), su richiesta dell'utente: **nelle aziende fino a 50 dipendenti, se la seconda linea non si trova, si accetta il titolare** (CEO, fondatore, titolare, socio, amministratore). Perche': nei primi giri reali 0 contatti in tutte le aziende da 2-50 dipendenti (la seconda linea li' spesso non esiste), contatti trovati solo da 51 dipendenti in su; le prove di altre fonti per le persone (rapporto `reports/Actor Apify per lead migliori.md`) non hanno aggiunto contatti. Nelle aziende piu' grandi, o di dimensione sconosciuta, i titolari restano esclusi. Tutto il resto invariato. La v5 e' in `cold_outreach.v5.md`.

v5 (2026-10-12), su richiesta dell'utente: **unione con RBI_Auto_Test** in un solo workflow (cartella `RBI_Workflow_Unico`, base = v4).
- **Prima le aziende, poi le persone:** ogni giro cerca aziende che lavorano su tecnologie Microsoft (Google → pagina LinkedIn dell'azienda), poi la seconda linea dentro quelle aziende (code_crafter sui siti trovati, LinkedIn come ripiego per le aziende rimaste scoperte). Perche': code_crafter da solo trova aziende qualsiasi, non la nicchia (Stato di verifica v2: 0 pertinenti su 54 con le parole chiave).
- **Rotazione parole chiave × regione:** una coppia di parole chiave e una regione a settimana (4 × 17 = 68 combinazioni diverse); 2 pagine Google per query invece di 1; aziende gia' controllate ricordate nella scheda "Aziende viste" e saltate prima di pagare. Perche': in RBI_Auto_Test le aziende si ripetevano dopo pochi giri (solo la prima pagina di Google, ordine sempre uguale).
- **"Partner" non piu' escluso:** "Partner e CTO" si tiene (decisione dell'utente); "Responsabile tecnico" resta fuori.
- **Invito finale leggero:** niente "15 minuti per una chiamata".
- **Dopo il primo giro reale (stesso giorno):** code_crafter con `--domains` chiede 2 persone per sito (max 20 invece di 10), perche' restituiva piu' persone della stessa azienda; nuovo controllo di qualita' "infinito troncato" ("Nel coordinar dei progetti").
- **Invariati:** seconda linea, nessun limite di dimensione, schema fisso dell'email, budget 0,50 $ a giro e 2,50 $ al mese, stesso Google Sheet, **nessun invio di email**, trigger spento salvo richiesta. App Modal nuova `rbi-outreach-unico`.

v4 (2026-10-12), su richiesta dell'utente: **nessun limite di dimensione aziendale** (prima solo PMI 11-200 dipendenti). `find_leads.DEFAULT_SIZES` e' vuoto; le fasce si possono ancora passare a mano con `--sizes`. Tutto il resto invariato. La v3 e' in `cold_outreach.v3.md`.

v3 (2026-10-12), su richiesta dell'utente:
- **Target:** seconda linea (CTO, CIO, COO, responsabili IT, operations e delivery) al posto dei titolari; titolari, fondatori e soci esclusi sia nella ricerca sia nel controllo.
- **Trigger automatico:** ogni lunedi' alle 8:00 (Europe/Rome) su Modal, senza intervento dell'utente; orchestratore `pipeline.py` con controlli di qualita' nel codice e scheda "Log outreach" nel foglio.
- **Invariati:** actor Apify, budget 0,50 $ a giro, Claude Haiku, Google Sheet, **nessun invio di email**.
- Perche' il controllo del ruolo e' cambiato: in v2 confrontava per sottostringa ("cto" in "Dire**cto**r", "cio" in "So**cio**").

La v2 e' in `cold_outreach.v2.md`, la v1 in `cold_outreach.v1.md`.

## Obiettivo

Ogni settimana trovare fino a 5 persone della seconda linea (IT, operations, delivery) di aziende italiane di qualsiasi dimensione **che lavorano su tecnologie Microsoft** (Business Central, Power Platform, Dynamics 365, Power Apps, Azure, Copilot Studio, Power Automate, Power BI), una regione e una coppia di parole chiave per settimana, un contatto per azienda, scrivere per ognuna un'email di primo contatto in italiano con Claude e salvarla nel Google Sheet come bozza. **Le email non vengono mai inviate.**

## Trigger

**Automatico** — ogni lunedi' alle 8:00 Europe/Rome, app Modal `rbi-outreach-unico` (funzione `weekly_run`). Si accende solo con `OUTREACH_SCHEDULE=on` al deploy (vedi Operazioni day-2); un deploy normale lo lascia **spento**.

**A richiesta** — l'utente dice qualcosa come:

- "Lancia adesso il giro del cold outreach"
- "Trova 3 responsabili IT in Piemonte e scrivi le email nel foglio"

## Input Richiesti

Giro automatico (nessun input a mano):
- `OUTREACH_OFFER` (obbligatorio, Modal Secret / `.env`) — cosa si propone, 1-2 frasi. Va nelle email, non nella ricerca
- `OUTREACH_SENDER` (obbligatorio, Modal Secret / `.env`) — nome e cognome che firma
- Regione: automatica, una a settimana da `pipeline.REGIONS` (17 regioni, partenza Lombardia il 2026-10-12)
- Parole chiave: automatiche, una coppia a settimana da `pipeline.TERM_PAIRS` (4 coppie dalle 8 parole chiave dell'utente in `discover_companies.DEFAULT_TERMS`); la stessa combinazione regione × coppia torna dopo 68 settimane
- Lead per giro: 5 (`pipeline.MAX_LEADS_PER_RUN`); aziende controllate per giro: 10 (`pipeline.MAX_COMPANIES_PER_RUN`)

Giro a mano: come sopra (`--region-index`, `--terms-index` per scegliere), oppure i singoli script (vedi docstring).

## Prerequisiti

- File `.env` con: `APIFY_TOKEN`, `ANTHROPIC_API_KEY`, `GOOGLE_SHEET_ID`, `OUTREACH_OFFER`, `OUTREACH_SENDER` (vedi `.env.example`)
- `credentials.json` nella root: chiave del service account Google, foglio condiviso (Editor) con il suo `client_email`. Verifica: `.venv\Scripts\python.exe implementation/check_google_setup.py`
- **Piano Apify a pagamento** (attivo: STARTER)
- Modal: login gia' fatto (`.venv\Scripts\modal.exe profile current` → `<workspace>`); Secret `rbi-outreach-unico` creato con `implementation/modal_secrets.py`
- Dipendenze: `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`

## Dipendenze esterne

Verificate dalla documentazione/API ufficiale il 2026-10-12.

| Servizio | Piano richiesto | Uso via API/script | Costo minimo per esecuzione | Limiti/quote | Permessi richiesti |
|----------|-----------------|--------------------|-----------------------------|--------------|--------------------|
| Apify `apify/google-search-scraper` (v5) | A pagamento (STARTER attivo) | Si' | 0,001 $ avvio + 0,0025 $/pagina (2 query × 2 pagine = 0,011 $); tetto minimo accettato 0,50 $ | Ordine dei risultati stabile: senza rotazione e piu' pagine le aziende si ripetono | Token Apify |
| Apify `harvestapi/linkedin-company` (v5) | A pagamento | Si' | 0,004 $ per azienda (max 10 = 0,04 $) | Dati pubblici della pagina aziendale (sito, sede, specializzazioni) | Token Apify; nessun account LinkedIn dell'utente |
| Apify `harvestapi/linkedin-company-employees` (v5, ripiego) | A pagamento | Si' | 0,02 $ avvio + 0,012 $ per profilo con email (max 10 = 0,14 $) | `companyBatchMode: all_at_once` (un solo avvio); filtro ruoli approssimativo: ricontrollato nel codice | Token Apify; nessun account LinkedIn dell'utente |
| Apify `code_crafter/leads-finder` | A pagamento (STARTER attivo) | Si' | 0,02 $ avvio + 0,002 $/lead (reale riletto: 0,03 $ per 5 lead); tetto minimo accettato 0,50 $ per run | `fetch_count` default 100000: sempre impostato; niente paginazione (stessi risultati a parita' di filtri) | Token Apify |
| Anthropic API (Claude Haiku 4.5) | Credito prepagato | Si' | ~0,003 $ per email (con eventuale rigenerazione) | — | Chiave API |
| Google Sheets API | Gratuito | Si' | 0 | Quote Google standard | Service account Editor sul foglio |
| Modal (cron) | Starter: 0 $ + 30 $/mese di credito incluso | Si' | < 0,01 $ di credito per giro (0,125 core per pochi minuti) | 5 cron sul piano Starter; uno schedule non si mette in pausa (si toglie e si rifa' il deploy); log conservati 1 giorno | Login Modal; Secret con le chiavi |

## Pipeline

### Giro completo (automatico o a mano): `pipeline.py`

```bash
.venv\Scripts\python.exe implementation/pipeline.py [--count 5] [--region-index N] [--terms-index N] [--tag TEST] [--dry-run] [--reuse-leads]
```

L'orchestratore esegue, in ordine, gli step sotto con le stesse validazioni, intercetta le uscite degli script e scrive **sempre** una riga nella scheda "Log outreach" (salvo foglio irraggiungibile: allora l'esito e' solo nell'output / nei log Modal).

Prima di spendere:
1. Apre il foglio, la scheda "Log outreach" e la scheda "Aziende viste" (create se mancano; colonne nuove in coda aggiunte da sole; colonne diverse: si ferma, exit 1)
2. Legge email e siti gia' nel foglio (`sheet_export.known_contacts`) e le aziende gia' controllate (`run_log.seen_slugs`)
3. `OUTREACH_OFFER`/`OUTREACH_SENDER` mancanti → esito `errore`, exit 1
4. Run id (settimana ISO, es. `2026-W42`) gia' concluso o che ha speso → esito `saltato`, exit 4
5. Spesa del mese + 0,50 $ > 2,50 $ → esito `saltato`, exit 4

**Validazione** (riga del Log): `Esito` = `ok` (5 righe scritte) / `parziale` (meno righe: leggere Dettagli) / `vuoto` / `saltato` / `errore` / `prova` (dry-run). `Costo totale $` <= 0,50.

**Dopo il successo:** rileggere il foglio; le email vanno rilette da una persona prima di qualsiasi uso (vedi Note: errori di senso).

### Step 1: Trova le aziende (v5)

```bash
.venv\Scripts\python.exe implementation/discover_companies.py --terms "Business Central,Power Platform" --place Lombardia [--pages 2] [--exclude-slugs "slug1,slug2"]
```

Google: `site:linkedin.com/company "<parola chiave>" <Regione>`, 2 pagine per query → slug delle pagine LinkedIn aziendali; quelli gia' in "Aziende viste" si saltano **prima** di pagare LinkedIn; max 10 aziende controllate. Si tengono solo aziende con sede in Italia, con un sito vero (non linktr.ee, meetup...), non community/enti/scuole, con termini Microsoft in descrizione/specializzazioni, **non gia' nel foglio**.

**Validazione:** exit 0, `companies` >= 1 ognuna con `domain` e `slug`, `cost_usd` <= 0,06. Exit 4 = nessuna azienda valida (esito `vuoto`, le aziende scartate si segnano comunque come viste).

**Dopo il successo:** `.tmp/companies.json`; nel giro completo una riga per azienda controllata nella scheda "Aziende viste" (Esito: `scartata: <motivo>`, `contatto: <ruolo> (<fonte>)`, `nessun contatto`), tranne in `--dry-run`.

### Step 2: Trova le persone

```bash
.venv\Scripts\python.exe implementation/find_leads.py --count 5 --domains "azienda1.it,azienda2.it"
.venv\Scripts\python.exe implementation/find_people_linkedin.py --companies "slug1=azienda1.it,slug2=azienda2.it"
```

Prima code_crafter sui siti trovati (economico), seconda linea; poi (v6) **per le aziende fino a 50 dipendenti ancora senza contatto** code_crafter con i titoli dei titolari (`pipeline.OWNER_TITLES`, nessuna esclusione); poi, **solo per le aziende rimaste senza contatto** e se servono altri lead, i dipendenti dalla pagina LinkedIn dell'azienda (un solo avvio per tutte, seconda linea). Un contatto per azienda. Default per entrambi: 15 ruoli di seconda linea (`DEFAULT_JOB_TITLES`), titolari esclusi (`DEFAULT_EXCLUDE_TITLES`, per code_crafter anche come `contact_not_job_title`), email valida sul dominio dell'azienda, non gia' nel foglio. Un errore di code_crafter non ferma il giro se il ripiego trova qualcuno (l'errore resta nei Dettagli).

**Validazione:**
- Almeno 1 lead; `apify_cost_usd` di tutto il giro <= 0,30
- `discarded`: ogni scarto ha un motivo (titolare o socio, ruolo diverso, paese diverso, email assente, email di un altro dominio, nessuna email valida sul dominio aziendale, non lavora nell'azienda, gia' nel foglio, azienda gia' presa in questo giro)

**Dopo il successo:** `.tmp/leads.json` scritto dall'orchestratore, con `apify_cost_usd` = scoperta + persone (il budget di `write_emails` lo conta)

### Step 3: Scrivi le email

```bash
.venv\Scripts\python.exe implementation/write_emails.py --offer "<offerta>" --sender "<Nome Cognome>"
```

**Schema fisso** (decisione dell'utente, 2026-10-12): Claude scrive solo due frasi, il codice monta il resto.

```
Oggetto: Meno lavoro manuale in {Azienda}          (senza azienda: "Meno lavoro manuale nei reparti IT e operations")
Gentile {Nome Cognome},
{apertura}   <- Claude: 1 frase affermativa sull'azienda, solo dai dati, cita l'azienda
{offerta}    <- OUTREACH_OFFER, fissa
{esempio}    <- Claude: 1 domanda su un'attivita' concreta dell'azienda
Se il tema Le interessa, mi risponda pure: ne parliamo quando Le è più comodo.   (v5: invito leggero)
Cordiali saluti,
{mittente}   <- OUTREACH_SENDER
```

Controlli: `slot_problems` sulle due frasi (max 35 parole, una sola frase, esempio = domanda, apertura = affermazione che cita l'azienda e non parla del mittente) + `quality_problems` sull'email montata (saluto, chiusura, firma, lunghezza, chiusure straniere, esperienze inventate, anglicismi, tu/voi, parole storpiate, supposizioni come fatti, emoji). Se non passa: rigenerata **una volta** con gli errori nel prompt, poi scartata con motivo e frasi scartate (`frasi_scartate`, visibili nel Log).

**Validazione:** exit 0 (`success`) o 4 (`partial`: leggere `errors`); `total_cost_usd` <= 0,50

**Dopo il successo:** `.tmp/emails.json`, `.tmp/run_state.json` (`write_emails`)

### Step 4: Scrivi nel Google Sheet

```bash
.venv\Scripts\python.exe implementation/sheet_export.py [--tag TEST]
```

**Validazione:** exit 0, `rows_written` = numero di email; Stato = "Bozza - non inviata" (con prefisso se `--tag`); duplicati saltati per email

**Dopo il successo:** `.tmp/run_state.json` (`sheet_export`); `alert_user.py success` (nel giro automatico la notifica e' la riga del Log)

## Limiti di Sicurezza

| Limite | Valore | Dove |
|--------|--------|------|
| Budget per giro (Apify + Claude) | 0,50 $ | `write_emails.py` (`MAX_BUDGET_USD`), `pipeline.py` (`RUN_BUDGET_USD`) |
| Tetto mensile | 2,50 $ (5 lunedi' x 0,50 $), letto dal Log prima di spendere | `pipeline.py` (`MONTHLY_CAP_USD`) |
| Tetto di spesa passato ad Apify | 0,50 $ (minimo accettato dall'actor) | `find_leads.py` (`MAX_APIFY_CHARGE_USD`) |
| Lead chiesti all'actor | `count` x 2, max 10; con `--domains` 2 per sito, max 20 | `find_leads.py` (`FETCH_MULTIPLIER`, `MAX_FETCH`, `MAX_FETCH_WITH_DOMAINS`) |
| Pagine Google per query | 2 (max 3) | `discover_companies.py` (`GOOGLE_PAGES`, `MAX_GOOGLE_PAGES`) |
| Aziende controllate su LinkedIn per giro | 10 | `pipeline.py` (`MAX_COMPANIES_PER_RUN`), `discover_companies.py` |
| Profili LinkedIn per giro (ripiego) | 2 per azienda scoperta, max 10 | `find_people_linkedin.py` (`MAX_PROFILES`) |
| Spesa Apify massima del giro | ~0,31 $ (Google 0,011 + aziende 0,04 + code_crafter 0,06 + titolari 0,06 + persone 0,14) | test `test_worst_case_apify_spend_within_run_budget` |
| Aziende gia' controllate | Saltate prima di pagare LinkedIn | scheda "Aziende viste", `run_log.seen_slugs` |
| Max lead per giro | 5 | `pipeline.py`, `find_leads.py`, `write_emails.py`, `sheet_export.py` |
| Tentativi per email | 2 (una rigenerazione) | `write_emails.py` (`MAX_ATTEMPTS`) |
| Un giro per settimana | run id = settimana ISO; un secondo giro non rispende | `run_log.run_already_done` |
| Mai due giri insieme | `max_containers=1`, `retries=0` | `modal_app.py` |
| Invio email | **Mai** | Nessuno script invia; test `test_no_script_sends_email` |
| Duplicati | Scartati prima di Claude (email e sito gia' nel foglio, un contatto per azienda) e di nuovo prima della scrittura | `find_leads.py`, `sheet_export.py` |
| Trigger | Spento salvo `OUTREACH_SCHEDULE=on` al deploy | `modal_app.py` (`SCHEDULE_ON`) |

## Casi Limite

| Situazione | Exit Code | Azione |
|------------|-----------|--------|
| `OUTREACH_OFFER`/`OUTREACH_SENDER` mancanti | 1 | Compilarli nel `.env`, poi `modal_secrets.py` |
| Scheda "Log outreach" con colonne diverse | 1 | Rinominare la scheda o ripristinare l'intestazione (`run_log.LOG_HEADERS`) |
| Chiavi mancanti o rifiutate (Apify, Anthropic, Google) | 2 | Correggere `.env`, poi `modal_secrets.py` |
| Errore Apify / Claude / Google (rete, 5xx), errore imprevisto | 3 | Leggere Dettagli nel Log; rilanciare a mano (il run id non e' bloccato se non ha speso) |
| Nessuna azienda nuova per regione e parole chiave (`vuoto`) | 4 | Possibile nelle regioni piccole con parole chiave di nicchia; la settimana dopo cambiano entrambe. Vedi Note |
| Aziende trovate ma nessun contatto valido (`vuoto`/`parziale`) | 4 | Normale: circa meta' delle aziende non ha una persona di seconda linea con email valida. Le aziende restano segnate come viste |
| Scheda "Aziende viste" non scrivibile | — | Il giro continua, errore in Dettagli (`aziende_viste_error`): il giro dopo potrebbe ripagare quelle aziende |
| Email scartate dai controlli (`parziale`) | 4 | Leggere il motivo in Dettagli; se ricorre, correggere il prompt |
| Giro gia' fatto / tetto mensile (`saltato`) | 4 | Nessuna azione |

## Recupero da Interruzione

- Giro automatico: se fallisce prima di spendere il run id resta libero → rilanciare a mano `modal run implementation/modal_app.py` (stesso run id della settimana). Se ha speso, il run id e' bloccato: per riprovare passare `--run-id <id>-bis`.
- Giro a mano: `.tmp/run_state.json`; `.tmp/leads.json` scritto (step 2 concluso) → `pipeline.py --reuse-leads` (non rispende Apify); `sheet_export` e' idempotente. Le aziende gia' pagate sono in "Aziende viste": un rilancio non le ripaga.

## Operazioni day-2

- **Dove leggere l'esito:** scheda "Log outreach" del Google Sheet (una riga per giro, con parole chiave e aziende trovate/valide) e scheda "Aziende viste" (una riga per azienda); log dettagliati nella dashboard Modal, app `rbi-outreach-unico` (conservati 1 giorno)
- **Rivedere un'azienda gia' vista:** cancellare la sua riga in "Aziende viste"
- **Accendere il lunedi':** PowerShell `$env:OUTREACH_SCHEDULE="on"; .venv\Scripts\modal.exe deploy implementation/modal_app.py; Remove-Item Env:OUTREACH_SCHEDULE`
- **Mettere in pausa / spegnere:** `.venv\Scripts\modal.exe deploy implementation/modal_app.py` (senza la variabile: lo schedule sparisce)
- **Fermare tutto:** `.venv\Scripts\modal.exe app stop rbi-outreach-unico`
- **Dopo modifiche al codice:** rieseguire i test, poi il deploy (con la variabile se il trigger deve restare acceso)
- **Dopo cambio chiavi, offerta o mittente:** aggiornare `.env`, poi `.venv\Scripts\python.exe implementation/modal_secrets.py` (nessun nuovo deploy necessario)
- **Cambiare orario:** `CRON` in `modal_app.py`, poi deploy con la variabile
- **Cambiare regioni, parole chiave, ruoli o dimensioni:** `pipeline.REGIONS`, `discover_companies.DEFAULT_TERMS` (a coppie in `pipeline.TERM_PAIRS`), `find_leads.DEFAULT_JOB_TITLES` / `DEFAULT_EXCLUDE_TITLES` / `DEFAULT_SIZES`, poi test e deploy
- **Giro manuale nel cloud:** `.venv\Scripts\modal.exe run implementation/modal_app.py [--tag TEST] [--dry-run] [--reuse-leads]`

## Stato di verifica

| Parte del workflow | Stato | Come e' stato provato | Data |
|--------------------|-------|-----------------------|------|
| Step 1 per ruolo/paese/settore/dimensione (v2, titolari) | ✅ | dati reali (5 run) | 2026-10-05 |
| Step 1 per specializzazione (`--keywords`, `--require-terms`) | ❌ per nicchie tecnologiche | dati reali: 0 pertinenti su 54 | 2026-10-05 |
| Step 1 per siti (`--domains`) | ✅ precisi, copertura bassa | dati reali | 2026-10-05 |
| Step 2 email (v2) | ✅ dopo correzione del prompt | 2 lead reali | 2026-10-05 |
| Step 3 foglio | ✅ riletto, rilancio senza duplicati | 2 lead reali | 2026-10-05 |
| v3 scoperta filtri seconda linea | ✅ per titoli 4/5 pertinenti; ❌ filtri `seniority_level`/`functional_level` 2/5 | dati reali, 2 run da 5 lead, 0,06 $ | 2026-10-12 |
| v3 Step 1 seconda linea + scarti (titolari, dominio email, gia' nel foglio) | ✅ 5 tenuti su 10, un'azienda scartata perche' gia' nel foglio | dati reali, Lombardia | 2026-10-12 |
| v3 Step 2 controlli di qualita' | ⚠️ 1 email rigenerata e passata, 1 scartata ("aziende simili"); 1 email con "voi" passata al controllo → controllo esteso e testato; errori di senso non coperti | dati reali + test | 2026-10-12 |
| v3 giro completo locale (`pipeline.py`) | ✅ 1 lead, poi 5 lead: 4 righe TEST, Log riletto | dati reali, offerta segnaposto | 2026-10-12 |
| v3 Log | ✅ dopo correzione: la prima scrittura e' finita nella vecchia scheda "Log" con colonne diverse (riga rimossa) | dati reali | 2026-10-12 |
| v3 giro manuale nel cloud (Modal) | ✅ Secret, foglio, Claude 5/5, Log | dati gia' pagati, `--dry-run` | 2026-10-12 |
| v3 trigger automatico (cron vero) | ✅ partito alle 12:18 Europe/Rome (orario di prova), run id 2026-W42, fermato prima di spendere per offerta mancante, riga nel Log; poi trigger rispento (deploy v3 senza schedule) | giro avviato dal cron vero, 0 $ | 2026-10-12 |
| v3 giro completo nel cloud, Lazio | ⚠️ parziale: 5 lead, 3 email (2 scartate per "voi"); alla rilettura 1 con esperienza inventata ("ho sviluppato") e 1 con supposizione → controlli e prompt estesi | dati reali, riga TEST, offerta proposta (Power Platform, Andrea Asselle) | 2026-10-12 |
| v3 giro completo nel cloud, Veneto (dopo il nuovo prompt) | ⚠️ ok sui controlli di allora: 5 lead, 5 email, 0 scartate; alla rilettura 2 con "Develuppo" e 1 con supposizione → controlli estesi; ricontrollo sul foglio: i controlli nuovi intercettano tutte e 5 le email difettose della giornata | dati reali, righe TEST | 2026-10-12 |
| v3 schema fisso, Emilia-Romagna | ⚠️ 3 email su 5: 2 scartate da controlli troppo severi ("sviluppo software" dell'azienda preso per l'offerta; sigle con punti) → corretti e testati; le 3 scritte pulite alla rilettura | dati reali, righe TEST | 2026-10-12 |
| v3 schema fisso, Piemonte (controlli corretti) | ✅ 5 email su 5, 0 scartate; rilette: nessun errore di forma ne' di senso evidente | dati reali, righe TEST | 2026-10-12 |
| v4 ricerca senza limite di dimensione | ✅ nessun `size` inviato, 2 CTO su 4 restituiti, email sul dominio aziendale; entrambi di microaziende (4 e 2 dipendenti) | dati reali, solo step 1, 0,028 $ | 2026-10-12 |
| RBI_Auto_Test: scoperta aziende Google → LinkedIn | ✅ 60-90% pertinenti; ⚠️ persone con email valida in circa meta' delle aziende; aziende ripetute dopo pochi giri (solo pagina 1 di Google) | dati reali (altra cartella, prima dell'unione) | 2026-10-05/12 |
| v5 unione: scoperta + persone + ripiego LinkedIn + "Aziende viste" + rotazione | ⚠️ solo nei test (231 verdi, API mockate) | mock | 2026-10-12 |
| v5 giro reale da capo a fondo, Lombardia + Business Central/Power Platform | ⚠️ parziale: 24 aziende trovate, 10 controllate, 8 valide (tutte partner Microsoft); code_crafter 10 persone ma concentrate su 3 aziende (6 scarti "azienda gia' presa") → 3 lead; ripiego LinkedIn su 5 aziende: 1 profilo restituito, 0 utili; 3 email, 0 scartate dai controlli; alla rilettura 1 su 3 con errore di forma non intercettato ("Nel coordinar dei progetti"); foglio, Log (colonne nuove aggiunte) e "Aziende viste" (10 righe) riletti | dati reali, nessuna etichetta TEST, run id 2026-W42, 0,128 $ (Apify 0,123 + Claude 0,005) | 2026-10-12 |
| v5 correzioni dopo il giro reale (fetch 2 per sito, controllo "infinito troncato") | ⚠️ controllo provato sulle 3 bozze reali: intercetta l'email difettosa, nessun falso allarme sulle altre; fetch solo nei test | dati reali (controllo) + mock (fetch); bozza difettosa corretta a mano nel foglio e riletta | 2026-10-12 |
| v5 trigger su `rbi-outreach-unico` (cron vero, giro completo nel cloud) | ✅ partito alle 16:08 Europe/Rome dal cron (orario di prova, run id `2026-W42-trigger` con `OUTREACH_RUN_ID_SUFFIX`), Secret letto (offerta e mittente compresi), giro completo: 20 aziende trovate, 10 controllate **tutte diverse dal giro precedente** ("Aziende viste" funziona), 8 valide; code_crafter 7 persone → 1 lead; ripiego LinkedIn 2 profili → 1 lead (COO); 2 email, 0 scartate; righe, Log e "Aziende viste" riletti; poi trigger rispento (deploy senza variabili) | dati reali, 0,132 $ (Apify 0,129 + Claude 0,003) | 2026-10-12 |
| v7 ruoli allargati, prova mirata sulle 8 aziende senza contatto dei primi giri | ✅ 3 contatti nuovi (Head of Business Intelligence, CxO, Project Manager) in 3 aziende prima a zero; trovati e corretti 4 scarti sbagliati per estensione diversa (.it/.com) | dati reali, `find_leads.py --domains` + `find_people_linkedin.py`, 0,172 $ | 2026-10-12 |
| v7 giro completo, Veneto + Microsoft Azure/Copilot Studio | ⚠️ parziale: 23 aziende trovate, 10 controllate, solo 3 valide (4 erano community: meetup, podcast, Startup Grind); 1 contatto (Project Manager, ruolo nuovo v7) in un'azienda da 501-1000; 0 nelle altre 2 (11-50 e 201-500); 1 email, forma corretta, domanda finale un po' lunga | dati reali, run id `2026-W42-v7`, 0,181 $ | 2026-10-12 |
| v7 filtro community prima di LinkedIn | ⚠️ solo nei test, con i titoli reali visti nei giri (meetup, podcast, user group, Startup Grind) | mock | 2026-10-12 |
| v7 su Modal (`rbi-outreach-unico`) | ✅ pubblicata senza orario (trigger spento); giro nel cloud non rifatto dopo v6/v7 | deploy | 2026-10-12 |
| v6 titolare nelle aziende fino a 50 dipendenti, Lazio + Dynamics 365/Power Apps | ❌ giro vuoto: 16 aziende trovate, 10 controllate, 4 valide (3 da 2-50 dipendenti, 1 da 1001-5000); code_crafter seconda linea 0, **titolari 0** (le 3 piccole non sono nel database), LinkedIn 0. La regola v6 e' corretta (test) ma non aggiunge contatti se l'azienda non e' nel database. Visti anche: un'azienda delle Marche trovata con la query "Lazio"; un'azienda con il sito del gruppo di cui fa parte | dati reali, run id `2026-W42-v6`, 0,111 $ | 2026-10-12 |
| v5 fetch 2 per sito | ⚠️ attivo nel giro del trigger, ma code_crafter ha restituito solo 7 persone per 8 siti: il limite e' la copertura del database, non il numero chiesto | dati reali | 2026-10-12 |
| v3 con offerta e mittente salvati nel Secret | ⚠️ dedotto, non visto dal vivo: la partenza dal cron e la lettura del Secret (chiavi) sono dimostrate, il giro completo nel cloud pure (offerta passata a mano); OUTREACH_OFFER/SENDER si leggono dal Secret come le chiavi. Accettato dall'utente come verificato (progetto didattico) | cron vero 12:18 + giri cloud manuali | 2026-10-12 |

Resa e costo reali (2026-10-12): Lombardia 5 lead utili su 10, 4 email su 5; Lazio 5 su 10, 3 email su 5; Veneto 5 su 10, 5 email su 5. Circa 0,057 $ a giro (Apify 0,04 + Claude 0,017). Alla rilettura umana 3 email su 13 avevano errori che i controlli di allora non vedevano. Con lo schema fisso (Piemonte): 5 su 10 lead, 5 email su 5, 0,048 $ a giro (Claude 0,008); gli errori visti prima (offerta storpiata, esperienze inventate, "voi" nell'invito) non possono piu' comparire perche' quelle parti sono testo fisso.

## Decisioni dell'utente

- Seconda linea IT/operations/delivery, non i titolari (2026-10-12) — test `TestSecondLine`
- Email da schema fisso: Claude scrive solo apertura ed esempio, offerta/invito/firma fissi (2026-10-12) — test `TestTemplate`
- Titolari, fondatori e soci esclusi anche se hanno un ruolo di seconda linea (es. "Founder & CTO", "Socio e Responsabile IT") — test `test_owners_excluded`
- **"Partner e CTO" si tiene** (Partner non e' un vertice), **"Responsabile tecnico" si esclude** (2026-10-12; in v4 "Partner" era escluso: vale la decisione dell'utente) — test `test_second_line_kept`, `test_partner_not_excluded_responsabile_tecnico_not_target`, `test_partner_e_cto_kept`
- Invito finale leggero, niente "15 minuti" (2026-10-12) — test `test_light_call_to_action`
- (v7) Ruoli allargati a Project Manager, BU Manager / Business Unit Manager, Head of Business Intelligence, CxO (2026-10-12) — test `test_second_line_kept`
- (v6) Titolare accettato solo nelle aziende fino a 50 dipendenti (fascia LinkedIn), solo se la seconda linea non si trova; limite 50 scelto da me sulla richiesta "a+b" dell'utente, che puo' cambiarlo (`pipeline.OWNER_OK_MAX_EMPLOYEES`) (2026-10-12) — test `test_owner_accepted_only_up_to_50_employees`, `test_owner_only_in_small_uncovered_companies`
- Prima le aziende di nicchia Microsoft, con le 8 parole chiave dell'utente a rotazione insieme alla regione; fonte attuale (Google → LinkedIn) migliorata, seconda fonte (Indeed / elenco partner Microsoft) da valutare dopo (2026-10-12) — test `test_terms_rotation_with_region`
- Unico workflow, stesso Google Sheet (da svuotare dei record di prova, con consenso) (2026-10-12)
- Giro ogni lunedi' mattina, senza lancio manuale (2026-10-12) — test `test_schedule_off_unless_explicit` (resta spento finche' l'utente non chiede l'accensione)
- Budget 0,50 $ a giro — test `test_run_budget_and_monthly_cap`
- Nessun limite di dimensione aziendale, ne' minimo ne' massimo (2026-10-12), anche sapendo che entrano microaziende e consulenti singoli — test `test_no_company_size_limit_by_default`, `test_explicit_sizes_still_supported`
- Le email non vanno mai inviate — test `test_no_script_sends_email`
- Una regione a settimana, 5 lead a giro (2026-10-12) — test `test_region_rotation`

## Note

- Scoperta 2026-10-12: i filtri strutturati dell'actor (`seniority_level` c_suite/director/head/manager, `functional_level` IT/operations) restituiscono Chief Strategy Officer e soci: 2/5 pertinenti. L'elenco di titoli (`contact_job_title`) da' 4/5. Si usa l'elenco + `contact_not_job_title` per i titolari (gli esclusi non vengono addebitati).
- L'actor cerca il titolo come testo libero e non ha paginazione: con gli stessi filtri restituisce sempre le stesse persone nello stesso ordine. In v5 code_crafter cerca solo dentro i siti trovati nello step 1, quindi la ripetizione dipende dalla scoperta aziende: per questo rotazione parole chiave × regione, 2 pagine Google e "Aziende viste".
- (v5, da RBI_Auto_Test) Le aziende si ripetevano perche' si leggeva solo la prima pagina di Google e l'ordine dei risultati e' stabile. Con la regione nella query le regioni piccole (es. Calabria, Umbria) possono dare pochi risultati: aspettarsi giri `vuoto` e verificarlo nei primi giri reali.
- (v5) La regione serve a variare i risultati di Google; la sede dell'azienda si controlla solo come "Italia" (non come regione), e la persona si cerca in tutta Italia.
- (v5) Le righe di "Aziende viste" create dai giri di prova (tag TEST) vanno cancellate insieme alle righe TEST del foglio, altrimenti quelle aziende restano escluse.
- (v5) LinkedIn: solo dati pubblici tramite actor Apify; mai l'account o i cookie dell'utente.
- (v5) Resa reale dei primi 2 giri (Lombardia, Business Central/Power Platform): 16 aziende valide su 20 controllate, 5 contatti (3 + 2), circa 0,13 $ a giro, cioe' ~0,026 $ a bozza. Il collo di bottiglia e' trovare una persona di seconda linea con email valida: circa 1 azienda valida su 3.
- (v5) Rilettura delle email del giro dal trigger: forma corretta; una frase sull'azienda e' vaga e probabilmente dedotta dal nome (errore di senso, non intercettabile dai controlli). Rileggere sempre le bozze.
- (v5, prove del rapporto `reports/Actor Apify per lead migliori.md`, 2026-10-12, dati reali, ~0,11 $ in tutto) Nessuna alternativa aumenta i contatti sulle 16 aziende valide dei primi due giri:
  - B `pipelinelabs/lead-scraper-apollo-zoominfo-lusha-ppe` con `countOnly` (gratis): 9 persone con email verificata in 4 aziende su 16, tutte gia' coperte tranne 1; seconda linea 1 sola (gia' nel foglio). Copertura peggiore di code_crafter.
  - C `harvestapi/linkedin-profile-search` (seniority 210/220/300/310 + funzioni IT/Operations/Engineering/Project, 11 aziende senza contatto): 3 profili, 1 pertinente (CTO) ma senza email; 0,11 $. Filtri combinati forse troppo stretti: non provata senza funzioni.
  - A `qualifyops/email-finder-verified` e `blessiticus/b2b-work-email-finder...` sul CTO senza email: entrambi NOT_FOUND (4 e 14 pattern rifiutati dal server), 0 $ (pagano solo se trovano).
  - (b) `harvestapi/linkedin-profile-search` modalita' Short senza filtri di funzione su 8 aziende senza contatto (0,10 $): 25 profili, 1 solo di seconda linea secondo la nostra lista (lo stesso CTO, email non trovata da qualifyops), 6 titolari, 18 altri. Tra gli "altri" ruoli forse utili ma fuori lista: Project Manager, BU Manager, Head of Business Intelligence, CxO. Allargare la lista dei ruoli e' una decisione dell'utente.
  - Conclusione: nelle piccole aziende IT italiane le persone di seconda linea con email verificabile sono poche in tutte le fonti provate; la resa (~1 contatto ogni 3 aziende valide) sembra strutturale. La leva rimasta e' il numero di aziende in ingresso (es. directory partner Microsoft, prova F del rapporto).
- (v5) Prova del trigger: `OUTREACH_SCHEDULE=on`, `OUTREACH_CRON="<min> <ora> * * *"`, `OUTREACH_RUN_ID_SUFFIX=trigger` al deploy; poi deploy normale senza variabili per spegnere.
- (v5, primo giro reale) Il ripiego LinkedIn sulle 5 aziende scoperte ha restituito 1 solo profilo, non utile (0,03 $ a vuoto): resa da osservare nei prossimi giri prima di cambiarlo.
- (v5) `OUTREACH_OFFER` e `OUTREACH_SENDER` nel `.env` di `RBI_Workflow_Unico` (offerta neutra di esempio, firma "Andrea Asselle"), scritti il 2026-10-12.
- `company_size` puo' non rispettare il filtro `size` (visti 4 e 13 dipendenti con filtro 11-200): il dato dell'actor e' approssimativo.
- Email di un altro dominio rispetto al sito (gruppo, lavoro precedente) ora scartate nel codice. Se il sito manca il controllo non si puo' fare.
- Ruoli scartati di proposito: "Direttore Tecnico" (spesso produzione, non IT), "Vice President IT" (non in elenco), "Product Owner", "Delivery Partner". Il confronto e' a parola intera.
- Errori di Haiku visti nelle email v3: "voi" mescolato al Lei ("gestite", "interessarVi", "supportarvi") anche con la regola nel prompt → controllo nel codice. Errori di senso non intercettabili: supposizioni presentate come fatti ("in banche come <Azienda> ... molti processi ancora manuali"). Le bozze vanno rilette prima dell'uso.
- Altri errori di Haiku visti il 2026-10-12 e ora nei controlli: parole storpiate ("Develuppo"), esperienze attribuite al mittente ("Ho sviluppato soluzioni che..."), generalizzazioni come fatti ("in realtà come la Sua i team spesso..."). I controlli restano incompleti: rileggere sempre le bozze.
- Il campo ruolo puo' contenere caratteri invisibili (zero-width): `sheet_export.clean_title` li toglie.
- `modal run ... --region-index N` sceglie la regione per le prove; il cron usa sempre quella della settimana.
- Le righe TEST nel foglio contano come "gia' nel foglio": quelle persone non riceveranno una bozza vera finche' le righe TEST non vengono cancellate.
- Pulizia del 2026-10-12, su richiesta dell'utente: cancellate da Foglio1 le 41 righe di prova (TEST e AUTO-TEST, backup locale prima) e la scheda "Log" della vecchia automazione; fermate le app Modal `rbi-outreach-auto` e `cold-outreach-v3`; eliminati Task, Schedule e webhook Apify `rbi-outreach-auto`. Restano: Foglio1 (bozze vere), "Log outreach" (storia della spesa, serve al tetto mensile), "Aziende viste", app Modal `rbi-outreach-unico` (trigger spento).
- Prompt email (v2): senza regole esplicite Haiku chiudeva in francese e inventava esperienze del mittente; regole mantenute.
- Campi reali dell'output code_crafter: `first_name, last_name, full_name, email, personal_email, mobile_number, job_title, linkedin, company_name, company_website, industry, company_size, headline, seniority_level, functional_level, city, state, country, company_linkedin, company_founded_year, company_description, company_annual_revenue_clean, company_technologies`. Nessun campo di affidabilita' dell'email.
- Gli eventi `lead-fetched` compaiono nel run solo a fine esecuzione: il costo reale va riletto dopo (`usageTotalUsd`), coincide con la stima (0,03 $ per 5 lead).
- I lead contengono dati personali: trattarli nel rispetto del GDPR (informativa, opt-out) prima di inviare qualsiasi email reale.
- Su Windows gli script forzano stdout/stderr UTF-8; i comandi Python in linea con heredoc nella shell non funzionano: usare file.
- Senza limite di dimensione entrano microaziende e consulenti singoli (prova v4: 4 e 2 dipendenti), dove il "CTO" puo' coincidere con il titolare. Scelta consapevole dell'utente; se servisse, `--sizes` permette di reintrodurre un minimo.
