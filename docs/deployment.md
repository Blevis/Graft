# Deployment and operations

Graft runs in two explicitly selected modes from the same image:

| | Demo | Private |
| --- | --- | --- |
| Data | Fictional starter pack, seeded on start | Real records; nothing is seeded |
| Sign-in | Demo accounts (`AUTH_MODE=demo`, `DEMO_MODE=true`) | OIDC only (`AUTH_MODE=oidc`, `DEMO_MODE=false`) |
| Clock | Fixed as-of date (2026-10-14) | Real time in the org's time zone |
| Model | None (recorded examples only) | Local Ollama on a private network |
| Where | Laptop, Render blueprint (`render.yaml`) | A machine or VM you control |

The app refuses to start in private mode without OIDC settings, a strong `SESSION_SECRET` and an organisation slug
(`check_production_settings`). Password sign-in (`/api/auth/login`, demo accounts only) returns 404 whenever `DEMO_MODE=false` or `AUTH_MODE=oidc`.
Document upload needs no extra service: the Docker image includes Tesseract OCR for scans and photos. Without the
`tesseract` binary (e.g. a bare local Python setup) PDFs, Word and text files still work, and scans are refused with
a clear message.

## 1. Local development (demo)

```bash
cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head && .venv/bin/python -m app.seed.seed
.venv/bin/uvicorn app.main:app --reload            # API on :8000; the analysis worker runs in-process
cd ../frontend && npm ci && npm run dev               # SPA on :5173, proxies /api
```

Or `docker compose up` (demo profile: app + Postgres; no model).

## 2. Private inference with Ollama

### Apple Silicon (native, recommended for a single Mac)

Docker on macOS has no GPU access, so run Ollama natively and bind it to loopback:

```bash
brew install ollama                                   # or the signed app from ollama.com
OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 ollama serve
ollama pull qwen3:8b                                  # one-time download; the only step that needs internet
```

Then in `backend/.env`: `OLLAMA_BASE_URL=http://127.0.0.1:11434`, `LLM_MODEL=qwen3:8b`. Pin the weights:

```bash
cd backend && .venv/bin/python -m app.ops model-status    # copy "digest" into LLM_MODEL_DIGEST
```

A different digest later (re-pull, tampering) makes the model "misconfigured" until the pin is updated.

### Linux server (Compose, private profile)

```bash
cp .env.example .env.private      # fill SESSION_SECRET, OIDC_*, POSTGRES_PASSWORD, OLLAMA_VERSION, LLM_MODEL_DIGEST
docker compose --profile provision run --rm ollama-pull     # one-time model download (egress network)
docker compose --profile private up -d db ollama app-private worker
```

- `ollama`, `db` and `worker` sit on the `private` network, declared `internal: true`: no route to the internet.
  No Ollama port is published. `OLLAMA_NO_CLOUD=1` disables cloud models and features.
- The app accepts only `OLLAMA_BASE_URL` hosts listed in `OLLAMA_ALLOWED_HOSTS` and only tags in
  `LLM_ALLOWED_MODELS`; cloud tags (`-cloud`, `:cloud`) are always rejected. There is no per-request endpoint.
- Pin `OLLAMA_VERSION` to a specific release you have tested; never `latest`.
- Network policy to apply on the host as well (defence in depth): deny outbound traffic from the Ollama container
  and the database; allow the app only to the identity provider and the SMTP/relay endpoints you use.
- Observed with Ollama 0.40.18: even with `OLLAMA_NO_CLOUD=1` the server schedules its own periodic "model
  recommendations" fetch from ollama.com (`OLLAMA_REMOTES` defaults to `ollama.com`). It carries no Graft data, but it
  is egress from the model host: on the native Mac setup block it with the firewall after the model pull; in Compose
  the `internal: true` network already prevents it.

### Model choice

