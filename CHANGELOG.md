# Changelog

## Skill

### v3 — create **and** modify, manual **and** automatic (October 2026)

Tested blind on a real modification + automation task: see [case-study-2](case-study-2/README.md#7-what-the-blind-test-of-v3-showed).

- **Two modes.** A: create a new workflow (the v2 procedure). B: modify an existing one.
  - B1 read the Rule, scripts, tests and verification status first; tell the user what changes, what stays, what could break.
  - B2 work in a copy of the folder when the workflow works and the change is experimental.
  - B3 if an external service changes, verify it again (plan, cost, limits) and make a new discovery call.
  - B4 minimal, versioned changes: the old Rule is saved as `v1`, the new one says at the top what changed and why. **User decisions go into the Rule and into a test that fixes them.**
  - B5 run the whole test suite; a test broken by the change must be understood, not just updated.
  - B6 real run; the verification table keeps old rows and adds new ones.
- **New `automation-rules.md`** for workflows that start on their own:
  - choose the simplest trigger (cloud cron, vendor schedule + webhook, external event, local scheduler);
  - a deterministic orchestrator that always writes an outcome;
  - no double spending: drop what was already done before every paid call, one item per entity, vary the input between runs;
  - quality checks in code instead of the Brain rereading (regenerate once, then discard with a reason);
  - trigger security: secret token, idempotency, never two runs at once, secrets never printed;
  - per-run and monthly spending caps, a human-readable log row for every run;
  - trigger test from the real trigger, then **off until the user asks**; switching it on needs an explicit action, never a normal deploy;
  - day-2 operations documented in the Rule.
- **`script-rules.md`**
  - §7 always set the parameters that decide spending (vendor defaults can be 100,000 results, or one paid start per item);
  - §7b re-check external data in code: whole-word matching ("Socio" contains "cio"), similar-but-different cases (a podcast is not a company), every discard has a reason;
  - §9 tests must never reach real resources: removing an environment variable is not enough if the code reloads `.env`, block the client in an autouse fixture (a test wrote to the real sheet before this rule).
- **Data sources rule (A3):** company and people databases search by name, sector, size and role, not by "what a company does". For a niche: find the entities with a text search, enrich them, then look for people.
- **`rule-template.md`:** automatic trigger section, day-2 operations, user decisions, verification status.

### v2 — trust external services less (October 2026)

Based on the 15 issues of the v1 blind test ([case-study](case-study/test-log.md)): verify every external service before building, a real minimal discovery call before writing any parsing code, script rules (timeouts, response-shape checks, per-item outcome, idempotency, `--dry-run`, UTF-8 on Windows), mandatory honest final report.

### v1 — first version

Procedure to create a Rules-Brain-Implementation workflow. Tested blind: the lead search never produced a usable lead.

## Case-study workflow (cold outreach)

Find B2B contacts → Claude drafts an email → Google Sheet. Never sends.

| Version | Change |
|---|---|
| v1-v2 | CEOs of Italian companies from a lead database; emails by Claude Haiku; Google Sheet |
| Paid plan test | Lead database works via API on a paid plan, but cannot find niche companies by keyword (0/54) |
| Discovery | Companies first: Google search of LinkedIn company pages → LinkedIn company data → people in those companies |
| First automation | Apify Schedule → webhook → Modal → orchestrator → sheet + log |
| v3 (blind test) | Second-line roles instead of owners; weekly Modal cron; orchestrator with quality checks; log tab; monthly cap; **fixed email template** (Claude writes 2 sentences) |
| v4 | No company size limit |
| v5 (merge) | One workflow: niche discovery + weekly rotation of keywords × region (68 combinations), 2 Google pages, "seen companies" memory, lighter call to action |
| v5.1 | 2 people per website from the lead database; check for truncated verbs in emails |
| v6 | Companies up to 50 employees: the owner when no second line is found |
| v7 | Wider roles (project manager, BU manager, head of BI, CxO); `.it`/`.com` emails of the same company accepted; communities dropped before paying |
