# Rules for RBI scripts

They apply to every script in `implementation/`, whatever it does.

## Structure
- Docstring with Usage, Exit codes, Prerequisites.
- `argparse`, `.env` loading, local imports via `sys.path.insert`.
- Success: JSON on stdout with `status` and `timestamp`.
- Error: JSON `{"error": ...}` on stderr + exit code: 0 ok, 1 input, 2 auth/credentials, 3 API error, 4 empty or partial data.
- Hard limits as constants for every action that spends money or is irreversible (quantity, cost per run).
- No secrets in the code: only `.env`, and keep `.env.example` updated.

## 1. Timeouts
Every external call (HTTP, SDK, database, subprocess) has an explicit timeout. No infinite waits.

## 2. Check the shape of the response
- Do not trust a "successful" status: check that the response has the expected shape (required fields present, correct type).
- An error message, an informational object or a summary row **must never become valid data**. If the response doesn't have the expected shape: exit code 3, no output file written.
- If the response contains rows of different types (data, summary, info), explicitly keep only the data rows.

## 3. Outcome per item
If the script processes several items (companies, customers, invoices, rows...), the output reports for each one: ok / skipped / failed + reason. Example:
```json
"items": [
  {"input": "acme.it", "status": "ok", "count": 2},
  {"input": "beta.it", "status": "empty", "reason": "no results"}
]
```
If some items fail and others don't: exit code 4 (partial), not 0.

## 4. Repeatable actions (idempotency)
If the script writes, sends, creates or modifies something externally, a second run with the same input **must not duplicate** the effect: check what has already been done (unique key, state in `.tmp/`) and skip it, reporting `skipped_duplicates`. Do not delete and rewrite existing data to avoid duplicates.

## 5. Retries
Retry only transient errors (timeout, 429, 5xx) and only for operations that are safe to repeat. Increasing wait (e.g. 1s, 2s, 4s), max 3 attempts. Never retry input, authentication or permission errors.

## 6. Test mode
Every script with external effects has an option to try it without consequences:
- `--dry-run`: runs everything except the final action and shows what it would do, or
- `--tag TEST`: performs the action but clearly marks the data as a test.

## 7. Costs
- If the script spends money, estimate the cost before each call and stop if it exceeds the per-run cap.
- After the run, read the **real cost** from the service when possible, instead of only reporting the estimate.

## 8. Environment (Windows)
- Force UTF-8 at the start of `main()`: `sys.stdout.reconfigure(encoding="utf-8")` and the same for `stderr`.
- Read and write files with `encoding="utf-8"`.
- Do not use inline Python scripts in shell commands: save them to a file and run them from there.
- Use the project interpreter and set a timeout on long commands.
