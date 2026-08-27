#!/bin/sh
set -e

# Seed a fake-LLM demo run on first boot so the dashboard is populated out of the
# box. Skips when the DB already has a run (later restarts, real runs, mounted
# volume). SEED_DEMO=false disables it entirely.
if [ "${SEED_DEMO:-true}" = "true" ]; then
  python - <<'PY' || true
import os
import sqlalchemy as sa

from app.db.engine import _normalize_pg_url  # normalizes postgres:// + pins psycopg2

url = _normalize_pg_url(os.environ.get("DATABASE_URL", "sqlite:///data/app.db"))
try:
    eng = sa.create_engine(url)
    with eng.connect() as c:
        n = c.execute(sa.text("select count(*) from runs")).scalar()
    # 0 -> seed (7); >0 -> already populated, skip (0)
    raise SystemExit(7 if not n else 0)
except SystemExit:
    raise
except Exception:
    # no DB / no `runs` table yet -> seed
    raise SystemExit(7)
PY
  if [ $? -eq 7 ]; then
    echo "[entrypoint] seeding demo run..."
    LLM_FAKE_MODE=true python -m app.demo || echo "[entrypoint] demo seed failed, continuing"
  else
    echo "[entrypoint] DB already has data, skipping demo seed"
  fi
fi

exec "$@"
