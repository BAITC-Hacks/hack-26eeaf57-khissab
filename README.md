# Career Quest

HackAlem AI, Halyk Bank track, Case 1: Career Quest.

Hackathon team repository for Khissab: `hack-26eeaf57-khissab`.

Career Quest is an offline-first employee development navigator. It recommends 1-3 next development activities from local JSON/CSV starter-kit data, explains the decision with multi-factor rationale, and shows HR where development is lagging.

## Status

P0-P5 are implemented: scaffold, validated loader, deterministic engine, grounded explanations, FastAPI endpoints, and a React/Vite/Tailwind frontend with separated Employee and HR views. SQLite persists uploaded profiles/history and completed-event progress. The model adapter has mocked contract tests; live-model wiring is optional and local-only.

## Architecture

```text
React + Vite + Tailwind
        |
        | HTTP
        v
FastAPI backend
        |
        +-- main.py     -> employee, recommendation, upload, completion, HR APIs
        +-- store.py    -> consistent snapshots and atomic SQLite transactions
        +-- loader.py   -> validates starter-kit JSON/CSV into SQLite
        +-- engine.py   -> deterministic recommendation scoring
        +-- explain.py  -> LLM rationale with offline template fallback
        |
        v
SQLite in /storage
```

## One-Command Run

```bash
cp .env.example .env    # optional; app runs without it
docker compose up --build
```

