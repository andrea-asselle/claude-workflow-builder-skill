# Blind test log

**Task:** rebuild a cold outreach workflow (find B2B leads → write emails with Claude → save to Google Sheets, never send) using only skill **v1**, in an empty folder, with no access to the original project.

**Setup:** Claude Code in VS Code, Python 3.11 venv, Apify free plan, $5 of prepaid Anthropic API credit, Google service account on an education Workspace account.

**Outcome:** email writing and sheet export work (tested with one made-up lead); lead search never produced a usable lead. See the [README](../README.md#result).

## A first, discarded run

The first attempt ran in VS Code's built-in chat instead of Claude Code, so the skill was probably never loaded. It produced a single monolithic script and tried outdated Claude model names one by one. The folder was reset and the test restarted in Claude Code. Lesson for testing: **check that the skill is actually invoked** before judging its output.

## Issues found

| # | What happened | Cause | Addressed in v2 by |
|---|---|---|---|
| 1 | The Apify actor was chosen from memory, with no comparison | Skill | Step 3: verify and compare 2-3 services before building |
| 2 | The actor required "full permission" access to the Apify account, discovered only when the run was rejected | Skill | Step 3: permissions column; ask before approving third-party permissions |
| 3 | The actor can't be run via API on the free plan; discovered at runtime ($0.02 spent) | Service + skill | Step 3: plan and API-usage columns |
| 4 | The actor's error message was saved as a lead, with status `success` | Code | `script-rules.md` §2: check the response shape |
| 5 | Two alternative actors charge a minimum of 100 leads per run | Service | Step 3: minimum cost per run |
| 6 | The only free API-capable actor searches by company, not by role/country | Service | Step 5: ask before changing what the workflow does. *The session did this correctly.* |
| 7 | Response field names were guessed; one sheet column would have stayed empty, job titles were truncated | Skill | Step 4: discovery call before writing the mapping |
| 8 | The search used only "CEO" and missed Italian titles ("Amministratore Delegato") | Code | Fixed in the session |
| 9 | No per-company outcome: the session had to query Apify by hand to see what happened to each company | Skill | `script-rules.md` §3: outcome per item |
| 10 | Apify refuses a per-run spending cap below $0.50 for that actor | Service | Handled: the session computed the real worst case (~$0.19) |
| 11 | JSON output came out in cp1252 instead of UTF-8 on Windows, breaking accented letters | Environment | `script-rules.md` §8 |
| 12 | Inline Python in shell commands broke on quotes | Environment | `script-rules.md` §8 |
| 13 | The first generated email had an anglicism and inconsistent formality | Prompt | Fixed in the session (stricter prompt) |
| 14 | The skill assumed project files (`test_all.py`, `load_env.py`) that don't exist in an empty project | Skill | Step 2: create the basics if missing |
| 15 | My own first evaluation called the result "more robust than the original" although no real lead was ever found | Evaluator | "When is it done" section + mandatory honest final report |

## Environment issue (not the skill)

On the Windows Server used for the test, `pip` hung forever. Since Python 3.12, `platform.machine()` / `platform.release()` query WMI on Windows, and WMI was not responding on that machine. `pip` calls these functions to build its user agent. Workaround: a Python 3.11 virtual environment created with `uv`, and `uv pip install` instead of `pip`.

## What the session did well

- Split the work into separate scripts with clear exit codes, and wrote 46 mocked tests.
- Stopped after 2 of 3 attempts instead of burning the last one blindly.
- Asked before approving third-party permissions and before changing the requirement.
- Read real costs from Apify instead of reporting only estimates.
- Found and fixed its own bug (issue 4), adding a regression test.
- Wrote what it learned into the Rule.
- Added a GDPR note: leads are personal data.

## Costs

| Service | Spent |
|---|---|
| Apify | ~$0.025 |
| Anthropic API (2 emails) | ~$0.003 |
