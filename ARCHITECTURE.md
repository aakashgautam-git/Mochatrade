# MochaTrade Crisis Command

ACM MarketSphere 2026 — Problem Statement 3, The Flash-Crash Simulation.

**Source of truth: [`MOCHATRADE_PS3_RESEARCH.md`](./MOCHATRADE_PS3_RESEARCH.md).**
Every number, policy and mechanism in this project comes from that file. Do not
invent a risk parameter. If a parameter is missing, ask — do not guess.

---

## Current phase

> **PHASE 5.5 — ENGINE FIX (complete).** Velocity cooldown with escalation,
> every pause reopens through a throttled call auction, and frames now carry
> per-fill liquidation records and per-tick depth snapshots for Phase 6. The
> protected macro run went from 56 pauses and 83 swings to 7 and 10. Two
> decisions are open; see "Open decisions" below. 313 tests green.
>
> **PHASE 6 — SIMULATOR SURFACE (complete).** The simulator UI, playback, charts, derived metrics (ladder, spans, cascade split).
>
> **PHASE 7 — WAR ROOM (complete).** Declare a SEV-1 against any seeded
> scenario and run one clock from T+0 to T+60: the live engine for the market
> event, then the drill clock for the rest of the hour. Three-layer triage
> (Venue L3 / Market L2 / Broker L1) from live engine state, the eleven-step
> playbook with owners and due times, role-stamped decisions with a written
> rationale, guardrail confirms on irreversible calls, and the first public
> updates. The incident drives the top-bar pill, including the new "Trading
> paused" state; simulator replays never do. Every live-engine request holds a
> per-incident lock.
>
> **PHASE 8 — FORENSICS (complete).** The published APE test (deviation
> beyond the tier NRR, 50% reversion inside 60 s, survival at the Reference
> Composite) runs on the incident's own tape and classifies every
> force-closed account A–G with its working. The incident verdict comes from
> the tape signatures, never from the scenario's label; with controls on, all
> six scenarios classify as designed. The Forensics page shows the verdict,
> the signals behind it, the deviation charts, and per account the three
> criteria, the persisted per-source oracle tape and the book at its decisive
> fill. Classification rules: see `riskengine/classifier.py`.
>
> **NEXT: PHASE 9 — Remediation.**
>
> **PHASE 5 — DESIGN SYSTEM AND SHELL (complete).** Primitives in
> `web/src/components/ui/`, themed chart wrappers in `components/charts/`, the
> app shell (rail, top bar, system-state pill, IST clock), a document palette
> for Report and Playbook, and `/kitchen-sink` rendering everything. Verified in
> a real headless browser: 60/60 Tab stops show a 2px focus ring, zero layout
> shift while stats count, and contrast measured live in both palettes. The
> screening demo lives on at `/demo` (standalone) and `/` (inside the shell).


Phases are numbered by the project plan, not by build order: the risk engine
(3) was built before the Django layer (2) because everything downstream needs a
trustworthy engine more than it needs a database.

| # | Phase | Status |
|---|---|---|
| 0 | Context — the domain research brief | Done |
| 1 | Scaffold — repo, tooling, design tokens, docs | Done |
| 2 | Django models + admin | Done |
| 3 | Risk engine — pure-Python core + tests | Done |
| 4 | REST API | Done |
| 5 | Design system | Done |
| 5.5 | Engine fix — velocity cooldown, reopening auction, Phase 6 data | Done |
| 6 | Simulator surface | Done |
| 7 | War room | Done |
| 8 | Forensics | **Done** |
| 9 | Remediation — claims, make-whole, pro-rata cap overflow | **Next** |
| 10 | Comms | Not started |
| 11 | Incident report | Not started |
| 12 | Seed data + polish | Not started |

Every phase updates this marker and ends in a commit. Do not start the next
phase without being asked.

---

## What this is

An interactive web app that does four things:

1. **SIMULATE** a flash crash on a perpetual futures market, tick by tick,
   deterministically — order book, mark price, oracle, liquidation cascade.
2. **PROVE** that a stack of risk controls measurably reduces the damage, by
   running the identical shock with controls off vs on and quantifying the delta.
