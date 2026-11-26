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
- **Live AI**: `GROQ_API_KEY` set and AI enabled in Settings. One Groq call per source (`openai/gpt-oss-120b`,
  strict JSON-schema structured output, so the response always matches `ai/schemas/extract_v1.json`),
  20 s timeout, max 2 attempts. The verifier still checks every quote against the original body.
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

## Roadmap to winning (Day 1, 14:00 → 22:00 cutoff; demo Day 2, 10:00)

### The pitch in one line
Graft is an onboarding-readiness platform where **an AI agent does the legwork and people make the decisions**:
the LLM reads every email and cites what it says, the rules flag conflicts, the agent investigates a case and proposes
the next actions with evidence, and the coordinator and technical owner approve, edit or reject each one.

### What wins, by judging weight

| Weight | Criterion | What the judges must see | Status at 14:00 |
| --- | --- | --- | --- |
| 40% | Usable, production-ready | A live URL. Eva's case works end to end for every role. Login, roles, tenancy and audit hold up. Nothing hollow. | Eva path works in Docker. Per-role visibility done. **Missing:** live deploy, a real Groq run, the agent, signup, org switcher. |
| 25% | Agent specification | `AGENT_SPEC.md` in the repo describing **every** agent (extraction, case agent, Ask Graft, triage) as built: inputs, tools, outputs, limits, human checkpoints, failure modes, measured results. | Only the extraction agent is specified, outside the repo, "not measured". |
| 15% | Use of LLMs | AI where it adds value with visible human checks: cited claims, rejected candidates, an agent trace the user can inspect, proposals that need approval, an eval with real numbers. | Extraction + verifier + task drafting are built and tested with a stub. **Missing:** a real Groq run, the agent, the eval. |
| 15% | Architecture | One-image deploy, CI green, four write paths with tests that enforce them, a short architecture doc. | 24 tests in. **Missing:** `docs/architecture.md`, CI confirmed green on GitHub. |
| 5% | Presentation | A 9-minute live demo: Eva's conflict, the agent proposing the fix, the human deciding. Honest about what is simulated. | Not started. |

Hand-in (starter pack §9 and §12): repository, setup instructions and spec by 22:00; a **pull request** with the
technical judge and our mentor requested as reviewers; an email with the deck and repo link to both organisers.
Commits after 22:00 do not count, and the organisers read the commit history.

### The AI we are adding

Three AI capabilities, one rule: **AI proposes, people decide.** Every AI output shows its mode, model, prompt version
and citations, and every agent run is stored with its full trace.

