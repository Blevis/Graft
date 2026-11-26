# Business rules

Answers from the Business Owner checkpoint (Erjon Rrumbullaku, Day 1) and what each one changes in Graft.
Until a question is answered, Graft runs on the **current assumption**, which is grounded in the starter pack.

Status: **checkpoint pending.**

| # | Question | Current assumption (source) | Answer | Change in Graft |
| --- | --- | --- | --- | --- |
| 1 | Is "closure reported on the same day as a scoped qualification from a different sender" the right conflict trigger? | Yes. Same case + same date = contemporaneous; one flag per source pair (AGENT_SPEC §4, Eva comparison rule). | _pending_ | `CLOSURE_CONFLICT` in `services/rules.py` |
| 2 | Who validates readiness: the Technical Lead, the KT Owner, or both? Can a line manager ever close onboarding? | Only the case's technical owner records a readiness review; a line manager's closure is a report (starter pack §8: "technical-owner validation"). | _pending_ | `POST /cases/{id}/reviews` authorisation |
| 3 | Are 3 working days (unanswered request) and 7 days (stale tracker) the right thresholds? | 3 working days; 7 calendar days. Both are org settings. | _pending_ | Settings `unanswered_working_days`, `stale_days` |
| 4 | Does "Active" access ever count as done without the employee's own successful test? | Never. Requested ≠ approved ≠ active ≠ usable; only the employee's test makes it usable (starter pack §7). | _pending_ | `ACCESS_NOT_CONFIRMED`; only the employee may set `confirmed_usable` |
| 5 | Who sets the expected readiness date, and should a missing date be flagged? | The coordinator records it (`PATCH /cases/{id}`); the flag exists but is off (setting `flag_missing_readiness_date`). The checklist lists it (starter pack §6); Lina's E5 and Owen's E6 show it missing. | _pending_ | Turn on `flag_missing_readiness_date` if confirmed |
| 6 | Which next actions would you trust an AI agent to propose? Should it ever draft messages to people? | It proposes tasks, drafted follow-up messages and access chases; a person accepts, edits or dismisses each one; nothing is sent automatically. | _pending_ | Case agent proposal kinds |

## Rules Graft applies today

| Rule | Severity | Fires when | Setting |
| --- | --- | --- | --- |
| `CLOSURE_CONFLICT` | high | A source reports closure or independence and a **different** source on the **same date** reports a scoped qualification (occasional support, pending complex scenarios, a "with support" / partial readiness classification). Only verified claims count. | — |
| `ACCESS_NOT_CONFIRMED` | high if any system is `not_provisioned` or `awaiting_approval`, else medium | Any tracked system is not `confirmed_usable`. | — |
| `UNANSWERED_REQUEST` | high | A source addressed to a role has no later source from that role, it is not itself a reply, and more than N working days have passed (weekdays after the send date up to the as-of date). | `unanswered_working_days` = 3 |
| `STALE_TRACKER` | medium | The tracker's last update is more than N days before the as-of date. | `stale_days` = 7 |
| `MISSING_PROJECT`, `MISSING_MANAGER` | medium | The tracker field is empty (a dash in the source). The value stays NULL. | — |
| `MISSING_TECH_OWNER` | high | The case has a project but nobody can validate readiness. | — |
| `MISSING_READINESS_DATE` | medium | No expected readiness date is recorded. | `flag_missing_readiness_date` (off) |

All ages are computed against the org's `as_of_date` (2026-10-14 in the demo org), never the wall clock.
