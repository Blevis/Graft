# Evaluation of Graft's AI features

Each run starts with a new, isolated SQLite database and the eight fictional starter-pack sources. The case agent and Ask Graft run through their HTTP routes as signed-in demo users. The live command runs the private Ollama model with outbound network access blocked by a socket guard; the replay command disables model access for the process. A run whose model was unavailable is reported as blocked, not as a pass.

## Model comparison

| Run | Model | Digest | Fresh extractions | Fixtures pass/fail/blocked | Cold ms | Warm median ms | Memory |
| --- | --- | --- | --- | --- | --- | --- | --- |
| groq_baseline_live | groq:openai/gpt-oss-120b | `—` | 6/8 | 10/1/6 | — | — | — |

## Replay run

Recorded 2026-11-26T15:54:48+00:00 · model access disabled for this process (recorded examples only). Fresh model extractions: **0/8**. [Raw outputs and traces](../backend/eval/results/replay.json).

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

## Historic baseline: Groq live run (before private inference)

Recorded 2026-11-26T13:40:54+00:00 · historic Groq run (hosted, before the move to private inference). Fresh model extractions: **6/8**. [Raw outputs and traces](../backend/eval/results/groq_baseline_live.json).

[Timestamped extraction payloads](../backend/eval/runs/live_extraction_20261126T134239368348Z.json).

Live extraction coverage is incomplete. Fallback outputs are identified below. Each source's `live_attempts` in the raw file lists model payloads actually received and retained by the application.

| Source | Actual mode | Verified claims | Rejected candidates |
| --- | --- | ---: | ---: |
| E1 | live | 3 | 0 |
| E2 | live | 3 | 0 |
| E3 | live | 3 | 0 |
| E4 | live | 2 | 0 |
| E5 | live | 0 | 0 |
| E6 | live | 2 | 0 |
| E7 | unavailable | — | — |
| E8 | unavailable | — | — |

Eva's same-day E3/E4 closure conflict: **detected** (E3: live, E4: live).

| API probe | HTTP | Actual mode | Mechanical checks |
| --- | ---: | --- | --- |
| eva-action | 200 | live | persisted_in_history=True, human_records_preserved=True, completed=True, one_to_three=True, case_citations=True |
| leo-action | 200 | unavailable | persisted_in_history=True, human_records_preserved=True, no_proposals=True |
| lina-action | 200 | unavailable | persisted_in_history=True, human_records_preserved=True, no_proposals=True |
| eva-evidence | 200 | live | grounded_citations_or_refusal=True, answers_with_e3=True |
| eva-readiness | 200 | unavailable | unavailable_refusal=True |
| unsupported | 200 | live | grounded_citations_or_refusal=True, unsupported_refused=True |

**Business-fixture totals:** 10 passed, 1 failed, 6 blocked; 17 supplied.

| Fixture | Evaluation mode | Served mode | Verdict |
| --- | --- | --- | --- |
| AG-EVA | live | live | pass |
| AG-LEO | unscored | unavailable | blocked |
| AG-LINA | unscored | unavailable | blocked |
| AQ-EVA-READY | live | live | pass |
| AQ-EVA-WHY | live | live | pass |
| AQ-LEO-ACCESS | unscored | unavailable | blocked |
| AQ-ATLAS-DOCS | live | live | pass |
| AQ-VISIBILITY | unscored | unavailable | blocked |
| AQ-UNSUPPORTED | live | live | pass |
| EX-E3 | live | live | fail |
| EX-E4 | live | live | pass |
| EX-E1 | live | live | pass |
| EX-E2 | live | live | pass |
| EX-E5 | live | live | pass |
| EX-E6 | live | live | pass |
| EX-E7 | unscored | unavailable | blocked |
| EX-E8 | unscored | unavailable | blocked |

## Reproduce

From the repository root, activate the backend environment and run:

```bash
cd backend
python -m eval.run_eval --mode replay
python -m eval.run_eval --mode live
```

Live mode uses `OLLAMA_BASE_URL` / `LLM_MODEL` from the environment or local .env and refuses any non-loopback, non-allowed network connection. Existing development and production databases are untouched. Live mode always archives provider payloads in `backend/eval/runs/live_extraction_<UTC>.json`. A null payload means no live response was recorded for that source. Results for each mode replace that mode's summary JSON file, and the report shows the latest available run of each mode. Exit 1 signals a failed check. Exit 2 signals incomplete live extraction, API or business-fixture coverage. A replay without business fixtures checks the seeded evidence behavior only.

Human review of an existing scored run uses `python -m eval.run_eval --mode manual --snapshot eval/results/live.json --reviews reviews.json`. The review file is a JSON array with one object per assessed fixture (`fixture_id`, `reviewer`, `verdict` equal to pass or fail, and `reason`). The report identifies the originating run by SHA-256, records each review separately, and leaves missing verdicts unscored. A human review requires an actual live or replay output for that fixture.

## Business-owner fixtures

The runner reads JSON objects or arrays of them from `backend/eval/fixtures/*.json`. An alternative directory is accepted via `--fixtures`. Every object requires a unique `id` and `kind`. Supported fields:

| Kind | Target | Expectations |
| --- | --- | --- |
| extract | `source` (E1–E8) | `contains_claims` and/or `excludes_claims`, arrays of partial exact claim objects with scope, value, reference or quote. |
| agent | `case` (e.g. ONB-005) | `cited_refs` and/or `text_contains`, arrays of strings. |
| ask | `question`, optionally `case` | `refused` (boolean), `cited_refs`, and/or `text_contains`. |

Example input: `{"id":"eva-gap","kind":"extract","source":"E3","contains_claims":[{"scope":"complex_scenarios","value":"coverage_pending"}]}`. For agent and Ask fixtures, `actor` can name a seeded demo account; the default is Elira Dervishi. The runner independently checks returned source IDs, claim IDs and exact Ask quote text through that actor's visible cases. Text checks use case-insensitive substring matching; reviewers should read the raw traces before treating a matching phrase as evidence of a useful recommendation.
