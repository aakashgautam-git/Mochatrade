# MochaTrade Crisis Command

ACM MarketSphere 2026 — Problem Statement 3, The Flash-Crash Simulation.

**Source of truth: [`MOCHATRADE_PS3_RESEARCH.md`](./MOCHATRADE_PS3_RESEARCH.md).**
Every number, policy and mechanism in this project comes from that file. Do not
invent a risk parameter. If a parameter is missing, ask — do not guess.

---

## Current phase

> **PHASE 0 — SKELETON (complete).**
> Repo layout, tooling, design tokens, ARCHITECTURE.md, README, Makefile. No
> application code.
>
> **Next: Phase 1 — `riskengine` core** (book, oracle, marking, liquidation,
> controls, scenario, engine) with pytest coverage and the determinism test.

Every phase updates this marker and ends in a commit.

| Phase | Scope | Status |
|---|---|---|
| 0 | Skeleton, tooling, tokens, docs | Done |
| 1 | `riskengine` — pure-Python simulation core + tests | Not started |
| 2 | Django models, RiskPolicy seed, REST API | Not started |
| 3 | Web shell, design system, Simulate surface | Not started |
| 4 | Controls Off vs On — the proof | Not started |
| 5 | War room — the live 60-minute playbook | Not started |
| 6 | Classify, remediate, incident report | Not started |

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
    book.py  oracle.py  marking.py  liquidation.py
    controls.py  scenario.py  engine.py  classifier.py  remediation.py
  core/              Django app: models, admin, serializers, views, urls
  tests/
  requirements.txt
web/                 Vite app
  src/  components/ features/ lib/ pages/ styles/
ARCHITECTURE.md  README.md  Makefile
```

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
| `--text-faint` | `#6B625B` | tertiary |
| `--accent` | `#C98A5E` | mocha — primary actions, key data |
| `--accent-soft` | `rgba(201,138,94,0.12)` | accent wash |
| `--pos` | `#5FA37A` | muted green |
| `--neg` | `#D96A6A` | muted red |
| `--warn` | `#D9A441` | amber |
| `--halt` | `#8B5CF6` | **halt / intervention states ONLY** |

Light theme — **Report and Playbook pages only**: `--bg #FAF7F4`,
`--surface #FFFFFF`, `--text #1C1917`.

### Type

Inter (UI) + JetBrains Mono (all numbers), loaded from Google Fonts. Every
price, quantity, percentage and countdown uses the mono face with
`font-variant-numeric: tabular-nums` so digits never jitter during animation.
Use the `.num` class.

### Layout, motion, accessibility

- 8px spacing grid. Tailwind's stock scale is a 4px grid — use even steps only
  (`p-2` = 8, `p-4` = 16, `p-6` = 24, `p-8` = 32).
- Radii: 10px cards, 8px controls, 6px chips. 1px hairline borders, never heavy
  shadows.
- Generous whitespace. Density comes from good typography, not from cramming.
- Motion: 150–200ms ease-out only. No spring bounce, no scale-on-hover above
  1.02. Numbers transition by **counting**, not by fading. Respect
  `prefers-reduced-motion`.
- Every state that uses colour also uses a label or a shape. Text contrast
  ≥ 4.5:1 against its surface.

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
