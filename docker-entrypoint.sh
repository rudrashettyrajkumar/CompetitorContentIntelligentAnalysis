#!/bin/sh
set -e

# Seed a demo run on first boot so the dashboard is populated on `docker compose up`.
# Skips if the DB already has data (subsequent restarts, mounted volume).
if [ "${SEED_DEMO:-true}" = "true" ]; then
  python - <<'PY' || true
import os, sqlalchemy as sa
url = os.environ.get("DATABASE_URL", "sqlite:///data/app.db")
try:
    eng = sa.create_engine(url)
    with eng.connect() as c:
        n = c.execute(sa.text("select count(*) from runs")).scalar()
    raise SystemExit(0 if n and n > 0 else 7)
except SystemExit:
    raise
except Exception:
    raise SystemExit(7)
PY
  if [ $? -eq 7 ]; then
    echo "[entrypoint] seeding demo run..."
    LLM_FAKE_MODE=true python -m app.demo || echo "[entrypoint] demo seed failed, continuing"
  fi
fi

exec "$@"