| Capability | What it does | Who triggers it | What it may write |
| --- | --- | --- | --- |
| **1. Evidence extraction** (LLM, built) | Reads one source, returns schema-matched claims; the verifier keeps only exact quotes. | Analyze button, inbox ingest, seed | Derived tables only (`analysis_runs`, `claims`) |
| **2. Case agent** (agentic, new, P0) | "Investigate this case": a bounded tool-calling loop over the case. It reads findings, sources, claims, tasks and access items, then returns a short assessment and 1–3 **proposals**: a task (owner, due date, cited claims), a drafted follow-up message (e.g. chasing Lina's unanswered request), or an access chase. | Coordinator, "Run agent" on a case | `agent_runs`, `agent_steps`, `agent_proposals` only |
| **3. Ask Graft** (LLM Q&A, new, P1) | A question box on the case and portfolio pages: "Why is Eva flagged?", "Which access is blocking Leo?". Answers only from data the asking user may see, with every statement cited; uncited answers are refused. It never answers "is X ready" with a decision; it points to the technical owner. | Any signed-in user | Nothing (read-only) |
| **4. Inbox triage agent** (agentic, new, P2 stretch) | On new evidence: find the case, analyze it, say what changed, propose follow-ups. Ambiguous matches become a proposed link, never an automatic one. | Inbox "Add evidence" | Derived tables + proposals |

**Agent design (applies to 2 and 4):**
- **Model:** Groq `openai/gpt-oss-120b` with tool calling. Structured outputs and tool use cannot be combined on Groq, so the
  agent's final answer is a `submit_proposals` tool call whose arguments are validated against a JSON schema server-side.
- **Tools (read-only):** `get_case`, `list_findings`, `read_source`, `list_claims`, `list_tasks`, `list_access_items`,
  `list_knowledge`, `get_settings`, `search_cases`. Each tool runs **as the requesting user**, through `load_case` /
  `visible_cases`, so the agent can never see more than its user.
- **Output tool:** `submit_proposals(assessment, proposals[])`. Each proposal must cite claim or source ids that exist on
  the case; uncited or invalid proposals are dropped and logged, like rejected claims.
- **Limits:** max 8 tool calls, 60 s wall clock, one run at a time per case, `ai_enabled=false` disables it,
  no key → "Agent unavailable" (manual work unaffected).
- **Human handoff:** proposals appear in an "Agent" panel with the trace (each tool call and result summary).
  **Accept** opens the normal task form pre-filled (origin `ai_suggested_edited`), **Dismiss** records why. The agent module has
  no import path to task or review writers; a test enforces it, like the extraction rule.
- **Prompt injection:** email bodies are passed as data inside tool results, never as instructions; the system prompt says so,
  and proposals that try to act outside the case are dropped.
- **Audit:** every run, proposal, accept and dismiss is an `AuditEvent`.
- **New data class:** *AI proposals* (`agent_runs`, `agent_steps`, `agent_proposals`) sit between derived and human data:
  recomputable, never authoritative, and they go stale when the evidence hash they were based on changes.

### Team split (4 people, separate paths, separate branches)

Fill in the names. Each person works on `feat/<area>` branches, commits at least every 30 minutes under their own git
identity, and merges through small PRs into `main`. A merges.

| Member | Area | Owns these paths |
| --- | --- | --- |
| **A · Platform & delivery** (lead): _name_ | Deploy, agent data model + API, security, integration, final PR | `backend/app/api/`, `backend/app/models/`, `backend/alembic/`, `backend/app/services/{tenancy,visibility}.py`, `Dockerfile`, `render.yaml`, `.github/` |
| **B · AI & agents**: _name_ | Groq runs, the agent loop and tools, Ask Graft, eval harness and measured results | `backend/app/ai/`, `backend/eval/`, `docs/eval.md` |
| **C · Spec & business**: _name_ | Business Owner checkpoint, `AGENT_SPEC.md` for all agents, eval expectations, business rules, architecture doc | `AGENT_SPEC.md`, `docs/business-rules.md`, `docs/architecture.md`, `backend/eval/fixtures/`, `backend/app/services/rules.py` (with A) |
| **D · Product UI & demo**: _name_ | Agent panel, Ask Graft box, role-specific polish, demo script, deck, backup recording | `frontend/src/`, `docs/demo-script.md`, the presentation |

API contract for the new pieces (A builds, B fills, D consumes), agreed before 15:00:
- `POST /api/cases/{id}/agent-runs` → starts a run, returns `{run_id, status, assessment, proposals[], steps[]}`
- `GET /api/cases/{id}/agent-runs` → past runs with their traces
- `POST /api/agent-proposals/{id}/dismiss {reason}` · accepting = the normal `POST /cases/{id}/tasks` with `proposal_id`
- `POST /api/ask {question, case_id?}` → `{answer, citations[{source_id, claim_id?, quote}], mode, model}`

### Phase 0 · 14:00–14:30 · Kick-off (everyone)
- [ ] Fill in the names above. Create `PROMPTS.md` with each person's owned paths and agent prompt.
- [ ] **C: book the Business Owner checkpoint now.** Only 14:00–16:00 slots remain, and each team gets one meeting.
- [ ] **A:** commit `AGENT_SPEC.md` to the repo root unchanged. C edits it from then on.
- [ ] **B:** create a Groq API key. Share it privately (never in git or chat) and put it in your local `.env`.
- [ ] **A + B + D:** agree the agent and Ask API shapes above (15 minutes, write them into `PROMPTS.md`).
- [ ] **A:** confirm GitHub Actions is green on `main`.

### Phase 1 · 14:30–16:30 · Go live, ask the business, agent skeleton
- [ ] **A:** delete the old Render resources and create the Blueprint again (`graft` + `graft-db`). Set `GROQ_API_KEY`.
      Starter plan so it does not sleep. Walk the Eva path on the live URL as coordinator, technical owner and employee.
- [ ] **A:** migration + models for `agent_runs`, `agent_steps`, `agent_proposals`; the endpoints above returning stored
      runs; audit events; tenancy + visibility tests for them.
- [ ] **B:** run live extraction on E1–E8 and keep the raw responses. Confirm live E3/E4 still raise the closure conflict.
- [ ] **B:** the agent loop in `backend/app/ai/agent.py`: tool definitions, the read-only tool implementations (calling
      existing services as the user), the 8-step / 60 s limits, `submit_proposals` validation. Test it with a stubbed
      Groq client first (as in `tests/test_groq_client.py`).
- [ ] **C:** run the checkpoint and write the answers into `docs/business-rules.md`. Questions to ask:
  1. Is "closure reported on the same day as a scoped qualification from another sender" the right conflict trigger?
  2. Who validates readiness: the Technical Lead, the KT Owner, or both? Can a line manager ever close onboarding?
  3. Are 3 working days (unanswered request) and 7 days (stale tracker) the right thresholds?
  4. Does "Active" access ever count as done without the employee's own successful test? (We assume never.)
  5. Who sets the expected readiness date, and should a missing date be flagged?
  6. Which next actions would you trust an AI agent to *propose*? Should it ever draft messages to people?
- [ ] **D:** the Agent panel on the case Overview: "Run agent" button, assessment, proposal cards (owner, due date,
      citations that jump to the Evidence tab), Accept → pre-filled task dialog, Dismiss with a reason, and an expandable
      trace. Build against a mocked response until A and B land.

### Phase 2 · 16:30–19:00 · Make it real
- [ ] **B + A:** wire the agent end to end on Eva, Leo and Lina. Target outputs: Eva → "Plan coverage of the two complex
      scenarios" for Ardit; Leo → chase Orion Portal approval and Helix provisioning, ask Leo to test Nova VPN;
      Lina → chase the Technical Manager's reply (drafted message, cites E5).
- [ ] **B:** Ask Graft (`POST /api/ask`): retrieval from the visible case data, an answer with citations, citation check
      (the cited quote must exist), refusal when nothing supports an answer.
- [ ] **D:** Ask Graft box on the case page and Home; citations open the source.
- [ ] **A + C:** apply the checkpoint answers in `services/rules.py` and Settings. Add **expected readiness date** and
      **exact role** to cases, with a `MISSING_READINESS_DATE` finding if the Business Owner confirms it.
- [ ] **A:** production hardening: refuse to start without a real `SESSION_SECRET` when `DEMO_MODE=false`; `Secure` cookie
      behind HTTPS.
- [ ] **C:** rewrite `AGENT_SPEC.md` to match the code: one section per AI capability (inputs, tools, outputs, limits, human
      checkpoint, failure modes), plus the rules engine and the matcher. Write the expected outcome for every eval fixture.
- [ ] **B:** eval harness `backend/eval/run_eval.py`: AGENT_SPEC §6 extraction fixtures, plus agent fixtures (Eva, Leo,
      Lina: did it propose the right action, cite real evidence, stay inside the case?) and Ask fixtures (cited, correct,
      refuses readiness decisions). Writes `docs/eval.md` with per-fixture results and run mode.

### Phase 3 · 19:00–20:15 · Evidence and documents · **feature freeze at 20:15**
- [ ] **B:** commit the measured eval run (raw JSON + `docs/eval.md`), including at least one failure and what it taught us.
- [ ] **C:** `docs/architecture.md`: diagram, the four write paths, the trust layer, the agent loop and its limits,
      tenancy and visibility, the deploy model. Put the measured numbers into `AGENT_SPEC.md`.
- [ ] **D:** `docs/demo-script.md` and a backup screen recording of the full demo from the live URL.
- [ ] **A:** merge every branch, run tests and build, redeploy, and walk the Eva path on production as each role.
- [ ] Stretch, only if everything above is green: the inbox triage agent; signup page; org switcher.

### Phase 4 · 20:15–21:45 · Hand-in
- [ ] Bug fixes only.
- [ ] **A:** open the submission pull request, request reviews from the technical judge and our mentor (handles are in the
      starter pack §12), make sure both have repo access.
- [ ] **C:** final README check: setup works from a clean clone, live URL listed, "what is simulated" stated.
- [ ] **D + C:** email the deck and the repo link to both organisers (addresses in the starter pack §12).
- [ ] **Everyone:** last commit pushed by **21:45**. The buffer until 22:00 is for anything that goes wrong.

### Day 2 · before 10:00 · Demo
- [ ] Two full rehearsals against a timer (9 minutes, strict). Open the live URL 10 minutes before the slot. Keep the local
      Docker stack as a fallback and the recording as a last resort.
- [ ] Demo plan (D owns it; everyone knows it):
  1. **0:00–1:00** The problem: trackers say "Ready", the evidence disagrees, nobody owns the next step.
  2. **1:00–3:00** Eva as the coordinator: tracker / evidence / review pills → cited claims → the rejected invented quote →
     the closure conflict.
  3. **3:00–4:30** **Run the agent** on Eva: watch the trace, read its assessment, accept its proposal, edit the due date,
     save. Ask Graft "Is Eva ready?" and show it answers with evidence and defers the decision to the technical owner.
  4. **4:30–5:45** Switch to the technical owner: record a scoped *Keep open* review. Refresh. Re-analyse. Nothing changes.
  5. **5:45–6:45** Leo signs in: he sees only his case, and only his own test makes access "usable".
  6. **6:45–8:15** How it is built: four write paths, verifier, agent limits, visibility, the eval numbers (including a failure).
  7. **8:15–9:00** What is simulated, the limitations, the next improvement.

### Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Groq is down or rate-limited during the demo | Extraction falls back to the verified cache and recorded examples. Store one real agent run on Eva beforehand and show it from history, labelled as a stored run. |
| The agent proposes something wrong live | That is the point of the human checkpoint: dismiss it with a reason on stage. Rehearse with real runs to know its behaviour. |
| Agent work runs late | Cut order: triage agent → Ask Graft → agent on Leo/Lina. The Eva agent run, the panel and the spec section are the minimum. |
| Render cold start or outage | Starter plan (no sleep); local `docker compose up` as backup; the screen recording as a last resort. |
| The Business Owner contradicts one of our rules | Thresholds are org settings; each rule is one function in `services/rules.py`, covered by tests. |
| Merge conflicts late in the day | Separate owned paths, small PRs, A merges, freeze at 20:15. |
| A secret lands in git | Keys live only in `.env` and Render; `.env*` and `DO_NOT_COMMIT/` are gitignored. Rotate the key if it leaks. |

### Done so far
- [x] Scaffold, Docker, Render Blueprint, CI workflow.
- [x] Data layer and a seed from the verbatim starter-pack data (checked against the organiser extraction): 10 cases, 8 sources.
- [x] Gap rules: closure conflict, access not confirmed, unanswered request, stale tracker, missing fields.
- [x] Trust layer: strict-schema Groq extraction, exact-quote verifier, verified cache, recorded examples, unavailable mode.
- [x] AI task drafting (`suggest-task`), labelled "AI suggestion · not saved", saved only by a human.
- [x] Eva path end to end in the UI (the coordinator assigns, the technical owner reviews; survives refresh and re-analysis).
- [x] Per-role visibility: employees see their own case, line managers their reports, technical owners their projects,
      anyone the case behind a task assigned to them; hidden cases are 404 everywhere (lists, inbox, insights, search).
- [x] Every nav page works on seeded data; audit trail; notifications; demo reset.
- [x] 24 backend tests: Eva path, tenancy, visibility per role, role checks, verifier, Groq client.

## Planned after the hackathon

Nothing below appears in the app's navigation.

- OIDC single sign-on (`AUTH_MODE=oidc`); today only demo login exists.
- Email / Teams webhook ingestion into the Inbox (today: paste).
- Source correction UI (new versions are already supported by the model and the link flow).
- Signup, the org switcher and the inbox triage agent, if they miss the 20:15 freeze.
