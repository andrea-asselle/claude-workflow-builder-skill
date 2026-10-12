---
name: new-rbi-workflow
description: Crea o modifica un workflow nel progetto RBI (Rules-Brain-Implementation): Rule in rules/, script deterministici in implementation/, test, CLAUDE.md; anche workflow automatici (orario, webhook, eventi). Usa quando l'utente vuole "creare/aggiungere/costruire un nuovo workflow", "modificare/cambiare/aggiornare un workflow" (es. cambiare servizio, fonte dati, destinatari), automatizzarlo o renderlo pianificato.
---

# Workflow RBI: creare e modificare (v3)

Un workflow RBI = **1 Rule** (cosa) + **N script** (come) + **test** + riga in CLAUDE.md. Il Brain (tu) non esegue logica: la delega agli script. In un workflow **automatico** il Brain non c'e': il suo lavoro lo fa un **orchestratore** nel codice.

Vale per qualsiasi tipo di workflow (fatture, CRM, report, sincronizzazione dati, scraping, email...).

**Prima di tutto scegli la modalita':**
- **A. Nuovo workflow** → sezione A
- **B. Modifica di un workflow esistente** (servizio, fonte dati, destinatari, regole, trigger) → sezione B

Regole comuni: [script-rules.md](script-rules.md) per ogni script, [automation-rules.md](automation-rules.md) se il workflow parte da solo.

---

## A. Nuovo workflow

Segui gli step in ordine. Non passare allo step successivo se la validazione fallisce.

