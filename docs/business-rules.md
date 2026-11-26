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

---

# Roles, ownership and AI guidance (PMO interview, Day 1)

Sources: the PMO interview notes taken independently by two transcribers (Blevis, Vigen), and the implementation
addendum `GRAFT_ROLE_AND_ORGANIZATION_SPEC`. The PMO was deliberately open-ended ("how would you approach it?"), so
this section separates **what the interview said** from **what the team decided**. No further PMO questions are
possible, so the decisions below are final for this build.

## What the interview said (findings)

| # | Finding (translated and condensed from both transcripts) | Where Graft implements it |
| --- | --- | --- |
| I1 | An onboarding has a manager and a technical lead. | `line_manager` and `technical_owner` responsibilities on every case |
| I2 | When a person starts on a project, the manager must assign a **technical lead** and a **person responsible for training**. Training is usually run by the tech lead, rarely by the manager, or by someone with management competence. | `training_responsible` is a separate responsibility; one person may hold several (Ardit Kola is technical owner *and* training responsible on Orion). Both are required by default, so missing ones show as ownership gaps. |
| I3 | Besides the line manager there is an **additional manager**: the main client contact, who talks to the client (or the business partner) and gathers requirements and details. | `project_manager` role, default label "Project Manager / Additional Manager" (relabel per org) |
| I4 | HR is involved through an **HR business partner** who stays in contact with the employee. | `hr_business_partner` role; summary-level view, no technical assessment notes |
| I5 | The **PMO** manages and steers; the **manager** has visibility of training and problems and "knows everything" about the employee's skills. | PMO: org-wide visibility. Line manager: full view of their reports (training log, flags, tasks) |
| I6 | **Access management depends on who can test it best** (access is potentially VPN). | Per-system access responsible; designated tester per system as an org setting (`access_tester_policy`); the starter-pack default (employee's own test) is kept |
| I7 | A **status has no defined expiry date**. | Tracker age is always shown; `stale_days` stays a configurable threshold (see open question O9) |
| I8 | Focus on making the **roles understandable**; there is a business home board where the PMO verifies users and needs visibility. | People & Roles, project teams, the Stakeholders panel, role-aware Home |
| I9 | Information must not be lost: documented, kept, visible to every stakeholder, so tomorrow it can be reused for **new cases**. | Append-only evidence, reviews and training log; responsibility history; knowledge references with provenance and re-verification flags |
| I10 | The goal is to improve an **existing process**, as added value, not a parallel one. | Graft keeps the tracker as one report among others and links to project-owned folders instead of copying documents |
| I11 | The chat's scope is **only the application**: nothing outside the app, only the data and context inside it. | Ask Graft answers only from evidence the asking user may see, with verbatim citations; no external sources |
| I12 | There must always be a **human touch**: the PMO should be able to steer the AI so it presents information the way each person wants it. | Versioned PMO AI guidance, personal focus/detail/format preferences, role response profiles. All presentation only |

## Team defaults (final: the PMO is no longer available for questions)

The interview was the only PMO checkpoint. Where it was silent or ambiguous, the team decided as below, grounded in
the interview, the starter pack (authoritative for the original cases) and the role addendum. Each decision is an org
setting or a single rule in `services/permissions.py`, so a real customer can change it without code changes.

| Decision | Setting | Why |
| --- | --- | --- |
| Required responsibilities on every case: technical owner and training responsible | `required_responsibilities` | Interview I2. Line manager can be added; the tracker's `MISSING_MANAGER` rule already covers an empty manager field |
| Project managers may assign responsibilities inside their own projects, only to people who already hold the role | `project_manager_can_assign` = true | Interview I2/I3: the managers allocate people on their projects |
| Only the employee's own successful test marks access usable; a designated per-system tester is opt-in | `access_tester_policy` = `employee` | Starter pack §7 is authoritative for the original cases; interview I6 motivates the opt-in |
| Only the org admin grants or revokes roles; nobody grants themselves anything; the last admin cannot be removed | — | No self-escalation (addendum §5.1) |
| Only the case's primary technical owner records a readiness review; no delegation | — | Starter pack §8 |
| Org admin, PMO and auditor read the whole audit trail; everyone else reads their own actions | — | Addendum permission matrix |
| Management viewer, auditor, HR business partner and project member get a **summary** view: no raw evidence, claims or review rationale | — | Least privilege (addendum §5.3) |
| Role display labels are org-configurable; codes and permissions never change | `role_labels` | The interview uses titles interchangeably (addendum §3.2) |

## Ambiguities in the interview and how they were resolved

| # | Ambiguity | Decision |
| --- | --- | --- |
| A1 | "Business Partner" is used on the client side ("the additional manager talks to the client or the business partner") and also for HR ("HR business partner"). | Only HR is modelled as a role (`hr_business_partner`). The client-side business partner is an external contact, not a Graft user; labels are configurable. |
| A2 | "Additional Manager / Project Leader" is described as the main client contact; one transcript also calls the coordinator "viewer of everything, aka additional manager". | Two roles: `project_manager` (project scope, client contact, default label "Project Manager / Additional Manager") and `pmo_coordinator` (organization scope, sees everything). They are not conflated. |
| A3 | "The manager knows everything (skills)" vs. what the PMO sees. | Line manager: full view of their reports. PMO: full operational view of every case. No HR-sensitive fields are stored, so none are exposed. |
| A4 | Who assigns the technical lead and training person: "the manager" (unspecified). | PMO/admin everywhere; project managers within their projects; nobody assigns themselves. |
| A5 | Skills and performance assessments. | Not stored as separate fields. Technical review rationale is case-team only; HR partner, viewers and auditors see summaries. |
| A6 | "Access depends on who tests it best." | Per-system access responsible coordinates; usability is confirmed by the employee, or by a designated tester when the org turns that on. |
| A7 | Technical sign-off delegation was not discussed. | No delegation: reassign the case's technical owner instead (history kept, review authority moves with it). |
| A8 | Which AI settings are personal vs. organizational. | Personal: focus, detail, format, working context. Organization (PMO/admin): versioned AI guidance. None of them affects permissions. |
| A9 | "A status has no defined expiry date." | Tracker age is always shown; `stale_days` (7) only flags a status as stale and is an org setting. |
| A10 | "No limit." | No limit on how many responsibilities a case has or how many a person holds; one primary per responsibility for formal actions. |
