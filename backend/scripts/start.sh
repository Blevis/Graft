#!/bin/sh
# Container entrypoint. Migrations always run; the fictional demo seed runs ONLY when DEMO_MODE=true.
set -e
alembic upgrade head
if [ "${DEMO_MODE:-false}" = "true" ]; then
  python -m app.seed.seed
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