`qwen3:8b` is the first benchmark candidate; `gpt-oss:20b` is the comparison when the hardware has ~16 GB free
for the model. Choose the default from `python -m eval.run_eval --mode live --model <tag>` (fixture accuracy,
cold and warm latency, resident memory). `docs/eval.md` keeps one row per model run, with the exact digest.
Set `LLM_THINK=false` for qwen3; gpt-oss takes `low`.

## 3. Identity (OIDC)

Register Graft as a confidential web client at your identity provider:

- redirect URI: `https://<host>/api/auth/oidc/callback` (`OIDC_REDIRECT_URI`)
- scopes `openid email profile`; authorization code flow with PKCE (S256)
- `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ORG_SLUG` (the Graft org people sign into)

Create the org and its first admin once (no password is stored; the admin signs in through OIDC by verified email):

```bash
docker compose --profile private run --rm app-private python -m app.ops create-org \
  --name "Acme" --slug acme --admin-name "Ada Admin" --admin-email ada@acme.example
```

Who gets in: an existing identity link, else an active member whose **verified** email matches, else (only if
`OIDC_GROUP_ROLE_MAP` is set) just-in-time provisioning from mapped groups, e.g.
`{"graft-pmo": "pmo_coordinator", "graft-tech-leads": "technical_owner"}`. Mapped roles are re-synced at every
sign-in. Suspending a member in People & Roles cuts access on their next request; sessions also expire after
`SESSION_HOURS`. State-changing requests require the CSRF token cookie echoed in `X-CSRF-Token`.

## 4. Evidence intake from a relay

```bash
python -m app.ops service-token --org acme --name mail-relay    # prints the token once; store it in the relay
```

The relay calls `POST /api/integrations/inbound` with `Authorization: Bearer <token>` and
`{external_id, received_at, sender, subject, body, author_role?, recipient_role?, case_ref?}` (≤ 64 KB,
body ≤ 20,000 characters). Re-delivery of the same `external_id` is a no-op; a different body under the same id is
rejected (409). Ambiguous messages wait in Inbox → Needs review. Revoke with `python -m app.ops revoke-token`.
Provider-specific registration (mail rules, ITSM webhooks) is operator configuration and is not in this repository.

## 5. Background processing

`ANALYSIS_WORKER=thread` runs the worker inside the web process (single container). With Compose `private`,
the web app uses `external` and the `worker` service runs `python -m app.worker`. Jobs live in the database: they
survive restarts, a crashed worker's lease expires after two minutes, and jobs wait (without spending attempts)
while the model is down. Inspect and retry with `python -m app.ops jobs` / `retry-jobs --org <slug>`.
Overdue reminders and escalations run every ten minutes in the worker, or now with `python -m app.ops reminders`.

## 6. Data protection, backups and restore

- **Transport:** terminate TLS in a reverse proxy in front of the app (Caddy, nginx). Cookies are `Secure`
  over HTTPS; set `FORWARDED_ALLOW_IPS` to the proxy address only.
