# Evaluation of Graft's AI features

Each run starts with a new, isolated SQLite database and the eight fictional starter-pack sources. The case agent and Ask Graft run through their HTTP routes as signed-in demo users. The live command requests Groq. The replay command disables provider access for the process.

## Live run

Recorded 2026-11-26T13:04:30+00:00 · Groq key absent. Fresh Groq extractions: **0/8**. [Raw outputs and traces](../backend/eval/results/live.json).

[Timestamped Groq extraction payloads](../backend/eval/runs/live_extraction_20261126T130430375670Z.json).

Live extraction coverage is incomplete. Fallback outputs are identified below. Each source's `live_attempts` in the raw file lists model payloads actually received and retained by the application.

| Source | Actual mode | Verified claims | Rejected candidates |
| --- | --- | ---: | ---: |
| E1 | replay | 3 | 0 |
| E2 | replay | 3 | 0 |
| E3 | replay | 4 | 1 |
| E4 | replay | 2 | 0 |
| E5 | unavailable | — | — |
| E6 | unavailable | — | — |
| E7 | unavailable | — | — |
| E8 | unavailable | — | — |

Eva's same-day E3/E4 closure conflict: **detected** (E3: replay, E4: replay).

E3 replay rejected "Eva independently resolves complex scenarios." with reason `no exact match in E3`. Only accepted claims feed the conflict rule. The recorded E3 example deliberately includes this bad candidate.

| API probe | HTTP | Actual mode | Mechanical checks |
| --- | ---: | --- | --- |
| eva-action | 200 | unavailable | persisted_in_history=True, human_records_preserved=True, no_proposals=True |
| leo-action | 200 | unavailable | persisted_in_history=True, human_records_preserved=True, no_proposals=True |
| lina-action | 200 | unavailable | persisted_in_history=True, human_records_preserved=True, no_proposals=True |
| eva-evidence | 200 | unavailable | unavailable_refusal=True |
| eva-readiness | 200 | unavailable | unavailable_refusal=True |
| unsupported | 200 | unavailable | unavailable_refusal=True |

**Business-fixture totals:** 0 passed, 0 failed, 0 blocked; 0 supplied.

No business-owner fixture files were supplied. Their accuracy remains unmeasured.

## Replay run

Recorded 2026-11-26T13:14:25+00:00 · Groq key absent. Fresh Groq extractions: **0/8**. [Raw outputs and traces](../backend/eval/results/replay.json).

| Source | Actual mode | Verified claims | Rejected candidates |
| --- | --- | ---: | ---: |
| E1 | replay | 3 | 0 |
| E2 | replay | 3 | 0 |
| E3 | replay | 4 | 1 |
| E4 | replay | 2 | 0 |
| E5 | skipped | — | — |
| E6 | skipped | — | — |
| E7 | skipped | — | — |
| E8 | skipped | — | — |

Eva's same-day E3/E4 closure conflict: **detected** (E3: replay, E4: replay).

E3 replay rejected "Eva independently resolves complex scenarios." with reason `no exact match in E3`. Only accepted claims feed the conflict rule. The recorded E3 example deliberately includes this bad candidate.

| API probe | HTTP | Actual mode | Mechanical checks |
| --- | ---: | --- | --- |
| eva-action | 200 | unavailable | persisted_in_history=True, human_records_preserved=True, no_proposals=True |
| leo-action | 200 | unavailable | persisted_in_history=True, human_records_preserved=True, no_proposals=True |
| lina-action | 200 | unavailable | persisted_in_history=True, human_records_preserved=True, no_proposals=True |
| eva-evidence | 200 | unavailable | unavailable_refusal=True |
| eva-readiness | 200 | unavailable | unavailable_refusal=True |
| unsupported | 200 | unavailable | unavailable_refusal=True |

**Business-fixture totals:** 4 passed, 0 failed, 13 blocked; 17 supplied.

| Fixture | Evaluation mode | Served mode | Verdict |
| --- | --- | --- | --- |
| AG-EVA | unscored | unavailable | blocked |
| AG-LEO | unscored | unavailable | blocked |
| AG-LINA | unscored | unavailable | blocked |
| AQ-EVA-READY | unscored | unavailable | blocked |
| AQ-EVA-WHY | unscored | unavailable | blocked |
| AQ-LEO-ACCESS | unscored | unavailable | blocked |
| AQ-ATLAS-DOCS | unscored | unavailable | blocked |
| AQ-VISIBILITY | unscored | unavailable | blocked |
| AQ-UNSUPPORTED | unscored | unavailable | blocked |
| EX-E3 | replay | replay | pass |
| EX-E4 | replay | replay | pass |
| EX-E1 | replay | replay | pass |
| EX-E2 | replay | replay | pass |
| EX-E5 | unscored | skipped | blocked |
| EX-E6 | unscored | skipped | blocked |
| EX-E7 | unscored | skipped | blocked |
| EX-E8 | unscored | skipped | blocked |

## Reproduce

From the repository root, activate the backend environment and run:

```bash
cd backend
python -m eval.run_eval --mode replay
python -m eval.run_eval --mode live
```

Live mode reads `GROQ_API_KEY` from the environment or local .env. Existing development and production databases are untouched. Live mode always archives provider payloads in `backend/eval/runs/live_extraction_<UTC>.json`. A null payload means no live response was recorded for that source. Results for each mode replace that mode's summary JSON file, and the report shows the latest available run of each mode. Exit 1 signals a failed check. Exit 2 signals incomplete live extraction, API or business-fixture coverage. A replay without business fixtures checks the seeded evidence behavior only.

Human review of an existing scored run uses `python -m eval.run_eval --mode manual --snapshot eval/results/live.json --reviews reviews.json`. The review file is a JSON array with one object per assessed fixture (`fixture_id`, `reviewer`, `verdict` equal to pass or fail, and `reason`). The report identifies the originating run by SHA-256, records each review separately, and leaves missing verdicts unscored. A human review requires an actual live or replay output for that fixture.

## Business-owner fixtures

The runner reads JSON objects or arrays of them from `backend/eval/fixtures/*.json`. An alternative directory is accepted via `--fixtures`. Every object requires a unique `id` and `kind`. Supported fields:

| Kind | Target | Expectations |
| --- | --- | --- |
| extract | `source` (E1–E8) | `contains_claims` and/or `excludes_claims`, arrays of partial exact claim objects with scope, value, reference or quote. |
| agent | `case` (e.g. ONB-005) | `cited_refs` and/or `text_contains`, arrays of strings. |
| ask | `question`, optionally `case` | `refused` (boolean), `cited_refs`, and/or `text_contains`. |

Example input: `{"id":"eva-gap","kind":"extract","source":"E3","contains_claims":[{"scope":"complex_scenarios","value":"coverage_pending"}]}`. For agent and Ask fixtures, `actor` can name a seeded demo account; the default is Elira Dervishi. The runner independently checks returned source IDs, claim IDs and exact Ask quote text through that actor's visible cases. Text checks use case-insensitive substring matching; reviewers should read the raw traces before treating a matching phrase as evidence of a useful recommendation.