3. **DRILL** the 60-minute crisis playbook as a live war room where the operator
   makes real decisions that change the simulation outcome.
4. **RESOLVE** the aftermath — classify the event against a published Abnormal
   Price Event policy, compute who gets made whole, generate the incident report.

---

## The critical domain fact — do not get this wrong

**MochaTrade is not an exchange.** It is a non-custodial broker / front-end
built on Hyperliquid, monetised via builder codes. It **cannot pause a matching
engine** and it **cannot roll back trades**. Fills are on-chain and final; the
builder agent wallet can execute trades but cannot move user funds.

The app must model three distinct layers and make the operator triage between
them. Minute one is not "what did the market do" — it is "which of our three
layers broke."

| Layer | Scope | MochaTrade's power |
|---|---|---|
| **L3 VENUE** | Hyperliquid / HyperCore: the shared book, HLP, ADL | **None.** HyperCore keeps matching. |
| **L2 MARKET** | A HIP-3 dex MochaTrade deploys: oracle, margin tiers, max leverage, `haltTrading` | **Full control, full liability.** 500k HYPE slashable up to 100% for a bad oracle or downtime. |
| **L1 BROKER** | The app, API, order router, margin display, UPI on-ramp, INR ledger, support | **Full control.** |

Two consequences that must stay visible in the UI:

- `haltTrading` is the nuclear option, not step one: it cancels all orders and
  settles everyone at the current mark — the very mark under dispute. The
  Protect Switch (reduce-only + liquidation throttle + 3x leverage cap) comes
  first.
- For a three-person team, the most likely *"we caused this"* failure is **L1**,
  not the matching engine: the app froze, the API rate-limited, or a UPI top-up
  did not settle before the liquidation fired.

### Product thesis — put this on screen

> **Trades stand. People get made whole.**

Never reverse, always compensate, decide by a rule published *first*. Reversal
is unavailable (on-chain), creates a second set of victims (JELLY, Mar 2025),
is hostile to Indian precedent (SAT/Emkay), and runs against CFTC/FIA best
practice (all trades stand; adjust rather than cancel).

---

## Tech stack — do not substitute

**Backend:** Python 3.11+, Django 5.x, Django REST Framework, SQLite,
django-cors-headers, pytest + pytest-django.

**Frontend:** Vite + React 18 + TypeScript, Tailwind CSS v3, Recharts,
lucide-react, zustand (client state), @tanstack/react-query (server state),
framer-motion (sparingly).

**Explicitly excluded:** websockets, Channels, Celery, Redis, Docker.
Real-time feel comes from server-held deterministic state stepped via plain
REST calls and animated client-side. This is a hackathon — it must never fail
on stage.

---

## Repo layout

```
backend/
  manage.py
  config/            settings, urls, wsgi
  riskengine/        PURE PYTHON. No Django imports anywhere in here.
    params.py  rng.py                      (added in Phase 1 — see below)
    book.py  oracle.py  marking.py  liquidation.py
    controls.py  scenario.py  engine.py  classifier.py  remediation.py
  core/              Django app: models, admin, serializers, views, urls
  tests/
  requirements.txt
web/                 Vite app
  src/  components/ features/ lib/ pages/ styles/
ARCHITECTURE.md  README.md  Makefile
```

### Two modules added to the original layout

- **`params.py`** — `RiskParams`, the pure-Python mirror of the `RiskPolicy`
  model, plus `FIELD_SOURCES`, a citation for every single field. Everything
  imports it, so it cannot live inside `controls.py` (which is about which
  controls are *on*, not what the numbers *are*).
- **`rng.py`** — the seeded generator. Wraps `random.Random` for the uniform
  stream but implements `normal()` as Box-Muller, because `random.gauss` caches
  a spare deviate and so consumes a varying number of uniforms per call, which
  quietly breaks replay. Sub-streams are derived by label through BLAKE2b, not
  `hash()`, whose salt is randomised per process.

### Three parameters are ours, not the brief's

Marked `DERIVED` in `FIELD_SOURCES` and stated as such rather than dressed up as
sourced: `partial_liq_target_mm_multiple` (1.5x MM), `velocity_trigger_frac_of_dcb`
(0.5) and `price_band_frac_of_dcb` (1.0). The brief specifies each mechanism but
publishes no value for it.

