---
name: new-rbi-workflow
description: Crea un nuovo workflow nel progetto RBI (Rules-Brain-Implementation): scrive la Rule in rules/, gli script deterministici in implementation/, i test e aggiorna CLAUDE.md. Usa quando l'utente vuole "creare/aggiungere/costruire un nuovo workflow", automazione o SOP in questo progetto.
---

# Nuovo workflow RBI (v2)

Un workflow RBI = **1 Rule** (cosa) + **N script** (come) + **test** + riga in CLAUDE.md. Il Brain (tu) non esegue logica: la delega agli script.

Vale per qualsiasi tipo di workflow (fatture, CRM, report, sincronizzazione dati, scraping, email...).

## Procedura

Segui gli step in ordine. Non passare allo step successivo se la validazione fallisce.

### 1. Chiarisci (max 4 domande, solo se non deducibili)
- Obiettivo e trigger (che frase dice l'utente?)
- Input obbligatori/opzionali
- Servizi esterni e credenziali necessarie (`.env`, OAuth)
- Effetti collaterali irreversibili (invio email, scrittura dati, costi API)?
- Vincoli dell'utente: budget, piano gratuito o a pagamento, account personale o aziendale

### 2. Prepara il progetto
- Usa l'interprete del progetto (es. `.venv`), non `python3` di sistema.
- Se mancano le basi (caricamento `.env`, file dei test, `.tmp/run_state.json`, notifica di fine), **creale prima di tutto**. Se esistono (`load_env.py`, `google_auth.py`, `clickup_api.py`, `alert_user.py`...), riusale.
- Crea un nuovo script solo se la responsabilita' non e' gia' coperta.

### 3. Verifica le dipendenze esterne PRIMA di costruire
Per ogni servizio, API o libreria esterna, leggi la documentazione ufficiale (scheda, README, pagina prezzi) e riporta all'utente, in una tabella:

| Servizio | Piano richiesto | Uso via API/script | Costo minimo per esecuzione | Limiti/quote | Permessi richiesti |
|---|---|---|---|---|---|

- Se un vincolo e' incompatibile con i requisiti o con i vincoli dell'utente (piano gratuito, budget, permessi): **fermati e dillo prima di scrivere codice**, con le alternative.
- Se devi scegliere tra piu' servizi, confronta almeno 2-3 opzioni con questi criteri. Non scegliere a memoria.
- **Niente a memoria:** nomi di modelli, versioni di API, endpoint e nomi dei campi vanno presi dalla documentazione. Per l'API di Claude usa la skill `claude-api`.

### 4. Chiamata di scoperta
Prima di scrivere il codice che legge una risposta esterna, fai **una chiamata reale e minima** (1 elemento, costo minimo) e guarda la forma vera della risposta: nomi dei campi, campi vuoti, formato degli errori. Scrivi la mappatura dei dati su quella, non su nomi ipotizzati. Se la chiamata costa, dichiaralo prima.

### 5. Scomponi in step
Uno script = una responsabilita' (es. prendi dati → trasforma → scrivi). Ogni step ha un output verificabile (JSON su stdout) e un exit code per ogni tipo di errore. L'output di uno step e' l'input del successivo tramite file in `.tmp/`.

**Se un vincolo obbliga a cambiare cosa fa il workflow** (es. un servizio non supporta la ricerca richiesta), chiedi all'utente prima di procedere.

### 6. Scrivi la Rule
Copia [rule-template.md](rule-template.md) in `rules/<nome_workflow>.md` (versione `v1`). Sezioni obbligatorie: Obiettivo, Trigger, Input, Prerequisiti, Dipendenze esterne (la tabella dello step 3), Pipeline (comando + **Validazione** + **Dopo il successo** per ogni step), Limiti di Sicurezza, Casi Limite, Recupero da Interruzione, Stato di verifica.
Non sovrascrivere una Rule esistente senza permesso: crea `v2`.

### 7. Scrivi gli script
Parti da [script-template.py](script-template.py) e **segui tutte le regole di [script-rules.md](script-rules.md)** (timeout, controllo delle risposte, esito per elemento, azioni ripetibili, modalita' di prova, ambiente Windows).

### 8. Test
Una classe di test per script, con API esterne mockate (`@patch`). Copri: successo, input non valido, credenziale mancante, errore API, dati vuoti, **risposta di errore con esito "riuscito"**, rilancio senza duplicati. Esegui i test con l'interprete del progetto e mostra l'esito reale.

I test con API simulate **non dimostrano** che il workflow funziona: servono solo a proteggere la logica.

### 9. Documenta
- Riga nella tabella "Workflow disponibili" di `CLAUDE.md`
- Nuove dipendenze in `requirements.txt`, variabili in `.env.example`

### 10. Esecuzione reale
1. Prima con **1 solo elemento reale** e, se previsto, in modalita' di prova (`--dry-run` / `--tag TEST`).
2. Poi con l'input richiesto dall'utente.
Valida ogni step con i criteri della Rule, **rileggi il risultato finale dalla destinazione** (foglio, CRM, file...) invece di fidarti dell'output dello script, salva lo stato in `.tmp/run_state.json` dopo ogni step, poi notifica la fine.

## Quando il workflow e' "finito"
Solo quando ha girato **da capo a fondo con dati reali** e il risultato e' stato riletto dalla destinazione. Una prova con dati finti, con API simulate o con un solo step funzionante **non** conta come prova completa.

## Rapporto finale (obbligatorio)
Chiudi sempre con questa tabella, senza abbellire:

| Parte del workflow | Stato | Come e' stato provato |
|---|---|---|
| ... | ✅ dimostrato / ⚠️ solo nei test o con dati finti / ❌ non funziona | dati reali / mock / dato inventato |

Se la parte centrale del workflow (quella che produce il valore) non funziona, dillo nella prima riga del rapporto.

## Regole
- Se un output non torna: fermati e diagnostica. Max 3 tentativi, poi chiedi all'utente.
- Cio' che impari dagli errori va nella Rule (sezione Note), non solo nello script.
- Prima di azioni esterne irreversibili (email reali, scritture su CRM, pagamenti) o di approvare permessi su servizi di terzi: chiedi all'utente.
- Non chiedere all'utente di incollare chiavi in chat: indicagli quali variabili mettere nel `.env`.
- Non committare `.env`, `credentials.json`, `token.json`.
