# Career Quest

HackAlem AI · Halyk Bank track · Case 1 · Team Khissab

Employees receive scattered training, mentoring, and HR notifications without a clear connection to their career goals. The result described in the technical specification (TZ) is formal completion at the deadline and low turnout for voluntary activities despite a spent development budget. Career Quest connects each employee's assessed skills, target-grade requirements, and participation history to 1–3 useful next activities, explains the numbers behind each choice, and updates progress after completion. HR gets an aggregate view of skill gaps and participation. **The deterministic engine selects activities; the optional LLM only explains them.**

## Quickstart with Docker

Prerequisites: Git, Docker with a running daemon, Docker Compose **2.24+** (for the optional `.env` file), and the separately supplied Career Quest starter kit. Keep ports **5173** and **8000** free. Commands below use Bash or Zsh.

```bash
git clone https://github.com/BAITC-Hacks/hack-26eeaf57-khissab.git
cd hack-26eeaf57-khissab
```

Extract the supplied starter kit so that `case_1/career_quest_dataset/` is inside this repository. If it is elsewhere, replace that source path in the copy command:

```bash
mkdir -p data
cp -R case_1/career_quest_dataset/. data/
cp .env.example .env
docker compose up --build
```

Copy `.env.example` only on initial setup; it contains working defaults with an empty API key. Copying it is optional: Compose also loads `.env.example` directly and applies `.env` overrides if present.

Open:

- **App:** [http://localhost:5173](http://localhost:5173)
- **API health:** [http://localhost:8000/health](http://localhost:8000/health)
- **API schema:** [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)
- **Interactive API docs:** [http://localhost:8000/docs](http://localhost:8000/docs) (its Swagger UI assets need internet; the app and API do not).

From a second terminal in the repository root:

```bash
curl --fail -sS http://localhost:8000/health
curl --fail -sS 'http://localhost:8000/recommend/E0002?limit=1'
```

Expect `{"status":"ok"}` and a recommendation with `explanation.source: "template"` and `explanation.fallback_reason: "no_api_key"`. No secret, model download, cloud database, or external service is required. The initial image build needs internet or locally cached base images and packages. Prepare these before an offline defense; subsequent startup can use `docker compose up --no-build`.

SQLite is created and seeded on first startup at `storage/career_quest.sqlite3`, mounted as `/app/storage/career_quest.sqlite3`. Restarts preserve uploads and completions. `docker compose down` stops the app and retains this file. Source data is validated on every startup, so keep `data/` present even after seeding. Later additions go through `/upload`; replacing source files does not overwrite an existing database.

### Starter-kit files

| File under `data/` | Contents |
|---|---|
| `employees.json` | 200 synthetic employee profiles |
| `events.json` | 40 development activities |
| `skills.json` | 60 skills, proficiency levels 0–5, and 32 role/grade profiles |
| `activity_history.csv` | 2,743 participation records |
| `README.md` | Dataset schema and rules supplied with the kit |

The snapshot date is **2026-10-01**, with history from **2024-10-01 through 2026-09-30**. The engine uses the snapshot as its clock.

`data/` and the original `case_1/` folder are gitignored because the starter-kit terms restrict the synthetic data to the hackathon. They must be supplied separately, not committed or published. `storage/` and `.env` are also gitignored to keep local progress, uploaded data, and optional credentials out of Git. The committed `examples/` fixtures are independently fabricated demo data.

## Run without Docker

Use Python **3.11+** (the Docker image uses 3.12), Node.js **22** (matching the frontend image), and npm. Install dependencies while online or from a local cache. Copy the starter kit into `data/` as above. Stop Docker services first if they occupy the same ports.

Terminal 1, from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
DATA_DIR=./data DATABASE_URL=sqlite:///./storage/career_quest.sqlite3 LLM_API_KEY= \
  python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2, from the repository root:

```bash
cd frontend
npm install
VITE_API_URL=/api VITE_API_PROXY_TARGET=http://127.0.0.1:8000 \
  npm run dev -- --host 127.0.0.1
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` requests to the backend and strips the prefix. Compose uses the same proxy with `http://backend:8000`. Python does not automatically load `.env`; the explicit local paths above replace the container-only `/app/...` defaults. The empty key forces offline template explanations.

## Main demo scenario

Use a freshly seeded database for the example numbers below; earlier completions change the persisted results.

1. Open **Employee**. The app selects **E0002** by default. Inspect the Middle Backend Engineer profile, Senior trajectory, skill gaps, and **Completed / Past activities**.
2. Inspect the first recommendation, **EV_005 — System Design Fundamentals**. Its card shows skill contributions, engagement counts, score, rationale, explanation source, and gateway unlocks. Recommendations always carry numerical evidence.
3. Click **Mark complete** on EV_005. System Design and API Design both move from **1 to 2**, and trajectory progress moves from **60% to 64%**. The completion appears in history; EV_005 leaves the recommendations and eligible follow-up activities are recomputed. Reloading preserves the update.
4. Open **HR overview**. It shows the top 10 lagging skills by total missing levels, the **count** of employees without a recommended step, and the top 12 activities by history-record count. The API returns the full aggregate lists.
5. Use **Upload** to test an unseen jury profile and its history, following the instructions below.

Progress is `100 × (1 − total_gap / total_required_levels)`, rounded to two decimals. It describes coverage of target requirements; completing an activity does not automatically change the employee's grade.

## Architecture and technology

```text
Starter-kit JSON / CSV
          |
          v
loader.py: validate references, seed once
          |
          v
SQLite <---- store.py: atomic uploads and completions
          |
          v
engine.py: hard filters, deterministic scoring, top 1–3
          |
          v
explain.py: optional local LLM phrasing + self-check
           or offline template fallback
          |
          v
FastAPI (backend/main.py)
          |
          v
React + Vite + Tailwind (Employee / HR / Upload)
```

FastAPI coordinates reads, scoring, explanations, and writes. The loader checks unique IDs and references between employees, managers, roles/grades, skills, events, and history before seeding SQLite. Uploads validate the merged dataset and commit atomically. Profile reads and scoring run independently of optional model requests.

The stack is **Python, FastAPI, Pydantic, SQLite, HTTPX, pytest**, and **React 19, Vite 6, Tailwind CSS 3, Lucide icons**, packaged with Docker Compose. There is no vector database, RAG, embedding pipeline, or cloud database.

The engine's output is final before explanation begins. The model chooses clause order and one of two supported phrasings per fact through a `submit_explanation` tool call. A local validator requires every supplied fact exactly once and rejects extra claims or numbers. The application renders the wording and numeric values from the original factors. Templates use the same facts when the model is absent or fails.

## How recommendations are calculated

The TZ requires rationale based on **at least three factors**. Each explanation covers the target grade, skill gaps against that grade's requirements (including criticality and effective gain), and participation history, plus the resulting score. A low skill alone is insufficient: an activity must be relevant, accessible, useful, and weighted by the employee's past engagement.

1. **Choose the target requirements.** Use the employee's career-goal role/grade when supplied; otherwise use the current role and next grade in Junior → Middle → Senior → Lead. A Lead without a target stays at Lead requirements. Missing skills count as zero. Current levels come from assessed `employee.skills`; historical completions are not replayed into those levels, including post-review completions.
2. **Apply hard eligibility filters.** Require the employee's **current** role and grade to match `target_roles`/`target_grades`, and every skill prerequisite to be met. Exclude mandatory activities and already-completed event IDs. Only recurring club **EV_036** may be repeated; it still must pass the other filters.
3. **Calculate useful skill gains.** Use `develops_skills`, cap the gain at both the activity's `max_level` and the remaining target gap, and apply a zero floor. Each level toward a target-grade critical skill is worth **3**; other required skills have weight **1**.
4. **Weight by participation in the activity's type.** Across that employee's prior history, each `declined`, `no_show`, or `dropped` record multiplies the type's penalty by **0.6**. Each self-initiated completion adds a **1.15** multiplier, with the self-completion factor capped at **1.3**. Clamp their product to **0.2–1.3**. History is grouped by **type**, such as course or workshop; completed-event exclusion is by **event ID**.
5. **Rank useful eligible activities.** Multiply benefit by engagement and return up to three positive-score activities. Return an empty list if none qualifies. Ties use earliest availability, shorter duration, higher average event feedback, then event ID. Self-paced activities are available on the snapshot date; activities without an upcoming session sort last on availability.

```text
gap            = max(0, required - current)
effective_gain = max(0, min(gain, max_level - current, gap))
benefit        = sum(effective_gain × (3 if critical else 1))
decline_factor = 0.6 ^ skip_count
self_factor    = min(1.15 ^ self_completion_count, 1.3)
engagement     = clamp(decline_factor × self_factor, 0.2, 1.3)
score          = benefit × engagement
```

Future-dated history after the snapshot does not affect scoring, completion exclusion, or feedback tie-breaks. Scores are not rounded internally; the UI formats numbers for display.

**Gateway evidence:** `gateway_to` identifies a higher-ceiling activity blocked only by prerequisites when the recommended event is the sole currently eligible way to improve the relevant critical skill. It shows the unmet prerequisites and projected levels after completion. `unlocked_after_completion` is true only when all blockers would be satisfied. A gateway supplies an explanation of the next path; it adds **no scoring bonus** and bypasses no eligibility rule.

### Worked example: E0002

On the untouched starter kit, E0002 is a Middle Backend Engineer targeting Senior. **EV_005** ranks first:

| Skill | Current | Senior requirement | Gap | Critical weight | EV_005 gain / ceiling | Effective gain | Contribution |
|---|---:|---:|---:|---:|---|---:|---:|
| System Design | 1 | 4 | 3 | 3 | +1 / level 3 | 1 | 3 |
| API Design | 1 | 4 | 3 | 3 | +1 / level 3 | 1 | 3 |

Benefit is **6**. Course history contains **two drops** (EV_005 and EV_010) and **two self-initiated completions** (EV_012 and EV_010). Therefore:

```text
decline_factor = 0.6² = 0.36
self_factor    = min(1.15², 1.3) = 1.3
engagement     = 0.36 × 1.3 = 0.468
EV_005 score   = 6 × 0.468 = 2.808
```

The earlier drop lowers the score but does not make EV_005 ineligible. Its critical-skill benefit still puts it above EV_036 (**1.0**) and EV_011 (**0.414**). These are the initial top three. JSON may show floating-point precision such as `0.46799999999999997` for `0.468`.

EV_005 is currently the only eligible activity improving these critical gaps. **EV_006 — Designing High-Load Systems** and **EV_007 — Architecture Review Circle** both require System Design **2**, while E0002 has **1**. Completing EV_005 raises it to **2**, so both gateway entries have `unlocked_after_completion: true`. Their System Design ceilings are **5** and **4**, respectively, beyond EV_005's ceiling of **3**.

Inspect the evidence before completing the activity:

```bash
curl --fail -sS 'http://localhost:8000/recommend/E0002?debug=true'
```

Normal `factors` contain the chosen event's gaps, engagement counts/multipliers, benefit, score, target grade, and gateways. `debug_factors` additionally contains current/target roles and grades, tie-break values, and weighted personal history across all event types.

## How to test with jury profiles

The defense does not require editing source files or restarting. **POST `/upload`** accepts new employee profiles and/or history in the dataset schema and immediately recomputes recommendations from persisted SQLite state.

### Through the UI

1. In **Upload → Files**, select `examples/trap_employees.json` as **employees_file** and `examples/trap_activity_history.csv` as **history_file**. For jury data, select the equivalent supplied JSON/CSV files.
2. Click **Upload and open**. Expect **1 employee and 3 history rows** inserted for the demo. The app opens **DEMO_TRAP** automatically.
3. Inspect the trajectory, past activities, recommendation factors, and rationale. HR aggregates update too.

Alternatively, **Upload → JSON** accepts a batch object with `employees` and `activity_history` arrays, plus optional `meta`. Employee objects use all fields shown in the committed employee fixture. History objects use the CSV column names; numeric values must be JSON numbers and empty optional values must be `null`.

### Through the API

Run from the repository root. Use **either** the UI upload above **or** this command for the demo IDs; submitting both to the same database causes the expected duplicate-ID error.

```bash
curl --fail -sS -i http://localhost:8000/upload \
  -F 'employees_file=@examples/trap_employees.json;type=application/json' \
  -F 'history_file=@examples/trap_activity_history.csv;type=text/csv'

curl --fail -sS 'http://localhost:8000/recommend/DEMO_TRAP?debug=true'
```

Expected upload status: **201 Created**. Response body:

```json
{
  "inserted": {"employees": 1, "activity_history": 3},
  "employee_ids": ["DEMO_TRAP"],
  "reference_errors": 0
}
```

For a jury-provided combined JSON batch, save it as `jury_batch.json` locally and submit:

```bash
curl --fail -sS -i http://localhost:8000/upload \
  -H 'Content-Type: application/json' \
  --data-binary @jury_batch.json
```

Multipart `employees_file` uses the dataset's `{ "meta": ..., "employees": [...] }` wrapper; `meta` is optional. `history_file` uses the exact `activity_history.csv` columns. JSON uses `activity_history` for its history array. Either collection may be omitted, but at least one row is required. Supplied `meta.as_of_date` must be `2026-10-01`. Skill, event, role/grade, manager, and employee references must resolve against the existing data or employees in the same batch.

Uploads are append-only: duplicate employee or history-record IDs return **409**, never overwrite existing progress. Invalid schemas/references return **422** and roll back the whole batch. The limit is **2 MiB**, **1,000 employees**, and **10,000 history rows** per request. A history-only upload can reference an existing employee. Imported history changes engagement and completed-event eligibility; it does not change supplied assessed skill levels. Use fresh IDs throughout the files to repeat a jury test. Keep jury files local and uncommitted.

### Expected trap-profile behavior

The committed **DEMO_TRAP** has Application Security at **0**, its lowest target skill, and three workshop skips: declined, no-show, and dropped. The eligible **EV_011 — Secure Coding Workshop** gains one non-critical level, but its workshop multiplier is `0.6³ = 0.216`, making its score **0.216**. It is **absent from the top three**. **EV_005 ranks first with score 6**, because it develops the promotion-critical System Design and API Design gaps and has neutral course engagement. Inspect `debug_factors.engagement_by_type.workshop` to see all three skips even though the workshop is not recommended.

The unit-test trap mirrors the TZ's **Public Speaking versus System Design** example using a separate synthetic catalog. Public Speaking starts at 0 and its workshop could gain 5 levels, but three skips reduce its score to **1.08**. The critical System Design course scores **3**, followed by two alternatives scoring **2** each. Thus the lowest-skill workshop is excluded. The test also removes history and critical weighting separately to prove that both factors are needed. This is a fixture-specific result of the scoring rule, not a blanket ban on activities a person has skipped.

## API reference

Base URL: `http://localhost:8000`. All responses are JSON; the shapes below list the principal fields.

| Method and path | Request / response shape |
|---|---|
| `GET /health` | `{status: "ok"}` |
| `GET /employees` | `[{id, name, role, grade, department}]` |
| `GET /employees/{id}` | `{profile, trajectory, as_of_date, activity_history}`; history is limited to the requested employee, newest first, with event title/type and dataset fields. |
| `GET /recommend/{id}?limit=3&debug=false` | `{employee_id, as_of_date, recommendations: [{event_id, title, type, format, duration_hours, upcoming_sessions, score, factors, rationale, explanation, gateway_to}]}`. `limit` is 1–3; `debug=true` adds `debug_factors` to each item. Zero useful eligible steps returns `[]`. |
| `POST /complete` | Body `{employee_id, event_id, request_id}` → `{employee_id, event_id, request_id, record_id, skills, skill_changes, trajectory}`. |
| `POST /upload` | JSON batch or multipart files described above → `201` with `{inserted: {employees, activity_history}, employee_ids, reference_errors}`. |
| `GET /hr/overview` | `{as_of_date, employee_count, employees_without_recommendation: {count}, most_lagging_skills, participation_by_activity}`. Skill rows contain `skill_id`, `skill_name`, `total_gap`, `employees_affected`, `critical_employees`; activity rows contain `event_id`, `title`, `type`, `records`, `participants`, `status_counts`. |

`trajectory` contains `target_role`, `target_grade`, `skills` (current/required/gap/critical), `total_gap`, `critical_gap`, and `progress_pct`. `explanation` contains `source`, `model`, `fallback_reason`, and `validated_fact_ids`; its rendered text is returned as `rationale`.

To exercise completion through HTTP instead of the UI, on the initial E0002 state:

```bash
curl --fail -sS http://localhost:8000/complete \
  -H 'Content-Type: application/json' \
  -d '{"employee_id":"E0002","event_id":"EV_005","request_id":"jury-e0002-ev005-1"}'
curl --fail -sS http://localhost:8000/employees/E0002
```

Completion rechecks eligibility, persists a self-initiated completion at the snapshot date, and applies `new_level = current + max(0, min(gain, max_level - current))`. Actual learning is capped by the event ceiling, not by the target gap. An above-ceiling skill never decreases. Use a unique `request_id` per intentional completion; retrying the same ID and employee/event returns the saved response without duplicate progress, even after restart. EV_036 requires a new ID for each intentional repeat session.

Unknown profiles or completion employee/event IDs return **404**; malformed input or broken upload references **422**; duplicate uploads, ineligible completion, or conflicting request IDs **409**; oversized uploads **413**; unsupported upload media types **415**. A busy database returns **503** with `Retry-After: 1`. Default CORS origins are `http://localhost:5173` and `http://127.0.0.1:5173`.

## Optional local LLM

The default template path is complete and needs no key. To use a model, first run a **local, tool-capable OpenAI-compatible Chat Completions server**. No model is bundled or downloaded automatically. Edit the following `.env` values for your loaded model and server:

```dotenv
LLM_MODEL=your-loaded-model-id
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=local
LLM_TIMEOUT_SECONDS=8
```

| Variable | Meaning |
|---|---|
| `LLM_MODEL` | Loaded model identifier. The starter value `gpt-4o-mini` is only a configurable name, not a bundled model or automatic cloud connection. |
| `LLM_BASE_URL` | Local API prefix; the adapter appends `/chat/completions`. Only loopback hosts and `host.docker.internal` are accepted. |
| `LLM_API_KEY` | Nonempty token enables the adapter. Use the server's token, or the non-secret `local` placeholder if it does not require authentication. Empty/omitted always selects templates. |
| `LLM_TIMEOUT_SECONDS` | Total model-request deadline, default and maximum **8 seconds**. Up to three explanations run concurrently, with no retries. |

For Docker Desktop, `host.docker.internal` reaches a server on the host. For a Python backend on the host, use `http://127.0.0.1:11434/v1` instead. Adjust the port to your server. Remote endpoints fall back to templates; the model server must also operate locally.

Reapply Compose environment changes with `docker compose up --build` (a restart alone does not reload them). For a local backend, stop its previous process and run from the repository root:

```bash
DATA_DIR=./data DATABASE_URL=sqlite:///./storage/career_quest.sqlite3 \
  .venv/bin/python -m uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000
```

Existing shell variables override `.env`; clear any previously exported `LLM_*` settings that conflict. Confirm model use:

```bash
curl --fail -sS 'http://localhost:8000/recommend/E0002?limit=1'
```

Check **`recommendations[0].explanation.source == "llm"`** and **`fallback_reason == null`**. HTTP 200 alone is insufficient: provider errors, timeouts, missing configuration, and invalid output deliberately return successful template explanations with a diagnostic reason.

The adapter requires a forced `submit_explanation` function call with a strict schema. The model supplies fact IDs and `direct`/`supportive` phrasing choices; the local self-check rejects free prose, missing/duplicate facts, extra fields, and invented numeric claims. The prompt contains only the preselected event and relevant factors, excluding employee identity and raw history. Automated LLM tests use a mocked HTTP transport; they do not establish compatibility with a particular live model server.

## Project layout

```text
.
├── AGENTS.md / CLAUDE.md       Repository instructions
├── README.md
├── docker-compose.yml
├── .env.example
├── data/                      Supplied JSON/CSV and schema README (gitignored)
├── storage/                   Persisted SQLite database (gitignored)
├── examples/
│   ├── trap_employees.json
│   └── trap_activity_history.csv
├── backend/
│   ├── main.py                FastAPI routes and application lifecycle
│   ├── app/main.py            Compatibility import of backend.main:app
│   ├── loader.py              Dataset parsing, reference validation, seeding
│   ├── engine.py              Deterministic selection and trajectory
│   ├── explain.py             Grounded LLM adapter and template fallback
│   ├── store.py               SQLite snapshots, atomic writes, retry handling
│   ├── schemas.py / uploads.py Request validation and JSON/multipart parsing
│   ├── tests/                 Loader, engine, explanation, and API tests
│   ├── requirements.txt
│   └── Dockerfile
└── frontend/
    ├── src/main.jsx           Employee, HR, upload, and recommendation views
    ├── src/index.css
    ├── vite.config.js         Local API proxy
    ├── tailwind.config.js
    ├── package.json
    └── Dockerfile
```

## Verification

With the starter kit in `data/` and the local Python dependencies installed as above, run from the repository root:

```bash
source .venv/bin/activate
python -m pytest backend/tests -q
```

Expected: **79 passed**. Without the starter kit, dataset-dependent checks are skipped, so install it for the complete verification. Tests use isolated temporary databases and do not change the demo's persisted progress.

After the Compose build, the same suite can run without host Python. The application image does not include the committed upload fixtures, so mount `examples/` read-only in a disposable test container:

```bash
docker compose run --rm --no-deps -v "$PWD/examples:/app/examples:ro" \
  backend python -m pytest backend/tests -q
```

To inspect data loading and run the adversarial check individually:

```bash
python -m backend.loader --data-dir ./data --database-url sqlite:///:memory:
python -m pytest backend/tests/test_engine.py -k adversarial_trap -q
```

The loader should report `employees=200`, `events=40`, `skills=60`, `role_profiles=32`, `activity_history=2743`, and `reference_errors=0`. Frontend build check, from the repository root after installing npm dependencies:

```bash
npm --prefix frontend run build
```

The suite covers all hard filters, capped gains, critical weighting, by-type engagement, deterministic ordering, gateway projections, the trap profile, explanation grounding/fallback, upload validation and rollback, completion retries and persistence, employee-history scoping, and HR aggregate privacy. Real-dataset endpoint tests assert responses within **2 seconds** without an LLM. Model timeout/concurrency tests support the **10-second** recommendation budget through the 8-second model ceiling; they are not an end-to-end browser latency benchmark.

## Constraints and demo boundaries

- **Voluntary development:** mandatory activities are excluded from recommendations. History affects relevance; the app does not assign activities, force attendance, or award points for mandatory processes.
- **Explainability:** every recommendation exposes multiple factors and numbers. The LLM cannot change selection or supply new numbers. The template fallback supports the full no-key scenario.
- **Privacy and separation:** Employee and HR views are separate; the HR endpoint returns aggregates with no employee IDs, names, raw history, or individual engagement factors. The employee-history endpoint scopes results to its requested profile, and LLM prompts omit personal identifiers and raw history.
- **Access-control limit:** this is a local synthetic-data demo. Its profile selector can open any employee, and API routes have no authentication or role-based authorization. UI separation and aggregate HR responses do not enforce the TZ's production employee/HR permission boundary.
- **No public employee rankings**, reward economy, vector database, RAG, embeddings, or required cloud service. SQLite and no-key explanations work offline after dependencies are prepared.
