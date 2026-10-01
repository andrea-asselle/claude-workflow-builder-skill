# Rule: <Workflow Name> (v1)

## Goal

<One sentence: what the workflow produces and for whom.>

## Trigger

The user says something like:

- "<example phrase 1>"
- "<example phrase 2>"

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

## Verification Status

Update after every real run.

| Workflow part | Status | How it was tested | Date |
|---------------|--------|-------------------|------|
| <step 1> | ✅ / ⚠️ / ❌ | real data / mock / made-up data | <date> |

## Notes

- <lessons learned, edge cases found, to be updated with every new finding>
