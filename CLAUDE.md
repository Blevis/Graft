# Graft — Onboarding & Knowledge-Transfer Readiness Platform (SaaS)

Team K · Engineering Albania Student Hackathon 2026 · hard deadline 22:00 Day 1 (later commits don't count).

## What we are building
A deployable, multi-tenant SaaS where a company's PMO tracks onboarding and knowledge transfer across projects.
Model it on how CRM/support platforms work: Salesforce (orgs, record pages, approvals, audit trail),
HubSpot (activity timeline, pipelines, tasks, workflows), Intercom (shared inbox, assignment, SLAs, AI agent with human handoff).

It answers one business question: **what evidence shows an employee can actually work independently, and who acts next?**

The hero workflow, which must work perfectly, is Eva Stone (ONB-005). Her tracker says Ready with Support; on the same day the
line manager says onboarding is closed and the technical lead says two complex scenarios are still uncovered. The AI extracts
cited claims, the rules flag the conflict, the coordinator assigns a follow-up, and the assigned technical owner records a
scoped Keep-open review. Everything survives a refresh and re-analysis. Everything else in the platform exists to make this
credible as a product.

Judging: 40% usable production-ready solution · 25% agent spec (AGENT_SPEC.md) · 15% LLM use · 15% architecture · 5% demo.

## Non-negotiable rules
1. **No hollow modules.** A nav item or button exists only if it works on seeded data. Planned features go on the roadmap
   in README / the Integrations page, clearly labelled "Planned". Never use a dead link or a fake "coming soon" spinner.
2. **AI proposes, people decide.** Three data classes, three write paths:
   - Evidence (`sources`): immutable and versioned. Never UPDATE a source; a correction is a new version row.
   - Derived (`analysis_runs`, `claims`, `findings`): recomputable. AI/rules code has NO import path to task/review writers.
   - Human (`tasks`, `reviews`): written only by their API routes, append-only for reviews.
   - AI proposals (`agent_runs`, `agent_steps`, `agent_proposals`): written only by the agent; never authoritative.
     A proposal becomes a task only when a human accepts it through the normal task route.
   Re-analysis must never change, duplicate or delete a task or review (a test enforces this).
7. **Visibility by role and scope** (`services/visibility.py`, `services/permissions.py`): org admin, PMO, management
   viewer and auditor (org scope) see every case; project-scoped grants show that project's cases; case grants and
   case responsibilities show that case; employees their own case; anyone the case behind a task assigned to them.
   Each visible case has a view level (full / employee / summary / access_only) that shapes the payload server-side.
   Every case read goes through `load_case` / `visible_cases`; a hidden case is 404, exactly like another org.
   Routers never compare role names: they ask `Policy(db, ctx)`.
8. **Roles ≠ responsibilities ≠ AI preferences.** `role_assignments` (canonical code at org/project/case scope; many
   per person), `case_responsibilities` (who is accountable on one case; project defaults inherited, case overrides
   never mutate the project), `user_preferences` / `ai_guidance_versions` (presentation only, never read by an
   authorization check). Nobody grants themselves a role; the last org admin cannot be removed.
3. **Tenancy everywhere.** Every tenant table has `org_id NOT NULL`. All reads/writes go through `scoped(db, ctx)` helpers
   that filter by `ctx.org_id`. Cross-org access returns 404 (not 403). A test enforces it.
4. **Authorization is server-side.** Role comes from the session, never the request body.
5. **Every write emits an AuditEvent** in the same transaction (actor, org, entity, action, before/after JSON).
6. **No real data, no credentials.** Fictional data only. We store no passwords (demo login now, OIDC SSO in prod).
   No API keys in git; `.env.example` has empty values.

## Stack
- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0 + Alembic, Pydantic v2, PyJWT. Postgres in production, SQLite for
  dev and tests (same models; avoid Postgres-only types).
- **Frontend:** React + Vite + TypeScript, React Router, TanStack Query, Tailwind + shadcn/ui, lucide-react. No chart library;
  use stat tiles and tables.
- **Delivery:** one Docker image. FastAPI serves the built SPA from `/` and the API under `/api`, single origin, no CORS.
  `docker-compose.yml` runs app + postgres. Deploy target: Render (or Railway/Fly) with managed Postgres. GitHub Actions runs
  pytest + frontend build on every PR.
- **LLM:** Groq (`GROQ_API_KEY`, `LLM_MODEL`, default `openai/gpt-oss-120b` with strict JSON-schema output), called only from `backend/app/ai/client.py`.

## Repository layout
```
backend/app/
  main.py            app factory, static SPA mount, routers
  config.py          env settings (DATABASE_URL, AUTH_MODE=demo|oidc, AS_OF_DATE, DEMO_MODE, LLM_*)
  db.py              engine/session; scoped() helpers
  models/            org, user, membership, project, case, source, analysis, claim, finding, task,
                     access_item, review, knowledge_ref, setting, audit_event, notification
  schemas/           pydantic request/response models (the API contract)
  api/               routers: auth, org, users, cases, timeline, inbox, tasks, reviews, access, knowledge,
                     insights, settings, audit, admin
  services/          tenancy.py, audit.py, rules.py (gap rules), matching.py (inbox→case), timeline.py
  ai/                prompts/extract_v1.txt, prompts/suggest_v1.txt, schemas/*.json, client.py, verifier.py, cache/
  seed/              seed.py (reads data/seed.json into org "Engineering Albania (demo)"; also a small "Sandbox Co" org)
backend/alembic/     migrations
backend/tests/       unit + acceptance (pytest)
frontend/src/
  site/              public website: Landing, Pricing, Login, Signup
  app/               AppShell (sidebar, top bar with org switcher, notifications, user menu) + modules:
                     home/ cases/ inbox/ tasks/ knowledge/ insights/ settings/
  components/ui/     shadcn components
  lib/api.ts         typed fetch client + TanStack Query hooks
data/seed.json       verbatim starter-pack data. Never edit its text.
docs/                business-rules.md (stakeholder answers), architecture.md, eval.md, demo-script.md
AGENT_SPEC.md        human-owned. Propose changes in chat; a human commits them.
```

## Domain model
- **Organization** (tenant) → **Membership**(user, role) → **User**
- **Membership**(org, user, status active|suspended) — no role column. **RoleAssignment**(user, role_code, scope_type
  organization|project|case, scope_id, default_for_cases, valid_from/until, is_active, revoked_*).
- Canonical roles (`services/roles.py`; labels configurable per org, codes never): `org_admin`, `pmo_coordinator`,
  `project_manager`, `line_manager`, `technical_owner`, `training_responsible`, `hr_business_partner`,
  `access_responsible`, `project_member`, `employee`, `management_viewer`, `auditor`. Legacy `admin` → `org_admin`,
  `viewer` → `management_viewer` (accepted on input).
- **CaseResponsibility**(case, user, responsibility_type, access_item_id?, is_primary, source case_override|manual|migrated,
  assigned_by/at, is_active, ended_*). The primary technical owner (assigned or inherited) is the only readiness reviewer.
- **TrainingEntry**(case, kind plan|session|observation, title, notes, capacity) — append-only, never changes the stage.
- **Project**(name, code) · **EmployeeCase**(employee name, movement, start, project?, manager_name? (tracker),
  tracker_status, tracker_updated_at, stage). Owners come from responsibilities, not case columns.
  `stage` is derived from the latest review, never from the tracker: pre_onboarding → access → shadowing →
  supported_execution → independent_execution → validated.
- **Source**(kind email|update|tracker_note|tracker_row, case_id?, project_id?, author_role, recipient_role, date,
  body, body_sha256, version, supersedes_id?, ingested_via seed|paste|upload|webhook)
- **AnalysisRun**(source_id, body_sha256, prompt_version, model, mode live|cached|replay|unavailable, status) ·
  **Claim**(scope, value, reference, quote, start, end) · **RejectedCandidate**(raw, reason)
- **Finding**(rule_id, severity, message, evidence refs). Recomputed; holds no human state.
- **Task**(case_id, finding_id?, title, owner_user_id or owner_role, due_date, sla_hours, status open|done,
  cited_source_ids, origin manual|ai_suggested_edited|automation)
- **AccessItem**(case_id, system, state requested|approved|active|confirmed_usable|not_provisioned|awaiting_approval,
  requested_at, owner_role, next_follow_up, evidence source ids)
- **Review**(case_id, disposition keep_open|validate_scope|close, scope, rationale, cited_source_ids, task_id?, reviewer, created_at)
- **KnowledgeRef**(project_id, title, location path/URL, owner_role, last_verified). A reference only, never a copied document.
- **Setting**(org_id, key, value): stale_days=7, unanswered_working_days=3, as_of_date, ai_enabled=true, default SLA hours.
- **AuditEvent** · **Notification**(user, text, link, read)

## API contract (all under /api; JSON; session cookie)
- Auth: `GET /auth/demo-accounts` (DEMO_MODE only) · `POST /auth/demo-login {user_id}` · `POST /auth/logout` · `GET /auth/me`
- `GET /org` · `GET /users` · `POST /signup {org_name, your_name}` → new org with sample data (P1)
- Cases: `GET /cases?view=needs_attention|mine|stale|access_blocked|all` → rows with
  `{id, ref, employee, project, tracker_status, tracker_age_days, stage, reasons[{rule_id,severity,message}], next_task, review_state}`
- `GET /cases/{id}` → `{case, sources, claims, rejected, findings, tasks, access_items, latest_review, reviews, knowledge, analysis}`
- `GET /cases/{id}/timeline` → mixed chronological events (source received, AI run, finding raised, task created/done, review saved)
- `POST /cases/{id}/analyze` (analysis tables only) · `POST /cases/{id}/suggest-task` (AI draft, not persisted)
- Inbox: `GET /inbox?status=unmatched|matched` · `POST /inbox {body, author_role, date, title}` → new Source, auto-match,
  auto-analyze · `POST /inbox/{source_id}/link {case_id}`
- Tasks: `GET /tasks?mine=1&status=open` · `POST /cases/{id}/tasks` (coordinator/admin) · `PATCH /tasks/{id} {status}` (owner)
- Reviews: `POST /cases/{id}/reviews`. Only the case's technical owner, else 403.
- Access: `GET/POST /cases/{id}/access-items` · Knowledge: `GET /knowledge`
- Insights: `GET /insights` → counts by reason/severity/project, overdue tasks, stage distribution
- Settings: `GET/PATCH /settings` (admin) · `GET /audit?entity=` (admin, coordinator)
- People & roles: `GET|POST /org/members` · `PATCH /org/members/{user_id}` · `GET /org/roles` · `PATCH /org/roles/labels`
  · `GET|POST /org/role-assignments` · `PATCH|DELETE /org/role-assignments/{id}` (org admin)
- Projects: `GET /projects` · `GET /projects/{id}` · `GET|POST /projects/{id}/assignments` · `PATCH|DELETE /projects/{id}/assignments/{aid}`
- Case stakeholders: `GET|POST /cases/{id}/responsibilities` · `PATCH|DELETE .../{aid}` · `GET|POST /cases/{id}/training`
- AI presentation: `GET|PATCH /me/preferences` · `GET|PATCH /settings/ai-guidance` (versioned) · `POST /ask {question, case_id?, focus?, detail?, format?}`
- `GET /home?context=` → role-aware work queue sections
- `POST /admin/reset` (DEMO_MODE only) · `GET /health`

## Domain rules from the starter pack (do not "simplify")
- AS_OF_DATE = 2026-10-14 (an org setting). Ages, staleness and SLAs are computed against it, never wall-clock, in demo orgs.
- A tracker status is one report among others, never ground truth. Always show its age.
- Access: requested ≠ approved ≠ active ≠ confirmed_usable. Only an employee's successful test counts as usable.
- KT stages: shadowing ≠ supported execution ≠ independent execution. Training completed ≠ can execute.
- Final readiness = observed execution + technical-owner validation. AI never decides readiness.
- Atlas docs (E8) live at `/Team/Operations/Onboarding`. Store the reference only.
- Missing tracker fields stay NULL. Display "—" and raise MISSING_* findings.

## AI layer (the "trust layer")
- One source per extraction call. Output constrained by `ai/schemas/extract_v2.json` (an enum of valid scope/value pairs, split server-side) and validated by the verifier.
- Verifier: the quote must occur exactly once in the immutable body; compute start/end server-side and assert
  `body[start:end] == quote`. Failures go to `rejected_candidates` and never feed rules or the UI evidence list.
- Timeout 20s, max 2 attempts. Fallback: verified cache for (source_id, body_sha256, prompt_version, model) → mode `cached`;
  otherwise mode `unavailable` (the UI still shows originals; manual tasks and reviews still work).
- Every AI output in the UI shows: mode badge, model + prompt version, and a click-to-source citation.
- The org setting `ai_enabled=false` disables AI calls entirely; the platform still works.
- Suggest-task: the AI drafts `{title, owner_role, rationale, cited_claim_ids}`. The UI labels it "AI suggestion · not saved"
  and a human edits and saves it via the normal task route.

## Agents (case agent, Ask Graft, inbox triage) — see README "AI capabilities"
- Groq tool calling, bounded: max 8 tool calls, 60 s, one run per case at a time. `ai_enabled=false` or no key → "Agent
  unavailable"; manual work is unaffected.
- Tools are read-only and run **as the requesting user** (through `load_case` / `visible_cases`). The agent never sees
  more than its user, and `backend/app/ai/` has no import path to task or review writers (a test enforces it).
- Final output is a `submit_proposals` tool call validated server-side; every proposal must cite claim or source ids that
  exist on the case, else it is dropped and logged. Source bodies are data inside tool results, never instructions.
- Ask Graft answers only from the asking user's visible data, cites every statement, refuses when nothing supports an
  answer, and never decides readiness (it points to the technical owner).
- Every run, step, proposal, accept and dismiss is stored and audited; the UI shows the trace.

## UI conventions (Salesforce/HubSpot record-page feel)
- Sidebar nav: Home · Cases · Projects · Inbox · Tasks · Knowledge · Ask Graft · Insights · Settings (Rules & AI ·
  People & Roles · AI Guidance). The user menu lists roles with scope and a presentation-only working context. Top bar: org name, global search on case/employee,
  notifications bell, user menu with role badge.
- Case record page has a header with three separate status pills: **Tracker report**, **Evidence**, **Technical review**.
  Overview also has **Stakeholders & responsibilities** (inherited vs case override, gaps) and the training log.
  Tabs: Overview (findings, checklist, tasks, latest review) · Evidence (sources with highlighted claims) · Timeline ·
  Access · Knowledge.
- Every save refetches from the API (no optimistic state), so a hard refresh always matches.
- Clean and dense, light theme, one accent colour. No animations beyond shadcn defaults.

## Commands
- Dev: `docker compose up` (app on :8000, postgres), or locally `cd backend && uvicorn app.main:app --reload` +
  `cd frontend && npm run dev` (Vite proxies /api).
- Migrate/seed: `alembic upgrade head && python -m app.seed.seed`. Reset demo: `python -m app.seed.seed --reset`
  (explicit only; startup never deletes human records).
- Tests: `cd backend && pytest -q` · Build: `cd frontend && npm run build`

## Working style
- Stay inside your owner's paths (README → Roadmap → Team and ownership). Small commits with real messages, at least every 30 min; organizers read the history.
- Before saying "done", run the pass condition (curl / pytest / browser) and show the output.
- Unsure about a business rule: check docs/business-rules.md, then ask the human. Don't invent one.
- If time is short, cut breadth, never the Eva path, tenancy checks, or the audit/append-only guarantees.
