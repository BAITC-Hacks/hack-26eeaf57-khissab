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