### Two modelling rules the engine depends on

- **A leverage cap shrinks the position, never the capital.** The notional
  distribution describes the uncapped book; a cap holds the user's money fixed
  and reduces what they can open with it. Inverting this makes every cap look
  like it *increases* losses.
- **Loss is valued at the final Reference Composite for every run**, and
  deposits paid in mid-run are netted out. Valuing each run at its own final
  mark means a stack that merely moved the mark looks like it moved the money.

### The anti-drift guard

`RiskPolicy` and `RiskParams` must stay in exact 1:1 correspondence.
`tests/test_policy_mirror.py` fails the build if a field exists in one and not
the other, if a model default is retyped instead of read from the dataclass, if
any `help_text` diverges from its citation, or if `to_params()` stops
round-tripping. Adding a risk parameter means adding it to `RiskParams` and
`FIELD_SOURCES` first; the model follows.

The two ladders — the five-rung maintenance-margin table and the per-tier
NRR/DCB table — are related rows (`PolicyMarginTier`, `PolicyInstrumentTier`)
edited as admin inlines, not JSON blobs. They are the parameters most likely to
be changed live in front of a judge.

`IncidentAction` is append-only and this is enforced, not merely intended: add,
change and delete all return 403 from the admin.

### The config-bypass guard

No file in `core/` may import `DEFAULT_PARAMS` or construct `RiskParams`, except
`models.py` (which generates the mirror and owns `to_params()`) and
`seed_policy.py` (which builds v1 from the defaults). Every engine run goes
through `core/runner.py`, which reads the active `RiskPolicy`.
`tests/test_api.py::test_no_view_bypasses_the_active_policy` enforces this by
AST scan, so a docstring mentioning the rule cannot trip it and an aliased
import cannot slip past it. Without this rule the admin's policy editor would be
decorative: a judge edits a tier and the page does not move.

### Run cache

A completed run is keyed on `(scenario, controls_enabled, seed,
policy_fingerprint)`. The fingerprint hashes the actual parameter VALUES, not
`RiskPolicy.version` — editing a margin tier does not bump the version, and a
version-keyed cache would serve a stale run that contradicts the admin.
Reverting an edit restores the old fingerprint and hits the original runs.

### The evidence tape

Every frame carries `sources`: one `SourceObservation` per oracle source with
the price the composite used, the raw price the source printed, its effective
weight (zero when excluded), whether it was clamped, and why it was excluded.
Closed and unreachable sources record no price rather than a live-looking one.
Persisted runs write the same data into `PriceObservation`, alongside three
derived rows per tick: our mark, the published composite, and the
reconstructed Reference Composite. `riskengine.engine.FRAME_SCHEMA` is part of
the run cache key, so adding a frame field invalidates stored runs instead of
serving them without it. Responses are gzipped; a full comparison is ~280 KB on
the wire.

### Pauses, cooldown and the reopening auction (Phase 5.5)

