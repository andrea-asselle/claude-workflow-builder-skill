# claude-workflow-builder-skill

A [Claude Code](https://claude.com/claude-code) skill that builds business automation workflows the same way every time: a written procedure (**Rule**), small deterministic Python scripts (**Implementation**), and Claude only orchestrating them (**Brain**).

I wrote it, tested it "blind" on a real task, logged everything that went wrong, and rewrote it. This repo contains both versions and the full case study.

> **Status: work in progress.** v2 is based on the test findings but has not been through a new end-to-end test yet.

## The idea

When an LLM reasons *and* executes at the same time, errors compound: five steps at 90% reliability each give ~59% overall. The RBI structure separates the two:

| Layer | Where | Role |
|---|---|---|
| **Rules** | `rules/*.md` | *What* must happen: an SOP per workflow, with validation criteria for every step |
| **Brain** | Claude | *When* and *which* tool to use. It does not run business logic itself |
| **Implementation** | `implementation/*.py` | *How*: one script per responsibility, JSON output, exit codes, hard limits |

The Rules/Brain/Implementation structure comes from the starter project this skill was built for (not included in this repo). Similar ideas exist under other names, e.g. *Directive-Orchestration-Execution* or *Workflows-Agents-Tools*.

## What the skill does

Given a request like *"I need a workflow that does X"*, the skill makes Claude:

1. Clarify goal, inputs, credentials, side effects and the user's constraints (budget, free/paid plans).
2. Prepare the project, creating the shared basics if they are missing.
3. **Verify every external service before building**: required plan, API usage, minimum cost per run, limits, permissions. Stop if something conflicts with the requirements.
4. Make one real, minimal **discovery call** to see the actual response shape before writing any parsing code.
5. Split the work into single-responsibility scripts.
6. Write the Rule from a template.
7. Write the scripts following [`script-rules.md`](skill/script-rules.md): timeouts, response-shape checks, per-item outcome, idempotent writes, retries with backoff, `--dry-run`, UTF-8 on Windows.
8. Write mocked tests (and say clearly that they do not prove the workflow works).
9. Document the workflow.
10. Run it for real, first with one item, and read the result back from the destination.

It must close with an honest report: ✅ proven with real data / ⚠️ only in tests or with fake data / ❌ not working.

## Repository layout

```
skill/               v2 (current) — English translation
  original-it/       v2 as written and used, in Italian
skill-v1/            v1 (the version that was tested) — English translation
  original-it/       v1 as written and tested, in Italian
case-study/
  test-log.md        everything that went wrong in the blind test, and the v2 rule that addresses it
  workflow/          the code Claude produced during the test (secrets and personal data removed)
```

The skill was written and tested in Italian. The English files are translations with the same structure and content; the translations themselves have not been run in a separate test.

## How to use it

Copy the `skill/` folder into your project as `.claude/skills/new-rbi-workflow/`, then ask Claude Code for a new workflow. The skill expects (or creates) a project with `rules/`, `implementation/`, `.tmp/` and a `CLAUDE.md`.

## The blind test

I gave v1 to a fresh Claude Code session, in an empty folder, with no access to the original project, and asked it to rebuild an existing workflow: **cold outreach** — find B2B leads (CEOs of Italian companies) with Apify, write a personalised email for each one with the Claude API, and put everything in a Google Sheet. No emails are ever sent. Budget: $0.50 per run, max 5 leads.

### Result

| Part of the workflow | Status | How it was tested |
|---|---|---|
| **Lead search (Apify)** | ❌ No usable leads | Real runs |
| Email writing (Claude Haiku 4.5) | ⚠️ Works | One made-up lead |
| Writing to Google Sheets | ⚠️ Works, 13 columns read back and checked | One made-up lead |
| Logic (limits, errors, duplicates) | ⚠️ 46 tests passing | Mocked APIs |

**The workflow is not complete: its core step never produced a usable lead.** Total cost of the test: about $0.03.

### Known limitation: the lead source

Lead search depends on the Apify actor. On Apify's free plan:

- `code_crafter/leads-finder`, used by the starter project, **cannot be run via API** (UI only).
- `braveleads/...` and `olympus/...` charge a **minimum of 100 leads per run**.
- `atomus/leads-finder` returns **no emails** on the free plan.
- `themineworks/b2b-leads-finder` works via API but **searches by company, not by role and country**; on the three companies tested it found no CEO.

The starter project found real leads with `code_crafter` (most likely on a paid plan). Running this version on a paid plan is the next test. The bottleneck was the data source, not the pipeline — but that is an assumption until it's proven.

### What I learned

The most useful finding: **v1 trusted external services too much.** Claude picked a service from memory, guessed the response field names, treated an error message as valid data, and discovered plan limits only after building around them. v2 adds explicit checks for each of these. Details in [`case-study/test-log.md`](case-study/test-log.md).

## License

MIT — see [LICENSE](LICENSE).