Docker is the primary run path. Use Docker Compose 2.24.0 or newer (`docker compose version`): [optional env files](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/#additional-information-1) require this version. Before starting a fresh clone, place the separately supplied starter kit in `data/` as described below. Open the frontend at http://localhost:5173 and backend health check at http://localhost:8000/health. The frontend uses Vite's `/api` proxy in Compose, so browser requests stay on the frontend origin while the proxy forwards to the backend service.

The backend loads committed `.env.example` defaults first, then gitignored `.env` overrides when that file exists. Missing `.env`, an omitted `LLM_API_KEY`, or an empty key uses deterministic template explanations without making model requests. Only `VITE_API_URL` and `VITE_API_PROXY_TARGET` are passed to the frontend, with working Compose defaults when unset or empty. See [Enable a local LLM (optional)](#enable-a-local-llm-optional) to opt into model explanations. Recommendation selection remains local. Runtime must work offline; the initial image/dependency build requires packages and base images to be available or cached before disconnecting.

`DATABASE_URL=sqlite:////app/storage/career_quest.sqlite3` points to `/app/storage` in the container, bind-mounted from the repo's gitignored `/storage/` directory. First startup creates the directory/file and seeds it transactionally. Subsequent starts validate the source dataset but preserve the existing database, including progress and any later uploads. No prebuilt database or secret is required or committed.

From a clean clone, with Docker Desktop running (replace the dataset path with the supplied starter kit):

```bash
git clone https://github.com/BAITC-Hacks/hack-26eeaf57-khissab.git
cd hack-26eeaf57-khissab
mkdir -p data
cp -R /path/to/career_quest_dataset/. data/
cp .env.example .env    # optional; app runs without it
docker compose up --build
```

After backend startup, check from another terminal:

```bash
curl --fail http://localhost:8000/health
docker compose logs --tail=50 backend frontend
```

Building images initially requires network access or cached base images/packages; once prepared, `docker compose up --no-build` runs offline. Stop with `docker compose down`; the bind-mounted SQLite file remains.

### No-Key Check

On a fresh clone, skip the optional copy to check startup without `.env`. Alternatively, leave `LLM_API_KEY` empty or omit it from `.env`. Use the same `docker compose up --build` command; after startup, run in another terminal:

```bash
docker compose config --quiet
curl --fail -sS 'http://localhost:8000/recommend/E0002?limit=1'
```

Expect HTTP 200, a nonempty `recommendations` array, `recommendations[0].explanation.source == "template"`, and `fallback_reason == "no_api_key"`. The API regression test `test_startup_without_llm_key_uses_template` covers startup with no LLM settings, a configured model/endpoint with the key omitted, and an explicitly empty key; it asserts no model call occurs. Run it with `python -m pytest backend/tests/test_api.py -k startup_without_llm_key -q`.

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
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend, terminal 2, also starting from the repository root:

```bash
cd frontend
npm install
VITE_API_URL=/api npm run dev -- --host 127.0.0.1
```

Open http://localhost:5173 and verify the backend with `curl http://127.0.0.1:8000/health` (returns `{"status":"ok"}`). The Vite proxy defaults to `http://127.0.0.1:8000`; set `VITE_API_PROXY_TARGET` only if the backend runs elsewhere. For a static build served without Vite's proxy, set `VITE_API_URL` to the backend URL. Install dependencies once while online or from a local cache; startup, data loading, and the template fallback require no network service or API key.

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

P1 covers dataset ingestion and validation as the foundation for the TZ's profile/history and additional test-profile requirements. P2 verifies the recommendation core and trap profile below. P4 verifies upload and completion flows through HTTP. P5 adds the user-facing Employee and HR views on top of those endpoints.

## API Surface

| Endpoint | Response / behavior |
|---|---|
| `GET /employees` | Array of `{id, name, role, grade, department}` for profile selection. |
| `GET /employees/{id}` | `{profile, trajectory, as_of_date, activity_history}`; trajectory includes target role/grade, each required skill's current/required/gap/critical flag, total/critical gaps, and progress percentage. History contains only this employee's records, newest date/record ID first, with event `title` and `type` plus the dataset fields (`record_id`, `event_id`, `date`, `status`, etc.). All six statuses are included; no history returns `[]`. |
| `GET /recommend/{id}?limit=3` | `{employee_id, as_of_date, recommendations}`; 0-3 positive eligible steps, each with event details, score, slim `factors`, `rationale`, explanation provenance, and `gateway_to`. Empty means no eligible useful step, not an error. |
| `GET /recommend/{id}?debug=true` | Also includes `debug_factors` with the full engine factors and all engagement types. Default responses and LLM prompts remain slim. |
| `POST /complete` | JSON `{employee_id, event_id, request_id}`; returns updated `skills`, `skill_changes`, `trajectory`, and persisted record/request IDs. |
| `POST /upload` | JSON or multipart dataset files; atomic insert of new employees and/or history. Returns inserted counts, new employee IDs, and `reference_errors: 0`. |
| `GET /hr/overview` | Aggregate target-grade gaps by skill, count of employees with no recommended step, and per-activity participant/status counts. No employee IDs, names, raw history, or engagement factors. |

`trajectory.progress_pct` is `100 * (1 - total_gap / total_required_levels)`, not a promotion decision; skills above a requirement do not inflate it. Completion changes skill levels and trajectory, never the employee's grade automatically. All requests read the persisted SQLite state, so no cache refresh or restart is needed after writes. Requests with unknown employee/event IDs return 404; malformed schemas or broken references return 422; duplicate upload IDs or ineligible completions return 409. A busy database returns 503 with `Retry-After: 1`.

`CORS_ORIGINS` defaults to `http://localhost:5173,http://127.0.0.1:5173`, matching `.env.example`. Set it explicitly if Vite uses another port. CORS permits GET/POST and Content-Type, with no wildcard origin or credentials. OpenAPI is at `/openapi.json`, including both upload formats. The optional `/docs` explorer loads its UI assets from a CDN; the API itself needs no internet.

This is a local hackathon demo API, not an authentication boundary. HR receives aggregates only, but employee/debug routes are unauthenticated. Do not expose the server to untrusted networks or use it for real personnel data before adding authentication and authorization. P5 separates the Employee and HR UI views.

## Frontend Demo (P5)

The React app has two separated views:

- Employee view: profile selector, role/grade/department, target trajectory, current skill levels versus target-grade requirements, recommendation cards, and Completed / Past activities loaded from SQLite. History shows event title, type, date, and status, including completed, in progress, dropped, no show, declined, and overdue activities.
- Recommendation cards: each card shows the score, event metadata, every skill gap used for scoring (`current -> required`, gap, effective gain, critical flag), engagement counts/factors, rationale text, explanation source, and `gateway_to` unlock evidence.
- Mark complete: posts `POST /complete`, updates the visible skill levels and trajectory from the response, merges the new completion into history by `record_id`, then re-fetches recommendations and HR aggregates without a browser reload. Reopening or reloading the employee retains persisted history without duplicating session completions; separate recurring event sessions remain separate records.
- HR overview: reads only `GET /hr/overview` aggregates: lagging skills, count of employees with no recommended step, and participation by activity. It does not render employee engagement histories.
- Upload panel: supports multipart `employees_file` + `history_file` and JSON upload batches. After a successful upload, the app refreshes employees, opens the first inserted employee, and shows recommendations immediately.

For the committed trap demo, start the app, upload `examples/trap_employees.json` and `examples/trap_activity_history.csv` from the Upload panel, and confirm that `DEMO_TRAP` opens automatically. The recommendation cards expose the numeric reason critical courses outrank the skipped workshop path.

### Complete a Step

```bash
curl -sS http://127.0.0.1:8000/complete \
  -H 'Content-Type: application/json' \
  -d '{"employee_id":"E0002","event_id":"EV_005","request_id":"demo-e0002-ev005-1"}'
curl -sS http://127.0.0.1:8000/employees/E0002
curl -sS http://127.0.0.1:8000/recommend/E0002
```

The server rechecks all hard filters inside the write transaction. Each developed skill becomes `current + max(0, min(gain, max_level - current))`; an above-cap skill never decreases, and actual learning is not capped to the target-grade gap. The new self-initiated completion is dated at the dataset snapshot and immediately affects engagement and completed-event exclusion. Existing historical completions are never replayed into assessed skills.

Use a unique `request_id` (for example a UUID) per intentional completion. A retry with the same ID and employee/event returns the original successful response, including after a restart, without adding gains or history. Reusing the ID for another employee/event returns 409. A new request ID for an already completed event also returns 409, except `EV_036`: a new ID records a new club session, while a retry remains idempotent. Profile, history, and retry response commit together or all roll back. To fetch current state after a replay of an older completion, use `GET /employees/{id}`.

### Upload Extra Profiles and History

`POST /upload` accepts either:

- `application/json`: `{ "meta": {"as_of_date":"2026-10-01"}, "employees": [...], "activity_history": [...] }`. Rows follow the starter-kit fields; history numeric values are numbers and empty optional values are null. Meta and either collection may be omitted, but at least one row is required.
- `multipart/form-data`: `employees_file` with the `{meta, employees}` JSON wrapper and/or `history_file` with the exact `activity_history.csv` columns. Empty optional CSV values are parsed as null. Supplied metadata must match the snapshot. No file paths or filenames are trusted or written to disk.

Upload size is limited to 2 MiB, at most 1,000 profiles and 10,000 history rows per batch. Uploads are append-only, not an upsert: duplicate employee/record IDs return 409 and never overwrite profiles or progress. All cross-references are checked against the merged existing + uploaded graph before committing, including managers in the same batch. Broken references return field/record diagnostics and roll back the entire batch. Imported history influences recommendations but does not recompute the supplied assessed skills. History-only uploads can refer to existing employees.

The committed `examples/` files contain a newly fabricated profile and three fabricated workshop skips, not starter-kit employee data. With the starter kit loaded, run:

```bash
curl -sS http://127.0.0.1:8000/upload \
  -F 'employees_file=@examples/trap_employees.json;type=application/json' \
  -F 'history_file=@examples/trap_activity_history.csv;type=text/csv'
curl -sS 'http://127.0.0.1:8000/recommend/DEMO_TRAP?debug=true'
```

Expected upload: `201`, one employee and three history rows, zero broken references. The critical System Design/API Design course `EV_005` ranks first (score 6), while `EV_011` for the profile's lowest skill, App Security, is absent from the top three after three workshop skips. `debug_factors.engagement_by_type.workshop` retains all three skips and multiplier `0.216`; the regular slim factors show only each recommended activity's relevant type. Running the same upload again returns 409; change all fixture employee/record IDs to try another profile without overwriting the first.

### API Verification (P4)

```bash
python -m pytest backend/tests -q
python -m pytest backend/tests/test_api.py -q
```

Tests cover every endpoint, JSON and file upload round-trips, broken-reference/schema rejection and atomic rollback, same-batch managers, history-only ingestion, immediate recomputation, completion eligibility/caps, concurrent retry safety, repeatable clubs, restart persistence, CORS, HR aggregate privacy, and explanation timeout/fallback behavior. The real-dataset test checks E0002's course multiplier `0.468`, EV_005 score `2.808`, its gateway unlock after completion, and the committed demo upload. Seeded endpoint requests are checked against the 2-second non-LLM budget. Optional explanations are the only slow path, run concurrently with an 8-second ceiling within the 10-second recommendation budget; slow model calls do not block profile reads. All tests use isolated temporary databases and leave `/data` untouched.

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

The CLI validates the source dataset and prints recommendations with complete factors. It reads the original assessed profiles from `data/` and does not read or modify the persisted SQLite database. Add `--limit 1` or `--limit 2` to request fewer steps. Use the P4 HTTP API to inspect uploaded profiles or completed-event progress in SQLite.

For application code, `RecommendationEngine(validated_dataset).recommend(employee_id, limit=3)` returns the ranked list. `evaluate(employee_id)` returns all candidate scores, eligibility flags, and hard-filter exclusion reasons for inspection. Tests cover every hard filter, by-type history, by-ID completion exclusion, the `EV_036` exception, mixed penalty/bonus clamping, missing skills, target grades, the zero-floor edge case, tie-break order, deterministic output, and all 200 starter-kit employees.

P2 verifies deterministic selection and numeric multi-factor evidence, including the adversarial check below. P3 adds grounded rationale and P4 adds upload/complete HTTP flows; Employee/HR views remain for P5.

## Explanations (P3)

Activate the local virtual environment and install the pinned backend requirements as above. The template path is fully offline and needs no key:

```bash
python -m backend.explain E0002 --data-dir ./data --template
python -m pytest backend/tests -q
```

The CLI retains the full recommendation/factors object and adds `explanation.text`, `source` (`template` or `llm`), `model`, `fallback_reason`, and `validated_fact_ids`. It does not write to SQLite. The P4 `/recommend/{id}` endpoint returns this text as `rationale`, provenance as `explanation`, and slim factors by default.

## Enable a local LLM (optional)

The adapter uses a local server implementing OpenAI-compatible Chat Completions function calls. No model is bundled or downloaded automatically. With a tool-capable model server already running on the host, create `.env` if needed (`cp .env.example .env`), then edit these entries (replace the model ID and port with those of your server):

```dotenv
LLM_MODEL=your-loaded-model-id
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=local
LLM_TIMEOUT_SECONDS=8
```

Use the server's token instead of `local` if it requires authentication. For an unauthenticated local server, the non-secret `local` placeholder opts into the adapter; an empty key always chooses templates. The sample `gpt-4o-mini` in `.env.example` is only a configurable identifier, not a bundled model or cloud connection. Start or reapply the configuration with the normal command (an existing container is recreated when its environment changes):

```bash
docker compose up --build
```

After backend startup, run in another terminal:

```bash
curl --fail -sS 'http://localhost:8000/recommend/E0002?limit=1'
```

Verify `recommendations[0].explanation.source == "llm"` and `fallback_reason` is null. A successful HTTP response alone is not proof of live LLM use: the API deliberately returns templates when the model fails. `docker compose restart` does not reload environment changes; use `docker compose up --build` after editing `.env`.

`explain.py` sends `POST ${LLM_BASE_URL}/chat/completions` with `Authorization: Bearer ${LLM_API_KEY}`. Set the base URL to the API prefix, usually `/v1`, not the full `/chat/completions` path. It expects OpenAI-compatible **Chat Completions function calling**, including a forced `submit_explanation` tool call and `strict: true` schema. The response must contain exactly one `choices[0].message.tool_calls` entry with JSON-string `function.arguments` shaped as `{"clauses":[{"fact_id":"grade","phrasing":"direct"}, ...]}` covering every supplied fact once; free text or incompatible tool output triggers fallback. This is not the Responses API or a server's native `/api/chat` endpoint.

For a local Python backend, use `LLM_BASE_URL=http://127.0.0.1:<port>/v1` in `.env` and start it from the repo root with `DATA_DIR=./data DATABASE_URL=sqlite:///./storage/career_quest.sqlite3 .venv/bin/python -m uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000`. Unset any exported `LLM_*` variables that would override the file.

To check the adapter directly from the local Python environment, run `python -m backend.explain E0002 --data-dir ./data --env-file .env --limit 1`. Existing shell variables take precedence over `.env` for this CLI; unset an exported empty `LLM_API_KEY` before using `--env-file`.

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

The test also proves the case is adversarial: removing history makes the lowest-skill workshop rank first; removing critical weighting makes the critical course fall outside the top three. The separate above-cap test proves that `current > max_level` with `current < required` contributes 0, leaves other useful contributions intact, and excludes an event with no remaining benefit. This unit fixture uses a synthetic event catalog; the separate `DEMO_TRAP` upload example above works against the unchanged starter-kit catalog, and is also tested end to end.
