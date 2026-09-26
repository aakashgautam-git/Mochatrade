# Handoff

Checkpoint of 26 Sep 2026, before moving the build to a cloud machine.
`ARCHITECTURE.md` is the authority for the design and the phase table;
`PROGRESS.md` has three lines per phase (done / deviations / issues).

## Current phase

**Phase 12 — Seed data + polish. Next; not started.** Phases 0–11 are done
and committed on `main`. After Phase 12 comes the final pass.

| Phase | Commit |
|---|---|
| Circuit-breaker bounds fix | `18681be` |
| 7 War room | `eec2c70` |
| 8 Forensics | `4cae1b5` |
| 9 Remediation | `88c0da3` |
| 10 Comms + public status page | `2e57c1b` |
| 11 Report + Playbook | `b776174` |

Last full check at `b776174`: backend 377 passed, 2 skipped (`make test`);
web 34 passed (`make test-web`); TypeScript strict typecheck clean. The
production build (`make build`) has not been run since Phase 6.

## What's done

- **Simulator** (`/simulator`): six seeded crises, controls off vs on, shared
  price axis, cascade, depth, oracle tape. **Overview** (`/`) and the
  screening demo (`/demo`) are unchanged.
- **War Room** (`/war-room`): declare a SEV-1, one T+0 to T+60 clock (engine
  ticks, then the drill clock), three-layer triage, the 11-step playbook,
  role-stamped decisions with guardrail confirms, public updates. It drives
  the top-bar pill, including "Trading paused"; simulator replays never do.
- **Forensics** (`/forensics`): the published APE test on the incident's own
  tape; every force-closed account classified A–G with its working; the
  per-source oracle tape and the book at each account's decisive fill.
- **Remediation** (`/remediation`): make-whole per class, the five-step
  funding waterfall up to the per-incident cap, pro-rata above it,
  provisional credit for C/D/E, claim decisions, and "Recalibrate from
  simulation" (reserve = 2x worst modelled loss, new policy version, cap
  untouched).
- **Comms** (`/comms`): nine templates across four audiences, language
  guardrails from the research (blocks and warnings), draft → IC approval →
  publish.
- **Public status page** (`/status`, standalone, light): six components from
  live state in plain words, incident timeline, public updates only.
- **Report** (`/report`) and **Playbook** (`/playbook`): light-palette
  documents; precedents and India angles placed where the research puts them.
- Every nav section is a real page; the placeholder page is deleted.

## What's half-done

Nothing in the code is half-written; the tree was clean at `b776174`.

- **No demo incident on a fresh database.** `make seed` creates the policy,
  the six scenarios and the twelve cached runs, but no incident. Forensics,
  Remediation, Comms and Report therefore open on an empty state until an
  incident is declared in the War Room and its clock is run. This is Phase
  12's first job.
- **Final pass not run:** click-through of every nav section, `make build`,
  final `ARCHITECTURE.md` and handoff update, final report.
- **Open by decision** (`KNOWN_ISSUES.md`): calibrating the velocity guard
  against the liquidation throttle.
- **Local dev database only** (`backend/db.sqlite3`, not in git): it holds
  test incidents and a policy v2 written by a recalibration run. A fresh
  clone starts clean on policy v1 after `make seed`. Claims opened before the
  Indian-number formatting change show "Rs 15,000,000"-style text in that
  local database; re-opening claims refreshes it.

## What's next

1. **Phase 12, seed data.** A `seed_demo` management command, wired into
   `make seed`. It declares a few demo incidents, runs their markets, then
   classifies, opens claims and publishes the first updates, so every page
   has real engine data on a fresh start. Suggested incidents:
   - macro cascade, controls off: class C, pro-rata above the cap;
   - broker outage, controls on: class D;
   - long-tail manipulation: class G.
2. **Phase 12, polish.** Fix only what the click-through shows.
3. **Final pass.** Run the full test suites, the typecheck and the build.
   Click through every nav section. Update `ARCHITECTURE.md` and this file.
   Write the final report.

## Cloud setup

Prerequisites:
- **Python 3.13.** The system `python3` 3.10 is too old.
- **Node 23.6 or newer.** The web unit tests run `.ts` files directly through
  Node's built-in type stripping. It was developed on Node 26.
- `make` and `git`.

```sh
git clone https://github.com/aakashgautam-git/Mochatrade.git
cd Mochatrade

# Backend: virtualenv, dependencies, database
cd backend
python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
cd ..

# Web: use a project-local npm cache. The default ~/.npm was root-owned on
# the original machine and broke installs; the Makefile does the same.
cd web
npm_config_cache=../.cache/npm npm install
cd ..

# Seed: risk policy v1, six scenarios, twelve pre-computed runs (~15 s)
make seed

# Run: Django on :8000 and Vite on :5173 (Vite proxies /api to Django)
make dev

# Verify
make test        # backend (pytest), ~2.5 min
make test-web    # web unit tests
make typecheck
make build
```

`make setup` does the venv, pip install, migrate and npm install in one step.
All Makefile paths are relative, because the repository may sit under a
directory whose name contains a space. The database is SQLite at
`backend/db.sqlite3` (gitignored). The timezone is Asia/Kolkata.