- **At rest:** put the Postgres volume, the model volume, logs and backup files on encrypted storage (LUKS or
  the cloud provider's volume encryption; FileVault on a Mac). Postgres itself does not encrypt data files.
- **Credentials:** `POSTGRES_PASSWORD`, `SESSION_SECRET`, `OIDC_CLIENT_SECRET` and relay tokens come from the
  environment or a secret store, never from git.
- **Backup:** `python -m app.ops backup --out /backups/graft-$(date +%F).dump` (SQLite: online copy;
  Postgres: `pg_dump -Fc`). The file is written with mode 600. Encrypt before it leaves the host, e.g.
  `age -r <recipient> -o graft.dump.age graft.dump`, then delete the plaintext.
- **Restore (into an empty database only):**
  `python -m app.ops restore --from graft.dump --to <empty DATABASE_URL>`, then `alembic upgrade head`, then
  `python -m app.ops verify --database-url <url>` (row counts, every claim's quote at its offsets, every review
  citation resolvable in its org; non-zero exit on any failure).
- **Retention:** `python -m app.ops retention --org <slug>` prints what is eligible (dry run); add `--apply`.
  See docs/business-rules.md, "Retention", for what is kept and why.

## 7. Verification commands

```bash
cd backend && .venv/bin/pytest -q                       # 123 tests, synthetic data and stubbed provider
.venv/bin/python -m eval.run_eval --mode replay          # offline evaluation, recorded examples
.venv/bin/python -m eval.run_eval --mode live --model qwen3:8b   # real local inference, network-guarded
cd ../frontend && npm run build
```

## 8. Gates before processing real employee records

Each item must be checked off by an operator on the target environment. Status as of this commit:

| Gate | Status |
| --- | --- |
| Live evaluation on the chosen model with weights preloaded and internet blocked meets the release checks in docs/eval.md | **Not met** (see "Live measurements" below): agent and Ask checks pass live; extraction does not yet |
| Model digest pinned (`LLM_MODEL_DIGEST`) and `OLLAMA_VERSION` pinned | Open (operator) |
| PostgreSQL clean install, upgrade from the previous schema and downgrade/upgrade round trip | Open locally; automated in CI (`migrations-postgres`) on the next push |
| Restore of a Postgres backup into a disposable database passes `app.ops verify` | **Open**: only the SQLite round trip is verified (tests) |
| OIDC against the real identity provider (state, nonce, PKCE, group mapping) | Open: verified against a mocked issuer in tests only |
| TLS proxy, encrypted volumes, host egress policy for model and database | Open (operator) |
| Retention periods approved by the data owner | Open: defaults in docs/business-rules.md are assumptions |
| Closure exception policy decided (`allow_closure_exceptions`) | Default off |

Until every gate is closed, keep the AI capabilities disabled for the org (Settings → AI) or keep `OLLAMA_BASE_URL`
empty; the manual workflow (evidence, tasks, reviews, sign-off) does not depend on the model. Orgs created with
`python -m app.ops create-org` start with AI disabled for this reason.

### Live measurements (Apple M1 Pro, 16 GB, Ollama 0.40.18, `qwen3:8b` Q4_K_M, digest `500a1f067a9f…b8b41`)

Run with the model preloaded, Ollama bound to 127.0.0.1 with `OLLAMA_NO_CLOUD=1`, and the eval's socket guard
blocking every non-loopback connection.

| Check | Result |
| --- | --- |
| Provider behaviour (real server) | Cold start 10.6 s (4.7 s load), warm extraction ~4 s; timeout, busy (refused in 200 ms), oversized input, cloud tag (refused by Graft and by Ollama: 403) and a native tool-call turn all behave as specified |
| Full live eval, prompt `extract_v1` / schema `extract_v2` | 8/8 sources extracted live; agent and Ask probes all pass (cited, scoped, readiness deferred, unsupported refused); business fixtures 9 pass / 8 fail; Eva's E3/E4 conflict **not** detected (the model put a `reference` on non-access claims and merged facts into one quote; the verifier rejected them). Committed as `backend/eval/results/live_qwen3_8b.json` and in docs/eval.md |
| Prompt `extract_v2` / schema `extract_v3` (now the default), extraction fixtures only | 4 of 8 pass (E1, E2, E3 with all four expected claims, E5). Remaining failures: invented `confirmed_usable` from "All tools are available" / "access expected" and `initial_training/completed` from "training guide is available". Not yet a full eval run |
| Same, with qwen3 thinking on | 2 of 8, 16–167 s per source: rejected as the default |
| `gpt-oss:20b` | Not run: ~13 GB exceeds this machine's 11.8 GiB GPU budget; benchmark it on target hardware |

Next steps before enabling live extraction: a deterministic verifier check that an access claim names a specific
system, a full live eval on `extract_v2`/`extract_v3`, and a larger model on the target hardware.
