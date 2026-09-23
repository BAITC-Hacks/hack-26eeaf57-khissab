You are building my HackAlem AI hackathon solution: Case 1 "Career Quest"
(Halyk Bank track). I'm attaching the full technical spec (TZ) and the dataset.

FIRST: read AGENTS.md in the repo root and /data/README.md. Obey AGENTS.md on
every step — it defines the rules, the fixed stack, the engine spec, the API
surface, and the definition of done. Do not deviate from it without asking.

Then build the whole project, in this order, running and verifying after each
stage:

1. Scaffold: repo layout from AGENTS.md, docker-compose.yml (single-command
   run), .env.example, README.md skeleton. Put the dataset in /data.
2. backend/loader.py — load employees.json, events.json, skills.json,
   activity_history.csv into SQLite (or in-memory). Validate all references.
3. backend/engine.py — the deterministic recommendation core, exactly per
   AGENTS.md §4: target-grade skill gaps, critical-skill weighting, event
   benefit from develops_skills (capped at max_level), hard eligibility filter
   (prerequisites, target_roles/grades, exclude mandatory and already-completed
   except EV_036), engagement-history weighting from declined/no_show/dropped
   vs self-completed. Return top 1–3 with a machine-readable `factors` object.
   Write unit tests, including the trap-profile test in AGENTS.md §7.
4. backend/explain.py — turn a recommendation's `factors` into natural-language
   rationale via an LLM (model behind .env, tool-calling / agentic self-check).
   MUST have a template fallback that works with no API key and never invents
   numbers outside `factors`.
5. backend/main.py — FastAPI endpoints: GET /employees, GET /employees/{id}
   (profile + trajectory), GET /recommend/{id}, POST /complete (moves skill
   progress + trajectory), POST /upload (ingest extra profiles+history in
   dataset schema — mandatory), GET /hr/overview.
6. frontend/ — React + Vite + Tailwind. Two separated views: Employee
   (profile, trajectory, 1–3 recommendations each showing the "why" factors as
   numbers, mark-complete button) and HR (most-lagging skills, people with no
   recommended step, participation by activity).
7. README.md — architecture diagram, one-command run, tech list, and a section
   showing how to upload and test a trap profile. This is worth 25 points.

Constraints (from AGENTS.md, repeated because they decide the score):
- Multi-factor rationale only (≥3 factors); the LLM never selects, only explains.
- Must run with `docker compose up`, no secrets, no internet, no cloud DB.
- No vector DB / RAG / embeddings. No gamification until the core passes §7.
- UI ≤2s, AI recommendation ≤10s.

Before you say a stage is done, actually run it and confirm the §7 checklist
items it covers. Ask me if the spec and AGENTS.md conflict on anything.

## §4 — Concrete engine and progress contract

The original instructions above referenced missing sections. These definitions
make that contract explicit for this repository and preserve the fixed stack.

- Target `career_goal`, otherwise the next grade (Lead remains Lead).
- Reconstruct effective skills from the assessment plus completed history after
  `last_review_date` and on/before the dataset snapshot. Application completions
  are tracked explicitly, including same-day completions. Never double-count.
- Gap = max(0, required - effective current). Effective event gain is capped by
  gain, max_level and remaining gap. Weight critical skills 3, others 1.
- Require current role/grade audience and prerequisites. Exclude mandatory and
  completed events except EV_036. Filters use effective skills.
- By activity type: decline/no_show/dropped factor = 0.6^count; self-completion
  factor = min(1.15^count, 1.3); engagement = clamp(product, 0.2, 1.3).
- Score = benefit × engagement. Return 0–3 positive eligible steps. Ties:
  availability, duration, feedback, event ID. Gateways add evidence, not score.
- Keep assessment and history separately; completion and upload are atomic.
- Each rationale includes grade/target, skill gaps and engagement evidence.
  The model never selects events or supplies authoritative numbers.

## §7 — Acceptance checklist

Run and verify before claiming completion:

- Dataset reference validation and expected starter-kit counts.
- Trap test: low Public Speaking plus three skips loses to a promotion-critical
  System Design step; removing history or critical weighting exposes the trap.
- Role/grade/prerequisite/mandatory/completed hard filters and EV_036 exception.
- Post-assessment learning, max_level, same-day application completions,
  backdated uploads, idempotency, restart persistence and legacy migration.
- JSON and multipart jury upload; invalid batches roll back.
- Profile, skills, trajectory, history, recommendation numbers and completion UI.
- HR-only list of employees without a step, skill gaps and participation.
- API authentication, employee ownership checks and HR-only upload/overview.
- Profile/UI does not wait for AI; normal profile target ≤2s, AI ≤10s.
- Model tool-call self-check and no-key/error/timeout template fallback.
- Frontend tests/build, backend tests, Docker and prepared offline startup.
- README includes architecture, stack, single-command run, authentication,
  trap upload, optional model configuration and reproducible verification.

The owner explicitly requested OpenAI integration after the audit and approved
sending de-identified synthetic recommendation factors to OpenAI. It is optional;
no-key and forced-template offline operation must continue working. Never commit
API keys, authentication keys, the provided dataset or local progress.
