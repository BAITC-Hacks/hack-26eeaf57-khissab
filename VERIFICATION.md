# Career Quest — verification record

## Pre-push recheck — 2026-09-23

The final working-tree check passed **116 backend tests in 2.55s**, **5 frontend
tests**, and the Vite production build in **1.54s**. `git diff --check` passed.
The source credential-pattern scan found no matches; private data and local
state remain excluded from the commit.

## README refresh recheck — 2026-09-23

The documentation refresh reran the current host suites: **113 backend tests
passed in 3.44s**, **2 frontend tests passed**, and the Vite production build
passed in **2.09s**. The loader independently confirmed 200 employees, 40 events,
60 skills, 32 role profiles and 2,743 history rows with zero reference errors.
The backend emitted the same AnyIO deprecation warning noted below.

The README screenshots were captured from a separate, freshly seeded temporary
database, using `LLM_PROVIDER=template` and local demo access. Employee E0002
showed 62% coverage and recommendation score 2.808; HR showed 200 people and
34 without a step. Both existing Compose services also reported healthy.
No completion was applied to the owner's working database for these captures.

The remaining sections retain the earlier implementation audit and its measured
Docker, offline and live-model results. Those longer checks were not rerun as
part of the documentation refresh.

---

Date: 2026-09-23. Scope: Career Quest mandatory requirements in the supplied TZ,
the dataset README and AGENTS.md §7. Dataset clock: 2026-10-01.

## Jury sign-in follow-up — 2026-09-23

The simplified local login was verified after the original audit below:

| Check | Observed result |
|---|---|
| Complete backend suite, host Python 3.11 | 116 passed in 4.16s |
| Complete backend suite, Docker Python 3.12, `--network none` | 116 passed in 3.64s; data and example fixtures mounted read-only |
| Frontend tests | 5 passed, including delayed old-session 401 preserving a newly opened session |
| Frontend production build | Passed on host and during Docker image build |
| Offline bundle refresh and startup | Both images built/exported; `scripts/run-offline.sh -d --wait` loaded them and both services became healthy |

New coverage checks fixed E0002/HR demo identities, anonymous and ownership
restrictions, HR-only uploads, rejection of arbitrary identity/role fields,
explicit local-only enablement, disabled/nonlocal demo entry, session hashing,
restart persistence, logout, expiry, legacy session-table migration and rejection
of demo tokens when demo mode is disabled. Private sign-in accepts employee IDs,
10-character codes and existing long codes; username aliases share rate limits.

Browser checks confirmed one-click E0002 entry, no HR navigation for the
employee, session restoration after refresh, sign-out, one-click HR entry
directly into the overview, and the HR upload screen. The account form reports
invalid credentials without blocking another attempt. The login was visually
checked at 375×812 and 1280×800; both demo buttons are readable and usable.
The local installation is running in forced-template mode for these checks.
No activity completion or dataset upload was performed by this auth follow-up;
automated tests use isolated temporary databases.

The sections below retain the original full-project audit and its measurements.

## Automated checks

| Check | Observed result |
|---|---|
| Starter-kit loader and reference validation | 200 employees, 40 events, 60 skills, 32 role profiles, 2,743 history rows; 0 reference errors |
| Backend suite, host Python 3.11 | 89 passed in 1.57s |
| Backend suite, Docker Python 3.12 with `--network none` | 89 passed in 2.22s |
| Frontend deferred-response tests | 2 passed; a pending or failing recommendation does not block the profile |
| Frontend production build | Vite 6.4.3; passed on host and inside Linux/ARM64 Docker (1.62s) |
| npm dependency audit during clean lockfile generation | 0 known vulnerabilities reported |

The backend run emits one dependency deprecation warning about AnyIO's
BlockingPortal alias. There are no failed tests.

Coverage includes the Public Speaking trap, separate history/critical-weight
ablation checks, every hard eligibility filter, EV_036 repeats, level ceilings,
post-assessment completions, same-day application completions, chronological
backdated imports, idempotency, concurrent retries, rollback, restart persistence,
legacy progress migration, JSON/multipart uploads, invalid references, ownership,
HR permissions, forged/expired/revoked sessions, login throttling, strict model
output validation, missing-key fallback and concurrent timeout fallback.

## Browser scenarios

Verified through the running app at `http://localhost:5173`, with model calls
disabled for starter-kit browser checks:

1. Employee sign-in exposes only that employee's workspace. HR/upload controls
   are absent. E0002 shows Mentoring 2, including post-assessment learning, and
   62% target coverage.
2. HR overview identifies 34 starter-kit employees without a next step. Opening
   E0010 from that list shows the correct profile and the no-eligible-step state.
