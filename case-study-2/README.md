# Case study 2: from a manual workflow to a weekly automation

What happened between skill v2 and v3, and how the cold outreach workflow evolved from "search leads by hand" to a weekly cloud job that finds niche companies, finds a contact in each, drafts an email and logs everything. All numbers come from real runs (October 2026). No email was ever sent.

People and companies found during the runs are not named here.

## Timeline

| Step | What changed | Why |
|---|---|---|
| 1. Paid plan test | Ran the lead search on Apify's paid plan | v1's blind test failed on the free plan; the question was whether the data source or the pipeline was the problem |
| 2. Niche discovery | Companies first, then people | Lead databases search by name, sector and size, not by "what a company does": 0 relevant leads out of 54 when searching for Microsoft partners by keyword |
| 3. First automation | Apify Schedule → webhook → Modal → pipeline | Try a real trigger before writing automation rules into the skill |
| 4. Skill v3 | Modes A (create) / B (modify) + automation rules | Steps 1-3 were modifications and automations, which v2 did not cover |
| 5. Blind test of v3 | A fresh session modified the workflow and made it run every Monday | Same method as the v1 test |
| 6. Merge | The two branches (blind test + my automation) became one workflow, using the skill's modify mode | Two copies of the same workflow writing to the same sheet |
| 7. Yield work | Research on alternatives, three paid tests, three rule changes | Finding people turned out to be the real bottleneck |

## 1. The data source was the problem, partly

On a paid plan the lead database (`code_crafter/leads-finder`) worked via API and returned real people with verified emails. It could not, however, find companies by specialisation: searching for partners of Microsoft business software returned 0 relevant companies out of 54. When given the companies' websites, it found people in about one company out of three.

So the workflow was split: **find the companies first** (text search), **enrich** them, **then** look for people inside them. This became a rule in the skill.

## 2. How the workflow finds companies

1. Google search (Apify actor) for `site:linkedin.com/company "<keyword>" <region>`, two result pages per query.
2. Community pages (meetups, user groups, podcasts) are dropped from the slug or Google title, before paying for anything.
3. Companies already checked in earlier runs are skipped (a "seen companies" tab in the sheet).
4. Each new LinkedIn company page is read (Apify actor): headquarters in Italy, a real website, Microsoft terms in description or specialities, not a nonprofit/school, not already in the sheet.

Keywords (8 Microsoft products) and region (17 Italian regions) rotate every week: 68 different combinations before one repeats. Without rotation, the same companies came back after a few runs because Google's ordering is stable.

**Real result:** 16 valid companies out of 20 checked on the first two runs; later combinations were weaker (3-4 out of 10), mostly because "Azure" also finds communities, which is what the filter in point 2 now addresses.

## 3. How it finds people

1. The lead database on the companies' websites, second-line roles (CTO, CIO, COO, IT / operations / delivery managers, project managers, BU managers, head of BI).
2. For companies with up to 50 employees and no second line found: the owner.
3. For companies still without a contact: the company's public LinkedIn employee list (Apify actor, no login).
4. One contact per company, email on the company domain, verified.

I tested three alternatives before changing anything (about $0.20 in total):

| Test | Result |
|---|---|
| A second B2B database (free count) | Fewer people than the current one, mostly at the same companies |
| LinkedIn people search by seniority and function | 3 profiles for 11 companies, 1 relevant, no email |
| Two "email from name + domain" finders | Both found nothing (all candidate addresses rejected by the mail server) |

What did help came from reading the data: LinkedIn showed people with roles that were not in the list (project manager, BU manager, head of BI). Adding them produced **3 new contacts in 3 companies that previously had none**. A bug was also discarding emails like `@company.it` for a website `company.com` (4 out of 5 discards in that test).

**Real yield:** about one contact for every three valid companies. Small Italian IT companies often have no second line, and are often missing from the B2B databases altogether.

## 4. Emails without a human reading them

In a scheduled run nobody rereads the drafts before they land in the sheet. The first approach was quality checks in code (Italian closing, no invented experience, formal "Lei", no anglicisms...). Real runs kept finding new errors: mixed formal/plural address, a sender "experience" invented by the model, a made-up word, a truncated verb.

The fix that worked best came from the blind-test session: a **fixed email template**. Claude writes only two sentences (one about the company, one question about a concrete activity); greeting, offer, invitation and signature are fixed text. Most of the errors seen before can no longer appear, because those parts are no longer generated. The remaining checks run on the two sentences; an email that fails is regenerated once, then discarded with the reason.

One kind of error is still not caught: sentences that are vague or inferred from the company name when the data is thin. The drafts still need a human read before any use.

## 5. The automation

- **Trigger:** a Modal cron, every Monday at 8:00 (Europe/Rome). It is switched on only by an explicit variable at deploy time; a normal deploy leaves it off.
- **Orchestrator:** a deterministic `pipeline.py` runs the steps in the Rule's order, catches each script's exit and always writes one row to a Log tab: date, run id, region, keywords, companies found/valid, people found, discards with reasons, cost per service, outcome.
- **No double spending:** one run per ISO week; companies already seen or already in the sheet are dropped before any paid call; per-run cap ($0.50) and monthly cap ($2.50) checked before spending.
- **Verified from the real trigger:** the cron fired at a test time, ran the full chain in the cloud and wrote 2 drafts; then the trigger was switched off again.

## 6. Numbers

| | Value |
|---|---|
| Cost per run | $0.11 – $0.18 (Apify ~$0.11-0.18, Claude < $0.01) |
| Drafts per run (target 5) | 0 – 3 |
| Cost per draft (4 real runs) | ~$0.09 |
| Tests | 263, external APIs mocked, real resources blocked |
| Total spent on the day of the merge (runs + tests) | ~$1.20 |

The weak number is drafts per run. It is documented in the Rule's verification table instead of being hidden.

## 7. What the blind test of v3 showed

A fresh Claude Code session, with only the skill v3 and a copy of the workflow, was asked to change the target roles and make the workflow run every Monday.

- **Followed:** versioned Rule, deterministic orchestrator with quality checks, duplicates removed before paying, monthly cap, Log, a real cron test then trigger off, tests isolated from real resources (citing the new rule), an honest final report.
- **Introduced in that session:** weekly region rotation, and the fixed email template.
- **Missed:** it modified the workflow in place instead of in a copy, and its first log row went into the other automation's log tab in the same sheet (it noticed and removed it).

## 8. What I decided not to do

Scraping LinkedIn with a logged-in account (even a dedicated one) would expose contact details that are not public. It breaks LinkedIn's terms and would be the wrong thing to show in a portfolio. The workflow only uses public data through Apify actors that need no login.

## Lessons

1. **Measure before you buy.** Three alternative data sources looked promising on paper; free counts and $0.10 tests showed none of them helped.
2. **Look at the data before changing the tool.** The useful fixes (wider roles, `.it`/`.com`, community filter) came from reading discard reasons, not from a new service.
3. **Move generation out of the risky parts.** A fixed template removed more errors than any check did.
4. **Automation needs its own rules.** Nobody reads the Rule or the output at 8:00 on Monday: idempotency, spending caps, a log row for every run and a trigger that is off by default have to be in the code.
5. **Report the weak numbers.** The workflow works end to end; it finds fewer contacts than hoped. Both are in the verification table.
