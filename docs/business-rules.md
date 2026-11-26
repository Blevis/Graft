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
this section separates **what the interview said** from **what Graft assumes** until the PMO confirms it.

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

## Proposed defaults (implemented, configurable, awaiting PMO confirmation)

| Default | Setting | Why |
| --- | --- | --- |
| Required responsibilities on every case: technical owner and training responsible | `required_responsibilities` | Interview I2. Line manager can be added; the tracker's `MISSING_MANAGER` rule already covers an empty manager field |
| Project managers may assign responsibilities inside their own projects, only to people who already hold the role | `project_manager_can_assign` = true | Spec matrix; open question O4 |
| Only the employee's own successful test marks access usable; a designated per-system tester is opt-in | `access_tester_policy` = `employee` | Starter pack §7 is authoritative for the original cases; interview I6 suggests the opt-in |
| Only the org admin grants or revokes roles; nobody grants themselves anything; the last admin cannot be removed | — | Spec §5.1 (no self-escalation) |
| Only the case's primary technical owner records a readiness review. No delegation yet | — | Starter pack §8; open question O7 |
| Org admin, PMO and auditor read the whole audit trail; everyone else reads their own actions | — | Spec matrix |
| Management viewer, auditor, HR business partner and project member get a **summary** view: no raw evidence, claims or review rationale | — | Spec §5.3; open questions O3 and O5 |
| Role display labels are org-configurable; codes and permissions never change | `role_labels` | Spec §3.2 ("Business Partner" is *not* auto-mapped to HR) |

## Open questions for the PMO

| # | Question | Current assumption |
| --- | --- | --- |
| O1 | Is "Business Partner" the HR Business Partner or the client-facing Project Manager here? (The interview uses it on the client side: "the additional manager talks to the client or the business partner".) | Not auto-mapped; the org chooses labels |
| O2 | Is "Additional Manager" a formal title for Project Manager / Project Leader, or a distinct role? One transcript also calls the *coordinator* "viewer of everything, aka additional manager / project leader". | `project_manager` (project scope) is separate from `pmo_coordinator` (org scope) |
| O3 | Does the PMO see every employee field, or only operational onboarding information? | Operational onboarding information; no HR-sensitive fields exist yet |
| O4 | Can project managers assign line managers, technical owners and training responsibles, or only PMO/admin? | Yes inside their projects (setting) |
| O5 | Which roles may see employee skills and performance assessments; are any fields HR-only? | Technical review rationale is case-team only; HR partner sees summaries |
| O6 | Who validates access per system: Access Support, the employee, the system owner or another tester? | The employee, unless the org turns on designated testers |
| O7 | Can a technical owner delegate readiness sign-off, and what evidence does the delegation need? | No delegation |
| O8 | Which AI preferences can individuals set, and which only PMO/admin? | Individuals: focus, detail, format, working context. PMO/admin: org guidance |
| O9 | The PMO said a status has no defined expiry. Is 7 days the right staleness threshold, or should staleness be per status? | 7 days, org setting `stale_days` |
| O10 | "No limit" (interview note 2): is there no limit on how many people/responsibilities an onboarding can involve, or on its duration? | No limit on responsibilities per case or per person |
