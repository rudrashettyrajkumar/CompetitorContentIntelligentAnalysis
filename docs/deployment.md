# Deployment

The UI and API deploy **together as one container**. FastAPI serves the built
React SPA (`frontend/dist`) at `/` and the API at `/api/*` on a single port. The
frontend calls relative `/api/...` URLs and there is no CORS middleware, so the
SPA must be served from the same origin as the API — do not split them without
adding a base-URL env to `frontend/src/api.ts` + `CORSMiddleware` to the API.

**Single instance only.** Pipeline runs execute as in-process background threads
and (when enabled) APScheduler runs in-process too. Never scale past one instance.

The Dockerfile `CMD` binds `$PORT` when the platform injects one (Render) and
falls back to `8000` (Fly, docker-compose, local).

---

## Current target: Render free tier (`render.yaml`)

$0: a free web service + a free Render Postgres. Deploys from GitHub.

### Steps

1. Commit and push the branch containing `render.yaml`.
2. Render dashboard → **New +** → **Blueprint** → select the repo → **Apply**.
   This creates the `cci-db` Postgres and the `competitor-intelligence` web service.
3. When prompted, set the three secrets: `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`,
   `GROQ_API_KEY` (at least one required).
4. First build takes ~10–15 min (heavy deps). App URL: `https://competitor-intelligence.onrender.com`.

`DATABASE_URL` is wired automatically from `cci-db` via `fromDatabase`.
`build_engine()` normalizes the `postgres://` scheme and pins `psycopg2`.

### Free-tier limitations (accepted for now)

| Limit | Effect | Mitigation |
|---|---|---|
| Web service **sleeps after ~15 min idle** | Cold start ~30–60s; a pipeline run in progress is **killed** if the instance sleeps | Keep the run page open (it polls every 2s and holds the instance awake), or ping via cron (below) |
| **APScheduler disabled** (`SCHEDULER_ENABLED=false`) — it can't run on a sleeping instance | The recurring intelligence loop (EPIC-08) does not fire | External cron → `POST /api/runs` (below) |
| Free Postgres is **suspended 30 days after creation** | All data lost | Before day 30, swap to Neon/Supabase (below) or upgrade the DB |
| 750 free instance-hours/month | One service is fine if it sleeps | — |

### External cron (replaces the in-process scheduler)

Use a free scheduler (cron-job.org, GitHub Actions `schedule`, etc.) to POST a run
on your cadence. This also wakes the sleeping service and DB.

```
POST https://competitor-intelligence.onrender.com/api/runs
Content-Type: application/json

{"period_days": 30, "adapter": "mock"}
```

### Moving off Render Postgres later (Neon / Supabase)

1. Create the DB on Neon (auto-resumes on query — best fit) or Supabase (use the
   **pooler / IPv4** connection string, port 6543).
2. In `render.yaml`: delete the `databases:` block, change the `DATABASE_URL`
   env entry from `fromDatabase:` to `sync: false`.
3. Set `DATABASE_URL` in the Render dashboard to the new connection string
   (`postgresql://...` — the scheme is normalized in code).
4. Redeploy. Schema is recreated on first boot (`create_all`); existing data is
   not migrated automatically.

---

## Alternative: Fly.io + SQLite volume (`fly.toml`)

Paid (Fly has no free tier; the volume bills monthly), but no cold starts and the
in-process scheduler works. No local Docker needed — remote builder.

```bash
curl -L https://fly.io/install.sh | sh          # install flyctl
fly auth login                                    # `! fly auth login` in Claude Code

fly launch --no-deploy --copy-config --name <app-name> --region <region>
fly volumes create cci_data --size 1 --region <region> --yes
fly secrets set OPENROUTER_API_KEY=... NVIDIA_API_KEY=... GROQ_API_KEY=...
fly deploy --remote-only                          # later deploys: just this line
```

`fly.toml` sets `SCHEDULER_ENABLED=true`, `DATABASE_URL=sqlite:////data/app.db`
(absolute path on the volume), and `auto_stop_machines=off` to keep the scheduler alive.

---

## Environment reference

| Var | Render (free) | Fly | Notes |
|-----|---------------|-----|-------|
| `LLM_FAKE_MODE` | `false` | `false` | live provider chain |
| `SEED_DEMO` | `false` | `false` | skip the fake-LLM demo seed run |
| `DATABASE_URL` | from `cci-db` | `sqlite:////data/app.db` | Postgres scheme normalized + psycopg2-pinned in `build_engine` |
| `SCHEDULER_ENABLED` | `false` | `true` | in-process APScheduler; off on sleepy free tier |
| `LOG_LEVEL` | `INFO` | `INFO` | |
| `OPENROUTER_API_KEY` / `NVIDIA_API_KEY` / `GROQ_API_KEY` | secrets | secrets | ≥1 required; roster in `config/models.yaml` |
| `APIFY_TOKEN` | optional | optional | only if `collection.adapter` in `config/app.yaml` is `apify` |

## First run after deploy

With `SEED_DEMO=false` the database starts empty; tables are created on first boot.
Then, in the dashboard:

1. Upload a competitor list (**Competitors → upload**, `.xlsx` — template at
   `data/input/competitors_template.xlsx`).
2. Start a run. The pipeline collects (mock adapter by default — set
   `collection.adapter: apify` in `config/app.yaml` for real LinkedIn data),
   classifies, analyzes, and generates the strategy + 30-day calendar.

## Schema changes

There is no Alembic. Startup runs `Base.metadata.create_all()` — creates missing
tables, never alters existing ones. A future version that changes a column needs a
manual migration or a DB wipe. Add Alembic before the second schema version.
