# Graft — Onboarding & Knowledge-Transfer Readiness

Team K · Engineering Albania Student Hackathon 2026.

A multi-tenant SaaS where a PMO tracks onboarding and knowledge transfer across projects, answering one question:
**what evidence shows an employee can actually work independently, and who acts next?**
AI extracts cited claims from evidence, rules flag conflicts, and people (coordinator, technical owner) decide.
Every case names its stakeholders (line manager, project manager, technical lead, training responsible, HR business
partner, access responsible), so ownership is visible and gaps are actionable.

**Live:** https://graft-560i.onrender.com (sign in at [/login](https://graft-560i.onrender.com/login) with any demo account).

All data is fictional (starter pack). Every navigation item works on the seeded data.

## Walkthrough (Eva Stone, ONB-005)

1. Open `/login`, sign in as **Elira Dervishi (PMO Coordinator)**. Home and Cases show 6 cases needing attention.
2. Open **ONB-005 Eva Stone**. The tracker says *Ready with Support*; the Evidence pill says *Conflicting reports*:
   the Line Manager (E4) reports closure while the Technical Lead (E3) reports occasional support and two uncovered
   complex scenarios, same day. Every claim links to its exact span in the original; one invented candidate is shown
   as rejected by the verifier.
3. **Assign** the flag to Ardit Kola (technical owner) with a due date. The coordinator cannot record a review (403).
4. Switch account to **Ardit Kola**, open ONB-005, **Record technical review** → *Keep open*, scope *Overall onboarding*,
   linked to the task. Refresh: everything is there. Coordinator → **Analyze evidence** twice: task and review unchanged.

### Roles and stakeholders

A person can hold several roles, each granted at **organization**, **project** or **case** scope. Roles decide what
you may do; **responsibilities** say who is accountable on a specific case; **AI preferences** only change how the
assistant presents things. The three are stored and enforced separately (`services/permissions.py`).

| Role (code) | Sees | Can do |
| --- | --- | --- |
| Organization Admin (`org_admin`) | Everything in the org | Settings, people and role grants, demo reset. Not a technical reviewer unless also assigned |
| PMO Coordinator (`pmo_coordinator`) | Every case | Assign responsibilities and follow-ups, analyze evidence, run the case agent, AI guidance |
| Project Manager / Additional Manager (`project_manager`) | Cases in their projects | Project team, responsibilities and follow-ups inside their projects |
| Line Manager (`line_manager`) | Their direct reports | Follow-ups for their reports |
| Technical Lead / Technical Owner (`technical_owner`) | Their projects' or assigned cases | **The readiness review**, when they are the case's primary technical owner |
| Training Responsible (`training_responsible`) | Assigned cases | Training & KT log (plan, session, observation). Never signs off readiness |
| HR Business Partner (`hr_business_partner`) | Their employee cohort, summary only | HR follow-ups; no technical assessment notes |
| Access Responsible (`access_responsible`) | Access items on assigned cases/systems | Move access through requested → approved → active; cannot confirm usability or review |
| Project Member (`project_member`) | Project cases, summary only | Their own tasks |
| Employee (`employee`) | Their own case | Their tasks; confirm their own access works |
| Management Viewer (`management_viewer`) / Auditor (`auditor`) | Summaries (auditor: full audit trail) | Nothing: read-only |

