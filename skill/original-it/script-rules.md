# Regole per gli script RBI

Valgono per ogni script in `implementation/`, qualunque cosa faccia.

## Struttura
- Docstring con Usage, Exit codes, Prerequisites.
- `argparse`, caricamento del `.env`, import locali via `sys.path.insert`.
- Successo: JSON su stdout con `status` e `timestamp`.
- Errore: JSON `{"error": ...}` su stderr + exit code: 0 ok, 1 input, 2 auth/credenziali, 3 errore API, 4 dati vuoti o parziali.
- Hard limit in costanti per ogni azione che spende soldi o e' irreversibile (quantita', costo per esecuzione).
- Nessun segreto nel codice: solo `.env`, e aggiornare `.env.example`.

## 1. Timeout
Ogni chiamata esterna (HTTP, SDK, database, subprocess) ha un timeout esplicito. Nessuna attesa infinita.

## 2. Controllo della forma della risposta
- Non fidarti dello status "riuscito": verifica che la risposta abbia la forma attesa (campi obbligatori presenti, tipo giusto).
- Un messaggio di errore, un oggetto informativo o una riga di riepilogo **non devono mai diventare dati validi**. Se la risposta non ha la forma attesa: exit code 3, nessun file di output scritto.
- Se la risposta ha righe di tipo diverso (dati, riepilogo, info), filtra esplicitamente solo quelle di dati.

## 3. Esito per ogni elemento
Se lo script elabora piu' elementi (aziende, clienti, fatture, righe...), l'output riporta per ciascuno: ok / saltato / fallito + motivo. Esempio:
```json
"items": [
  {"input": "acme.it", "status": "ok", "count": 2},
  {"input": "beta.it", "status": "empty", "reason": "nessun risultato"}
]
```
Se una parte fallisce ma le altre no: exit code 4 (parziale), non 0.

## 4. Azioni ripetibili senza danni (idempotenza)
Se lo script scrive, invia, crea o modifica qualcosa all'esterno, un secondo lancio con lo stesso input **non deve duplicare** l'effetto: controlla cosa e' gia' stato fatto (chiave univoca, stato in `.tmp/`) e saltalo, riportando `skipped_duplicates`. Non cancellare e riscrivere dati esistenti per evitare i duplicati.

## 5. Tentativi
Ritenta solo errori temporanei (timeout, 429, 5xx) e solo per operazioni ripetibili senza danni. Attesa crescente (es. 1s, 2s, 4s), massimo 3 tentativi. Mai ritentare errori di input, di autenticazione o di permessi.

## 6. Modalita' di prova
Ogni script con effetti esterni ha un'opzione per provarlo senza conseguenze:
- `--dry-run`: esegue tutto tranne l'azione finale e mostra cosa farebbe, oppure
- `--tag TEST`: esegue l'azione ma marca chiaramente i dati come prova.

## 7. Costi
- Se lo script spende, stima il costo prima di ogni chiamata e fermati se supera il tetto per esecuzione.
- Dopo l'esecuzione, leggi il **costo reale** dal servizio quando possibile, invece di riportare solo la stima.

## 8. Ambiente (Windows)
- Forza UTF-8 all'inizio di `main()`: `sys.stdout.reconfigure(encoding="utf-8")` e lo stesso per `stderr`.
- Leggi e scrivi i file con `encoding="utf-8"`.
- Non usare script Python scritti in linea nei comandi di shell: salvali in un file e lanciali da li'.
- Usa l'interprete del progetto e dai un timeout ai comandi lunghi.
