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
- Dipendenze in `requirements.txt`, installate con l'interprete del progetto (es. `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`)

## Dipendenze esterne

Verificate dalla documentazione ufficiale il <data>.

| Servizio | Piano richiesto | Uso via API/script | Costo minimo per esecuzione | Limiti/quote | Permessi richiesti |
|----------|-----------------|--------------------|-----------------------------|--------------|--------------------|
| <servizio> | <gratuito/pagamento> | <si/no> | <costo> | <limiti> | <permessi> |

## Pipeline

### Step 1: <Nome>

```bash
<interprete del progetto> implementation/<script_1>.py --<arg> <valore> [--dry-run]
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

## Stato di verifica

Aggiornare dopo ogni esecuzione reale.

| Parte del workflow | Stato | Come e' stato provato | Data |
|--------------------|-------|-----------------------|------|
| <step 1> | ✅ / ⚠️ / ❌ | dati reali / mock / dato inventato | <data> |

## Note

- <cose imparate, edge case scoperti, da aggiornare a ogni nuovo apprendimento>
