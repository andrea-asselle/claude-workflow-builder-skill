---
name: new-rbi-workflow
description: Creates a new workflow in the RBI (Rules-Brain-Implementation) project: writes the Rule in rules/, the deterministic scripts in implementation/, the tests in test_all.py and updates CLAUDE.md. Use when the user wants to "create/add/build a new workflow", automation or SOP in this project.
---

<!-- v1 — translated from the original Italian version used in the blind test (see original-it/). Kept as the "before" of the comparison. -->

# New RBI workflow

An RBI workflow = **1 Rule** (what) + **N scripts** (how) + **tests** + a row in CLAUDE.md. The Brain (you) does not execute logic: it delegates it to the scripts.

## Procedure

Follow the steps in order. Do not move to the next step if validation fails.

### 1. Clarify (max 4 questions, only if they can't be inferred)
- Goal and trigger (what does the user say?)
- Required/optional inputs
- External services and required credentials (`.env`, OAuth)
- Irreversible side effects (sending email, writing data, API costs)?

### 2. Reuse before creating
Read `implementation/` and the existing Rules. Reuse `load_env.py`, `google_auth.py`, `clickup_api.py`, `alert_user.py`. Create a new script only if the responsibility is not already covered.

### 3. Split into steps
One script = one responsibility. Each step must have a verifiable output (JSON on stdout) and a dedicated exit code for each error type. If there are several steps, the output of one is the input of the next one through files in `.tmp/`.

### 4. Write the Rule
Copy [rule-template.md](rule-template.md) to `rules/<workflow_name>.md` (version `v1`). Required sections: Goal, Trigger, Inputs, Prerequisites, Pipeline (command + **Validation** + **After success** for each step), Safety limits, Edge cases (exit code → action table), Recovery from interruption.
Do not overwrite an existing Rule without permission: create `v2`.

### 5. Write the scripts
Start from [script-template.py](script-template.py). Project conventions:
- Docstring with Usage, Exit codes, Prerequisites
- `argparse`, `load_env()`, local imports via `sys.path.insert`
- Success output: JSON on stdout with `status` and `timestamp`
- Errors: JSON `{"error": ...}` on stderr + exit code (0 ok, 1 input, 2 auth/credentials, 3 API error, 4 empty/partial data)
- Hard limits as constants (costs, quantities) for every action that spends money or is irreversible
- No secrets in the code: only `.env`, update `.env.example`

### 6. Tests
Add in `implementation/test_all.py` a test class per script, with external APIs mocked (`@patch`). Cover: success, invalid input, missing credential, API error, empty data. Run `python3 -m pytest implementation/test_all.py -v` and show the real result.

### 7. Document
- Add the row to the "Available workflows" table in `CLAUDE.md`
- Add new dependencies to `requirements.txt` and variables to `.env.example`

### 8. First controlled run
Run the workflow with minimal input (e.g. 1 item). Validate each step against the Rule's criteria, save state to `.tmp/run_state.json` after each step, then `python3 implementation/alert_user.py success`.

## Rules
- If an output doesn't match: stop and diagnose. Max 3 attempts, then ask the user.
- What you learn from errors goes into the Rule (not randomly into the script).
- Before irreversible external actions (real emails, CRM writes) confirm with the user.
- Never commit `.env`, `credentials.json`, `token.json`.
