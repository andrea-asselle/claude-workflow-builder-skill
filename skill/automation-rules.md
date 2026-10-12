# Rules for automatic workflows (v3)

They apply when the workflow starts on its own: on a schedule, from a webhook or from an event. Nobody reads the Rule during the run and nobody rereads the output: everything the Brain did goes into the code.

## 1. Choosing the trigger
Verify the trigger like any external service (SKILL A3) and choose the simplest one that covers the case:

| Trigger | When | Examples |
|---|---|---|
| Cloud schedule | Periodic runs, computer off | Modal `Cron`, the platform's scheduler |
| Vendor schedule + webhook | A single external service to launch on a schedule | Apify Schedule → webhook at the end of the run |
| External event (webhook) | React to a change | A CRM calling an endpoint when a status changes |
| Local scheduling | Only if the computer stays on and is not shared | Windows Task Scheduler, cron |

If the pipeline uses **several services in a row**, prefer a schedule where the orchestrator runs (e.g. Modal) over chains of webhooks between vendors.

## 2. Deterministic orchestrator
A module (e.g. `pipeline.py`) runs the steps in the Rule's order and performs their validations:
- it calls the existing scripts, catching their exits (`sys.exit`) and recording the outcome instead of stopping;
- it keeps the details of a failed step (e.g. cost already spent) for the summary;
- it **never ends without writing an outcome** (even on unexpected errors).

## 3. No double spending
- Before **every paid call**, drop what has already been done: entities already checked in earlier runs (persistent state), items already in the destination.
- Keep **one item per entity** when it makes sense (e.g. one contact per company).
- A fixed search at a regular frequency returns the same results: **vary the input** between runs (rotating terms, next pages) and state the recurring cost.

## 4. Quality checks in code
What the Brain checked by rereading (format, language, invented facts, length...) becomes a check function: an invalid item is **regenerated once**, then discarded with the reason. Every new error found in production is added to the check **and** to a test. Checks do not see errors of meaning: the output still has to be reread if it goes to real people.

## 5. Trigger security
- Public endpoints protected by a **secret token**, compared safely (`hmac.compare_digest`) **before** any spending.
- **Idempotency:** each run (run id, event) is processed only once; vendor retries are ignored.
- **Never two runs at once** (e.g. `max_containers=1`, exclusive schedule).
- The endpoint answers immediately and passes the work to the background: vendors retry if the answer is slow.
- Secrets in the platform's secret manager (e.g. Modal Secrets), loaded by scripts that never print them.

## 6. Costs
- A cap **per run** and a **monthly** cap (persistent state), checked before every spending.
- Record the **real** or estimated cost of each service at every run.

## 7. Visibility
A **Log** the user can read without opening the code (e.g. a tab in the sheet): date, id, outcome, quantities per step, discards with reason, costs. One row even when the run produces nothing or fails.

## 8. Testing and switching on the trigger
1. Mocked tests of orchestrator and endpoint: wrong token, repetition, failed run, empty data.
2. Deploy **without an active trigger**; manual run in the cloud, on already-paid data if possible.
3. Endpoint without a token → must refuse.
4. A run started by the **real trigger** (e.g. a schedule a few minutes ahead) → check Log and destination.
5. Repeat the same delivery (webhook) → no additional effect.
6. **Switch the trigger off** and leave it off: it is switched on only at the user's request. Switching it on must require an explicit action (e.g. a variable at deploy time), never happen with a normal deploy.

## 9. Day-2 operations (in the Rule)
How to pause, stop everything, update the code, change the keys, change the schedule or the input.
