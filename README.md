# claude-workflow-builder-skill

A [Claude Code](https://claude.com/claude-code) skill that builds and modifies business automation workflows the same way every time, and the workflow I use to test it, **niche-prospector**: a scheduled job that finds companies in a niche (currently Italian companies working on Microsoft technologies), finds a contact in each one and drafts a personalised email in a Google Sheet. **No email is ever sent.**

## The skill

### The idea: Rules, Brain, Implementation

When an LLM reasons *and* executes at the same time, errors compound: five steps at 90% reliability each give ~59% overall. The RBI structure separates the two:

| Layer | Where | Role |
|---|---|---|
| **Rules** | `rules/*.md` | *What* must happen: an SOP per workflow, with validation criteria for every step |
| **Brain** | Claude | *When* and *which* tool to use. It does not run business logic itself |
| **Implementation** | `implementation/*.py` | *How*: one script per responsibility, JSON output, exit codes, hard limits |

The structure comes from the starter project this skill was built for (not included here). Similar ideas exist under other names, e.g. *Directive-Orchestration-Execution* or *Workflows-Agents-Tools*.

### Project structure

Every RBI project has the same layout. The skill works inside it: it writes the Rule, the scripts and the tests, and creates the shared basics if they are missing.

| Folder / file | What it holds | Why |
|---|---|---|
| `rules/` | One procedure per workflow, in Markdown: steps, validation after each step, limits, edge cases, verification status | The *what*. It can be read and changed without touching the code; Claude reads it before running anything |
| `implementation/` | Python scripts, one per responsibility, plus the tests | The *how*. Deterministic code: same input, same result, and it can be tested |
| `.tmp/` | Files passed from one step to the next (e.g. `leads.json`) and the run state (`run_state.json`) | Every step reads the previous step's output from a file, so a run can be checked, re-run or resumed after an interruption without paying again. Safe to delete |
| `CLAUDE.md` | Project instructions and the list of available workflows | Claude Code reads it at the start of every session: it is the entry point that tells Claude which Rule to follow |
| `.env` | API keys and settings | Secrets stay out of the code and are never committed |

### What it makes Claude do

**Mode A — create a workflow.** Clarify goal, constraints and side effects; verify every external service *before* building (plan, API access, minimum cost, limits, permissions); make one real, minimal discovery call to see the actual data; split the work into single-responsibility scripts; write the Rule, the scripts and mocked tests; run it for real, first with one item, and read the result back from the destination.

**Mode B — modify a workflow.** Read the Rule, scripts, tests and verification status first; work in a copy if the change is experimental; re-verify any service that changes; make minimal, versioned changes; turn every user decision into a test; rerun the whole suite and a real run.

**Automatic workflows** ([`automation-rules.md`](skill/automation-rules.md)): a deterministic orchestrator replaces the Brain, no double spending, quality checks in code, a secure and idempotent trigger, per-run and monthly spending caps, a log row for every run, and a trigger that stays **off** until the user asks.

Every run ends with an honest report: ✅ proven with real data / ⚠️ only in tests or with limits / ❌ not working.

## The workflow: niche-prospector

The niche is defined by search keywords and a qualification filter (`discover_companies.py`), plus the target roles (`find_leads.py`); today they are set for Microsoft partners in Italy. Another niche in Italy means changing those; another country also means regions, country and the language of the emails.

| Step | What happens | Technology |
|---|---|---|
| 1. Companies | Google search of LinkedIn company pages for a Microsoft product and an Italian region (both rotate every run); communities and companies already seen are dropped; each page is checked (HQ in Italy, real website, Microsoft specialisation) | Apify actors (Google Search, LinkedIn company) |
| 2. People | One contact per company: IT / operations / delivery roles; in companies up to 50 employees the owner if no one else is found; verified email on the company domain | Apify actors (B2B lead database, LinkedIn employees) |
| 3. Email | Fixed structure (subject, greeting, offer, invitation, signature) plus two sentences written by Claude from the information found about the company and the contact; automatic quality checks | Claude API (Haiku) |
| 4. Output | Drafts in a Google Sheet, never sent; a log tab with outcome, discards and costs of every run | Google Sheets API |
| Trigger | Starts on its own in the cloud on the chosen day and time; per-run ($0.50) and monthly ($2.50) spending caps | Modal |

Everything is plain Python: one script per step, a deterministic orchestrator, 263 tests with external APIs mocked.

**Real results:** it works end to end, including a run started by the real cloud trigger. In small Italian IT companies it finds about one contact for every three valid companies; a run costs about $0.11–0.18.

## Repository layout

```
skill/               v3 (current) — English translation
  original-it/       v3 as written and used, in Italian
skill-v2/            v2 — English + original-it
skill-v1/            v1 — English + original-it
case-study/          blind test of v1: what went wrong and how v2 addresses it
case-study-2/        from manual workflow to weekly automation; blind test of v3
  niche-prospector/  the current workflow (v7): Rule, scripts, tests (no secrets, no real data)
CHANGELOG.md         what changed in the skill (v1 → v3) and in the workflow (v1 → v7)
```

The skill was written and tested in Italian. The English files are translations with the same structure and content; the translations themselves have not been run in a separate test.

## How to use it

Copy the `skill/` folder into your project as `.claude/skills/new-rbi-workflow/`, then ask Claude Code for a new workflow or a change to an existing one. The skill expects the [project structure](#project-structure) above; if the shared basics are missing (`.env` loading, test file, run state), it creates them first.

## License

MIT — see [LICENSE](LICENSE).
