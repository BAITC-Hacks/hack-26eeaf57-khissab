# Career Quest

HackAlem AI, Halyk Bank track, Case 1: Career Quest.

Career Quest is an offline-first employee development navigator. It recommends 1-3 next development activities from local JSON/CSV starter-kit data, explains the decision with multi-factor rationale, and shows HR where development is lagging.

## Status

P0 scaffold is in place. Functional loader, engine, explanation layer, API endpoints, UI, and final polish are implemented in later phases.

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
docker compose up --build
```

The app must run fully without any API key. `.env.example` is used by Docker Compose by default. `LLM_API_KEY` is optional: when it is empty, explanations use a deterministic template fallback and the recommendation engine stays fully local.

## Data

The starter kit is copied locally into `/data` from `case_1/career_quest_dataset/`.

`/data` is gitignored and must not be committed. The original `case_1/` starter-kit folder is also kept locally and gitignored.

Expected starter-kit counts:

- 200 employees
- 40 events
- 60 skills
- 2,743 activity history rows

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
