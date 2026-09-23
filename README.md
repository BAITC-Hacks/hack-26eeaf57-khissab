# Career Quest

HackAlem AI, Halyk Bank track, Case 1: Career Quest.

Career Quest is an offline-first employee development navigator. It recommends 1-3 next development activities from local JSON/CSV starter-kit data, explains the decision with multi-factor rationale, and shows HR where development is lagging.

## Status

P0 scaffold, P1 dataset loader/validation, and P2 deterministic recommendation engine are in place. The backend seeds SQLite on startup and exposes `/health`; the frontend is still a placeholder. Run the engine through the CLI below. The explanation layer, business API endpoints, UI, and final polish follow in P3-P6.

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

P1 covers dataset ingestion and validation as the foundation for the TZ's profile/history and additional test-profile requirements. P2 verifies the recommendation core and trap profile below. The upload endpoint and user-facing must-have scenarios remain scheduled for later phases.

## API Surface

Planned endpoints from the binding spec:

- `GET /employees`
- `GET /employees/{id}`
- `GET /recommend/{id}`
- `POST /complete`
- `POST /upload`
- `GET /hr/overview`

## Recommendation Rules

`backend/engine.py` implements the agreed formula with named constants `CRITICAL_WEIGHT=3.0`, `DECLINE_PENALTY=0.6`, and `SELF_COMPLETE_BONUS=1.15`. The LLM never selects recommendations; it only explains computed factors in P3. The engine uses no API key, network, or additional dependencies. Weights are fixed in code, not environment overrides.

1. Use `career_goal.target_grade` when set, otherwise the next grade in Junior, Middle, Senior, Lead. For a Lead without a target, use Lead requirements. Role requirements come from `career_goal.target_role` when set, otherwise the employee's role.
2. Current skill is the assessed `employee.skills` value, defaulting to 0. Per the P2 clarification, history does not recompute skills, including completions after `last_review_date`. For each target requirement, `gap = max(0, required - current)`.
3. Hard eligibility uses the employee's **current** role and grade, every prerequisite, `mandatory == false`, and no prior completion of that **event_id**. Only `EV_036` bypasses completed-event exclusion; all other filters still apply. Failed filters receive score 0 and exclusion reasons.
4. For each developed skill with a positive target gap, `effective_gain = max(0, min(gain, max_level - current, gap))`. Multiply by 3 for a target-grade critical skill, otherwise by 1, and sum as benefit. The zero floor is the user's P2 correction: an above-cap skill cannot penalize other useful skills on the event.
5. Count the employee's prior declined, no_show, and dropped records across **all events of the candidate's type**. Count prior self-initiated completions by that same type. `engagement = clamp(0.6 ** skips * 1.15 ** self_completions, 0.2, 1.3)`, clamping once after multiplying. `score = benefit * engagement`.
6. Return the top 1-3 eligible positive-score events, or an empty list when none can help. Do not pad with zero-benefit or ineligible events. Break ties by earliest upcoming session (self-paced is available on the snapshot date), shorter duration, then higher mean non-null feedback rating for that event. Events without upcoming sessions sort last on availability; no ratings sort after rated events. Exact remaining ties use event ID for reproducibility.

The dataset snapshot (`2026-10-01`) is the clock for historical records and upcoming sessions, including records/sessions on that date. Future-dated history does not affect completion exclusion, engagement, or feedback averages. The core leaves scores unrounded.

Each recommendation's `factors` contains target/current role and grade, gaps used with current/required levels, critical flags, capped gains, weights and contributions, total benefit, the selected event type's engagement multiplier, and tie-break values. `engagement_by_type` includes counts and weighted history records with IDs, statuses, dates, and initiators. Other types provide context for alternatives; only the candidate's type changes its score. This preserves the skipped-type evidence even when that type's event falls outside the top three.

## Engine Verification (P2)

From the repository root, run offline with standard Python:

```bash
python3 -m unittest discover -s backend/tests -v
python3 -m backend.engine E0002 --data-dir ./data
```

The CLI validates the source dataset and prints recommendations with complete factors. It reads the original assessed profiles from `data/` and does not read or modify the persisted SQLite database. Add `--limit 1` or `--limit 2` to request fewer steps. Application/SQLite integration is scheduled for P4.

For application code, `RecommendationEngine(validated_dataset).recommend(employee_id, limit=3)` returns the ranked list. `evaluate(employee_id)` returns all candidate scores, eligibility flags, and hard-filter exclusion reasons for inspection. Tests cover every hard filter, by-type history, by-ID completion exclusion, the `EV_036` exception, mixed penalty/bonus clamping, missing skills, target grades, the zero-floor edge case, tie-break order, deterministic output, and all 200 starter-kit employees.

P2 verifies the deterministic selection and numeric multi-factor evidence behind the TZ recommendation requirement, including the adversarial check below. Natural-language explanations, upload/complete HTTP flows, and Employee/HR views remain for P3-P5.

## Trap Profile Test

Run just the adversarial test:

```bash
python3 -m unittest backend.tests.test_engine.EngineTests.test_adversarial_trap_requires_both_type_history_and_critical_weight -v
```

The synthetic Middle-to-Senior profile has a unique lowest skill, Public Speaking at 0 with a requirement of 5. Its eligible workshop could close all 5 levels, so it is the strongest unpenalized candidate. Three prior records on **different** workshop IDs (one declined, one no_show, one dropped) reduce its multiplier to `0.6 ** 3 = 0.216`, yielding score `1.08`.

System Design is 2 against a critical requirement of 4; its eligible course gains 1 level and scores `1 * 3 = 3`. Two other eligible activities each score 2. The top three are therefore the critical course and those two alternatives, with the lowest-skill workshop excluded. Returned factors retain the critical gap and all three workshop skip records.

The test also proves the case is adversarial: removing history makes the lowest-skill workshop rank first; removing critical weighting makes the critical course fall outside the top three. The separate above-cap test proves that `current > max_level` with `current < required` contributes 0, leaves other useful contributions intact, and excludes an event with no remaining benefit. Upload instructions for this fixture will follow with the P4 endpoint.
