# Career Quest

HackAlem AI, Halyk Bank track, Case 1: Career Quest.

Career Quest is an offline-first employee development navigator. It recommends 1-3 next development activities from local JSON/CSV starter-kit data, explains the decision with multi-factor rationale, and shows HR where development is lagging.

## Status

P0 scaffold, P1 loader/validation, P2 deterministic engine, and P3 explanations are implemented. The backend seeds SQLite on startup and exposes `/health`; the frontend is still a placeholder. Run recommendations and explanations through the CLIs below. Business API endpoints, UI, and final polish follow in P4-P6. The model adapter has offline contract tests; a live model demonstration requires a separately configured local server.

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

`docker compose up` works fully without any API key via the deterministic template fallback. `.env.example` is used by Compose by default. `LLM_MODEL` selects the optional explanation model; `LLM_API_KEY` is optional. Recommendation selection remains local. Runtime must work offline; the initial image/dependency build requires packages and base images to be available or cached before disconnecting.

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

Open http://localhost:5173 and verify the backend with `curl http://127.0.0.1:8000/health` (returns `{"status":"ok"}`). Install dependencies once while online or from a local cache; startup, data loading, and the template fallback require no network service or API key.

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
python3 -m unittest backend.tests.test_loader -v
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

`backend/engine.py` implements the agreed formula with named constants `CRITICAL_WEIGHT=3.0`, `DECLINE_PENALTY=0.6`, and `SELF_COMPLETE_BONUS=1.15`. The LLM never selects recommendations; it only phrases computed facts. The engine uses no API key, network, or additional dependencies. Weights are fixed in code, not environment overrides.

1. Use `career_goal.target_grade` when set, otherwise the next grade in Junior, Middle, Senior, Lead. For a Lead without a target, use Lead requirements. Role requirements come from `career_goal.target_role` when set, otherwise the employee's role.
2. Current skill is the assessed `employee.skills` value, defaulting to 0. Per the P2 clarification, history does not recompute skills, including completions after `last_review_date`. For each target requirement, `gap = max(0, required - current)`.
3. Hard eligibility uses the employee's **current** role and grade, every prerequisite, `mandatory == false`, and no prior completion of that **event_id**. Only `EV_036` bypasses completed-event exclusion; all other filters still apply. Failed filters receive score 0 and exclusion reasons.
4. For each developed skill with a positive target gap, `effective_gain = max(0, min(gain, max_level - current, gap))`. Multiply by 3 for a target-grade critical skill, otherwise by 1, and sum as benefit. The zero floor is the user's P2 correction: an above-cap skill cannot penalize other useful skills on the event.
5. Count the employee's prior declined, no_show, and dropped records across **all events of the candidate's type**. Count prior self-initiated completions by that same type. `decline_factor = 0.6 ** skips`; `self_factor = min(1.15 ** self_completions, 1.3)`; `engagement = clamp(decline_factor * self_factor, 0.2, 1.3)`. The self-factor cap is distinct from the final clamp. Both component factors are exposed in debug output. `score = benefit * engagement`.
6. Return the top 1-3 eligible positive-score events, or an empty list when none can help. Do not pad with zero-benefit or ineligible events. Break ties by earliest upcoming session (self-paced is available on the snapshot date), shorter duration, then higher mean non-null feedback rating for that event. Events without upcoming sessions sort last on availability; no ratings sort after rated events. Exact remaining ties use event ID for reproducibility.

The dataset snapshot (`2026-10-01`) is the clock for historical records and upcoming sessions, including records/sessions on that date. Future-dated history does not affect completion exclusion, engagement, or feedback averages. The core leaves scores unrounded.

Each recommendation's `factors` contains target/current role and grade, gaps used with current/required levels, critical flags, capped gains, weights and contributions, total benefit, the selected event type's engagement multiplier, and tie-break values. `engagement_by_type` includes counts and weighted history records with IDs, statuses, dates, and initiators. Other types provide context for alternatives; only the candidate's type changes its score. This preserves the skipped-type evidence even when that type's event falls outside the top three.

`gateway_to` is additional deterministic evidence, not a scoring bonus. It appears when an activity is the only currently eligible event with a positive gain for a critical gap, and a higher-ceiling alternative is blocked solely by prerequisites. "Higher ceiling" means it can reach further toward the target requirement than the current activity. Gateway entries include the alternative's ID/title, the shared critical skills, every currently unmet prerequisite, and projected levels after completion. The activity must improve at least one blocking prerequisite. `unlocked_after_completion` is true only if all blockers would be met. Role/grade restrictions, mandatory events, and completed events cannot be bypassed; the engine never mutates assessed skills while projecting this evidence.

## Engine Verification (P2)

From the repository root, run offline with standard Python:

```bash
python3 -m unittest backend.tests.test_engine -v
python3 -m backend.engine E0002 --data-dir ./data
```

The CLI validates the source dataset and prints recommendations with complete factors. It reads the original assessed profiles from `data/` and does not read or modify the persisted SQLite database. Add `--limit 1` or `--limit 2` to request fewer steps. Application/SQLite integration is scheduled for P4.

