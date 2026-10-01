---
name: new-rbi-workflow
description: Creates a new workflow in an RBI (Rules-Brain-Implementation) project: writes the Rule in rules/, the deterministic scripts in implementation/, the tests, and updates CLAUDE.md. Use when the user wants to "create/add/build a new workflow", automation or SOP in this project.
---

# New RBI workflow (v2)

An RBI workflow = **1 Rule** (what) + **N scripts** (how) + **tests** + a row in CLAUDE.md. The Brain (you) does not execute logic: it delegates it to the scripts.

Applies to any kind of workflow (invoices, CRM, reports, data sync, scraping, email...).

## Procedure

Follow the steps in order. Do not move to the next step if validation fails.

### 1. Clarify (max 4 questions, only if they can't be inferred)
- Goal and trigger (what does the user say?)
- Required/optional inputs
- External services and required credentials (`.env`, OAuth)
- Irreversible side effects (sending email, writing data, API costs)?
- User constraints: budget, free or paid plan, personal or company account

### 2. Prepare the project
- Use the project interpreter (e.g. `.venv`), not the system `python3`.
- If the basics are missing (`.env` loading, test file, `.tmp/run_state.json`, end-of-run notification), **create them first**. If they exist (`load_env.py`, `google_auth.py`, `clickup_api.py`, `alert_user.py`...), reuse them.
- Create a new script only if the responsibility is not already covered.

### 3. Verify external dependencies BEFORE building
For each external service, API or library, read the official documentation (listing, README, pricing page) and report to the user in a table:

| Service | Required plan | API/script usage | Minimum cost per run | Limits/quotas | Required permissions |
|---|---|---|---|---|---|

- If a constraint is incompatible with the requirements or the user's constraints (free plan, budget, permissions): **stop and say so before writing code**, with alternatives.
- If you must choose between several services, compare at least 2-3 options with these criteria. Do not choose from memory.
- **Nothing from memory:** model names, API versions, endpoints and field names must come from the documentation. For the Claude API use the `claude-api` skill.

### 4. Discovery call
Before writing the code that parses an external response, make **one real, minimal call** (1 item, lowest cost) and look at the real shape of the response: field names, empty fields, error format. Write the data mapping from that, not from guessed names. If the call costs money, say so first.

### 5. Split into steps
One script = one responsibility (e.g. fetch data → transform → write). Each step has a verifiable output (JSON on stdout) and an exit code for each error type. The output of one step is the input of the next one through files in `.tmp/`.

**If a constraint forces a change in what the workflow does** (e.g. a service does not support the requested search), ask the user before proceeding.

### 6. Write the Rule
Copy [rule-template.md](rule-template.md) to `rules/<workflow_name>.md` (version `v1`). Required sections: Goal, Trigger, Inputs, Prerequisites, External dependencies (the table from step 3), Pipeline (command + **Validation** + **After success** for each step), Safety limits, Edge cases, Recovery from interruption, Verification status.
Do not overwrite an existing Rule without permission: create `v2`.

### 7. Write the scripts
Start from [script-template.py](script-template.py) and **follow all the rules in [script-rules.md](script-rules.md)** (timeouts, response checks, per-item outcome, repeatable actions, test mode, Windows environment).

### 8. Tests
One test class per script, with external APIs mocked (`@patch`). Cover: success, invalid input, missing credential, API error, empty data, **error response with a "successful" status**, re-run without duplicates. Run the tests with the project interpreter and show the real result.

Tests with mocked APIs **do not prove** the workflow works: they only protect the logic.

### 9. Document
- Row in the "Available workflows" table of `CLAUDE.md`
- New dependencies in `requirements.txt`, variables in `.env.example`

### 10. Real run
1. First with **a single real item** and, if available, in test mode (`--dry-run` / `--tag TEST`).
2. Then with the input requested by the user.
Validate each step against the Rule's criteria, **read the final result back from the destination** (sheet, CRM, file...) instead of trusting the script output, save state to `.tmp/run_state.json` after each step, then notify the end.

## When the workflow is "done"
Only when it has run **end to end with real data** and the result has been read back from the destination. A run with fake data, mocked APIs or only one working step **does not** count as a complete test.

## Final report (mandatory)
Always close with this table, without embellishing:

| Workflow part | Status | How it was tested |
|---|---|---|
| ... | ✅ proven / ⚠️ only in tests or with fake data / ❌ does not work | real data / mock / made-up data |

If the core of the workflow (the part that produces the value) does not work, say so in the first line of the report.

## Rules
- If an output doesn't match expectations: stop and diagnose. Max 3 attempts, then ask the user.
- What you learn from errors goes into the Rule (Notes section), not only into the script.
- Before irreversible external actions (real emails, CRM writes, payments) or before approving permissions on third-party services: ask the user.
- Do not ask the user to paste keys in the chat: tell them which variables to put in `.env`.
- Never commit `.env`, `credentials.json`, `token.json`.