### A1. Chiarisci (max 4 domande, solo se non deducibili)
- Obiettivo, e **chi o cosa** deve produrre (per un outreach: quali aziende, quali ruoli)
- **Trigger:** a richiesta (l'utente lo chiede) o **automatico** (orario, webhook, evento)? Se automatico, segui anche [automation-rules.md](automation-rules.md)
- Input, servizi esterni, credenziali (`.env`, OAuth)
- Effetti irreversibili (invio email, scritture, costi) e vincoli dell'utente (budget, piano gratuito o a pagamento)

### A2. Prepara il progetto
- Interprete del progetto (es. `.venv`), non `python3` di sistema.
- Se mancano le basi (caricamento `.env`, test, `.tmp/run_state.json`, notifica di fine), **creale prima**. Se esistono, riusale.

### A3. Verifica le dipendenze esterne PRIMA di costruire
Per ogni servizio, API o libreria esterna leggi la documentazione ufficiale (scheda, README, prezzi, schema di input) e riporta all'utente:

| Servizio | Piano richiesto | Uso via API/script | Costo minimo per esecuzione | Limiti/quote | Permessi richiesti |
|---|---|---|---|---|---|

- Vincolo incompatibile con i requisiti o con i vincoli dell'utente → **fermati e dillo prima di scrivere codice**, con le alternative.
- Scelta tra piu' servizi: confronta 2-3 opzioni con questi criteri e con **criteri di qualita' decisi prima della prova** (es. "almeno 2 risultati pertinenti su 3"). Non scegliere a memoria.
- **Niente a memoria:** modelli, versioni, endpoint, nomi dei campi, valori di default pericolosi (es. "numero di risultati: 100.000") vanno presi dalla documentazione. Per l'API di Claude usa la skill `claude-api`.
- **Fonti di dati:** i database (aziende, persone) cercano per nome, settore, dimensione, ruolo; **non** per "di cosa si occupa". Se serve una nicchia, separa i passi: prima trova le **entita'** con una ricerca nel testo (es. Google), poi **arricchiscile**, poi cerca le **persone**.

### A4. Chiamata di scoperta
Prima di scrivere il codice che legge una risposta esterna, **una chiamata reale e minima** (1 elemento, costo minimo; dichiaralo prima). Guarda la forma vera: nomi dei campi, campi vuoti, formato degli errori, **cosa cerca davvero il filtro** (es. una ricerca "per parola chiave" puo' cercare solo nel nome). Scrivi la mappatura su quella.

### A5. Scomponi in step
Uno script = una responsabilita'. Output verificabile (JSON su stdout), un exit code per ogni tipo di errore, passaggio di dati tramite file in `.tmp/`. Se un vincolo obbliga a cambiare cosa fa il workflow, chiedi all'utente prima di procedere.

### A6. Scrivi la Rule
Copia [rule-template.md](rule-template.md) in `rules/<nome_workflow>.md` (`v1`). Sezioni obbligatorie: Obiettivo, Trigger, Input, Prerequisiti, Dipendenze esterne, Pipeline (comando + **Validazione** + **Dopo il successo**), Limiti di Sicurezza, Casi Limite, Recupero da Interruzione, Stato di verifica. Per i workflow automatici anche: Operazioni day-2.

### A7. Scrivi gli script
Parti da [script-template.py](script-template.py) e segui **tutte** le regole di [script-rules.md](script-rules.md).

### A8. Test
Una classe di test per script, API esterne mockate. Copri: successo, input non valido, credenziale mancante, errore API, dati vuoti, risposta di errore con esito "riuscito", rilancio senza duplicati, **duplicati scartati prima delle chiamate a pagamento**. I test **non devono mai toccare risorse reali** (vedi script-rules §9). I test con mock **non dimostrano** che il workflow funziona.

### A9. Documenta
Riga in `CLAUDE.md`; dipendenze in `requirements.txt`; variabili in `.env.example`.

### A10. Esecuzione reale
1. **1 solo elemento reale**, in modalita' di prova (`--dry-run` / `--tag TEST`).
2. Poi l'input richiesto. Valida ogni step con la Rule, **rileggi il risultato dalla destinazione** (foglio, CRM, file...), salva lo stato, notifica la fine.
3. **Rileggi il contenuto prodotto** (es. le email): i controlli automatici prendono gli errori di forma, non quelli di senso.
4. Workflow automatico: prova anche **il trigger vero** (vedi automation-rules §8), poi lascia il trigger **spento** finche' l'utente non chiede di attivarlo.

---

## B. Modifica di un workflow esistente

### B1. Leggi prima di toccare
Leggi la Rule, gli script coinvolti, i test e la sezione **Stato di verifica**. Elenca all'utente cosa cambia, cosa resta uguale e quali parti gia' provate potrebbero rompersi.

### B2. Lavora su una copia se il workflow funziona
Se il workflow attuale funziona e la modifica e' sperimentale (es. nuovo fornitore di dati), lavora in una **copia della cartella** e cambia solo il necessario; il workflow che funziona resta intatto.

### B3. Se cambia un servizio esterno
Ripeti **A3 e A4** per il nuovo servizio: verifica, confronto con criteri fissati prima, chiamata di scoperta. Non dare per scontato che i campi, i filtri o i limiti siano uguali a quelli del vecchio.

### B4. Modifica minima e versionata
- Cambia solo il necessario; non riscrivere script che non c'entrano.
- **Rule:** salva la versione attuale (es. `rules/<nome>.v1.md`) e scrivi la nuova (`v2`) con in cima cosa e' cambiato e perche'.
- Le **decisioni dell'utente** (es. "questo ruolo si tiene, quest'altro no") vanno nella Rule e in un **test** che le fissa.

### B5. Test
Aggiorna i dati di prova al nuovo comportamento, aggiungi i test del caso nuovo, riesegui **tutta** la suite: un test rotto per la modifica va capito, non solo aggiornato.

### B6. Esecuzione reale e Stato di verifica
Come A10. Aggiorna lo **Stato di verifica**: le righe vecchie restano, le nuove dicono cosa e' stato provato dopo la modifica.

---

## Quando il workflow e' "finito"
Solo quando ha girato **da capo a fondo con dati reali** (e, se automatico, partendo dal trigger vero) e il risultato e' stato riletto dalla destinazione. Dati finti, mock o un solo step funzionante **non** bastano.

## Rapporto finale (obbligatorio)
Chiudi sempre con questa tabella, senza abbellire:

| Parte del workflow | Stato | Come e' stato provato |
|---|---|---|
| ... | ✅ dimostrato / ⚠️ funziona con limiti o solo nei test / ❌ non funziona | dati reali / mock / dato inventato |

Aggiungi **resa e costo reali** (es. "2 risultati utili su 6, 0,10 $ per giro"). Se la parte che produce il valore non funziona o rende poco, dillo nella prima riga.

## Regole
- Output che non torna: fermati e diagnostica. Max 3 tentativi, poi chiedi all'utente.
- Cio' che impari va nella Rule (sezione Note), non solo nello script.
- Prima di azioni irreversibili (invii, scritture su CRM, pagamenti), di approvare permessi su servizi di terzi o di **attivare un trigger automatico**: chiedi all'utente.
- Non chiedere all'utente di incollare chiavi in chat: indicagli quali variabili mettere nel `.env`.
- Non committare `.env`, `credentials.json`, `token.json`.