For application code, `RecommendationEngine(validated_dataset).recommend(employee_id, limit=3)` returns the ranked list. `evaluate(employee_id)` returns all candidate scores, eligibility flags, and hard-filter exclusion reasons for inspection. Tests cover every hard filter, by-type history, by-ID completion exclusion, the `EV_036` exception, mixed penalty/bonus clamping, missing skills, target grades, the zero-floor edge case, tie-break order, deterministic output, and all 200 starter-kit employees.

P2 verifies the deterministic selection and numeric multi-factor evidence behind the TZ recommendation requirement, including the adversarial check below. P3 adds grounded rationale. Upload/complete HTTP flows and Employee/HR views remain for P4-P5.

## Explanations (P3)

Activate the local virtual environment and install the pinned backend requirements as above. The template path is fully offline and needs no key:

```bash
python -m backend.explain E0002 --data-dir ./data --template
python -m pytest backend/tests -q
```

The CLI retains the full recommendation/factors object and adds `explanation.text`, `source` (`template` or `llm`), `model`, `fallback_reason`, and `validated_fact_ids`. It does not write to SQLite. No HTTP explanation endpoint is introduced before P4.

The optional adapter uses a local server implementing OpenAI-compatible Chat Completions function calls. No model is bundled or downloaded automatically. Configure a gitignored `.env` with `LLM_BASE_URL` (for example `http://127.0.0.1:11434/v1`), `LLM_MODEL` matching a model already loaded on that server, and its optional authentication token in `LLM_API_KEY`. The sample `gpt-4o-mini` is only a configurable model identifier; it does not configure or contact a cloud provider. Because an empty key always chooses the template, an unauthenticated local server may use a non-secret placeholder such as `LLM_API_KEY=local` to opt into the adapter.

```bash
python -m backend.explain E0002 --data-dir ./data --env-file .env --limit 1
```

Existing shell variables take precedence over `.env`. In particular, unset an exported empty `LLM_API_KEY` before using `--env-file`. Compose continues to use `.env.example` and the no-key template by default. The local CLI above is the P3 verification path for optional model configuration.

From Docker Desktop, use `http://host.docker.internal:<port>/v1` for a model running on the host. The adapter accepts loopback and `host.docker.internal` endpoints only, ignores proxy environment variables, and does not follow redirects. Remote endpoints fall back to the template under the repo's offline rule. The model service itself must also operate locally without forwarding to a cloud provider.

The model receives a **slim** object: the preselected event ID/title, target grade, specific gap numbers/critical flags, **only its event type's** engagement counts/factors, benefit/score, and `gateway_to`. Other types, employee identifiers, unrelated profile fields, raw participation records, and tie-break metadata remain out of the prompt.

The model calls `submit_explanation` with a phrasing plan: each required fact ID once, in its chosen order, using `direct` or `supportive` wording. A local self-check rejects unknown/duplicate/missing facts, extra fields or numbers, free prose, refusals, and unexpected tool calls. Only validated references are rendered into natural language using the original factors. This deliberately constrains LLM wording to two factual variants per clause; the model cannot invent or swap numeric claims, change the recommended event, or claim a still-locked gateway is unlocked. The fallback uses the same renderer with direct wording. The wire format follows the official [function-calling guide](https://developers.openai.com/api/docs/guides/function-calling).

`LLM_TIMEOUT_SECONDS` defaults to 8 and cannot exceed 8. Up to three explanations run concurrently, each with a cancellable total request deadline and no retries, leaving time within the 10-second recommendation budget for local scoring/fallback. Response size is bounded. Missing configuration, timeout, connection/authentication errors, and invalid model responses return a template with a diagnostic reason; secrets/provider error bodies are never included in output.

Verification covers the corrected three-self-completion cap, E0002's course multiplier `0.468` and score `2.808`, gateway prerequisites for EV_006/EV_007, slim prompt contents, valid tool calls, numeric injection attempts, missing evidence, HTTP errors/redirects, cancellation, and no-key fallback. HTTP contract tests use `httpx.MockTransport` and do **not** count as live-model validation. A live response is identifiable by `source=llm` only when using the real configured endpoint, not the test transport.

## Trap Profile Test

Run just the adversarial test:

```bash
python3 -m unittest backend.tests.test_engine.EngineTests.test_adversarial_trap_requires_both_type_history_and_critical_weight -v
```

The synthetic Middle-to-Senior profile has a unique lowest skill, Public Speaking at 0 with a requirement of 5. Its eligible workshop could close all 5 levels, so it is the strongest unpenalized candidate. Three prior records on **different** workshop IDs (one declined, one no_show, one dropped) reduce its multiplier to `0.6 ** 3 = 0.216`, yielding score `1.08`.

System Design is 2 against a critical requirement of 4; its eligible course gains 1 level and scores `1 * 3 = 3`. Two other eligible activities each score 2. The top three are therefore the critical course and those two alternatives, with the lowest-skill workshop excluded. Returned factors retain the critical gap and all three workshop skip records.

The test also proves the case is adversarial: removing history makes the lowest-skill workshop rank first; removing critical weighting makes the critical course fall outside the top three. The separate above-cap test proves that `current > max_level` with `current < required` contributes 0, leaves other useful contributions intact, and excludes an event with no remaining benefit. Upload instructions for this fixture will follow with the P4 endpoint.
