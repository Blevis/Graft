# Graft — Onboarding & Knowledge-Transfer Readiness

Team K · Engineering Albania Student Hackathon 2026.

A multi-tenant SaaS where a PMO tracks onboarding and knowledge transfer across projects, answering one question:
**what evidence shows an employee can actually work independently, and who acts next?**
AI extracts cited claims from evidence, rules flag conflicts, and people (coordinator, technical owner) decide.

All data is fictional (starter pack). Every navigation item works on the seeded data.

## Demo walkthrough (Eva Stone, ONB-005)

1. Open `/login`, sign in as **Elira Dervishi (PMO Coordinator)**. Home and Cases show 6 cases needing attention.
2. Open **ONB-005 Eva Stone**. The tracker says *Ready with Support*; the Evidence pill says *Conflicting reports*:
   the Line Manager (E4) reports closure while the Technical Lead (E3) reports occasional support and two uncovered
   complex scenarios, same day. Every claim links to its exact span in the original; one invented candidate is shown
   as rejected by the verifier.
3. **Assign** the flag to Ardit Kola (technical owner) with a due date. The coordinator cannot record a review (403).
4. Switch account to **Ardit Kola**, open ONB-005, **Record technical review** → *Keep open*, scope *Overall onboarding*,
   linked to the task. Refresh: everything is there. Coordinator → **Analyze evidence** twice: task and review unchanged.

Demo accounts (fictional): Dren Basha (admin), Elira Dervishi (PMO coordinator), Ardit Kola and Nadia Ferri
(technical owners), Luca Gray (line manager), Eva Stone and Leo Marin (employees), Mira Shehu (management, read-only),
Sam Rivera (admin of a second tenant, *Sandbox Co*, used to show tenant isolation).

### AI modes
- **Live AI**: `ANTHROPIC_API_KEY` set and AI enabled in Settings. One call per source, structured JSON output,
  20 s timeout, max 2 attempts, server-side refusal fallback enabled.
- **Verified cache**: identical input (source, body hash, prompt, schema, model) already extracted → reused, never duplicated.
- **Recorded example**: E1–E4 ship with the expected extractions from `AGENT_SPEC.md` (`backend/app/ai/cache/replay/`),
  bound to each body's SHA-256 and replayed through the same verifier. Used for the seed so the demo is deterministic
  without a key. Labelled in the UI; never presented as a live model response.
- **Analysis unavailable**: originals stay visible; tasks and reviews still work.

## Run it

**Docker (app + Postgres 16):**

```bash
docker compose up --build
# SPA:    http://localhost:8000/        (sign in at /login)
# Health: http://localhost:8000/api/health
# Startup runs migrations and seeds the demo orgs once; it never deletes human records.
# Reset explicitly: docker compose exec app python -m app.seed.seed --reset  (or user menu → Reset demo data as admin)
```

**Local dev (hot reload):**

```bash
cd backend && python -m venv .venv && .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt && alembic upgrade head
uvicorn app.main:app --reload                                   # :8000

cd frontend && npm install && npm run dev                       # :5173, proxies /api → :8000
```

**Tests / build:** `cd backend && pytest -q` · `cd frontend && npm run build`

Configuration is via environment variables; see [.env.example](.env.example). No secrets are committed.

## Deploy (Render)

`render.yaml` is a Blueprint: one Docker web service + one managed Postgres (Frankfurt).
Render → **New → Blueprint** → select this repo → set `ANTHROPIC_API_KEY` when prompted (optional; the app runs
without AI). Health check: `/api/health`. Migrations run on container start (`alembic upgrade head`).

## Architecture (one image, one origin)

```
Browser ──► FastAPI (uvicorn)
            ├── /api/*   JSON API (routers in backend/app/api)
            └── /*       built React SPA (frontend/dist) with index.html fallback
            └── SQLAlchemy 2.0 ──► Postgres (prod) / SQLite (dev, tests)
            └── backend/app/ai ──► Anthropic (only place the LLM is called)
```

| Path | What |
| --- | --- |
| `backend/app/main.py` | App factory, `/api/health`, router registration, SPA mount |
| `backend/app/config.py` | Env settings (pydantic-settings) |
| `backend/app/db.py` | Engine / session |
| `backend/app/api/` | One router per API group (auth, org, users, cases, timeline, inbox, tasks, reviews, access, knowledge, insights, settings, audit, admin) |
| `backend/app/{models,schemas,services,ai,seed}/` | Domain models, API schemas, rules/tenancy/audit, AI trust layer, seed loader |
| `backend/alembic/` | Migrations |
| `frontend/src/site/` | Public pages: `/`, `/pricing`, `/login` |
| `frontend/src/app/` | Authenticated app at `/app/*` (Home, Cases, Inbox, Tasks, Knowledge, Insights, Settings) |
| `frontend/src/lib/types.ts` | TypeScript mirror of the API contract |
| `frontend/src/mocks/case-ONB-005.json` | Contract-shaped `GET /api/cases/ONB-005` fixture (offsets verified by `backend/tests/test_mock_offsets.py`) |
| `data/seed.json` | Starter-pack cases and evidence, verbatim |
| `Dockerfile`, `docker-compose.yml`, `render.yaml` | Build and deploy |
| `.github/workflows/ci.yml` | pytest + frontend build on every push and PR |

## AI-assisted development files

This repo is built with Claude Code. These files steer the coding agent and document the product agent; they are
committed on purpose so reviewers can see how the work was specified.

| File | Purpose | Owner |
| --- | --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Project instructions for Claude Code: product scope, non-negotiable rules (evidence/derived/human write paths, tenancy, audit), stack, layout, API contract, domain rules | Team |
| [`AGENT_SPEC.md`](AGENT_SPEC.md) | Specification of the evidence-extraction agent: trigger, literal system prompt, output schema, validation, failure handling, evaluation fixtures | Humans only (agents propose changes in chat) |
| `PROMPTS.md` | Per-teammate prompts and owned paths for parallel agent sessions | Team |
| `.claude/settings.json` | Shared Claude Code project settings (if present) | Team |

Not committed (see `.gitignore`): `.claude/settings.local.json`, `.claude/worktrees/`, `CLAUDE.local.md`, `.env*`
(except `.env.example`), virtualenvs, `node_modules`, build output, local SQLite files.

## Roadmap (Planned)

Nothing below appears in the app's navigation.

- OIDC single sign-on (`AUTH_MODE=oidc`); today only demo login exists.
- Self-serve signup (`POST /signup`) creating a new org with sample data.
- Email / Teams webhook ingestion into the Inbox (today: paste).
- Source correction UI (new versions are already supported by the model and the link flow).