3. HR multipart upload of `examples/trap_employees.json` and
   `examples/trap_activity_history.csv` inserts 1 fabricated profile and 3 rows,
   then opens DEMO_TRAP automatically.
4. DEMO_TRAP initially has 80% target coverage. EV_005 ranks first with benefit 6,
   engagement 1 and score 6. Expanded evidence shows target grade, skill gaps,
   critical weights, participation counts and score calculation.
5. Marking EV_005 complete changes System Design 1 → 2, API Design 2 → 3, target
   coverage 80% → 84%, critical gap 5 → 3 and completed activities 0 → 1.
   Reloading retains 84%, the completion history and newly eligible activities.
6. Skills and history screens open correctly. The completed-history filter
   shows 10 completed records out of E0002's 15 participation records.
7. HR participation initially shows 12 programs; **View all 40 activities**
   exposes all 40 rows. No-step profile links remain actionable.
8. Sign-out returns to the login screen and invalidates the server session.

The local demo database now includes DEMO_TRAP and its EV_005 completion.
The original 200 starter-kit profiles were not completed or changed by this
browser completion test. Re-uploading the same fixture correctly conflicts;
use an isolated fresh database when reproducing the initial trap state.

## Latency and live model evidence

| Scenario | Observed result |
|---|---|
| Browser switch to E0002, through visible profile heading | 104 ms |
| Authenticated profile HTTP request | 19 ms |
| Template recommendation HTTP request | 17 ms |
| Live OpenAI, one fabricated recommendation | 3.126s; `source=llm`, no fallback |
| Live OpenAI, three fabricated recommendations concurrently | 2.957s total; all three `source=llm`, four validated facts each, no fallback |
| Running Docker API → OpenAI, fabricated DEMO_TRAP | 1.512s for three recommendations; all `source=llm`, 4/5/4 validated facts, no fallback; profile 45 ms |

The live checks used `gpt-4o-mini`: isolated fabricated factors from
`backend.check_llm`, followed by the independently authored `examples/` DEMO_TRAP
profile through the running authenticated API. No starter-kit employee's profile
or participation history was exported for these live checks. Credentials
were loaded from the ignored local environment and are not part of this report.
The model never selects activities or supplies factual numbers. Its tool-call
plan must pass the local fact-coverage check before being rendered.

These measurements meet the 2s UI and 10s recommendation targets on this machine.
They are point-in-time observations, not guarantees about every machine or
provider. The model deadline is capped at 8s and falls back to grounded text;
profile requests and rendering remain independent of that deadline.

## Offline startup and packaging

`bash scripts/prepare-offline.sh` built both images and exported a 152.4 MiB
local bundle. `bash scripts/run-offline.sh -d --wait` loaded that bundle and
started both services with `--no-build --pull never`; both health checks passed.
Browser sign-in, recommendations and DEMO_TRAP's persisted 84% progress worked
after this full container recreation. The offline overlay overrides existing
provider credentials and disables all model calls. Fonts are served locally.

A clean Linux build exposed an npm optional-dependency lockfile issue. The
lockfile was regenerated without host `node_modules`, restoring Linux ARM64,
Linux x64 and macOS Rollup packages. Docker now runs the production build during
image creation. Container dependencies stay in the image rather than a reused
anonymous volume, so an older volume cannot hide updated dependencies.

The network-isolated backend test uses Docker `--network none`. The browser
offline-start test uses the explicit template overlay and cached images; the
host's physical internet connection was not disabled.

After offline verification, normal `docker compose up -d --no-build --pull never
--wait` restored the owner's OpenAI configuration. Both services passed health
checks. The DEMO_TRAP end-to-end model result above was measured in this running
configuration. The offline script remains available for the defense.

## Reproduce

```bash
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m backend.loader --data-dir ./data --database-url sqlite:///:memory:
```

Network-isolated backend suite using the prepared image:

```bash
docker run --rm --network none \
  -v "$PWD/backend:/app/backend:ro" \
  -v "$PWD/data:/app/data:ro" \
  -v "$PWD/examples:/app/examples:ro" \
  -e DATA_DIR=/app/data -e DATABASE_URL=sqlite:///:memory: \
  -e LLM_PROVIDER=template career-quest-backend:local \
  python -m pytest backend/tests -q
```

Explicit paid live model check, using fabricated facts only:

```bash
.venv/bin/python -m backend.check_llm --env-file .env
```

The official jury's additional profiles and scoring have not been supplied.
This record establishes the tested mandatory behavior; optional gamification,
rewards, calendar integrations and interface localization are outside this scope.
