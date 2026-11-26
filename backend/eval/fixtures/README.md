# Evaluation fixtures

Expected outcomes, written before measuring.

## Layout

| Path | Read by | Contents |
| --- | --- | --- |
| `extraction.json`, `agent.json`, `ask.json` | `python -m eval.run_eval` (globbed, flat format) | The checks the harness can score today. |
| `spec/*.json` | People (not globbed) | The full expectations from `AGENT_SPEC.md` §6–§8, including negative checks and permission checks the harness does not score yet. |

The flat files are derived from `spec/`. When an expectation changes, edit `spec/` first, then the flat file.

## Flat format (harness)

One JSON array per file; every object needs a unique `id` and a `kind`:

- `extract`: `source` (E1–E8) plus `contains_claims` and/or `excludes_claims`, each a list of
  `{scope, value[, reference][, quote]}` patterns matched exactly against **accepted** claims.
- `agent`: `case` plus `cited_refs` and/or `text_contains`; optional `actor` (a demo account name).
- `ask`: `question`, optional `case`, plus `refused`, `cited_refs` and/or `text_contains`; optional `actor`.

Text checks are case-insensitive substrings. Fixtures needing a live model are reported as `blocked` in replay mode.

## Not yet scored by the harness (in `spec/` only)

- Negative agent and Ask checks: the agent must not propose closing onboarding or marking access usable; Ask must not
  state that Eva is ready or leak another employee's systems (`must_not_propose`, `must_not_say`, `must_not_cite`).
- Permission checks (`AG-EMPLOYEE-BLOCKED` 403, `AG-HIDDEN-CASE` 404) and the verifier fixtures (`VF-*`): covered by
  pytest (`tests/test_agent_api.py`, `tests/test_verifier_rules.py`).
- End-to-end workflow checks (`spec/workflow.json`): covered by pytest (`tests/test_eva_path.py`,
  `tests/test_visibility.py`, `tests/test_groq_client.py`).