Projects carry **defaults** (e.g. Ardit Kola is Orion's technical owner and training responsible); a case inherits
them unless a coordinator records a **case-level override**, which never changes the project or other cases. Required
responsibilities nobody holds are shown as **ownership gaps**; Graft never fills them silently.

Demo accounts (fictional, no passwords):

| Person | Roles and scope |
| --- | --- |
| Dren Basha | Organization Admin |
| Elira Dervishi | PMO Coordinator |
| Klea Hoxha | Project Manager · Orion, Atlas (client contact) |
| Ardit Kola | Technical Owner · Orion, Aurora, Atlas; Training Responsible · Orion; training override on ONB-001 |
| Nadia Ferri | Technical Owner · Nimbus, Helios, Nova, Pulse, Vega |
| Besa Leka | Training Responsible · Aurora, Nimbus |
| Luca Gray | Line Manager of Eva (ONB-005); Project Member · Orion |
| Teuta Gjoni | HR Business Partner for ONB-002 and ONB-005 |
| Gent Morina | Access Responsible for Leo's systems (ONB-002) |
| Erion Daci | Project Member · Orion |
| Eva Stone, Leo Marin | Employees (ONB-005, ONB-002) |
| Mira Shehu | Management Viewer (read-only) |
| Ilir Prifti | Auditor (read-only, full audit trail) |
| Sam Rivera | Admin of a second tenant, *Sandbox Co*, used to show tenant isolation |

Try: sign in as **Gent Morina** and open ONB-002 (access view only, can approve but not confirm usability); as **Teuta
Gjoni** (summary, no review rationale); as **Klea Hoxha** → Projects → Orion → Team; as **Dren Basha** → Settings →
People & Roles; as **Ardit Kola** switch the working context in the user menu and watch Home and Ask Graft re-focus
without any change in what he can do.

### AI modes
- **Live AI**: `GROQ_API_KEY` set and AI enabled in Settings. One Groq call per source (`openai/gpt-oss-120b`,
  strict JSON-schema structured output against `ai/schemas/extract_v2.json`, which only allows valid scope/value pairs),
  20 s timeout, max 2 attempts. The verifier still checks every quote against the original body.
- **Verified cache**: identical input (source, body hash, prompt, schema, model) already extracted → reused, never duplicated.
- **Recorded example**: E1–E4 ship with the expected extractions from `AGENT_SPEC.md` (`backend/app/ai/cache/replay/`),
  bound to each body's SHA-256 and replayed through the same verifier. Used for the seed so results are deterministic
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
Render → **New → Blueprint** → select this repo → set `GROQ_API_KEY` when prompted (optional; the app runs
without AI). Health check: `/api/health`. Migrations run on container start (`alembic upgrade head`).

## Architecture (one image, one origin)

```
Browser ──► FastAPI (uvicorn)
            ├── /api/*   JSON API (routers in backend/app/api)
            └── /*       built React SPA (frontend/dist) with index.html fallback
            └── SQLAlchemy 2.0 ──► Postgres (prod) / SQLite (dev, tests)
            └── backend/app/ai ──► Groq (only place the LLM is called)
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

## Roadmap (Day 1, to the 22:00 cutoff)

Hand-in requirements (starter pack §9 and §12): repository, setup instructions and specification by 22:00; a pull
request with the technical judge and our mentor requested as reviewers; the submission email to both organisers.
Commits after 22:00 do not count.

### Team and ownership

Each person works on their own `feat/<area>` branch, commits at least every 30 minutes under their own git identity,
stays inside their paths, and merges through small PRs into `main`. Blevis merges.

| Member | Area | Owns these paths |
| --- | --- | --- |
| **Blevis Allushi** · platform, delivery, specification | Deploy, merging, hardening, Business Owner checkpoint, business rules, `AGENT_SPEC.md`, architecture doc, final PR | `backend/app/api/` (except `agents.py`, `ask.py`), `backend/app/services/`, `backend/app/models/` (except `agent.py`), `Dockerfile`, `render.yaml`, `.github/`, `AGENT_SPEC.md`, `docs/business-rules.md`, `docs/architecture.md`, `backend/eval/fixtures/` |
| **Vigen Myrtolli** · AI and agents | Live Groq runs, the case agent (loop, tools, tables, endpoints), Ask Graft, eval harness and measured results | `backend/app/ai/`, `backend/app/models/agent.py`, `backend/app/api/agents.py`, `backend/app/api/ask.py`, the agent migration, `backend/eval/` (except `fixtures/`), `docs/eval.md`, `backend/tests/test_agent*.py`, `backend/tests/test_ask*.py` |
| **Mateos Sharka** · agent UI | Agent panel and Ask Graft on the case page and Home | `frontend/src/app/cases/agent/`, `frontend/src/app/ask/`, agent/ask hooks and types in `frontend/src/lib/` |
| **Klea Mehmeti** · product UI | Role-specific views, case and inbox polish, readiness date and role fields in the UI, layout and empty states | `frontend/src/app/` (except `cases/agent/` and `ask/`), `frontend/src/site/`, `frontend/src/components/` |

Shared files (`frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`, `backend/app/main.py`, `backend/app/api/__init__.py`):
append only, in small commits, and say so in the team chat.

### AI capabilities

One rule throughout: **AI proposes, people decide.** Every AI output shows its mode, model, prompt version and
citations, and every agent run is stored with its full trace.

| Capability | What it does | Triggered by | May write |
| --- | --- | --- | --- |
| **Evidence extraction** (built) | Reads one source and returns schema-matched claims; the verifier keeps only exact quotes. | Analyze, inbox ingest, seed | `analysis_runs`, `claims`, `rejected_candidates` |
| **Case agent** (P0) | A bounded tool-calling loop over one case: reads findings, sources, claims, tasks and access items, then returns a short assessment and 1–3 proposals (a task with owner, due date and citations; a drafted follow-up message; an access chase). | Coordinator, "Run agent" on a case | `agent_runs`, `agent_steps`, `agent_proposals` |
| **Ask Graft** (built) | Questions about a case or the portfolio, answered only from data the asking user may see, every statement cited, refusal when nothing supports an answer. Never decides readiness; points to the technical owner. Role profile, personal focus/detail/format and versioned PMO guidance shape presentation only, after permission filtering. | Any signed-in user | Nothing |
| **Inbox triage agent** (stretch) | On new evidence: find the case, analyze it, summarise what changed, propose follow-ups. Ambiguous matches become a proposed link. | Inbox "Add evidence" | Derived tables and proposals |

**Agent design**
- **Model:** Groq `openai/gpt-oss-120b` with tool calling. Structured outputs and tool use cannot be combined on Groq, so
  the final answer is a `submit_proposals` tool call whose arguments are validated against a JSON schema server-side.
- **Tools (read-only):** `get_case`, `list_findings`, `read_source`, `list_claims`, `list_tasks`, `list_access_items`,
  `list_knowledge`, `get_settings`. Each runs as the requesting user through `load_case` / `visible_cases`, so the agent
  never sees more than its user.
- **Output:** `submit_proposals(assessment, proposals[])`. Every proposal must cite claim or source ids that exist on the
  case; anything else is dropped and logged.
- **Limits:** at most 8 tool calls and 60 s per run, one run at a time per case. `ai_enabled=false` or no key →
  "Agent unavailable"; manual work is unaffected.
- **Human handoff:** Accept opens the normal task form pre-filled (origin `ai_suggested_edited`); Dismiss records a reason.
  `backend/app/ai/` has no import path to task or review writers, and a test enforces it.
- **Prompt injection:** source bodies are data inside tool results, never instructions.
- **Audit:** every run, proposal, accept and dismiss is an `AuditEvent`.
- **Data class:** AI proposals sit between derived and human data: never authoritative, stale once the evidence hash they
  were based on changes.

**API contract** (Vigen builds, Mateos consumes; agree before 15:00, then do not change it without telling both):
- `POST /api/cases/{id}/agent-runs` → `{id, case_id, status, assessment, proposals[], steps[], model, prompt_version, created_at}`
  - `status`: `completed | failed | unavailable`
  - proposal: `{id, kind: task|message|access_followup, title, body, owner_role, owner_user_id, due_date, cited_source_ids[], cited_claim_ids[], status: open|accepted|dismissed, dismiss_reason}`
  - step: `{index, tool, arguments, result_summary, duration_ms}`
- `GET /api/cases/{id}/agent-runs` → past runs, newest first, same shape
- `POST /api/agent-proposals/{id}/dismiss {reason}` → the proposal
- Accepting: the normal `POST /api/cases/{id}/tasks` with `origin: "ai_suggested_edited"` and `proposal_id`; the proposal
  becomes `accepted`
- `POST /api/ask {question, case_id?, focus?, detail?, format?}` → `{answer, citations[{source_id, claim_id, quote}], refused, mode, model, prompt_version, presentation}`

**Roles and ownership API**
- `GET /api/org/members` · `POST /api/org/members` · `PATCH /api/org/members/{user_id} {status}`
- `GET /api/org/roles` · `PATCH /api/org/roles/labels` · `GET|POST /api/org/role-assignments` · `PATCH|DELETE /api/org/role-assignments/{id}`
- `GET /api/projects` · `GET /api/projects/{id}` · `GET|POST /api/projects/{id}/assignments` · `PATCH|DELETE /api/projects/{id}/assignments/{aid}`
- `GET|POST /api/cases/{id}/responsibilities` · `PATCH|DELETE /api/cases/{id}/responsibilities/{aid}` · `GET|POST /api/cases/{id}/training`
- `GET|PATCH /api/me/preferences` · `GET|PATCH /api/settings/ai-guidance` · `GET /api/home?context=`

### Phase 0 · 14:00–14:30 · Kick-off
- [ ] **Blevis:** book the Business Owner checkpoint (only 14:00–16:00 slots remain); commit `AGENT_SPEC.md` unchanged;
      confirm GitHub Actions is green.
- [ ] **Vigen:** create a Groq API key, keep it in your local `.env` only, share it privately for Render.
- [ ] **Vigen + Mateos:** confirm the API contract above.
- [ ] **Everyone:** pull `main`, run the app with `docker compose up --build`, sign in as each role once.

### Phase 1 · 14:30–16:30 · Go live, ask the business, agent skeleton
- [x] **Blevis:** recreate the Render Blueprint (`graft` + `graft-db`), set `GROQ_API_KEY`, Starter plan. Walk the Eva path on
      the live URL as coordinator, technical owner and employee.
- [ ] **Blevis:** run the checkpoint and write the answers into `docs/business-rules.md`. Questions:
  1. Is "closure reported on the same day as a scoped qualification from another sender" the right conflict trigger?
  2. Who validates readiness: the Technical Lead, the KT Owner, or both? Can a line manager ever close onboarding?
  3. Are 3 working days (unanswered request) and 7 days (stale tracker) the right thresholds?
  4. Does "Active" access ever count as done without the employee's own successful test? (We assume never.)
  5. Who sets the expected readiness date, and should a missing date be flagged?
  6. Which next actions would you trust an AI agent to propose? Should it ever draft messages to people?
- [ ] **Vigen:** live extraction on E1–E8, keep the raw responses, confirm live E3/E4 still raise the closure conflict.
- [ ] **Vigen:** agent tables + migration, the loop in `backend/app/ai/agent.py`, the endpoints; tested with a stubbed Groq client.
- [ ] **Mateos:** Agent panel against a mocked response matching the contract.
- [ ] **Klea:** employee and line-manager experience (Home, case page, access confirmation), empty states.

### Phase 2 · 16:30–19:00 · Make it real
- [ ] **Vigen:** agent end to end on Eva, Leo and Lina; then Ask Graft.
- [ ] **Mateos:** switch the Agent panel to the real API; build the Ask Graft box on the case page and Home.
- [ ] **Blevis:** apply the checkpoint answers in `services/rules.py` and Settings; add **expected readiness date** and
      **exact role** to cases (API + migration), with a `MISSING_READINESS_DATE` finding if confirmed; production hardening
      (`SESSION_SECRET` required when `DEMO_MODE=false`, `Secure` cookie behind HTTPS).
- [ ] **Klea:** readiness date and role in the case header, edit form for the coordinator, checklist items wired to them.
- [ ] **Blevis:** rewrite `AGENT_SPEC.md` to match the code: one section per AI capability (inputs, tools, outputs, limits,
      human checkpoint, failure modes), the rules engine and the matcher; expected outcome for every eval fixture in
      `backend/eval/fixtures/`.
- [ ] **Vigen:** eval harness `backend/eval/run_eval.py` over those fixtures; writes `docs/eval.md`.

### Phase 3 · 19:00–20:15 · Evidence and documents · **feature freeze at 20:15**
- [ ] **Vigen:** commit a measured eval run (raw JSON + `docs/eval.md`), including at least one failure.
- [ ] **Blevis:** `docs/architecture.md`; measured numbers into `AGENT_SPEC.md`; merge all branches, run tests and build,
      redeploy, walk the Eva path on production as each role.
- [ ] **Mateos + Klea:** full click-through of every page as every role on the live URL; fix what breaks.
- [ ] Stretch, only if everything above is green: inbox triage agent; signup page; org switcher.

### Phase 4 · 20:15–21:45 · Hand-in
- [ ] Bug fixes only.
- [ ] **Blevis:** open the submission pull request, request reviews from the technical judge and our mentor (starter pack §12),
      check they have repo access; final README check from a clean clone with the live URL listed.
- [ ] **Everyone:** last commit pushed by **21:45**.

### Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Groq is down or rate-limited | Extraction falls back to the verified cache and recorded examples; stored agent runs remain viewable. |
| Agent work runs late | Cut order: triage agent → Ask Graft → agent on Leo/Lina. Minimum: the Eva agent run, the panel, the spec section. |
| Render outage | Local `docker compose up`. |
| The Business Owner contradicts one of our rules | Thresholds are org settings; each rule is one function in `services/rules.py`, covered by tests. |
| Merge conflicts late in the day | Separate owned paths, small PRs, one merger, freeze at 20:15. |
| A secret lands in git | Keys live only in `.env` and Render; `.env*` and `DO_NOT_COMMIT/` are gitignored. Rotate the key if it leaks. |

### Done so far
- [x] Scaffold, Docker, Render Blueprint, CI workflow.
- [x] Data layer and a seed from the verbatim starter-pack data (checked against the organiser extraction): 10 cases, 8 sources.
- [x] Gap rules: closure conflict, access not confirmed, unanswered request, stale tracker, missing fields.
- [x] Trust layer: strict-schema Groq extraction, exact-quote verifier, verified cache, recorded examples, unavailable mode.
- [x] AI task drafting (`suggest-task`), labelled "AI suggestion · not saved", saved only by a human.
- [x] Eva path end to end (the coordinator assigns, the technical owner reviews; survives refresh and re-analysis).
- [x] Per-role visibility: employees see their own case, line managers their reports, technical owners their projects,
      anyone the case behind a task assigned to them; hidden cases are 404 everywhere.
- [x] Every nav page works on seeded data; audit trail; notifications; demo reset.
- [x] 24 backend tests: Eva path, tenancy, visibility per role, role checks, verifier, Groq client.
- [x] PMO interview role model: 12 canonical roles with org/project/case-scoped grants, case responsibilities with
      project defaults and overrides, ownership gaps, field-level view levels, People & Roles, project teams, the
      Stakeholders panel, training log, role-aware Home, Ask Graft page with focus/detail/format, versioned PMO AI
      guidance. 88 backend tests (31 role and AI-boundary acceptance tests).

## Planned after the hackathon

Nothing below appears in the app's navigation.

- OIDC single sign-on (`AUTH_MODE=oidc`); today only demo login exists. Email invitations for new members (today an
  admin adds a demo member, no email is sent).
- Delegated technical sign-off and delegated user administration for the PMO (decisions A4 and A7 in
  `docs/business-rules.md`).
- Reusable lessons learned across cases (approved, generalised; never another employee's record).
- Email / Teams webhook ingestion into the Inbox (today: paste).
- Source correction UI (new versions are already supported by the model and the link flow).
- Signup, the org switcher and the inbox triage agent, if they miss the 20:15 freeze.
