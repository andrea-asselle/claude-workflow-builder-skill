# Rule: <Nome Workflow> (v1)

## Obiettivo

<Una frase: cosa produce il workflow e per chi.>

## Trigger

L'utente dice qualcosa come:

- "<frase esempio 1>"
- "<frase esempio 2>"

## Input Richiesti

- `<input_obbligatorio>` (obbligatorio) — <descrizione>
- `<input_opzionale>` (opzionale) — <descrizione e default>

## Prerequisiti

- File `.env` con: `<VARIABILI>`
- <credenziali OAuth / altri file>
- Dipendenze: `pip3 install -r requirements.txt`

## Pipeline

### Step 1: <Nome>

```bash
python3 implementation/<script_1>.py --<arg> <valore>
```

**Validazione:**
- Exit code 0
- <campo JSON> presente / >= atteso

**Dopo il successo:**
- Salvare output in `.tmp/<file>.json`
- Aggiornare `.tmp/run_state.json`

### Step 2: <Nome>

(ripetere lo schema)

## Limiti di Sicurezza

| Limite | Valore | Dove |
|--------|--------|------|
| <es. max elementi per run> | <valore> | `<script>.py` (`<COSTANTE>`) |

## Casi Limite

| Situazione | Exit Code | Azione |
|------------|-----------|--------|
| `.env` mancante | 1/2 | Istruzioni per creare `.env` |
| Errore API | 3 | Ritentare, poi escalare |
| Dati vuoti | 4 | Verificare i filtri |

## Recupero da Interruzione

Leggere `.tmp/run_state.json`:

- Step 1 completato → `.tmp/<file>.json` esiste, saltare a step 2

## Note

- <cose imparate, edge case scoperti, da aggiornare a ogni nuovo apprendimento>
