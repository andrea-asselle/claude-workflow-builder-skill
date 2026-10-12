---
name: new-rbi-workflow
description: Creates or modifies a workflow in an RBI (Rules-Brain-Implementation) project: Rule in rules/, deterministic scripts in implementation/, tests, CLAUDE.md; also automatic workflows (schedule, webhook, events). Use when the user wants to "create/add/build a new workflow", "modify/change/update a workflow" (e.g. change a service, data source, recipients), automate it or schedule it.
---

# RBI workflow: create and modify (v3)

An RBI workflow = **1 Rule** (what) + **N scripts** (how) + **tests** + a row in CLAUDE.md. The Brain (you) does not execute logic: it delegates it to the scripts. In an **automatic** workflow there is no Brain: its work is done by an **orchestrator** in the code.

Applies to any kind of workflow (invoices, CRM, reports, data sync, scraping, email...).

**First of all, choose the mode:**
- **A. New workflow** → section A
- **B. Modify an existing workflow** (service, data source, recipients, rules, trigger) → section B

Common rules: [script-rules.md](script-rules.md) for every script, [automation-rules.md](automation-rules.md) if the workflow starts on its own.

---

## A. New workflow

Follow the steps in order. Do not move to the next step if validation fails.

### A1. Clarify (max 4 questions, only if they can't be inferred)
- Goal, and **who or what** it must produce (for an outreach: which companies, which roles)
- **Trigger:** on request (the user asks) or **automatic** (schedule, webhook, event)? If automatic, also follow [automation-rules.md](automation-rules.md)
- Inputs, external services, credentials (`.env`, OAuth)
- Irreversible effects (sending email, writes, costs) and user constraints (budget, free or paid plan)

### A2. Prepare the project
- Project interpreter (e.g. `.venv`), not the system `python3`.
- If the basics are missing (`.env` loading, tests, `.tmp/run_state.json`, end-of-run notification), **create them first**. If they exist, reuse them.

### A3. Verify external dependencies BEFORE building
For each external service, API or library, read the official documentation (listing, README, pricing, input schema) and report to the user:

| Service | Required plan | API/script usage | Minimum cost per run | Limits/quotas | Required permissions |
|---|---|---|---|---|---|

- A constraint incompatible with the requirements or the user's constraints → **stop and say so before writing code**, with alternatives.
- Choosing between several services: compare 2-3 options with these criteria and with **quality criteria decided before the test** (e.g. "at least 2 relevant results out of 3"). Do not choose from memory.
- **Nothing from memory:** models, versions, endpoints, field names, dangerous default values (e.g. "number of results: 100,000") must come from the documentation. For the Claude API use the `claude-api` skill.
- **Data sources:** databases (companies, people) search by name, sector, size, role; **not** by "what a company does". If you need a niche, split the steps: first find the **entities** with a text search (e.g. Google), then **enrich** them, then look for the **people**.

### A4. Discovery call
Before writing the code that reads an external response, make **one real, minimal call** (1 item, lowest cost; announce it first). Look at the real shape: field names, empty fields, error format, **what the filter really searches** (e.g. a "keyword" search may only search the name). Write the mapping from that.

### A5. Split into steps
One script = one responsibility. Verifiable output (JSON on stdout), one exit code per error type, data passed through files in `.tmp/`. If a constraint forces a change in what the workflow does, ask the user before proceeding.

### A6. Write the Rule
Copy [rule-template.md](rule-template.md) to `rules/<workflow_name>.md` (`v1`). Required sections: Goal, Trigger, Inputs, Prerequisites, External dependencies, Pipeline (command + **Validation** + **After success**), Safety limits, Edge cases, Recovery from interruption, Verification status. For automatic workflows also: Day-2 operations.

### A7. Write the scripts
Start from [script-template.py](script-template.py) and follow **all** the rules in [script-rules.md](script-rules.md).

### A8. Tests
One test class per script, external APIs mocked. Cover: success, invalid input, missing credential, API error, empty data, error response with a "successful" status, re-run without duplicates, **duplicates discarded before paid calls**. Tests **must never touch real resources** (see script-rules §9). Tests with mocks **do not prove** the workflow works.

### A9. Document
Row in `CLAUDE.md`; dependencies in `requirements.txt`; variables in `.env.example`.

### A10. Real run
1. **A single real item**, in test mode (`--dry-run` / `--tag TEST`).
2. Then the requested input. Validate each step against the Rule, **read the result back from the destination** (sheet, CRM, file...), save state, notify the end.
3. **Reread the produced content** (e.g. the emails): automatic checks catch form errors, not errors of meaning.
4. Automatic workflow: also test **the real trigger** (see automation-rules §8), then leave the trigger **off** until the user asks to switch it on.

---

## B. Modify an existing workflow

### B1. Read before touching
Read the Rule, the scripts involved, the tests and the **Verification status** section. Tell the user what changes, what stays the same and which already-tested parts could break.

### B2. Work on a copy if the workflow works
If the current workflow works and the change is experimental (e.g. a new data provider), work in a **copy of the folder** and change only what is needed; the working workflow stays intact.

### B3. If an external service changes
Repeat **A3 and A4** for the new service: verification, comparison with criteria set beforehand, discovery call. Do not assume fields, filters or limits are the same as the old one.

### B4. Minimal, versioned change
- Change only what is needed; do not rewrite unrelated scripts.
- **Rule:** save the current version (e.g. `rules/<name>.v1.md`) and write the new one (`v2`) with what changed and why at the top.
- **User decisions** (e.g. "this role stays, that one doesn't") go into the Rule and into a **test** that fixes them.

### B5. Tests
Update the test data to the new behaviour, add tests for the new case, rerun the **whole** suite: a test broken by the change must be understood, not just updated.

### B6. Real run and Verification status
As A10. Update the **Verification status**: old rows stay, new rows say what was tested after the change.

---

## When the workflow is "done"
Only when it has run **end to end with real data** (and, if automatic, starting from the real trigger) and the result has been read back from the destination. Fake data, mocks or a single working step **do not** count.

## Final report (mandatory)
Always close with this table, without embellishing:

| Workflow part | Status | How it was tested |
|---|---|---|
| ... | ✅ proven / ⚠️ works with limits or only in tests / ❌ does not work | real data / mock / made-up data |

Add the **real yield and cost** (e.g. "2 useful results out of 6, $0.10 per run"). If the part that produces the value does not work or yields little, say so in the first line.

## Rules
- Output that doesn't match: stop and diagnose. Max 3 attempts, then ask the user.
- What you learn goes into the Rule (Notes section), not only into the script.
- Before irreversible actions (sending, CRM writes, payments), approving permissions on third-party services or **switching on an automatic trigger**: ask the user.
- Do not ask the user to paste keys in the chat: tell them which variables to put in `.env`.
- Never commit `.env`, `credentials.json`, `token.json`.
