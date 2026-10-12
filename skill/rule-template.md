# Rule: <Workflow Name> (v1)

<From v2 onwards only: what changed compared to the previous version and why. The previous version is in `<name>.v1.md`.>

## Goal

<One sentence: what the workflow produces and for whom (e.g. which entities, which roles).>

## Trigger

**On request** — the user says something like:

- "<example phrase 1>"
- "<example phrase 2>"

**Automatic** (if planned, see the skill's automation-rules) — <schedule / webhook / event>, where it runs, how it is switched on and off. Off until the user asks to switch it on.

## Required Inputs

- `<required_input>` (required) — <description>
- `<optional_input>` (optional) — <description and default>

## Prerequisites

- `.env` file with: `<VARIABLES>`
- <OAuth credentials / other files>
- Dependencies in `requirements.txt`, installed with the project interpreter (e.g. `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`)

## External Dependencies

Verified from the official documentation on <date>.

| Service | Required plan | API/script usage | Minimum cost per run | Limits/quotas | Required permissions |
|---------|---------------|------------------|----------------------|---------------|----------------------|
| <service> | <free/paid> | <yes/no> | <cost> | <limits> | <permissions> |

## Pipeline

### Step 1: <Name>

```bash
<project interpreter> implementation/<script_1>.py --<arg> <value> [--dry-run]
```

**Validation:**
- Exit code 0
- <JSON field> present / >= expected

**After success:**
- Save output to `.tmp/<file>.json`
- Update `.tmp/run_state.json`

### Step 2: <Name>

(repeat the pattern)

## Safety Limits

| Limit | Value | Where |
|-------|-------|-------|
| <e.g. max items per run> | <value> | `<script>.py` (`<CONSTANT>`) |

## Edge Cases

| Situation | Exit Code | Action |
|-----------|-----------|--------|
| Missing `.env` | 1/2 | Instructions to create `.env` |
| API error | 3 | Retry, then escalate |
| Empty data | 4 | Check the filters |

## Recovery from Interruption

Read `.tmp/run_state.json`:

- Step 1 completed → `.tmp/<file>.json` exists, skip to step 2

## Day-2 Operations (automatic workflows only)

- Pause: <command>
- Stop everything: <command>
- After code changes: <deploy command>
- After changing keys: <command>
- Where to read the outcome of each run: <Log>

## Verification Status

Update after every real run.

| Workflow part | Status | How it was tested | Date |
|---------------|--------|-------------------|------|
| <step 1> | ✅ / ⚠️ / ❌ | real data / mock / made-up data | <date> |
| <automatic trigger, if planned> | ✅ / ⚠️ / ❌ | run started by the real trigger | <date> |

Real yield and cost: <e.g. 2 useful results out of 6, $0.10 per run>.

## User Decisions

- <e.g. "role X stays, Y doesn't"> — fixed by the test `<test name>`

## Notes

- <lessons learned, edge cases found, to be updated with every new finding>
