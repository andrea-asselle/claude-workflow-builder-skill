# Regole per i workflow automatici (v3)

Valgono quando il workflow parte da solo: a orario, da un webhook o da un evento. Nessuno legge la Rule durante l'esecuzione e nessuno rilegge l'output: tutto quello che faceva il Brain va nel codice.

## 1. Scelta del trigger
Verifica il trigger come un servizio esterno (SKILL A3) e scegli il piu' semplice che copre il caso:

| Trigger | Quando | Esempi |
|---|---|---|
| Orario nel cloud | Giri periodici, PC spento | Modal `Cron`, scheduler della piattaforma |
| Schedule del fornitore + webhook | Un solo servizio esterno da lanciare a orario | Apify Schedule → webhook a fine run |
| Evento esterno (webhook) | Reagire a un cambiamento | CRM che chiama un endpoint al cambio di stato |
| Pianificazione locale | Solo se il PC resta acceso e non e' condiviso | Utilita' di pianificazione di Windows, cron |

Se la pipeline usa **piu' servizi in fila**, preferisci un orario sul posto dove gira l'orchestratore (es. Modal) invece di catene di webhook tra fornitori.

## 2. Orchestratore deterministico
Un modulo (es. `pipeline.py`) esegue gli step nell'ordine della Rule e ne fa le validazioni:
- richiama gli script esistenti, intercettando le loro uscite (`sys.exit`) e registrando l'esito invece di fermarsi;
- conserva i dettagli di uno step fallito (es. costo gia' speso) per il riepilogo;
- **non termina mai senza scrivere un esito** (anche per errori imprevisti).

## 3. Niente spese doppie
- Prima di **ogni chiamata a pagamento**, togli cio' che e' gia' stato fatto: entita' gia' controllate nei giri precedenti (stato persistente), elementi gia' nella destinazione.
- Tieni **un solo elemento per entita'** quando ha senso (es. un contatto per azienda).
- Con una ricerca fissa a frequenza regolare i risultati si ripetono: **varia l'input** tra un giro e l'altro (rotazione di termini, pagine successive) e dichiara il costo ricorrente.

## 4. Controlli di qualita' nel codice
Cio' che il Brain controllava rileggendo (formato, lingua, fatti inventati, lunghezza...) diventa una funzione di controllo: un elemento non valido viene **rigenerato una volta**, poi scartato con il motivo. Ogni errore nuovo trovato in produzione va aggiunto al controllo **e** a un test. I controlli non vedono gli errori di senso: l'output resta da rileggere se va a persone reali.

## 5. Sicurezza del trigger
- Endpoint pubblici protetti da **token segreto**, confrontato in modo sicuro (`hmac.compare_digest`) **prima** di qualsiasi spesa.
- **Idempotenza:** ogni esecuzione (run id, evento) si elabora una volta sola; le ripetizioni del fornitore vengono ignorate.
- **Mai due esecuzioni insieme** (es. `max_containers=1`, schedule esclusivo).
- L'endpoint risponde subito e passa il lavoro in background: i fornitori ritentano se la risposta e' lenta.
- Segreti nel gestore di segreti della piattaforma (es. Modal Secrets), caricati da script che non li stampano mai.

## 6. Costi
- Tetto **per esecuzione** e tetto **mensile** (stato persistente), controllato prima di ogni spesa.
- Registra a ogni giro il **costo reale** o stimato di ciascun servizio.

## 7. Visibilita'
Un **Log** leggibile dall'utente senza aprire il codice (es. una scheda del foglio): data, id, esito, quantita' per step, scarti con motivo, costi. Una riga anche quando il giro non produce nulla o fallisce.

## 8. Prova del trigger e accensione
1. Test con mock di orchestratore e endpoint: token errato, ripetizione, run fallito, dati vuoti.
2. Deploy **senza trigger attivo**; prova manuale nel cloud, se possibile su dati gia' pagati.
3. Endpoint senza token → deve rifiutare.
4. Un giro avviato dal **trigger vero** (es. orario a pochi minuti) → verifica Log e destinazione.
5. Ripeti la stessa consegna (webhook) → nessun effetto in piu'.
6. **Spegni il trigger** e lascialo spento: si accende solo su richiesta dell'utente. L'accensione deve richiedere un'azione esplicita (es. variabile al deploy), mai avvenire per un deploy normale.

## 9. Operazioni day-2 (nella Rule)
Come mettere in pausa, fermare tutto, aggiornare il codice, cambiare le chiavi, cambiare orario o input.
