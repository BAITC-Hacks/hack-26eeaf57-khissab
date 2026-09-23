# Career Quest

HackAlem AI, Halyk Bank track, Case 1: Career Quest.

Career Quest is an offline-first employee development navigator. It recommends 1-3 next development activities from local JSON/CSV starter-kit data, explains the decision with multi-factor rationale, and shows HR where development is lagging.

## Status

P0 scaffold and P1 dataset loader/validation are in place. The backend seeds SQLite on startup and exposes `/health`; the frontend is still a placeholder. The engine, explanation layer, business API endpoints, UI, and final polish follow in P2-P6.

## Architecture

```text
React + Vite + Tailwind
        |
        | HTTP
        v
FastAPI backend
        |
        +-- loader.py   -> validates starter-kit JSON/CSV into SQLite
        +-- engine.py   -> deterministic recommendation scoring
        +-- explain.py  -> LLM rationale with offline template fallback
        |
        v
SQLite in /storage
```

## One-Command Run

```bash
docker compose up
```

Docker is the primary run path. Before starting a fresh clone, place the separately supplied starter kit in `data/` as described below. Open the frontend at http://localhost:5173 and backend health check at http://localhost:8000/health.

`docker compose up` works fully without any API key via the deterministic template fallback (explanation layer scheduled for P3). `.env.example` is used by Compose by default. `LLM_MODEL` selects the optional explanation model; `LLM_API_KEY` is optional. Recommendation selection remains local. Runtime must work offline; the initial image/dependency build requires packages and base images to be available or cached before disconnecting.

`DATABASE_URL=sqlite:////app/storage/career_quest.sqlite3` points to `/app/storage` in the container, bind-mounted from the repo's gitignored `/storage/` directory. First startup creates the directory/file and seeds it transactionally. Subsequent starts validate the source dataset but preserve the existing database, including progress and any later uploads. No prebuilt database or secret is required or committed.

## Local run without Docker

This is the fallback for verification when Docker is unavailable. Use Python 3.12 (matching the backend image) and Node.js 20+ with npm. Run from the repository root, with the starter kit already in `data/`.

Backend, terminal 1:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
export DATA_DIR=./data
export DATABASE_URL=sqlite:///./storage/career_quest.sqlite3
export LLM_MODEL=gpt-4o-mini
export LLM_API_KEY=
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend, terminal 2, also starting from the repository root:

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev -- --host 127.0.0.1
```

Open http://localhost:5173 and verify the backend with `curl http://127.0.0.1:8000/health` (returns `{"status":"ok"}`). Install dependencies once while online or from a local cache; startup, data loading, and the planned template fallback require no network service or API key.

The local DB URL creates `storage/career_quest.sqlite3` under the repository root, inside gitignored `/storage/`. The loader also defaults to this repo-local path and `data/` when the environment variables are unset. Local commands explicitly override the container-only `/app/...` paths from `.env.example`; Python does not automatically load that file.

## Data

The starter kit is copied locally into the repo's `/data` directory from `case_1/career_quest_dataset/`. On a fresh clone, obtain the starter kit separately and run from the repository root:

```bash
mkdir -p data
cp -R case_1/career_quest_dataset/. data/
```

This copies the files and leaves the original starter kit in place.

`/data` is gitignored and must not be committed. The original `case_1/` starter-kit folder is also kept locally and gitignored.

Expected starter-kit counts:

- 200 employees
- 40 events
- 60 skills
- 2,743 activity history rows

`skills.json` also supplies 32 role/grade profiles, the proficiency scale, and the `2026-10-01` snapshot date. The loader preserves all JSON fields and metadata, parses optional CSV numbers as integers or null, and leaves assessed skills and history unchanged for the engine to interpret.

## Loader Verification (P1)

The loader and its tests use only Python's standard library, so they can run offline without installing the backend dependencies:

```bash
python3 -m backend.loader --data-dir ./data --database-url sqlite:///:memory:
python3 -m unittest discover -s backend/tests -v
```

The first command validates and imports into a temporary in-memory SQLite database. Expected counts are `employees=200`, `events=40`, `skills=60`, `activity_history=2743`, and `role_profiles=32`, with `reference_errors=0`. The starter-kit smoke test asserts these counts; it is explicitly skipped if the uncommitted dataset is absent. Synthetic validation tests still run without it. Counts are test expectations, not loader limits, so additional profiles/history in the same schema are supported.

To create the persistent database locally before starting the server:

```bash
python3 -m backend.loader --data-dir ./data --database-url sqlite:///./storage/career_quest.sqlite3
```

Validation checks unique skill, employee, event, history, and role/grade IDs; all skill references in employee skills, role requirements, critical skills, event gains, and prerequisites; employee role/grade and career-goal references; manager IDs (including Lead/same-department constraints); event target roles/grades; and history employee/event IDs. Invalid reference diagnostics include the offending record and field. Any validation error exits nonzero before database writes. SQLite foreign keys additionally enforce employee/manager, role/grade, and history relations.

P1 covers dataset ingestion and validation as the foundation for the TZ's profile/history and additional test-profile requirements. The upload endpoint and user-facing must-have scenarios remain scheduled for later phases; no recommendation or trap-profile result is claimed yet.

## API Surface

Planned endpoints from the binding spec:

- `GET /employees`
- `GET /employees/{id}`
- `GET /recommend/{id}`
- `POST /complete`
- `POST /upload`
- `GET /hr/overview`

## Recommendation Rules

The backend engine will use the deterministic formula from `AGENTS.md`: target-grade skill gaps, critical-skill weighting, hard eligibility filters, event benefit capped by `max_level`, engagement-history weighting, and a machine-readable `factors` object. The LLM never selects recommendations; it only explains computed factors.

## Trap Profile Test

The final README will include upload instructions and a reproducible trap-profile check showing that the engine does not choose a recommendation from a single lowest skill alone.
