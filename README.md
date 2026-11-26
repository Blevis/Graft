<p align="center">
  <img src="docs/assets/graft-hero.svg" alt="Graft — Know who is ready. Prove it. Act on it." width="100%">
</p>

<p align="center">
  <a href="https://graft-560i.onrender.com/"><img alt="Live demo" src="https://img.shields.io/badge/live%20demo-graft--560i.onrender.com-5025B8?style=for-the-badge"></a>
  <a href="#run-it-in-two-minutes"><img alt="Docker" src="https://img.shields.io/badge/run-docker%20compose%20up-3978F6?style=for-the-badge"></a>
  <a href="AGENT_SPEC.md"><img alt="Agent spec" src="https://img.shields.io/badge/agent-spec-7954E8?style=for-the-badge"></a>
  <a href="docs/eval.md"><img alt="Evaluation" src="https://img.shields.io/badge/AI%20eval-published-2454D6?style=for-the-badge"></a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11-160D35?style=flat-square">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-SQLAlchemy%202-160D35?style=flat-square">
  <img alt="React" src="https://img.shields.io/badge/React-Vite%20%2B%20TS-160D35?style=flat-square">
  <img alt="Postgres" src="https://img.shields.io/badge/Postgres-16-160D35?style=flat-square">
  <img alt="Ollama" src="https://img.shields.io/badge/LLM-private%20Ollama-160D35?style=flat-square">
  <img alt="Tests" src="https://img.shields.io/badge/backend%20tests-150-7954E8?style=flat-square">
</p>

<h3 align="center"><a href="https://graft-560i.onrender.com/">Try the live demo → graft-560i.onrender.com</a></h3>

<p align="center"><b>Team K · Engineering Albania Student Hackathon 2026</b></p>

---

> **Graft answers one question for every new joiner, transfer and handover:**
> ### *What evidence shows this person can actually work independently — and who acts next?*

Onboarding status today lives in a spreadsheet column that someone typed weeks ago. Graft replaces that guess with
**evidence**: it reads the emails, updates, tracker notes and documents your teams already produce, extracts
**cited** claims with a private AI model, flags where reports disagree, routes a follow-up to a named owner, and lets the
**technical owner** — never the AI — record the readiness decision. Every step is permission-checked, audited and
survives a refresh.

<br>

## Contents

