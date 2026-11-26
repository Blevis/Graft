# Architecture

## One image, one origin

```
Browser ──HTTPS──► Render web service (one Docker image)
                    uvicorn + FastAPI
                    ├── /api/*  JSON API ─────────────┐
                    └── /*      React SPA (built)      │
                                                       ▼
                      services: tenancy · visibility · rules · matching · audit · cases
                      ai:       client (Groq) · verifier · pipeline · agent* · ask*
                                                       │
                    Postgres 16 (Render managed) ◄─────┘          Groq API ◄── ai/client.py only
```
`*` in progress (see README roadmap).

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
| **Human** | `tasks`, `reviews` | `api/tasks.py`, `api/reviews.py` only | Reviews are append-only. Re-analysis never changes, duplicates or deletes either (tested). |

`backend/app/ai/` has no import path to the task or review routes. Every write adds an `AuditEvent` (actor, org,
entity, action, before/after) in the same transaction.

## The trust layer

1. **One source per call.** The model receives one immutable body plus its metadata.
2. **Constrained output.** Groq `openai/gpt-oss-120b` with strict JSON-schema output (`ai/schemas/extract_v1.json`).
3. **Exact-quote verifier.** A claim survives only if its quote occurs exactly once in the body; offsets are computed
   server-side and asserted (`body[start:end] == quote`). Access claims must name their system inside the quote.
   Failures are kept as `rejected_candidates` and never reach the rules or the evidence list.
4. **Modes, always labelled.** `live` → `cached` (same source, body hash, prompt, schema, model) → `replay` (recorded
   examples bound to the body's SHA-256) → `unavailable` (originals still shown; humans keep working).
5. **Limits.** 20 s timeout, at most 2 attempts; `ai_enabled=false` turns every AI call off.

## The case agent* (design)

A bounded Groq tool-calling loop over one case: read-only tools (`get_case`, `list_findings`, `read_source`,
`list_claims`, `list_tasks`, `list_access_items`, `list_knowledge`, `get_settings`) that run as the requesting user,
at most 8 tool calls and 60 s, ending in a `submit_proposals` call validated server-side. Proposals must cite ids on
the case. The full trace is stored and shown. Ask Graft uses the same visibility-scoped retrieval and cites every
statement; it never decides readiness.

## Tenancy and visibility

- **Tenancy:** every tenant table has `org_id NOT NULL`; every query goes through `scoped()` / `get_scoped()`.
  Another org's row is a 404, never a 403.
- **Visibility** (`services/visibility.py`): admin, coordinator and management see every case; technical owners their
  projects' cases; line managers their reports; employees their own case; anyone the case behind a task assigned to them.
  Every case read goes through `load_case` / `visible_cases`, so lists, inbox, insights, search and (later) the agent's
  tools all apply the same rule. A hidden case is a 404.
- **Authorisation:** the role comes from the server-side membership found via the signed session cookie, never from
  the request body. Only the case's technical owner can record a readiness review; only coordinators and admins
  assign tasks; only the employee can confirm their own access works.

## Security notes

- No passwords are stored (demo login now; OIDC planned). No credentials in the tracker or in git; `.env.example`
  has empty values.
- Outside demo mode the app refuses to start with the development `SESSION_SECRET` or one shorter than 32 characters.
- Session cookie: `HttpOnly`, `SameSite=Lax`, `Secure` over HTTPS.
- Source bodies are passed to the model as data inside a JSON payload; the prompts tell the model that instructions in
  them are document content.

## Quality gates

- `cd backend && pytest -q`: the Eva path, re-analysis safety, tenancy 404s, visibility per role, role checks, the
  verifier, the Groq client (stubbed), case fields, the hardening checks.
- `cd frontend && npm run build`: type check and production build.
- GitHub Actions runs both on every push and pull request.
