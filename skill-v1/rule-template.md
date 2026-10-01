# Rule: <Workflow Name> (v1)

<!-- v1 template — translated from the original Italian version (see original-it/). -->

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
- Dependencies: `pip3 install -r requirements.txt`

## Pipeline

### Step 1: <Name>

```bash
python3 implementation/<script_1>.py --<arg> <value>
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

## Notes

- <lessons learned, edge cases found, to be updated with every new finding>