- [Why companies choose Graft](#why-companies-choose-graft)
- [How it works](#how-it-works)
- [See it in 3 minutes — the Eva Stone story](#see-it-in-3-minutes--the-eva-stone-story)
- [Product tour](#product-tour)
- [The trust layer](#the-trust-layer-ai-proposes-people-decide)
- [Roles, responsibilities and visibility](#roles-responsibilities-and-visibility)
- [Plans](#plans)
- [Run it in two minutes](#run-it-in-two-minutes)
- [Architecture](#architecture)
- [Team and task split](#team-and-task-split)
- [Roadmap](#roadmap)

<br>

## Why companies choose Graft

| The problem today | What Graft does |
| --- | --- |
| *"The tracker says Ready."* A status is one person's opinion, often stale. | Shows the tracker as **one report among others, with its age**, next to the evidence that supports or contradicts it. |
| Line manager says *closed*, tech lead says *two scenarios still uncovered* — on the same day. Nobody notices. | **Conflict rules** catch contradictory reports automatically and raise a finding with both citations. |
| Access was *requested*, so everyone assumes it *works*. | Tracks **requested → approved → active → confirmed usable**. Only the employee's own successful test counts. |
| Follow-ups get lost in chat threads. | Every finding becomes an **owned task** with due date, SLA, queue, reassignment history and reminders. |
| AI tools hallucinate and decide things they shouldn't. | AI only **proposes**. Every quote is verified against the original text; invented text is rejected and shown as rejected. |
| Employee data can't leave the company. | Runs a **private model** (Ollama) on your network. No hosted inference, no data sent to third parties. |
| Auditors ask *"who decided this, and based on what?"* | Every write is an **audit event** with actor, before/after and citations. Reviews are append-only. |

<table>
<tr>
<td width="25%" align="center"><img alt="01" src="https://img.shields.io/badge/-01-5025B8?style=for-the-badge"><br><br><b>Faster time-to-productive</b><br><sub>Blockers surface the day they appear, not at the monthly status meeting.</sub></td>
<td width="25%" align="center"><img alt="02" src="https://img.shields.io/badge/-02-7954E8?style=for-the-badge"><br><br><b>Decisions you can defend</b><br><sub>Every readiness call links to the exact sentence that justified it.</sub></td>
<td width="25%" align="center"><img alt="03" src="https://img.shields.io/badge/-03-3978F6?style=for-the-badge"><br><br><b>Private by design</b><br><sub>Multi-tenant isolation, role-scoped views, on-prem AI, OIDC SSO.</sub></td>
<td width="25%" align="center"><img alt="04" src="https://img.shields.io/badge/-04-2454D6?style=for-the-badge"><br><br><b>Fits your process</b><br><sub>Templates, configurable thresholds, CSV import, inbound relay.</sub></td>
</tr>
</table>

<br>

## How it works

<p align="center">
  <img src="docs/assets/graft-flow.svg" alt="Evidence in → cited claims → findings → owned follow-up → technical review" width="100%">
</p>

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#EFEBFC","primaryTextColor":"#191629","primaryBorderColor":"#7954E8","lineColor":"#3978F6","secondaryColor":"#E5EEFF","tertiaryColor":"#F6F5FB","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
flowchart LR
    S[("Sources<br/>immutable · versioned")]:::evidence --> X["AI extraction<br/>one source per call"]:::ai
    X --> V{"Verifier<br/>exact quote, exact span"}:::ai
    V -- verified --> C["Claims"]:::ai
    V -- invented --> R["Rejected candidates"]:::muted
    C --> F["Rules engine<br/>findings"]:::ai
    F --> T["Task<br/>owner · due · SLA"]:::human
    T --> RV["Technical review<br/>append-only"]:::human
    classDef evidence fill:#F6F5FB,stroke:#77738A,color:#191629
    classDef ai fill:#EFEBFC,stroke:#7954E8,color:#191629
    classDef human fill:#E5EEFF,stroke:#2454D6,color:#191629
    classDef muted fill:#FFFFFF,stroke:#E5E2EF,color:#77738A
```

**Three data classes, three write paths.** Evidence is never edited (a correction is a new version). Derived data —
claims and findings — is recomputable at any time. Human data — tasks and reviews — is written only by people through
their own API routes. A test guarantees that re-running analysis never changes, duplicates or deletes a task or review.

### The readiness journey

A case's stage is derived from the **latest technical review**, never from the tracker. Training completed is not the
same as being able to execute, and shadowing is not supported execution.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#EFEBFC","primaryTextColor":"#191629","primaryBorderColor":"#7954E8","lineColor":"#5025B8","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
flowchart LR
    P["Pre-onboarding"]:::s1 --> A["Access"]:::s2 --> SH["Shadowing"]:::s3 --> SE["Supported<br/>execution"]:::s4 --> IE["Independent<br/>execution"]:::s5 --> VA["Validated<br/>by technical owner"]:::s6
    classDef s1 fill:#F6F5FB,stroke:#E5E2EF,color:#191629
    classDef s2 fill:#EFEBFC,stroke:#C9BCF8,color:#191629
    classDef s3 fill:#C9BCF8,stroke:#7954E8,color:#191629
    classDef s4 fill:#7954E8,stroke:#5025B8,color:#FFFFFF
    classDef s5 fill:#5025B8,stroke:#5025B8,color:#FFFFFF
    classDef s6 fill:#160D35,stroke:#160D35,color:#FFFFFF
```

### Access is four states, not one checkbox

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#E5EEFF","primaryTextColor":"#191629","primaryBorderColor":"#3978F6","lineColor":"#2454D6","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
stateDiagram-v2
    direction LR
    [*] --> Requested
    Requested --> Awaiting_approval
    Awaiting_approval --> Approved
    Requested --> Approved
    Approved --> Active: provisioned by access responsible
    Active --> Confirmed_usable: employee's own successful test
    Requested --> Not_provisioned
    Confirmed_usable --> [*]
```

<br>

## See it in 3 minutes — the Eva Stone story

> **Live demo: https://graft-560i.onrender.com/** — sign in at
> [/login](https://graft-560i.onrender.com/login). Every demo account is a fictional person; the sign-in page shows the
> shared demo password.

> **Demo data.** The organisers' starter pack (`data/seed.json`, ONB-001 to ONB-010, verbatim) plus our showcase dataset
> (`data/showcase.json`, ONB-011 to ONB-026): a signed-off case, a reopened sign-off, blocked access, a stale tracker, a closure conflict, an
> unanswered request, an HR document upload, paused and reassigned tasks, a training log and ambiguous inbox mail.
> The showcase is replayed through the real API as fictional users on first start (`SEED_SHOWCASE=true`, the default),
> with recorded extractions so it shows verified claims without a model. Eva's case is never touched.

| Step | Who | What you see |
| :---: | --- | --- |
| **1** | **Elira Dervishi** · PMO Coordinator | Insights shows the portfolio mid-quarter: **26 cases, 17 needing attention**, every chart populated. |
| **2** | Elira | Open **ONB-005 Eva Stone**. Tracker: *Ready with Support*. Evidence pill: **Conflicting reports** — the Line Manager (E4) reports closure while the Technical Lead (E3) reports two uncovered complex scenarios, same day. Each claim highlights its exact span in the original; one invented candidate sits in *Rejected*. |
| **3** | Elira | **Assign** the flag to Ardit Kola with a due date. Try to record a review yourself: refused (403) — coordinators coordinate, they don't sign off. |
| **4** | **Ardit Kola** · Technical Owner | Open ONB-005 → **Record technical review** → *Keep open*, scope *Overall onboarding*, linked to the task. |
| **5** | Anyone | Hard refresh: everything is there. Run **Analyze evidence** twice: the task and the review are untouched. |

```mermaid
%%{init: {"theme":"base","themeVariables":{"actorBkg":"#EFEBFC","actorBorder":"#7954E8","actorTextColor":"#191629","signalColor":"#5025B8","signalTextColor":"#191629","noteBkgColor":"#E5EEFF","noteBorderColor":"#3978F6","noteTextColor":"#191629","activationBkgColor":"#C9BCF8","activationBorderColor":"#7954E8","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
sequenceDiagram
    autonumber
    participant LM as Line Manager (E4)
    participant TL as Technical Lead (E3)
    participant G as Graft
    participant PMO as Elira · PMO
    participant TO as Ardit · Technical Owner
    LM->>G: "Onboarding is closed"
    TL->>G: "Two complex scenarios still uncovered"
    G->>G: Extract claims, verify every quote
    G-->>PMO: Finding: closure conflict (both citations)
    PMO->>G: Assign follow-up to Ardit, due date + SLA
    G-->>TO: Notification + task in queue
    TO->>G: Review: Keep open, scope "Overall onboarding"
    Note over G: Re-analysis recomputes claims and findings only.<br/>Task and review are untouched.
```

<details>
<summary><b>Second walkthrough — from new hire to sign-off</b></summary>

1. As **Elira**, Cases → **New case**: "Dina Kraja", project transfer, Nimbus, line manager Luca Gray. The
   project-transfer template is snapshotted: Nadia (Nimbus technical owner) and Besa (Nimbus training default) get
   their milestone tasks; handover and access tasks land in the **coordinator queue** (Queues → Unowned).
2. Reassign the access task to **Gent Morina** with a reason; the history shows queued → reassigned.
3. As **Nadia**, open the case → Evidence → **Add evidence**, then **Record decision**: try **Final sign-off** first
   (refused, listing the milestones not yet validated), then **Validated for scope** per milestone, then the
   sign-off with a citation. Readiness reads *Signed off*; the tracker status stays a separate report.
4. Cases → **Import CSV** previews rows with errors and duplicates; importing the same file twice creates nothing new.

</details>

<details>
<summary><b>More things to try</b></summary>

- **Gent Morina** → ONB-002: access-only view; can approve access but cannot confirm usability.
- **Teuta Gjoni** (HR): summary view, no review rationale.
- **Klea Hoxha** → Projects → Orion → Team.
- **Dren Basha** → Settings → People & Roles.
- **Ardit Kola** → switch the working context in the user menu: Home and Ask Graft re-focus, permissions don't change.
- **Sam Rivera** (Sandbox Co) → a second tenant. Nothing from the first org is reachable; it's a 404, not a 403.

</details>

<br>

## Product tour

| Module | What it gives you |
| --- | --- |
| **Home** | A role-aware work queue: what *you* need to act on today. |
| **Cases** | Saved views — *needs attention, mine, stale, access blocked, all* — with reasons and next task per row. Record page with three separate pills: **Tracker report · Evidence · Technical review**. Tabs for Overview, Evidence, Timeline, Access and Knowledge. |
| **Projects** | Project teams and default responsibilities that cases inherit (overrides never mutate the project). |
| **Inbox** | Paste text or upload a PDF, Word file, text file or scan. Graft auto-matches it to a case, extracts claims and refreshes findings. |
| **Tasks & Queues** | Owned follow-ups with SLA, claim / reassign / pause / resume, full history and overdue reminders. |
| **Knowledge** | References to where project docs live (never copies), with owner and last-verified date. |
| **Ask Graft** | Questions about a case or the portfolio, answered only from data you may see, every statement cited. Refuses when nothing supports an answer. |
| **Insights & Metrics** | Charts for reasons, severity, project, stage, tracker age, access states, workload and due dates — each with a table view of the same numbers. Outcome metrics with drill-down and scoped CSV export. |
| **Settings** | Rules & AI thresholds, People & Roles, versioned AI guidance, audit trail. |

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#EFEBFC","primaryTextColor":"#191629","primaryBorderColor":"#7954E8","lineColor":"#3978F6","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
flowchart LR
    subgraph IN["Evidence comes in"]
      P1["Paste"]:::i
      P2["Upload PDF · Word · scan"]:::i
      P3["Inbound relay"]:::i
      P4["CSV import"]:::i
    end
    IN --> M["Inbox auto-match<br/>to a case"]:::g
    M --> AN["Analyze<br/>claims + findings"]:::g
    AN --> H["Home · Cases · Queues"]:::o
    AN --> IS["Insights · Metrics · CSV export"]:::o
    AN --> AK["Ask Graft<br/>cited answers"]:::o
    classDef i fill:#F6F5FB,stroke:#E5E2EF,color:#191629
    classDef g fill:#7954E8,stroke:#5025B8,color:#FFFFFF
    classDef o fill:#E5EEFF,stroke:#3978F6,color:#191629
```

**Documents:** PDF, `.docx`, UTF-8 text and scans (PNG, JPEG, TIFF, scanned PDFs via Tesseract OCR). File type is
detected from the bytes, text is extracted on the server, and the original file is **not stored** — only its name, type,
size, SHA-256, method and page count. Limits: 10 MB, 30 pages, 20,000 characters per source.

<br>

## The trust layer: AI proposes, people decide

| Guarantee | How it's enforced |
| --- | --- |
| **No invented evidence** | Output is schema-constrained. The verifier requires each quote to appear **exactly once** in the immutable body and asserts `body[start:end] == quote`. Failures go to *rejected candidates* and never feed rules or the UI evidence list. |
| **AI never decides readiness** | Readiness = observed execution + technical-owner validation. `backend/app/ai/` has **no import path** to task or review writers — a test enforces it. |
| **Bounded agents** | The case agent uses read-only tools, max 8 tool calls, a time budget, one run per case. It runs *as the requesting user*, so it can never see more than they can. Every proposal must cite real claim or source ids. |
| **Human handoff** | *Accept* opens the normal task form pre-filled (origin `ai_suggested_edited`); *Dismiss* records a reason. Both are audited. |
| **Prompt-injection safe** | Source bodies are data inside tool results, never instructions. Ask Graft refuses instruction changes, private matters and judging people before any model call. |
| **Transparent modes** | Every AI output shows its mode badge (**Live · Verified cache · Recorded example · Unavailable**), model, prompt version and a click-to-source citation. |
| **Works without AI** | `ai_enabled=false` or no model → originals stay visible; manual tasks and reviews keep working; background jobs resume when the model returns. |
| **Measured, not marketed** | [`docs/eval.md`](docs/eval.md) publishes every live run against the business fixtures — failures included. |

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#EFEBFC","primaryTextColor":"#191629","primaryBorderColor":"#7954E8","lineColor":"#5025B8","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
flowchart TD
    R["Analysis requested"]:::q --> E{"AI enabled and<br/>model reachable?"}:::q
    E -- yes --> L["Live<br/>model call, 20 s, 2 attempts"]:::live
    E -- no --> C{"Verified cache for this<br/>source + hash + prompt + model?"}:::q
    L -- fails --> C
    C -- yes --> CA["Verified cache"]:::cache
    C -- no --> U["Unavailable<br/>originals shown, manual work continues"]:::un
    L --> VF["Verifier"]:::q
    CA --> VF
    classDef q fill:#FFFFFF,stroke:#E5E2EF,color:#191629
    classDef live fill:#5025B8,stroke:#5025B8,color:#FFFFFF
    classDef cache fill:#3978F6,stroke:#2454D6,color:#FFFFFF
    classDef un fill:#F6F5FB,stroke:#77738A,color:#77738A
```

### Tested, not promised

150 backend tests guard the guarantees above, grouped here by what they protect:

```mermaid
%%{init: {"theme":"base","themeVariables":{"pie1":"#5025B8","pie2":"#7954E8","pie3":"#3978F6","pie4":"#2454D6","pie5":"#C9BCF8","pieStrokeColor":"#FFFFFF","pieOuterStrokeColor":"#E5E2EF","pieTitleTextColor":"#191629","pieSectionTextColor":"#FFFFFF","pieLegendTextColor":"#191629","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
pie showData title Backend tests by area (150)
    "AI, agents and verifier" : 43
    "Roles, visibility, tenancy" : 40
    "Workflow, documents, sign-off, Eva path" : 29
    "Identity and data controls" : 20
    "Platform, insights, metrics" : 18
```

<br>

## Roles, responsibilities and visibility

A person can hold several roles, each granted at **organization**, **project** or **case** scope. **Roles** decide what
you may do; **responsibilities** say who is accountable on a specific case; **AI preferences** only change how the
assistant presents things. The three are stored and enforced separately — and a hidden case is a 404, exactly like
another tenant's.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#EFEBFC","primaryTextColor":"#191629","primaryBorderColor":"#7954E8","lineColor":"#3978F6","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
flowchart LR
    U["Signed-in user"]:::u --> RA["Role assignments<br/>org · project · case scope"]:::r
    U --> CR["Case responsibilities<br/>inherited or overridden"]:::r
    U -.-> PR["AI preferences<br/>presentation only"]:::p
    RA --> POL{"Policy"}:::pol
    CR --> POL
    POL -- visible --> VL["View level<br/>full · employee · summary · access only"]:::ok
    POL -- hidden --> NF["404<br/>same as another org"]:::no
    classDef u fill:#160D35,stroke:#160D35,color:#FFFFFF
    classDef r fill:#EFEBFC,stroke:#7954E8,color:#191629
    classDef p fill:#F6F5FB,stroke:#E5E2EF,color:#77738A
    classDef pol fill:#5025B8,stroke:#5025B8,color:#FFFFFF
    classDef ok fill:#E5EEFF,stroke:#3978F6,color:#191629
    classDef no fill:#FFFFFF,stroke:#77738A,color:#77738A
```

| Role | Sees | Can do |
| --- | --- | --- |
| Organization Admin | Everything in the org | Settings, people and role grants, demo reset |
| PMO Coordinator | Every case | Assign responsibilities and follow-ups, analyze evidence, run the case agent, AI guidance |
| Project Manager | Cases in their projects | Project team, responsibilities and follow-ups |
| Line Manager | Their direct reports | Follow-ups for their reports |
| **Technical Owner** | Their projects' or assigned cases | **The readiness review**, when primary technical owner on the case |
| Training Responsible | Assigned cases | Training & KT log. Never signs off readiness |
| HR Business Partner | Their cohort, summary only | HR follow-ups; no technical assessment notes |
| Access Responsible | Access items on assigned cases | Requested → approved → active; cannot confirm usability |
| Project Member | Project cases, summary only | Their own tasks |
| Employee | Their own case | Their tasks; confirm their own access works |
| Management Viewer / Auditor | Summaries (auditor: full audit trail) | Read-only |

<details>
<summary><b>Demo accounts</b> (fictional people)</summary>

Sign in at [graft-560i.onrender.com/login](https://graft-560i.onrender.com/login) with
`firstname.lastname@demo.graft.example` (Sandbox Co: `sam.rivera@sandbox.graft.example`) and the shared demo password
shown on the sign-in page. Passwords are salted scrypt hashes, attempts are throttled, and password sign-in exists only
for demo orgs in demo mode. Production orgs sign in with OIDC SSO.

| Person | Roles and scope |
| --- | --- |
| Dren Basha | Organization Admin |
| Elira Dervishi | PMO Coordinator |
| Klea Hoxha | Project Manager · Orion, Atlas |
| Ardit Kola | Technical Owner · Orion, Aurora, Atlas; Training Responsible · Orion |
| Nadia Ferri | Technical Owner · Nimbus, Helios, Nova, Pulse, Vega |
| Besa Leka | Training Responsible · Aurora, Nimbus |
| Luca Gray | Line Manager of Eva (ONB-005); Project Member · Orion |
| Teuta Gjoni | HR Business Partner for ONB-002 and ONB-005 |
| Gent Morina | Access Responsible for Leo's systems (ONB-002) |
| Erion Daci | Project Member · Orion |
| Eva Stone, Leo Marin | Employees (ONB-005, ONB-002) |
| Mira Shehu | Management Viewer |
| Ilir Prifti | Auditor |
| Sam Rivera | Admin of the second tenant, *Sandbox Co* |

</details>

<br>

## Plans

<table>
<tr>
<td width="33%" valign="top">
<h3>Pilot</h3>
<b>Free</b><br><br>
One project team · demo data · up to 25 onboarding cases
</td>
<td width="33%" valign="top">
<h3>Team · recommended</h3>
<b>€6 / employee case / month</b><br><br>
Unlimited projects · AI evidence extraction · full audit trail
</td>
<td width="33%" valign="top">
<h3>Enterprise</h3>
<b>Contact us</b><br><br>
OIDC SSO · private model on your network · data residency · custom retention and integrations
</td>
</tr>
</table>

<sub>Indicative pricing for the prototype. Nothing is billed.</sub>

<br>

## Run it in two minutes

Don't want to install anything? Use the **[live demo](https://graft-560i.onrender.com/)**.

**Docker (app + Postgres 16)**

```bash
docker compose up --build
```

- App: http://localhost:8000/ (sign in at `/login`) · Health: http://localhost:8000/api/health
- Startup runs migrations and seeds the demo orgs once; it never deletes human records.
- Reset explicitly: `docker compose exec app python -m app.seed.seed --reset` (or user menu → *Reset demo data* as admin).

**Local development (hot reload)**

```bash
cd backend && python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt && alembic upgrade head
uvicorn app.main:app --reload                                      # :8000
```

```bash
cd frontend && npm install && npm run dev                          # :5173, proxies /api → :8000
```

**Tests and build**

```bash
cd backend && pytest -q
```

```bash
cd frontend && npm run build
```

**Other entry points:** worker `python -m app.worker` · operator CLI `python -m app.ops --help` ·
eval `python -m eval.run_eval --mode replay|live`.

Configuration is via environment variables — see [`.env.example`](.env.example). No secrets are committed.

### Deployment profiles

| Profile | Command | AI | Identity |
| --- | --- | --- | --- |
| **Hosted demo** ([live](https://graft-560i.onrender.com/)) | Render → New → Blueprint → this repo (`render.yaml`) | Recorded examples; live AI via a tunnel ([guide](docs/deployment.md#live-ai-on-the-hosted-demo-tunnel-fictional-data-only)) | Demo accounts |
| **Local demo** | `docker compose up` | Recorded examples | Demo accounts |
| **Private** | `docker compose --profile private up -d` | Local Ollama on an internal network, pinned model digest | OIDC SSO |

Model provisioning and pinning, identity, backups and release gates: [`docs/deployment.md`](docs/deployment.md).

<br>

## Architecture

One Docker image, one origin, no CORS.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#EFEBFC","primaryTextColor":"#191629","primaryBorderColor":"#7954E8","lineColor":"#5025B8","secondaryColor":"#E5EEFF","tertiaryColor":"#F6F5FB","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
flowchart TB
    B["Browser"] -->|HTTPS| API
    subgraph IMG["One Docker image · uvicorn + FastAPI"]
      API["/api/* JSON API"]
      SPA["/* React SPA"]
      SVC["services<br/>tenancy · permissions · visibility · rules · matching · audit"]
      AI["ai/<br/>client · verifier · pipeline · agent · ask"]
      W["worker<br/>analysis jobs · overdue reminders"]
      API --> SVC --> AI
      W --> AI
    end
    SVC --> DB[("Postgres 16<br/>SQLite in dev/tests")]
    AI -->|private network only| OL["Ollama"]
    classDef box fill:#FFFFFF,stroke:#E5E2EF,color:#191629
    class B,SPA box
```

| Path | What |
| --- | --- |
| `backend/app/api/` | One router per API group |
| `backend/app/services/` | Tenancy, permissions, visibility, rules, matching, audit, timeline |
| `backend/app/ai/` | The trust layer — the only place a model is called |
| `backend/app/models/`, `schemas/` | SQLAlchemy models and the Pydantic API contract |
| `backend/alembic/` | Migrations |
| `backend/tests/` | Unit and acceptance tests (Eva path, tenancy, visibility per role, AI boundaries) |
| `backend/eval/` | Evaluation harness and recorded results |
| `frontend/src/site/` | Public pages: landing, pricing, login |
| `frontend/src/app/` | The authenticated app |
| `frontend/src/lib/` | Typed API client and TanStack Query hooks |
| `data/seed.json` | Starter-pack cases and evidence, verbatim |
| `Dockerfile`, `docker-compose.yml`, `render.yaml`, `.github/workflows/ci.yml` | Build, deploy, CI |

Deeper reading: [`docs/architecture.md`](docs/architecture.md) · [`docs/business-rules.md`](docs/business-rules.md) ·
[`AGENT_SPEC.md`](AGENT_SPEC.md) · [`docs/eval.md`](docs/eval.md).

**Non-negotiables:** every tenant table has `org_id NOT NULL` and every query goes through scoped helpers; role comes
from the session, never the request body; every write emits an audit event in the same transaction; no real data and
no credentials in git.

<br>

## Team and task split

Each member works on their own `feat/<area>` branch, commits at least every 30 minutes, stays inside their owned paths,
and merges through small PRs into `main`. **Blevis** is the single merger.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#EFEBFC","primaryTextColor":"#191629","primaryBorderColor":"#7954E8","lineColor":"#3978F6","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
flowchart LR
    A["<b>Blevis Allushi</b><br/>Platform & delivery<br/>API · services · deploy · spec"]:::a
    B["<b>Vigen Myrtolli</b><br/>AI & agents<br/>trust layer · agent · Ask Graft · eval"]:::b
    C["<b>Mateos Sharka</b><br/>AI experience UI<br/>agent panel · Ask Graft UI"]:::c
    D["<b>Klea Mehmeti</b><br/>Product UI<br/>app shell · cases · inbox · site"]:::d
    B -- agent API contract --> C
    A -- case & workflow API --> D
    C -- PR --> A
    D -- PR --> A
    B -- PR --> A
    classDef a fill:#160D35,stroke:#160D35,color:#FFFFFF
    classDef b fill:#5025B8,stroke:#5025B8,color:#FFFFFF
    classDef c fill:#3978F6,stroke:#3978F6,color:#FFFFFF
    classDef d fill:#2454D6,stroke:#2454D6,color:#FFFFFF
```

| Member | Focus | Owns these paths |
| --- | --- | --- |
| **Blevis Allushi** | **Platform, delivery, specification** — deploy, merging, hardening, business-owner checkpoint, business rules, agent spec, architecture doc, final PR | `backend/app/api/` (except `agents.py`, `ask.py`), `backend/app/services/`, `backend/app/models/` (except `agent.py`), `Dockerfile`, `render.yaml`, `.github/`, `AGENT_SPEC.md`, `docs/business-rules.md`, `docs/architecture.md`, `backend/eval/fixtures/` |
| **Vigen Myrtolli** | **AI and agents** — live model runs, the case agent (loop, tools, tables, endpoints), Ask Graft, eval harness and measured results | `backend/app/ai/`, `backend/app/models/agent.py`, `backend/app/api/agents.py`, `backend/app/api/ask.py`, the agent migration, `backend/eval/` (except `fixtures/`), `docs/eval.md`, `backend/tests/test_agent*.py`, `backend/tests/test_ask*.py` |
| **Mateos Sharka** | **AI experience UI** — agent panel on the case page, Ask Graft on the case page and Home, trace and proposal accept/dismiss | `frontend/src/app/cases/AiPanel.tsx`, `frontend/src/app/ask/`, agent/ask hooks and types in `frontend/src/lib/` |
| **Klea Mehmeti** | **Product UI** — role-specific views, case and inbox polish, readiness date and role fields, layout, empty states, public site | `frontend/src/app/` (except `cases/AiPanel.tsx` and `ask/`), `frontend/src/site/`, `frontend/src/components/` |

**Shared files** (`frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`, `backend/app/main.py`,
`backend/app/api/__init__.py`): append only, small commits, announce in the team chat.

### Task board

| Phase | Blevis · Platform | Vigen · AI | Mateos · AI UI | Klea · Product UI |
| --- | --- | --- | --- | --- |
| **0 · Kick-off**<br><sub>14:00–14:30</sub> | Book the business-owner checkpoint; commit `AGENT_SPEC.md`; confirm CI is green | Agree the agent API contract with Mateos | Agree the agent API contract with Vigen | Run the app, sign in as each role |
| **1 · Go live**<br><sub>14:30–16:30</sub> | Render Blueprint live (done); walk Eva path on prod; run checkpoint → `docs/business-rules.md` | Live extraction on E1–E8; agent tables, migration, loop and endpoints with a stubbed model | Agent panel against a mocked response | Employee and line-manager experience; access confirmation; empty states |
| **2 · Make it real**<br><sub>16:30–19:00</sub> | Apply checkpoint answers to rules and settings; readiness date and role (API + migration); production hardening; rewrite `AGENT_SPEC.md` to match code | Agent end to end on Eva, Leo, Lina; Ask Graft; eval harness over the fixtures | Switch panel to real API; Ask Graft box on case page and Home | Readiness date and role in the case header; coordinator edit form; checklist wiring |
| **3 · Evidence**<br><sub>19:00–20:15 · <b>freeze</b></sub> | `docs/architecture.md`; measured numbers into the spec; merge, test, build, redeploy | Commit a measured eval run including at least one failure | Click-through of every page as every role on prod | Click-through of every page as every role on prod |
| **4 · Hand-in**<br><sub>20:15–21:45</sub> | Open the submission PR with judge and mentor as reviewers; clean-clone README check | Bug fixes only | Bug fixes only | Bug fixes only |

> **Last commit pushed by 21:45.** Commits after 22:00 do not count.

<details>
<summary><b>Agent API contract</b> (Vigen builds, Mateos consumes — frozen after 15:00)</summary>

- `POST /api/cases/{id}/agent-runs` → `{id, case_id, status, assessment, proposals[], steps[], model, prompt_version, created_at}`
  - `status`: `completed | failed | unavailable`
  - proposal: `{id, kind: task|message|access_followup, title, body, owner_role, owner_user_id, due_date, cited_source_ids[], cited_claim_ids[], status: open|accepted|dismissed, dismiss_reason}`
  - step: `{index, tool, arguments, result_summary, duration_ms}`
- `GET /api/cases/{id}/agent-runs` → past runs, newest first
- `POST /api/agent-proposals/{id}/dismiss {reason}`
- Accept: normal `POST /api/cases/{id}/tasks` with `origin: "ai_suggested_edited"` and `proposal_id`
- `POST /api/ask {question, case_id?, focus?, detail?, format?}` → `{answer, citations[{source_id, claim_id, quote}], refused, mode, model, prompt_version, presentation}`

</details>

<details>
<summary><b>Risks and fallbacks</b></summary>

| Risk | Fallback |
| --- | --- |
| Model down or busy | Intake and manual work continue; jobs wait and resume; verified cache or recorded examples are served meanwhile. |
| Agent work runs late | Cut order: triage agent → Ask Graft → agent on Leo/Lina. Minimum: Eva agent run, panel, spec section. |
| Render outage | Local `docker compose up`. |
| Business owner contradicts a rule | Thresholds are org settings; each rule is one tested function in `services/rules.py`. |
| Late merge conflicts | Separate owned paths, small PRs, one merger (Blevis), freeze at 20:15. |
| A secret lands in git | Keys live only in `.env` and Render; `.env*` is gitignored. Rotate immediately if leaked. |

</details>

<br>

## Roadmap

### Hackathon day at a glance

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"Inter, Segoe UI, sans-serif","primaryTextColor":"#191629","taskBkgColor":"#7954E8","taskBorderColor":"#5025B8","taskTextColor":"#FFFFFF","taskTextLightColor":"#FFFFFF","taskTextOutsideColor":"#191629","activeTaskBkgColor":"#3978F6","activeTaskBorderColor":"#2454D6","doneTaskBkgColor":"#C9BCF8","doneTaskBorderColor":"#7954E8","critBkgColor":"#160D35","critBorderColor":"#160D35","sectionBkgColor":"#EFEBFC","altSectionBkgColor":"#F6F5FB","sectionBkgColor2":"#E5EEFF","gridColor":"#E5E2EF","todayLineColor":"#2454D6"}}}%%
gantt
    title Team K · Day 1 (14:00 – 22:00)
    dateFormat HH:mm
    axisFormat %H:%M
    todayMarker off
    section Blevis · Platform
    Kick-off         :a0, 14:00, 30m
    Render live      :done, a1, after a0, 60m
    Checkpoint       :a2, after a1, 60m
    Rules + hardening :a3, 16:30, 150m
    Merge + redeploy :a4, 19:00, 75m
    Submission PR    :crit, a5, 20:15, 90m
    section Vigen · AI
    Contract         :b0, 14:00, 30m
    Extraction + agent loop :b1, 14:30, 120m
    Agent + Ask Graft :b2, 16:30, 150m
    Eval run         :b3, 19:00, 75m
    Bug fixes        :crit, b4, 20:15, 90m
    section Mateos · AI UI
    Contract         :c0, 14:00, 30m
    Panel on mock    :c1, 14:30, 120m
    Real API + Ask UI :c2, 16:30, 150m
    Click-through    :c3, 19:00, 75m
    Bug fixes        :crit, c4, 20:15, 90m
    section Klea · Product UI
    Kick-off         :d0, 14:00, 30m
    Role views       :d1, 14:30, 120m
    Case header + forms :d2, 16:30, 150m
    Click-through    :d3, 19:00, 75m
    Bug fixes        :crit, d4, 20:15, 90m
    section Milestones
    Contract frozen                      :milestone, m0, 15:00, 0m
    Feature freeze                       :milestone, m1, 20:15, 0m
    Last push                            :milestone, m2, 21:45, 0m
    Hard deadline                        :milestone, m3, 22:00, 0m
```

### What shipped, phase by phase

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"Inter, Segoe UI, sans-serif","cScale0":"#160D35","cScaleLabel0":"#FFFFFF","cScale1":"#5025B8","cScaleLabel1":"#FFFFFF","cScale2":"#7954E8","cScaleLabel2":"#FFFFFF","cScale3":"#3978F6","cScaleLabel3":"#FFFFFF","cScale4":"#2454D6","cScaleLabel4":"#FFFFFF"}}}%%
timeline
    title From scaffold to submission
    Foundation : Scaffold, Docker, Render Blueprint, CI
               : Verbatim seed - 10 cases, 8 sources
    Trust layer : Private extraction and exact-quote verifier
                : Verified cache, recorded examples, unavailable mode
                : Gap rules - conflict, access, unanswered, stale, missing
    Eva path : Coordinator assigns, technical owner reviews
             : Survives refresh and re-analysis
    People and roles : 12 canonical roles, scoped grants
                     : Responsibilities, overrides, ownership gaps
    Agents and product : Case agent, Ask Graft, documents with OCR
                       : Queues, templates, CSV import, sign-off
                       : Insights charts, metrics, showcase data
```

### Where the effort went

Every phase was planned against the judging weights:

```mermaid
%%{init: {"theme":"base","themeVariables":{"pie1":"#160D35","pie2":"#5025B8","pie3":"#7954E8","pie4":"#3978F6","pie5":"#C9BCF8","pieStrokeColor":"#FFFFFF","pieOuterStrokeColor":"#E5E2EF","pieTitleTextColor":"#191629","pieSectionTextColor":"#FFFFFF","pieLegendTextColor":"#191629","fontFamily":"Inter, Segoe UI, sans-serif"}}}%%
pie showData title Judging weights (%)
    "Usable, production-ready solution" : 40
    "Agent specification" : 25
    "LLM use" : 15
    "Architecture" : 15
    "Demo" : 5
```

### Shipped

- [x] Multi-tenant data layer, seeded verbatim from the starter pack, plus a 16-case showcase dataset replayed through the API
- [x] Gap rules: closure conflict, access not confirmed, unanswered request, stale tracker, missing fields
- [x] Trust layer: schema-constrained private extraction, exact-quote verifier, verified cache, recorded examples, unavailable mode
- [x] AI task drafting, labelled *AI suggestion · not saved*, saved only by a human
- [x] Eva path end to end — survives refresh and re-analysis
- [x] 12 canonical roles with org / project / case scope, responsibilities with project defaults and overrides, ownership gaps
- [x] Case agent, Ask Graft, document upload with OCR, queues, templates, CSV import, outcome metrics, audit trail
- [x] Insights and Home charts, each with a table view of the same numbers
- [x] 150 backend tests: Eva path, tenancy, visibility per role, role checks, verifier, AI boundaries

<br>

---

<p align="center">
  <img src="docs/assets/graft-palette.svg" alt="Graft brand palette" width="100%">
</p>

<p align="center">
  <b><a href="https://graft-560i.onrender.com/">graft-560i.onrender.com</a></b><br>
  <sub><b>Graft</b> · Team K · Engineering Albania Student Hackathon 2026 · All data is fictional.</sub>
</p>
