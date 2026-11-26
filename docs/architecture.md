# Architecture

## One image, one origin

```
Browser ──HTTPS──► Render web service (one Docker image)
                    uvicorn + FastAPI
                    ├── /api/*  JSON API ─────────────┐
                    └── /*      React SPA (built)      │
                                                       ▼
                      services: tenancy · permissions · visibility · responsibilities · presentation
                                rules · matching · audit · cases
                      ai:       client (Ollama) · verifier · pipeline · agent · ask
                      worker:   analysis jobs (leases, retries) · overdue reminders
                                                       │
                    Postgres 16 ◄─────────────────────┘     Ollama (private network) ◄── ai/client.py only
```
Private deployments run the app, a worker, Postgres and Ollama on an internal network (docs/deployment.md); the
hosted demo profile has no model.

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2. SQLite in tests, Postgres in production;
  the models avoid Postgres-only types so both run the same migrations.
- **Frontend:** React, Vite, TypeScript, TanStack Query, Tailwind, shadcn/ui. Every save refetches from the API, so a
  hard refresh always shows the database state.
- **Start-up:** `alembic upgrade head`, then a seed that only runs when the demo org is missing (it never deletes human
  records), then uvicorn behind Render's proxy (`--proxy-headers`, so HTTPS is detected for the `Secure` cookie).

## Four data classes, four write paths

| Class | Tables | Written by | Guarantee |
| --- | --- | --- | --- |
| **Evidence** | `sources` | Seed, inbox ingest, inbox link | Immutable. A correction or a re-link is a new row with `version + 1` and `supersedes_id`. |
| **Derived** | `analysis_runs`, `claims`, `rejected_candidates`, `findings` | `ai/pipeline.py`, `services/rules.py` | Recomputable from evidence. Holds no human state. Finding ids are stable hashes, so a task can point at one across recomputes. |
| **AI proposals** | `agent_runs`, `agent_steps`, `agent_proposals` | The case agent* | Never authoritative. Become a task only when a person accepts one through the task route. |
| **Human** | `tasks`, `reviews`, `training_entries` | `api/tasks.py`, `api/reviews.py`, `api/responsibilities.py` only | Reviews and training entries are append-only. Re-analysis never changes, duplicates or deletes them (tested). |
| **Authorization** | `memberships`, `role_assignments`, `case_responsibilities` | `api/people.py`, `api/responsibilities.py` only | Soft revocation keeps history; every grant, revoke, assignment and replacement is audited. The AI layer has no import path here (tested). |
| **Presentation** | `user_preferences`, `ai_guidance_versions` | `api/preferences.py` | Never read by an authorization check. Guidance is append-only and versioned. |

`backend/app/ai/` has no import path to the task or review routes. Every write adds an `AuditEvent` (actor, org,
entity, action, before/after) in the same transaction.

## The trust layer

1. **One source per call.** The model receives one immutable body plus its metadata.
2. **Constrained output.** A local Ollama model (default `qwen3:8b`) through the native `/api/chat` with the JSON
   schema as `format` and `stream: false` (`ai/schemas/extract_v2.json`): each claim picks one entry from an enum of
   the 22 valid `scope/value` pairs, which the server splits back into scope and value. The full response is
   validated server-side; the endpoint host and model tag are allowlisted, cloud tags rejected, and calls are
   bounded by a concurrency semaphore (busy), a timeout and a context budget (oversized input is refused).
3. **Exact-quote verifier.** A claim survives only if its quote occurs exactly once in the body; offsets are computed
   server-side and asserted (`body[start:end] == quote`). Access claims must name their system inside the quote.
   Failures are kept as `rejected_candidates` and never reach the rules or the evidence list.
4. **Modes, always labelled.** `live` → `cached` (same source, body hash, prompt, schema, model) → `replay` (recorded
   examples bound to the body's SHA-256) → `unavailable` (originals still shown; humans keep working).
5. **Limits.** 20 s timeout, at most 2 attempts; `ai_enabled=false` turns every AI call off.

## The case agent* (design)

A bounded tool-calling loop over one case, in Ollama's native tool-call / tool-result format: read-only tools (`get_case`, `list_findings`, `read_source`,
`list_claims`, `list_tasks`, `list_access_items`, `list_knowledge`, `get_settings`) that run as the requesting user,
at most 8 tool calls and 60 s, ending in a `submit_proposals` call validated server-side. Proposals must cite ids on
the case. The full trace is stored and shown. Ask Graft uses the same visibility-scoped retrieval and cites every
statement; it never decides readiness.

## Role-aware AI: two layers

1. **Authorization first** (Layer A). `visible_cases` + `Policy.sees_evidence` choose the sources; nothing in the
   question, the working context, the preferences or the guidance can widen that set ("act as PMO" changes nothing).
2. **Presentation second** (Layer B, `services/presentation.py`). A role response profile (PMO, project manager,
   technical owner, ...) plus the user's focus/detail/format and the latest PMO guidance version shape emphasis, the
   number of passages and the layout (action list, status brief, chronological, stakeholder report). Every statement
   remains a verbatim, server-verified quote; guidance that tries to disable citations, change permissions or decide
   readiness is rejected at save time.

