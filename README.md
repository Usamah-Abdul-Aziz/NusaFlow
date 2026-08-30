# NusaFlow

NusaFlow is a portfolio-grade supply chain control tower focused on inventory visibility, demand forecasting, alert handling, and what-if planning.

## Overview

This MVP starts with the foundation layer:
- relational data model for core supply-chain entities
- FastAPI backend exposing operational APIs
- Next.js dashboard that consumes live API data
- SQLite-backed local development database with a Postgres-ready configuration path

This project uses synthetic data and simulated logistics events for demonstration purposes.

## Architecture

- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: FastAPI + SQLAlchemy + Pydantic
- Database: SQLite for local development; PostgreSQL-ready via `DATABASE_URL`

## Getting started

> Use Python 3.12 for the backend environment. FastAPI/Pydantic 2.x is not compatible with Python 3.13 in this setup.

### Backend

```bash
cd backend
py -3.12 -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Database migrations (Alembic)

Schema changes are managed by Alembic instead of `Base.metadata.create_all()`. Common commands, run from `backend/`:

```bash
alembic upgrade head                          # apply all pending migrations (run this before starting the app)
alembic revision --autogenerate -m "message"  # after changing a model in app/models.py
alembic downgrade -1                          # roll back the most recent migration
```

Migrations connect using the same `DATABASE_URL` the app uses (via `app/config.py`), so there's one source of truth for the connection string. Seeding still happens automatically on app startup and is idempotent (safe to restart without duplicating data) — but table creation itself is now migration-only, so a fresh clone must run `alembic upgrade head` once before the first `uvicorn` start.

Configuration

- `DATABASE_URL`: SQLAlchemy connection string. Defaults to local SQLite; set to a Postgres URL (e.g. Supabase) for hosted environments.
- `BACKEND_URL`: read by `frontend/next.config.mjs` (server-side only) to build the `/api/*` rewrite target. Defaults to `http://localhost:8000`; set this in your deployment environment (e.g. Vercel project settings) to point at the real backend host — do **not** use a `NEXT_PUBLIC_*` var for this, since rewrites run on the Next.js server, not the browser.
  **Note:** unlike the backend (which reads the shared root `.env` via `app/config.py`), Next.js only auto-loads env files from *inside* `frontend/` (`frontend/.env.local`, etc.) — it does not read the repo-root `.env`. For local dev this doesn't matter (the `http://localhost:8000` default already matches), but for anything else, set `BACKEND_URL` either in `frontend/.env.local` or directly in your hosting platform's environment variable settings, not by editing the root `.env`.
- CACHE_TTL (seconds): Controls how long aggregated demand values are cached in-memory. Default is 300 seconds. Set via environment variable CACHE_TTL.
- ADMIN_API_KEY: A secret token required to call admin endpoints such as cache flush. Set this to a strong secret in production and never commit it to source control. Example: export ADMIN_API_KEY=your-secret

All backend configuration is loaded once through `app/config.py` (a single `pydantic-settings` `Settings` object), which reads from `.env` at the repo root (falling back to `backend/.env` if you keep one there). If you edit `.env`, restart the backend — values are read once at process start, not re-read per request.

Testing the admin cache flush endpoint

The backend exposes a protected endpoint to flush the in-memory cache:

- POST /api/v1/admin/cache/flush

Authentication:
- Provide header `X-Admin-Token: <ADMIN_API_KEY>` or `Authorization: Bearer <ADMIN_API_KEY>`

Examples (PowerShell / Windows):

# Start backend with ADMIN_API_KEY set for this shell
$env:ADMIN_API_KEY = 'test-admin-token'
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# From another shell, call without token (should return 401 or 503 if not configured)
curl -X POST http://127.0.0.1:8000/api/v1/admin/cache/flush -i

# Call with wrong token (should return 401)
curl -X POST http://127.0.0.1:8000/api/v1/admin/cache/flush -H "X-Admin-Token: wrong-token" -i

# Call with correct token (should return 200 and {"detail":"cache flushed"})
curl -X POST http://127.0.0.1:8000/api/v1/admin/cache/flush -H "X-Admin-Token: test-admin-token" -i

Security notes

- The current implementation uses a single ADMIN_API_KEY for simplicity. For production, put admin endpoints behind proper authentication (OAuth2, JWT, or an admin-only firewall), and require TLS.
- The cache flush endpoint clears only the in-memory cache for the running process. In multi-process deployments use a shared cache like Redis and provide a distributed flush mechanism.

Production recommendations

1) Use a shared cache (Redis)
- Replace the in-memory cache used by avg_daily_demand with Redis (or another shared cache) so cached values persist across processes/instances.
- Use a predictable cache key scheme (product:warehouse:window_start) and set appropriate TTLs.
- To implement distributed cache invalidation, publish a "flush" message on a Redis channel and have all instances subscribe and clear their local caches (or simply rely on Redis TTL and key deletion).

2) Secure admin endpoints
- Do not rely on a single static ADMIN_API_KEY in production. Options:
  - Protect admin endpoints with OAuth2 or JWT tokens issued to admin users.
  - Restrict access using network controls (VPC, IP allowlists) and place admin endpoints behind an internal-only gateway.
  - Use mutual TLS for service-to-service calls when possible.

3) Enforce TLS
- Always serve the backend over HTTPS in production. Use a TLS terminator (load balancer, reverse proxy) or enable TLS in your hosting platform.
- Ensure admin API endpoints are only reachable via HTTPS and require strong authentication.

4) Process model and deployment
- When running multiple worker processes (uvicorn gunicorn, or multiple containers), remember that in-memory caches are per-process. Prefer a shared cache for consistency.
- If you keep an in-memory cache for performance, implement a distributed invalidation mechanism using Redis pub/sub or a message broker.

5) Monitoring and rates
- Add monitoring for cache hit/miss rates, and alerts for high cache miss rates which may indicate configuration or seeding issues.
- Rate-limit admin endpoints to reduce risk of abuse.

6) Secrets
- Store ADMIN_API_KEY and other secrets in a secure secrets manager or environment provided by your hosting platform. Do not commit secrets to source control.


### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 to view the app. `/` is a public landing page (Explore Demo / Create Workspace / Log in) — everything else lives under `/dashboard` and requires being logged in (`middleware.ts` redirects to `/login` otherwise). Pages: Overview (`/dashboard`), Inventory (`/dashboard/inventory`), Shipments (`/dashboard/shipments`, click into a shipment for its event timeline + "Simulate next step"), Suppliers (`/dashboard/suppliers`), Forecast (`/dashboard/forecast`), Replenishment (`/dashboard/replenishment`, click a row for the plain-English formula breakdown), Simulation (`/dashboard/simulation`, sliders with a debounced live preview — see Phase 7 below), Alerts (`/dashboard/alerts`, with acknowledge/resolve actions and a manual "Re-run alert engine" button). Uses [Recharts](https://recharts.org) for the forecast chart — the only charting dependency in the project, added because AGENTS.md section 6 names it as the preferred lightweight option and hand-rolling a historical/forecast/uncertainty-band line chart in raw SVG would be substantially more code to maintain for the same result.

**Gotcha if you add a new top-level directory under `frontend/`:** `tailwind.config.ts`'s `content` array has to list it explicitly (`app/`, `components/`, and `lib/` are covered). Tailwind's JIT only generates CSS for classes it finds in those globs — a class used only in an unlisted directory silently produces no CSS at all (no build error, no warning), which is exactly what happened when `components/` was added without updating this config: the sidebar's `md:w-56` never made it into the compiled stylesheet, so the whole layout collapsed to the right at desktop widths.

## API

Every endpoint below except `/health` and `/api/v1/auth/*` requires `Authorization: Bearer <token>` — see Authentication & Workspaces below.

- `GET /api/v1/health`
- `POST /api/v1/auth/signup` — creates a new, EMPTY workspace + its first user; returns a token
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/demo` — no credentials needed; logs into the shared, pre-seeded demo workspace
- `GET /api/v1/auth/me`
- `GET /api/v1/overview`
- `GET /api/v1/inventory`
- `GET /api/v1/inventory/analysis` — avg daily demand, days of inventory, stockout risk (paginated; filter by `sku`/`warehouse`)
- `GET /api/v1/shipments`
- `GET /api/v1/shipments/{id}`
- `GET /api/v1/shipments/{id}/events` — full event timeline for one shipment
- `POST /api/v1/shipments/{id}/simulate/advance` — advance a shipment one step (Created → Departed → Checkpoint/Delay → Delivered)
- `GET /api/v1/suppliers`
- `GET /api/v1/demand`
- `GET /api/v1/alerts` — filter with `?status=`, `?severity=`, `?alert_type=`
- `POST /api/v1/alerts/generate` — re-run all 6 alert rules now (also runs automatically on startup)
- `PATCH /api/v1/alerts/{id}?status=` — set to `ACKNOWLEDGED` or `RESOLVED`
- `GET /api/v1/forecasts` — summary list of every pair's latest forecast (method, backtest accuracy)
- `GET /api/v1/forecasts?sku=&warehouse=&horizon_days=` — full forecast for one pair: recent actuals + forecast points with an uncertainty band
- `POST /api/v1/forecasts/generate` — regenerate all forecasts (also runs automatically on startup); pass `?sku=&warehouse=` to regenerate just one pair
- `GET /api/v1/replenishment` — every pair's current recommendation; `?needs_reorder=true` filters to only recommended_quantity > 0; `?sku=&warehouse=` narrows to one pair
- `POST /api/v1/replenishment/generate` — regenerate all recommendations (also runs automatically on startup, after forecasts); pass `?sku=&warehouse=` to regenerate just one pair
- `POST /api/v1/simulations/run` — compute baseline-vs-simulated for the given scenario params, NOT persisted (live preview)
- `POST /api/v1/simulations` — save a named scenario (persists both the scenario and its baseline/simulated result pair)
- `GET /api/v1/simulations` / `GET /api/v1/simulations/{id}` — list saved scenarios / one scenario's detail
- `POST /api/v1/simulations/{id}/run` — re-execute a saved scenario against current real data (fresh result pair)
- `POST /api/v1/admin/cache/flush` — protected, see Configuration below
- `POST /api/v1/admin/demo/reset` — protected; wipes and re-seeds the shared demo workspace (see Authentication & Workspaces)

## Authentication & Workspaces

A deliberate expansion beyond the original 7-phase roadmap (AGENTS.md section 5 originally listed "large-scale multi-tenant SaaS" as a non-goal — this is a portfolio-scoped version of that, not the enterprise version).

**Model:** every account belongs to exactly one `Workspace` (no multi-workspace-per-user, no workspace switcher — kept deliberately simple). Nearly every domain table (Product, Warehouse, Supplier, Inventory, Shipment, Alert, Forecast, ReplenishmentRecommendation, SimulationScenario) carries a `workspace_id` and is filtered by it on every query. `DemandRecord` is the one exception — see the comment on that model in `app/models.py` for why. Two workspaces can each have their own warehouse coded `WH-JKT` or product SKU'd `SKU-101` — uniqueness on those fields is scoped per-workspace (`UniqueConstraint(workspace_id, code)`), not global.

**Auth:** JWT Bearer tokens, not server-side sessions or cookies-with-credentials — chosen specifically because the deployment target is frontend (Vercel) and backend (Render) on different origins, where cross-origin cookies need SameSite=None/Secure and careful CORS credential handling. The frontend stores the token in a plain (non-httpOnly) cookie so `middleware.ts` can gate `/dashboard/*` routes server-side, and attaches it as `Authorization: Bearer <token>` on every API call (see `frontend/lib/api.ts` / `frontend/lib/auth.ts`). Passwords are hashed with bcrypt. See `app/auth.py`'s module docstring for what this intentionally does NOT include (refresh token rotation, email verification, password reset, rate limiting) — sized to match AGENTS.md's existing "no Enterprise SSO / complex role hierarchy" stance, not enterprise-grade.

**Demo workspace:** one well-known workspace (`is_demo=True`, seeded automatically on startup — this is the same synthetic dataset all 7 phases were built and tested against) with a single shared "Demo User" account. Clicking "Explore Demo" on the landing page calls `POST /auth/demo`, which logs into that same account every time — no per-visitor sandbox. That means visitors share (and can see each other's edits to) demo state — acknowledging alerts, advancing shipments, saving simulation scenarios all persist. `POST /admin/demo/reset` (protected by `ADMIN_API_KEY`, same as `/admin/cache/flush`) wipes and re-seeds it back to a clean state; there's no scheduler to run this automatically (see Known limitations), so it's a manual "run this before you show someone the demo" step.

**New workspaces start empty.** `POST /auth/signup` creates a workspace with zero data — no synthetic seed. Its owner adds their own suppliers/warehouses/products (not yet exposed as create endpoints — see Known limitations) or explores read-only until they do.

## Notes

Current progress: all 7 phases from the original roadmap are implemented — Foundation, Inventory Intelligence, Real-Time Shipment Monitoring, Alert Engine, Demand Forecasting, Replenishment Recommendation, and What-If Simulation. Plus a Workspace/Auth layer beyond the original roadmap (see Authentication & Workspaces above).

What-If Simulation (Phase 7): `app/simulation_service.py` takes four parameters (demand change %, supplier lead-time delta, shipment delay delta, safety stock change %) and computes five metrics — stockout risk count, late shipments, service level %, estimated replenishment cost, and replenishment requirement — for both a baseline (all deltas zero) and the user's scenario, using the exact same calculation function for both so the comparison is guaranteed apples-to-apples. Every metric reuses an earlier phase's formula rather than re-deriving it (stockout risk mirrors Phase 2's threshold shape, replenishment/cost mirrors Phase 6's formula, late shipments mirrors Phase 3's delay calculation) — it's the same read-only trick as `alert_engine.py` and `replenishment_service.py`, just applied under counterfactual inputs. Nothing here writes to Inventory, Shipment, or Forecast — the only writes are to the simulation's own `SimulationScenario`/`SimulationResult` tables, and only for `POST /simulations` (save) or `POST /simulations/{id}/run` (re-run a saved one); `POST /simulations/run` (no id) computes and returns a comparison without persisting anything, for the frontend's debounced live-slider preview.

Replenishment Recommendation (Phase 6): `app/replenishment_service.py` applies the formula from AGENTS.md section 11 exactly — `max(Forecast Demand + Safety Stock - Current Stock - Incoming Stock, 0)`. "Forecast Demand" is grounded in real Phase 5 output: the sum of `estimated_demand` over the product's own `lead_time_days` (not the supplier's — a single product can arrive via different suppliers per shipment, so there's no one fixed "the" supplier lead time to anchor on; Product.lead_time_days is the stable per-SKU value already used elsewhere). Every recommendation stores its full inputs alongside the result so the API can return a plain-English `explanation` showing the arithmetic — AGENTS.md section 11: "Every recommendation must be explainable." Depends on a Forecast already existing for the pair (runs after `generate_all_forecasts` on startup); pairs without one are skipped, not guessed at.

Alert Engine (Phase 4): `app/alert_engine.py` runs 6 rule-based checks (`LOW_STOCK`, `CRITICAL_STOCK`, `STOCKOUT_RISK`, `SHIPMENT_DELAY`, `SUPPLIER_DELAY`, `DEMAND_SPIKE`) and reconciles the result against the `alerts` table: a condition that's newly true opens an alert, one that's still true gets its severity/description refreshed in place (never duplicated), and one that's no longer true gets auto-resolved. It reuses Phase 2/3 calculations rather than re-deriving them — STOCKOUT_RISK calls the same `analyze_inventory_item()` used by `/inventory/analysis`, SHIPMENT_DELAY calls the same `effective_status()`/`compute_delay_days()` used by `/shipments`. Runs automatically on app startup and can be re-triggered via `POST /alerts/generate`.

Demand Forecasting (Phase 5): `app/forecast_service.py` follows the pipeline in AGENTS.md section 11 literally — Historical Data → Data Cleaning (missing calendar days filled with 0) → Feature Engineering (weekday-of-week multipliers learned from real history) → two baseline models (flat moving average vs. weekday-seasonal) → Evaluation (both are backtested on the most recent 14 real days; whichever has the lower MAE is used) → Forecast (the winning model is re-fit on full history and projected 30 days out). No pandas/numpy/scikit-learn — at ~240 data points per pair, plain Python is simpler and adds zero new dependencies (AGENTS.md section 23: don't add a dependency unless it's actually necessary). Forecasts report `estimated_demand` with a `lower_bound`/`upper_bound` band derived from real backtest residual spread — deliberately not phrased as a guarantee (AGENTS.md section 11). Runs automatically on startup and can be re-triggered via `POST /forecasts/generate`.

## Deployment

Target stack: frontend on **Vercel**, backend on **Render**, database on **Supabase** (Postgres). This section is the actual sequence, in order — later steps need values from earlier ones.

### 1. Database — Supabase

1. Create a Supabase project.
2. Project Settings → Database → Connection string → copy the **URI** under **Direct connection** (port `5432`), not the pooler URL on `6543`. Render runs one persistent process with its own SQLAlchemy connection pool, which the direct connection is built for — the pgbouncer transaction pooler is for serverless/many-short-lived-connections deployments, which this isn't.
3. That's it for setup — don't run migrations here manually. Render's start command (below) runs `alembic upgrade head` against this database automatically on every deploy, and `app/config.py` accepts the connection string exactly as Supabase gives it (no need to change `postgresql://` to `postgresql+psycopg2://`).

### 2. Backend — Render

1. Push this repo to GitHub/GitLab, then in Render: **New +** → **Blueprint**, point it at the repo. It reads `render.yaml` at the repo root and creates the service with `rootDir: backend` already configured.
   - (No Blueprint support, or prefer clicking through manually? Create a **Web Service** by hand with: Root Directory `backend`, Build Command `pip install -r requirements.txt`, Start Command `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`, Health Check Path `/api/v1/health`.)
2. In the service's **Environment** tab, set the variables `render.yaml` marks `sync: false` (these are secrets/environment-specific, so they're deliberately not in the committed file):
   - `DATABASE_URL` — the Supabase connection string from step 1.
   - `ADMIN_API_KEY` — pick a strong secret (protects `/admin/cache/flush` and `/admin/demo/reset`).
   - `CORS_ORIGINS` — leave blank for now; comes back in step 4.
   - `SECRET_KEY` is already handled — `render.yaml` sets `generateValue: true`, so Render generates a secure random one itself.
3. Deploy. First boot runs all 6 Alembic migrations against the empty Supabase database, then seeds the demo workspace (same synthetic dataset this whole project was built and tested against). Check `/api/v1/health` on the resulting `*.onrender.com` URL once it's up.

### 3. Frontend — Vercel

1. **New Project** → import the same repo → set **Root Directory** to `frontend`. Vercel auto-detects Next.js; no other build config needed.
2. Project Settings → Environment Variables → add `BACKEND_URL` = the Render URL from step 2 (e.g. `https://nusaflow-backend.onrender.com`). This is read server-side by `next.config.mjs`'s rewrite — see that file's comments for why it's not a `NEXT_PUBLIC_*` var.
3. Deploy.

### 4. Close the loop: CORS

Go back to Render → Environment → set `CORS_ORIGINS` to the Vercel URL(s) from step 3, comma-separated if there's more than one (e.g. production + a preview deployment). Restart the service. Until this is set, the deployed frontend's requests will be blocked by the browser's CORS check even though the API itself is reachable — the symptom is requests failing with no response body, not a clean error.

### Verifying it worked

Visit the Vercel URL, click **Explore Demo**, confirm the dashboard loads real data (not stuck on a loading state, which usually means either `BACKEND_URL` or `CORS_ORIGINS` is still wrong). `POST /admin/demo/reset` (with `X-Admin-Token: <ADMIN_API_KEY>`) is the way to restore the shared demo workspace to a clean state after it's been shared around — see Authentication & Workspaces above for why that's needed.

## Testing

From `backend/`, with the virtualenv active:

```bash
python -m unittest discover tests -v
```

- `test_inventory_analysis.py`, `test_shipment_service.py`, `test_alert_engine.py`, `test_forecast_service.py`, `test_replenishment_service.py`, `test_simulation_service.py`, `test_auth.py` — unit tests that construct models/services directly against an in-memory SQLite DB. Fast, but they don't exercise the actual HTTP routing or response-serialization code in `main.py`.
- `test_api_endpoints.py` — hits every route through FastAPI's `TestClient` (real routing + the actual dict/relationship access each endpoint does). This is the layer that catches bugs the unit tests structurally can't see — e.g. it's what would have caught `GET /demand` 500ing because `DemandRecord.warehouse` wasn't wired up as a relationship, since that only broke inside the endpoint's own serialization loop, not in any service function. Also includes `test_workspace_isolation_across_two_accounts` — the single most important test in this project: confirms a second workspace's token gets an empty `/shipments` list and a `404` (not real data) when given the first workspace's real object id, both for reading and for mutating.

## Known limitations

- **No background scheduler.** Shipment lifecycle progress (`Created → Departed → Checkpoint/Delay → Delivered`) is advanced on demand via `POST /shipments/{id}/simulate/advance` rather than by a cron/worker process, so it keeps working on free-tier hosts where a long-lived background process isn't guaranteed to stay alive. Delay detection itself *is* fully live — `status`/`delay_days` in API responses are computed from real dates on every request, so a shipment can show up as overdue without anyone triggering a step. The alert engine follows the same pattern: it runs on-demand (startup + `POST /alerts/generate`), not on a timer.
- **In-memory cache is per-process.** `CACHE_TTL`-based caching in `inventory_analysis.py` won't stay consistent across multiple worker processes. A shared cache (Redis) would be needed for a multi-worker deployment.
- **SQLite in local dev, Postgres in production — verified, not just assumed.** SQLite is more lenient about constraints than Postgres, so this was actually tested against a real local Postgres instance (not just SQLite) before writing this deployment guide: all 6 migrations run cleanly from empty, the native Postgres `ENUM` types (vs. SQLite's CHECK-constraint emulation) come out correctly, composite unique constraints behave the same, and the full demo dataset seeds and serves identical numbers on both databases. `postgresql://` connection strings work as Supabase provides them, no rewriting needed.
- **Render's free tier spins down after inactivity.** The first request after ~15 minutes idle will be slow (the service cold-starting) rather than erroring — expected free-tier behavior, not a bug. A paid Render plan removes this if it matters for a live demo.
- **Forecasting can't distinguish a temporary spike from a permanent level shift.** Both baseline models scale from a 14-day recent-average "level" — if the last few days happened to include a real demand spike, that pulls the projected level up along with it, with no decay built in. A short-term spike will look like it's expected to continue at full strength for the whole 30-day horizon. Handling that properly (e.g. anomaly-aware smoothing, or explicitly modeling spike decay) is a reasonable next step beyond the Phase 5 baseline scope.
- **Frontend Next.js version has known, unpatched-here CVEs — checked specifically against `middleware.ts`.** `next` is pinned to `14.2.35`. Three Next.js middleware-authorization-bypass CVEs exist in the wild: `CVE-2025-29927` (fixed in `14.2.25` — we're above it), and `CVE-2026-44575`/`CVE-2026-45109` (both only affect `15.2.0` and above per their official advisories — 14.x was never in the affected range). So `middleware.ts`'s route-gating isn't known-vulnerable at the pinned version. `npm audit` still flags a few unrelated *high* advisories fixed only in Next 15/16 — Image Optimizer, WebSocket upgrades, i18n routing — none of which this app uses (no `next/image`, no i18n config). Upgrading to Next 16 to clear those is a reasonable follow-up, but it's a major-version jump with real breaking-change risk that needs its own dedicated testing pass rather than a drive-by bump.
- **`middleware.ts` is a UX convenience, not the real authorization boundary — on purpose, and this matters given the CVE history above.** Every security writeup on these middleware-bypass CVEs gives the same remediation: "enforce authorization at the route/API layer, don't rely solely on middleware." This app already does that independently of the CVEs — `middleware.ts` only redirects an unauthenticated browser to `/login` before a page even loads; the actual data comes from `fetchJson` calls straight to the FastAPI backend, which independently re-validates the JWT on every single request via `get_current_workspace_id` (see `app/auth.py`). Even a hypothetical future middleware bypass would only expose the empty dashboard shell HTML, not real data — the backend would still 401 every API call without a valid token.
