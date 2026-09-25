# MochaTrade Crisis Command

**ACM MarketSphere 2026 — Problem Statement 3: The Flash-Crash Simulation.**

An interactive war room for a perpetual-futures flash crash. It does four things:

1. **Simulate** a crash tick by tick, deterministically — order book, oracle,
   mark price, liquidation cascade.
2. **Prove** that a stack of risk controls reduces the damage, by running the
   identical seeded shock with controls off vs on and quantifying the delta.
3. **Drill** the first 60 minutes as a live playbook where the operator's
   decisions change the outcome.
4. **Resolve** the aftermath — classify the event against a published Abnormal
   Price Event policy, compute who gets made whole, and generate the report.

The premise that makes it different: **MochaTrade is not an exchange.** It is a
non-custodial broker built on Hyperliquid. It cannot pause the matching engine
and it cannot roll back a trade. So the operator has to triage across three
layers — the venue, the HIP-3 market MochaTrade deploys, and MochaTrade's own
app — and the only honest policy is:

> **Trades stand. People get made whole.**

---

## Setup

Requires **Python 3.11+** and **Node 18+**.

```bash
make setup     # venv + pip install + migrate, then npm install
make dev       # Django on :8000, Vite on :5173
```

Open <http://localhost:5173>.

If `python3.13` is not your interpreter, pass your own:
`make setup PY=python3.11`.

<details>
<summary>Without make</summary>

```bash
# backend
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/python manage.py migrate && ../.venv/bin/python manage.py runserver 8000

# frontend, in a second shell
cd web && npm install && npm run dev
```
</details>

---

## Commands

| Command | What it does |
|---|---|
| `make dev` | Both dev servers |
| `make test` | pytest suite, including the determinism and engine-purity tests |
| `make typecheck` | TypeScript strict check |
| `make build` | Production build of the web app |
| `make seed` | Seed the policy and scenarios, then pre-run all twelve comparisons |
| `make clean` | Remove venv, node_modules, caches and the local database |

---

## Layout

```
backend/
  riskengine/   pure Python simulation core — no Django, fully unit-tested
  core/         Django app: models, serializers, views
  tests/
web/            Vite + React + TypeScript client
MOCHATRADE_PS3_RESEARCH.md   the domain brief: source of truth for every number
ARCHITECTURE.md                    architecture, design tokens, engineering rules
```

---

## A note on the numbers

The **parameters** in this project are a proposal. The **mechanisms** are the
published specifications of Binance (mark price and index construction), CME
and the CFTC/FIA (volatility control layering), and Hyperliquid (two-stage
liquidation, backstop vault, HIP-3). The engine is deterministic and
unit-tested, so any parameter can be changed and the result recomputed. Full
provenance is in [`MOCHATRADE_PS3_RESEARCH.md`](./MOCHATRADE_PS3_RESEARCH.md).