- **Velocity cooldown and escalation.** After a velocity pause the layer may not
  fire for `velocity_cooldown_seconds`; if the move is still too fast in the
  first window after that, the next pause escalates (5s, 20s, 80s, capped at the
  breaker's 120s). Before this the protected macro run paused 56 times and the
  mark swung 83 times.
- **Every pause reopens through a call auction** (`riskengine/auction.py`).
  Queued liquidations become market orders against resting depth inside a
  collar -- the pre-trade price band around the Reference Composite -- and clear
  at one price: max volume, then min imbalance, then nearest the reference.
  What cannot match carries into continuous trading, which opens at that price.
- **The auction is throttled.** Unthrottled, the whole queue entered at once
  and max-volume uncrossing walked it to the collar floor, printing a 95-390 bps
  wick in one trade. The published participation cap applies to the auction's
  intake exactly as it does to continuous trading.
- **Known tension, not yet resolved:** the 20% TWAP participation moves price
  about 88 bps/s, while the velocity layer trips at about 40 bps/s. The engine's
  own permitted pace trips its own breaker, which is the root cause of the
  stutter. The cooldown and auction contain it; recalibrating the throttle
  would remove it. That is a policy decision, recorded in the Phase 5.5 report.

### Data recorded for Phase 6

Every frame carries `liquidations` (one record per fill: account, stage,
quantity, notional, price, whether it cleared in an auction, whether it closed
the account, and APE criterion 3) and `depth` (resting INR notional in ten
10 bps buckets a side, after the tick's consumption). Ten 10 bps buckets cover
exactly the 1% band the throttle's participation cap is measured against, and
sizes-only keeps a snapshot to twenty integers because prices follow from the
touch. Both are written to `LiquidationRecord` and `DepthSnapshot` in the same
transaction as the oracle tape. The stage that closed an account is its last
record with `closed` set; grouping a tick's records by stage is the cascade
split. A full comparison is ~425 KB gzipped.

### Open decisions (Phase 5.5)

1. **Throttle vs velocity calibration.** At 20% participation the engine's own
   pace (~88 bps/s) exceeds the velocity trigger (~40 bps/s). The shipped 10s
   cooldown keeps the controls ahead everywhere but pauses trading for 581 of
   720 seconds in the macro run and lets each reopen run 10s unchecked. An 8%
   participation removes the conflict (1 pause, 0 swings) at the cost of more
   liquidations and ADL. Not changed without approval: it is published policy.
2. **Resolved: the dynamic circuit breaker now fires.** Its bounds were
   (lookback low − variant, lookback high + variant), so a steady crash dragged
   its own floor down and never breached (zero fires in six scenarios). Bounds
   are now (lookback HIGH − variant, lookback LOW + variant), the look-back
   pauses during the breaker's own pause and restarts on resume. It fires in
   5 of 6 scenarios; controls-on still beats controls-off everywhere; the
   largest reopen wick in the protected macro run fell from 413 to 223 bps.

### Live engines

War-room incidents step a live `Engine` held in `runner._LIVE`, keyed by
incident code. It is never trusted to survive a restart: on a miss it is
rebuilt by replaying the persisted `IncidentAction` log from tick 0, which lands
on byte-identical state because the engine is deterministic.

### Money on the wire

Ledger figures serialise as two-place decimal strings (`"25000.00"`), never as
JSON numbers. Tick series stay numeric — they are chart samples, not money. The
one exception is the legacy `/api/compare/<slug>/`, which keeps numeric money
because the shipped screening-round page parses a number.

---

## Design direction

The aesthetic is **calm under pressure** — Linear, or a Bloomberg terminal
redesigned by someone with taste. **Not** a crypto casino.

**Banned:** neon, purple-blue gradients, glassmorphism, glow effects, emoji in
the UI.

Dark is the default (this is a war room). Warm charcoal, not blue-black — it
should feel like the *mocha* in MochaTrade.

### Tokens

Defined in `web/src/styles/tokens.css`, wired into `web/tailwind.config.js`.
Never write a raw hex in a component.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#14110F` | page |
| `--surface` | `#1C1917` | cards |
| `--surface-2` | `#262220` | elevated / hover |
| `--line` | `rgba(255,255,255,0.08)` | hairline borders |
| `--text` | `#F2EDE7` | primary |
| `--text-dim` | `#A79E96` | secondary |
| `--text-faint` | `#8C827A` | tertiary (was `#6B625B`, which failed AA at 2.93:1) |
| `--accent` | `#C98A5E` | mocha — primary actions, key data |
| `--accent-soft` | `rgba(201,138,94,0.12)` | accent wash |
| `--pos` | `#5FA37A` | muted green |
| `--neg` | `#D96A6A` | muted red |
| `--warn` | `#D9A441` | amber |
| `--halt` | `#8B5CF6` | **halt / intervention states ONLY** |

Light theme — **Report and Playbook pages only**: `--bg #FAF7F4`,
`--surface #FFFFFF`, `--text #1C1917`, `--text-faint #766C65` (was `#8A807A`,
3.85:1).

### Type

Inter (UI) + JetBrains Mono (all numbers), loaded from Google Fonts. Every
price, quantity, percentage and countdown uses the mono face with
`font-variant-numeric: tabular-nums` so digits never jitter during animation.
Use the `.num` class.

### Semantic tokens — `web/src/styles/semantic.css`

Derived from `tokens.css` by `color-mix`; no new hex values.

- **Never put a Tailwind opacity modifier on a token colour.** `bg-pos/10` and
  `border-neg/30` are silently dropped: Tailwind cannot inject alpha into an
  opaque `var(--pos)`. Use `bg-pos-soft`, `border-pos-edge`, `text-pos-fg`.
  (The screening demo's delta chips have never had their tints for this reason.)
- **Text on a tint uses the `-fg` tokens.** Raw `--halt` fails as text (4.13:1);
  every `-fg` on its own tint measures 5.3–7.1:1 in both palettes.
- **Solid fills come in pairs that invert per palette**: `accent-solid` /
  `on-accent-solid`, `halt-solid` / `on-halt-solid`. The naive pairs pass dark
  and fail light, and the top bar is visible on the light document pages.
- **`--text-faint` now passes AA in both palettes**: `#8C827A` dark (4.65:1 on
  surface, 5.00:1 on page) and `#766C65` light (5.12:1, 4.80:1). The original
  values failed at 2.93:1 and 3.85:1.
- After editing `tailwind.config.js`, **restart Vite**. The dev server does not
  reload the config, so new colour classes silently fail to generate.

### Layout, motion, accessibility

- 8px spacing grid. Tailwind's stock scale is a 4px grid — use even steps only
  (`p-2` = 8, `p-4` = 16, `p-6` = 24, `p-8` = 32).
- Radii: 10px cards, 8px controls, 6px chips. 1px hairline borders, never heavy
  shadows.
- Generous whitespace. Density comes from good typography, not from cramming.
- Motion: 150–200ms ease-out only. No spring bounce, no scale-on-hover above
  1.02. Numbers transition by **counting**, not by fading. Respect
  `prefers-reduced-motion`. Skeletons are static; the only loop is the button
  spinner, and it stops under reduced motion.
- **The one named exception: number count-up runs 400ms** (`COUNT_MS` in
  `web/src/hooks/useCountUp.ts`). At 200ms a count reads as a flicker rather
  than as counting, which defeats the rule that numbers transition by counting.
  Nothing else may exceed 200ms.
- Every state that uses colour also uses a label or a shape. Text contrast
  ≥ 4.5:1 against its surface.

### The shell

- **Routing is a 60-line history router** (`web/src/app/router.tsx`), by
  decision: no `react-router`. `/demo` is the screening page standalone; `/` embeds it inside
  the shell until Phase 6.
- **The system-state pill** changes colour, words and icon together, with a
  2px band across the top of the viewport for any non-normal state. LIQ PAUSED
  and HALTED share `--halt` (reserved for interventions) and differ by
  treatment: a pause is a tint, a halt is the one solid fill in the interface.
- **Chart colours** are read from the live tokens by `useChartTheme`, which
  re-reads on `data-theme` changes, so charts follow the document palette.
- **Control activity on the PriceChart is a lane above the plot**, one segment
  per real span. Full-height shading either striped the chart or, merged,
  claimed eleven minutes of intervention where there were 56 five-second pauses.

---

## Engineering rules

1. **`riskengine/` is pure Python.** Zero Django imports, zero DB access, zero
   network, zero wall-clock reads. Enforced by
   `backend/tests/test_engine_purity.py`. The credibility of the demo rests on
   this package being deterministic and independently testable.
2. **Every run is seeded.** Same seed + same params + same actions =
   byte-identical output. Asserted in a test.
3. **No magic numbers in view code.** All risk parameters live in a versioned
   `RiskPolicy` model, seeded from the research doc's defaults.
4. **TypeScript strict mode on. No `any`.**
5. **Every API response is typed** in `web/src/lib/types.ts`, hand-written to
   match the DRF serializers exactly. Serializer change and type change land in
   the same commit.
6. **Commit after each phase** with a clear message, and update the phase
   marker above.

### On stage, the parameters are a proposal — say so

The *parameters* are our proposal; the *mechanisms* are Binance's, CME's and
Hyperliquid's published specs; the engine is deterministic and unit-tested, so
any judge can change a parameter and watch the result move. That honesty is
part of the pitch, not a caveat to it.