## Tenancy and visibility

- **Tenancy:** every tenant table has `org_id NOT NULL`; every query goes through `scoped()` / `get_scoped()`.
  Another org's row is a 404, never a 403.
- **Membership ≠ roles ≠ responsibilities.** `memberships` says who belongs to the org (active / suspended).
  `role_assignments` grant a canonical role at organization, project or case scope (a person can hold many).
  `case_responsibilities` say who is accountable for one responsibility on one case. A project-scoped grant with
  `default_for_cases` is inherited by that project's cases at read time (`services/responsibilities.py`); a case-level
  row overrides it for that case only. Nothing is copied, so overrides never touch the project or other cases.
- **Request context** (`services/tenancy.py::load_ctx`): user, org, membership, active grants (respecting validity
  dates) and the presentation-only working context, all resolved from the signed session cookie and the database.
- **Visibility** (`services/visibility.py`): org admin, PMO, management viewer and auditor (org scope) see every case;
  any project-scoped grant shows that project's cases; any case grant or responsibility shows that case; employees
  their own case; designated access testers the case of their item; anyone the case behind a task assigned to them.
  Org-scoped eligibility roles (technical owner, line manager...) show nothing by themselves. A hidden case is a 404.
- **Field-level policy** (`services/permissions.py::Policy`): each visible case gets a view level —
  `full` (case team), `employee` (own case, no reviewer rationale), `summary` (viewer, auditor, HR partner, project
  member: no raw evidence, claims or rationale), `access_only` (access responsible: identity plus their systems).
  `services/cases.py` shapes the payload by level before it leaves the server, and Ask Graft sends the model source
  bodies only from `full`/`employee` cases.
- **Capabilities** live in one place (`Policy`): create task, assign responsibilities, record training, edit access,
  confirm access (employee, or a designated tester under `access_tester_policy=designated`), review (the case's
  primary technical owner only), manage roles (org admin only, never yourself, never the last admin).

## Security notes

- No passwords are stored (demo login now; OIDC planned). No credentials in the tracker or in git; `.env.example`
  has empty values.
- Outside demo mode the app refuses to start with the development `SESSION_SECRET` or one shorter than 32 characters.
- Session cookie: `HttpOnly`, `SameSite=Lax`, `Secure` over HTTPS.
- Source bodies are passed to the model as data inside a JSON payload; the prompts tell the model that instructions in
  them are document content.

## Quality gates

- `cd backend && pytest -q`: the Eva path, re-analysis safety, tenancy 404s, visibility per role, role checks, the
  verifier, the Ollama provider (httpx MockTransport: busy, timeout, invalid JSON, cloud tag, oversize, multi-turn
  tools), sign-off gate, workflow and queues, relay intake and jobs, OIDC with a mocked issuer, data controls,
  metrics, backup/restore.
- `cd frontend && npm run build`: type check and production build.
- GitHub Actions runs both on every push and pull request.


## Sign-off (policy v1)

Reviews stay append-only. `validate_scope` (optionally for one case milestone), `close` (final sign-off) and
`reopen` are dispositions; `services/readiness.py` derives milestone satisfaction and final readiness from the
review history, so nothing is ever edited. `close` is gated server-side in `api/reviews.py`: rationale, at least one
current case-bound citation, required milestones validated, no blocking access, or a documented, audited exception
when the org allows it. Each review stores the evidence snapshot it was made on, which drives the reassessment notice.

## Workflow

`workflow_templates` (versioned) → `case_requirements` (snapshot per case) → tasks routed by
`services/workflow.py` (responsibility holder, else the coordinator queue), with `task_assignments` (append-only
history) and `task_pauses` (waiting intervals). `services/sla.py` holds the org clock (as-of or real) and the
working-hours calendar. The AI layer has no import path to `services/workflow.py` (tested).

## Intake and background processing

Sources carry provenance (`channel`, `sender`, `received_at`, `external_id` with a partial unique index for
idempotency, `match_status`). `analysis_jobs` hold one active job per source version; the worker claims jobs with a
lease, runs `ai/pipeline.analyze_source` (the same service used for manual analysis, seed replay and evaluation),
defers while the model is unavailable without spending attempts, marks jobs superseded when a newer version exists,
and recomputes findings from current versions only. Jobs never touch tasks or reviews.

## Identity and sessions

Demo login (demo mode only) or OIDC (authorization code + PKCE, state, nonce, JWKS-verified ID token; identity links,
verified-email provisioning or group mapping). Sessions are signed, expiring cookies; the membership and grants are
re-read on every request, so suspension takes effect immediately. State-changing requests need the double-submit
CSRF token. Relays authenticate with hashed, scoped service tokens instead of sessions.

## View levels

`full` (case team) · `employee` (own case) · `summary` (viewer, auditor, HR partner, project member) ·
`access_only` (access responsible) · `task_only` (someone whose only link is a task: their tasks and exactly the
sources those tasks cite). The same level applies to case pages, direct source links (`GET /api/sources/{id}`),
Inbox, Knowledge, Insights, metrics, export, timeline, agent traces and Ask retrieval.
