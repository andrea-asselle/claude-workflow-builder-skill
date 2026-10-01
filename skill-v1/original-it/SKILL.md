---
name: new-rbi-workflow
description: Crea un nuovo workflow nel progetto RBI (Rules-Brain-Implementation): scrive la Rule in rules/, gli script deterministici in implementation/, i test in test_all.py e aggiorna CLAUDE.md. Usa quando l'utente vuole "creare/aggiungere/costruire un nuovo workflow", automazione o SOP in questo progetto.
---

# Nuovo workflow RBI

Un workflow RBI = **1 Rule** (cosa) + **N script** (come) + **test** + riga in CLAUDE.md. Il Brain (tu) non esegue logica: la delega agli script.

## Procedura

Segui gli step in ordine. Non passare allo step successivo se la validazione fallisce.

### 1. Chiarisci (max 4 domande, solo se non deducibili)
- Obiettivo e trigger (che frase dice l'utente?)
- Input obbligatori/opzionali
- Servizi esterni e credenziali necessarie (`.env`, OAuth)
- Effetti collaterali irreversibili (invio email, scrittura dati, costi API)?

### 2. Riusa prima di creare
Leggi `implementation/` e le Rules esistenti. Riusa `load_env.py`, `google_auth.py`, `clickup_api.py`, `alert_user.py`. Crea un nuovo script solo se la responsabilita' non e' gia' coperta.

### 3. Scomponi in step
Uno script = una responsabilita'. Ogni step deve avere un output verificabile (JSON su stdout) e un exit code dedicato per ogni tipo di errore. Se ci sono piu' step, l'output di uno e' l'input del successivo tramite file in `.tmp/`.

### 4. Scrivi la Rule
Copia [rule-template.md](rule-template.md) in `rules/<nome_workflow>.md` (versione `v1`). Sezioni obbligatorie: Obiettivo, Trigger, Input, Prerequisiti, Pipeline (comando + **Validazione** + **Dopo il successo** per ogni step), Limiti di Sicurezza, Casi Limite (tabella exit code → azione), Recupero da Interruzione.
Non sovrascrivere una Rule esistente senza permesso: crea `v2`.

### 5. Scrivi gli script
Parti da [script-template.py](script-template.py). Convenzioni del progetto:
- Docstring con Usage, Exit codes, Prerequisites
- `argparse`, `load_env()`, import locali via `sys.path.insert`
- Output di successo: JSON su stdout con `status` e `timestamp`
- Errori: JSON `{"error": ...}` su stderr + exit code (0 ok, 1 input, 2 auth/credenziali, 3 errore API, 4 dati vuoti/parziali)
- Hard limit in costanti (costi, quantita') per ogni azione che spende soldi o e' irreversibile
- Nessun segreto nel codice: solo `.env`, aggiorna `.env.example`

### 6. Test
Aggiungi in `implementation/test_all.py` una classe di test per script, con API esterne mockate (`@patch`). Copri: successo, input non valido, credenziale mancante, errore API, dati vuoti. Esegui `python3 -m pytest implementation/test_all.py -v` e mostra l'esito reale.

### 7. Documenta
- Aggiungi la riga nella tabella "Workflow disponibili" di `CLAUDE.md`
- Aggiungi nuove dipendenze a `requirements.txt` e variabili a `.env.example`

### 8. Prima esecuzione controllata
Esegui il workflow con input minimo (es. 1 elemento). Valida ogni step con i criteri della Rule, salva lo stato in `.tmp/run_state.json` dopo ogni step, poi `python3 implementation/alert_user.py success`.

## Regole
- Se un output non torna: fermati e diagnostica. Max 3 tentativi, poi chiedi all'utente.
- Cio' che impari dagli errori va nella Rule (non nello script a caso).
- Prima di azioni esterne irreversibili (email reali, scritture su CRM) conferma con l'utente.
- Non committare `.env`, `credentials.json`, `token.json`.
