# Rule: <Nome Workflow> (v1)

<Solo dalla v2 in poi: cosa e' cambiato rispetto alla versione precedente e perche'. La versione precedente e' in `<nome>.v1.md`.>

## Obiettivo

<Una frase: cosa produce il workflow e per chi (es. quali entita', quali ruoli).>

## Trigger

**A richiesta** — l'utente dice qualcosa come:

- "<frase esempio 1>"
- "<frase esempio 2>"

**Automatico** (se previsto, vedi automation-rules della skill) — <orario / webhook / evento>, dove gira, come si attiva e come si spegne. Spento finche' l'utente non chiede di attivarlo.

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

## Operazioni day-2 (solo workflow automatici)

- Mettere in pausa: <comando>
- Fermare tutto: <comando>
- Dopo modifiche al codice: <comando di deploy>
- Dopo cambio chiavi: <comando>
- Dove leggere l'esito di ogni giro: <Log>

## Stato di verifica

Aggiornare dopo ogni esecuzione reale.

| Parte del workflow | Stato | Come e' stato provato | Data |
|--------------------|-------|-----------------------|------|
| <step 1> | ✅ / ⚠️ / ❌ | dati reali / mock / dato inventato | <data> |
| <trigger automatico, se previsto> | ✅ / ⚠️ / ❌ | giro avviato dal trigger vero | <data> |

Resa e costo reali: <es. 2 risultati utili su 6, 0,10 $ per giro>.

## Decisioni dell'utente

- <es. "il ruolo X si tiene, Y no"> — fissata dal test `<nome del test>`

## Note

- <cose imparate, edge case scoperti, da aggiornare a ogni nuovo apprendimento>
