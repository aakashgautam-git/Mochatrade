# PHASE 6 — SIMULATOR SURFACE · Handoff brief

You are continuing an existing, working project. Your job is **Phase 6 only**.
Build it, verify it, commit it, report, and **stop**. Do not start Phase 7.

---

## 0. Read before you touch anything

Read these in full, in this order:

1. `ARCHITECTURE.md` — the authoritative brief: the domain fact, the design
   tokens, the engineering rules, the phase table, and two **open decisions**.
   If anything in this prompt conflicts with it, ARCHITECTURE.md wins — tell me
   about the conflict.
2. `MOCHATRADE_PS3_RESEARCH.md` — the source of truth for every number, policy
   and mechanism. **Never invent a risk parameter.**
3. Any local, gitignored agent stub file just points back to ARCHITECTURE.md. Ignore it.

**When to stop and ask instead of guessing** (write the question, do not proceed):

- You need to change anything in `backend/riskengine/` or a Django model.
- You would need a new npm or pip dependency.
- You would need to change a risk parameter or the active `RiskPolicy`.
- You would resolve one of the open decisions in section 5.
- You would change `/demo`, the Overview page, or the shape of
  `GET /api/compare/<slug>/`.

---

## 1. The project in six lines

MochaTrade Crisis Command, ACM MarketSphere 2026, problem statement 3 (the
flash-crash simulation). **MochaTrade is not an exchange.** It is a
non-custodial broker built on Hyperliquid. It cannot pause the matching engine
and cannot roll back a trade. The app simulates a flash crash deterministically,
**proves** a stack of risk controls reduces the damage (same seeded shock,
controls off vs on), drills the 60-minute playbook, and resolves the aftermath.
Thesis, visible in the UI: **"Trades stand. People get made whole."**

---

## 2. Environment and commands

- **The repo path contains a space**: `/Users/pranav/Desktop/mocha trade`. Quote
  every path in every shell command.
- **The Python venv is `backend/.venv` (Python 3.13).** The system `python3` is
  3.10 and is **too old**. Always use `backend/.venv/bin/python` and
  `backend/.venv/bin/pytest`.
- **`~/.npm` is root-owned on this machine and breaks installs.** Run npm as
  `npm_config_cache=../.cache/npm npm …` from `web/` (the Makefile already does
  this). You should not need to install anything.

| Command (from repo root) | What it does |
|---|---|
| `make dev` | Django on :8000 and Vite on :5173. Vite proxies `/api` to Django. |
| `make seed` | Seed the policy and scenarios, then pre-run all 12 comparisons (~13s). Idempotent. |
| `make test` | Backend pytest. **Currently 313 passed, 2 skipped** (~2 min). |
| `make typecheck` | `tsc --noEmit`, strict. |
| `make build` | Production web build. The >500 kB chunk warning (Recharts) is known; ignore it. |

Open http://localhost:5173. Useful routes: `/` (Overview), `/simulator` (your
page), `/kitchen-sink` (the design system), `/demo` (the frozen screening demo).

**Git:** branch `main`. HEAD is `dcf3863 Record per-fill liquidations and
per-tick depth for Phase 6`. Commit as the configured git user. **No AI-tool
attribution anywhere** — no co-author trailers, no "generated with" lines, no
tool names in commits or files. **Do not push.** `docs/screenshots/` and the local agent stub are
gitignored; keep it that way.

---

## 3. Rules enforced by tests, or broken silently if ignored

Enforced by tests (do not weaken any test to make it pass):

- `riskengine/` imports no Django (`tests/test_engine_purity.py`).
- `RiskPolicy` mirrors `riskengine.params.RiskParams` 1:1
  (`tests/test_policy_mirror.py`).
- Nothing in `core/` except `models.py` and `seed_policy.py` may import
  `DEFAULT_PARAMS` or construct `RiskParams` (`tests/test_api.py`).
- Controls-on beats controls-off in all 6 scenarios (`tests/test_engine.py`).
- Byte-identical replay (`tests/test_determinism.py`).

Conventions nothing will catch — each one has already caused a real bug here:

1. **Never use a Tailwind opacity modifier on a token colour.** `bg-pos/10`,
   `border-neg/30` and the like **compile to nothing, silently**. Use the
   semantic tokens instead: `bg-pos-soft`, `border-pos-edge`, `text-pos-fg`
   (likewise for `neg`, `warn`, `halt`, `accent`), and the solid pairs
   `bg-accent-solid` / `text-on-accent-solid` and `bg-halt-solid` /
   `text-on-halt-solid`. They are defined in `web/src/styles/semantic.css`.
2. **After editing `web/tailwind.config.js`, restart Vite.** The dev server does
   not reload the config, and new classes silently fail to generate. (Primary
   buttons rendered identically to ghost for exactly this reason.)
3. **No raw hex in components.** Colours come from tokens. Charts get concrete
   colour strings from `useChartTheme()`, which also follows the light theme.
4. **Every number uses the `.num` class** (JetBrains Mono, tabular figures).
5. **TypeScript is strict with `exactOptionalPropertyTypes` and
   `noUncheckedIndexedAccess`.** An optional prop that may receive `undefined`
   must be typed `?: T | undefined`, and `array[i]` is `T | undefined`. No `any`.
6. **lucide-react is 0.453.** Some icon names differ (e.g. `Loader2` does not
   exist, use `LoaderCircle`). Verify a name with
   `grep "declare const Name:" web/node_modules/lucide-react/dist/lucide-react.d.ts`.
7. **Routing is the in-house router** (`web/src/app/router.tsx`: `Link`,
   `navigate`, `usePathname`). Do **not** add react-router; that was an
   explicit decision.
8. **Motion:** 150–200ms ease-out only. The single named exception is number
   count-up at 400ms (`COUNT_MS`). Skeletons are static. Respect
   `prefers-reduced-motion`.
9. **Accessibility:** colour is never the only signal; always add text or a
   shape. Text contrast ≥ 4.5:1. Every interactive element shows the 2px mocha
   focus ring (global `:focus-visible` — do not add `outline-none`).
10. **Money:** new endpoints send money as two-place decimal strings
    (`MoneyString`). Parse with `parseMoney()` **for display only**. The legacy
    `/api/compare/<slug>/` alone keeps numeric money.
11. **`GET /api/scenarios/` returns a bare list**, not `{scenarios: [...]}`.
    Instrument tier and `has_rth` are on the **detail** endpoint
    `GET /api/scenarios/<slug>/` (`instrument.tier`, `instrument.has_rth`,
    `is_offhours`).
12. **Do not delete or restyle** `web/src/components/legacy/*` or
    `pages/LegacyDemo.tsx`. `/demo` (standalone) and `/` (Overview, embedded)
    both depend on them and are the fallback if the live round comes early.

---

## 4. Current state

**Done:** phases 0–5 and 5.5.

- The deterministic engine, with per-source oracle tape, velocity cooldown and
  escalation, reopening call auctions, per-fill liquidation records, and
  per-tick depth snapshots.
- A versioned `RiskPolicy` with a citation on every field.
- 18 DRF routes. Runs are cached by a policy fingerprint and pre-warmed.
- The design system: `web/src/components/ui/*` and
  `web/src/components/charts/*`.
- The shell: rail, top bar with system-state pill, IST clock, light palette for
  Report and Playbook.
- `/kitchen-sink`.

**`/simulator` is a placeholder.** That is your phase.

The files you will work in:

```
web/src/App.tsx                 route branches (add /simulator here)
web/src/app/nav.ts              rail entries; /simulator has `pending: {phase: 6}`
web/src/app/store.ts            zustand: setInstrument, systemState, …
web/src/lib/api.ts              fetchCompare(slug), fetchActivePolicy(), parseMoney, rupees
web/src/lib/types.ts            mirrors backend/core/serializers.py exactly
web/src/components/ui/          Card, Stat, Button, Toggle, Slider, Select, Badge,
                                Timeline, Countdown, Sparkline, EmptyState, Skeleton, Toast
web/src/components/charts/      PriceChart, DeviationChart, CascadeChart, DepthLadder,
                                ChartLegend, ChartTooltip, useChartTheme (+ minuteTicks)
web/src/pages/KitchenSink.tsx   uses fixtures for Cascade and Depth — replace them (§6.7)
```

---

## 5. Open decisions — do NOT resolve these

Build around them. Mention them in your report if they affect what you show.

1. **Throttle vs velocity calibration.** At the approved 20% participation, the
   engine's own liquidation pace (~88 bps/s) exceeds the velocity trigger
   (~40 bps/s). The shipped 10s cooldown keeps the controls ahead everywhere,
   but pauses trading for 581 of 720 s in the protected macro run. Each reopen
   then shows a V-dip in last-traded price. **Show this honestly; do not tune
   anything.**
2. **The dynamic circuit breaker never fires** (a bounds bug, awaiting a
   decision). Expect `pause_reason` values of `"velocity"` in practice; still
   handle `"circuit_breaker"` and `"halt"`.
3. **The global system-state pill has no "trading paused" state.** The pill
   represents the **live** market (Phase 7). **A replay must not drive it.** In
   the simulator, show state per panel with a Badge (§6.4).
4. Attribution by individual control needs an API that does not exist
   (`controls_enabled` is a boolean). **Out of scope** — do not build it.

---

## 6. PHASE 6 SPECIFICATION

**Goal.** The page a judge clicks around in to see the proof: pick any of the 6
scenarios, then play the identical seeded shock controls-off and controls-on
side by side. The mark, the book, the cascade and the outcome all move together
on one clock.

**Data:** one call per scenario: `fetchCompare(slug)` → `POST /api/runs/compare/`
→ `CompareResponse` with `off.ticks[]` and `on.ticks[]` (600–720 ticks each),
`summary` per side, and `delta`. Responses are ~425 KB gzipped and served from
cache in ~150ms.

- Use `useQuery(["compare", slug], …)`. `staleTime` is already `Infinity` in
  `main.tsx`.
- Fetch the active policy with `fetchActivePolicy()` and the scenario detail
  with `GET /api/scenarios/<slug>/`.
- **No backend changes.** Everything below is derivable client-side.

### 6.1 The data contract you consume (per `Tick`)

`tick, t_seconds, true_price, composite, composite_rung, oracle_health,
reference, book_mid, best_bid, best_ask, spread_bps, depth_pct_of_baseline,
mark, mark_source, divergence_bps, reduce_only, liquidations_paused,
trading_paused, pause_reason, velocity_level, halted, max_leverage, stage,
liquidated_this_tick, cum_liquidated_accounts, cum_liquidated_notional,
adl_accounts (cumulative), insurance_balance, unnecessary_liquidations
(PER TICK, not cumulative), accounts_open, aggregate_equity,
auction (AuctionRecord | null), liquidations (LiquidationRecord[]),
depth (DepthSnapshot | null), sources (SourceObservation[])`.

Exact derivations:

- **Depth ladder rows.** `depth.bids[i]` and `depth.asks[i]` are INR notional
  in bucket `i` (0 = nearest the touch). Label each row at its outer edge:
  - `bidPrice(i) = best_bid × (1 − (i+1) × depth.bucket_bps / 10_000)`
  - `askPrice(i) = best_ask × (1 + (i+1) × depth.bucket_bps / 10_000)`

  Feed `DepthLadder` with `levels` built this way, `mid = book_mid`,
  `spreadBps = spread_bps`, and `depthOfBaseline = depth_pct_of_baseline`.
- **Cascade split.** Group `tick.liquidations` by `stage` (`partial`, `market`,
  `backstop`, `adl`) and sum `notional` (INR) per tick.
- **Stage that closed an account.** The last record for that `account_id` with
  `closed === true`.
- **Control lane.** Contiguous tick spans (gap = 1 tick, **never merge across
  gaps**; merging turned 56 short pauses into one fake 11-minute band):
  - `trading_paused` spans, labelled by `pause_reason`: `velocity` →
    "Velocity pause", `circuit_breaker` → "Circuit breaker", `halt` → "Halted".
    Tone `halt`.
  - `liquidations_paused` spans → "Liq paused", tone `halt`.
  - `reduce_only` spans → "Reduce-only", tone `warn`.
- **Auctions.** Ticks where `tick.auction !== null`. Each has
  `clearing_price`, `collar_lo`, `collar_hi`, `liquidations_absorbed` /
  `liquidations_queued`, `liquidation_qty_carried`, and `reason`.
- **Unnecessary liquidations at the cursor** = the prefix sum of
  `unnecessary_liquidations`.
- **NRR for the DeviationChart.** Use the policy's `instrument_tiers` entry for
  `instrument.tier`. Use `nrr_offhours_pct` **only if** `instrument.has_rth &&
  is_offhours`; otherwise use `nrr_pct`. Convert with bps = pct × 100. Label it,
  e.g. "Tier 2 NRR ±8.0% (off-hours)".

### 6.2 Put the derivations in one pure module, with tests

Create `web/src/lib/sim.ts` containing **only pure functions and only
`import type` imports**. Suggested exports:

- `spans(ticks, key)`, `controlRegions(ticks)`
- `ladderAt(tick)`, `cascadeSeries(ticks)`
- `prefixSum(ticks, key)`, `stateAt(tick)`, `eventsUpTo(ticks, i)`
- `sharedPriceDomain(offTicks, onTicks)`, `nrrFor(policy, scenarioDetail)`

Test it with Node's built-in runner (**no new dependency**, verified working on
this machine's Node 26):

- File: `web/src/lib/sim.test.ts`, using `import { test } from "node:test"` and
  `import assert from "node:assert/strict"`.
- **It must import `./sim.ts` WITH the `.ts` extension.** Extension-less
  runtime imports fail under Node. `tsconfig` already sets
  `allowImportingTsExtensions`.
- `sim.ts` must use erasable TypeScript only: no `enum`, no `namespace`, no
  constructor parameter properties.
- Build minimal hand-made `Tick` fixtures through a `makeTick(overrides)` helper.
- Add `"test": "node --test src/lib/*.test.ts"` to `web/package.json` and a
  `test-web` Makefile target.
- Cover at least:
  - the ladder price formula
  - spans not merging across a gap
  - the cascade grouping, including `partial`
  - the prefix sum
  - the NRR choice (on- and off-hours, with and without an RTH)

### 6.3 Route wiring

- In `app/nav.ts`, remove `pending` from the `/simulator` entry.
- In `App.tsx`, add an explicit branch **before** the generic `if (section)`
  branch: `/simulator` → `<Shell current={section} title="Simulator"
  isDocument={false}><Simulator /></Shell>`.
- Create `web/src/pages/Simulator.tsx`.
- On load, call `useApp().setInstrument(scenario.instrument_symbol)`.
- **Do not call `setSystemState`** (§5.3).

### 6.4 Layout (top to bottom)

1. **Header.**
   - A scenario `Select` (all 6, default `oracle_defect_hip3`).
   - Chips: instrument, IST label, session (RTH / off-hours / weekend), layer,
     seed, policy version.
   - The scenario summary, and `assumed_scale_note` in small secondary text.
2. **Playback bar** (sticky under the top bar):
   - Play/Pause (primary button, the only primary on the page), step −1/+1 and
     −10/+10.
   - A scrubber using the existing `Slider` (0…n−1, readout `T+{t}s`).
   - Speed `Select`: 1×, 5×, 10×, 30× ticks per second.
   - Keyboard: Space (play/pause), ←/→ (±1), Shift+←/→ (±10), Home/End.
   - Drive playback with a `requestAnimationFrame` time accumulator, not
     `setInterval`, so it doesn't drift. Stop at the end.
3. **Two columns, "Unprotected" and "Protected"**. Side by side at `xl`,
   stacked below. Each column holds:
   - **A state Badge at the cursor, always with text:**
     - Halted → halt tone.
     - Velocity pause → halt tone, with "L{velocity_level}" when > 0.
     - Circuit breaker → halt tone.
     - Liq paused → halt tone.
     - Reduce-only → warn tone.
     - Degraded oracle (`composite_rung === 4`) → neg tone.
     - Otherwise "Continuous" → neutral.
   - **Four `Stat`s at the cursor:**
     - Accounts liquidated (`cum_liquidated_accounts`).
     - Unnecessary liquidations (prefix sum).
     - ADL events (`adl_accounts`).
     - Depth of baseline (%).

     Each has a `baseline` showing the other column's value at the same tick.
     Deltas use `goodWhen: "down"`, except depth, which uses `"up"`.
   - **`PriceChart`:**
     - Oracle, mark and LTP lines.
     - The control lane from §6.1.
     - Liquidation bursts: the top 8 ticks by `liquidated_this_tick`.
     - Auction markers.
     - A vertical cursor at the current tick.
     - **Both columns use one shared y-domain.**
   - **`CascadeChart`** (4 stages) with the cursor.
   - **`DepthLadder`** at the cursor, built from real `depth`.
   - **`DeviationChart`** with NRR from §6.1 and the cursor.
4. **Full width below the columns:**
   - **"At the close"**: the legacy verdict sentence, generated from the
     summaries. For example: "Same shock, same seed: 680 accounts liquidated
     and ₹1.21 Cr lost without controls, versus 0 and ₹5.9 L with them." Use
     `parseMoney(summary.user_loss_inr)` and `rupees()`. **User loss exists only
     in the summary; do not fake a per-tick value.**
   - **Oracle at T+{t}s**: a table from the Protected tick's `sources` with
     columns source, rung, used / clamped / stale Badges (with text), raw price,
     used price, and `excluded_reason`. Show `—` for a null price; a closed
     market printed nothing. The oracle feed is the same in both runs.
   - **Event feed** (`Timeline` primitive) up to the cursor, derived client-side.
     There is no `log` on the wire, and that is fine. Show:
     - pause starts, with reason, level and span length
     - each auction: "cleared at X, absorbed a/q, carried y"
     - oracle health changes
     - the first liquidation and the first ADL

     Add a Protected / Unprotected toggle.
   - Loading: `Skeleton`s. Error: an `EmptyState` saying "Start Django and run
     `make seed`".

### 6.5 Chart component changes (keep them backwards-compatible)

- **`PriceChart`:**
  - Add an optional `cursor?: number | undefined` (a dashed `ReferenceLine`).
  - Add optional `auctions?: {t: number; price: number}[] | undefined`, drawn
    as a diamond in accent with the legend entry "Reopening auction".
- **`DeviationChart` and `CascadeChart`:** add the optional `cursor`.
- **`CascadeChart`:**
  - Add a `partial` series: tone `pos`, legend "Partial — stage one,
    fee-free", with a distinct legend sample.
  - Y values become INR notional, with the axis and tooltip formatted in lakh.
  - Update the kitchen-sink call site accordingly.
- **`Stat`:** add an optional `duration?: number | undefined`, passed to
  `useCountUp`. During playback use `min(COUNT_MS, 0.8 × tickIntervalMs)` so
  counts settle between ticks. Paused or finished uses the default. Never
  exceed 400ms.
- Keep `isAnimationActive={false}` on every Recharts series.

### 6.6 Performance (measure it, don't assume)

- Derive every per-side series **once** per dataset (`useMemo` keyed on the
  data).
- During playback, reveal charts progressively by slicing the memoised series
  to `[0, cursor]`. Throttle chart re-renders to at most ~10 Hz at high speeds.
  Stats, badges and the ladder update every tick.
- Measure frame rate at 10× and 30× in the browser (a `requestAnimationFrame`
  sampler is enough) and report it.

### 6.7 Kitchen-sink update

The `CascadeChart` and `DepthLadder` cards currently use fixtures and say
"Phase 6 adds the split / levels".

- Switch both to live data from the macro-cascade comparison the page already
  fetches.
- Replace their "fixture" badges with "live".
- Update the card descriptions.
- Delete the `CASCADE`, `LIQUIDITY` and `ladder()` fixtures.
- The ladder demo may step through real ticks on its interval.

---

## 7. Verification (all of it, and report the results)

1. `make test` → still **313 passed, 2 skipped** (backend untouched).
2. `cd web && npm_config_cache=../.cache/npm npm test` → all `sim.test.ts` tests
   pass.
3. `make typecheck` and `make build` are clean.
4. **In a real browser** at 1440×900:
   - `/simulator` loads for **all 6 scenarios**.
   - Play, pause, scrub and all four speeds work, and so does every keyboard
     shortcut.
   - Tab through the page: every interactive element shows the visible 2px
     focus ring.
   - No layout shift while stats update during playback.
   - `/demo`, `/`, `/kitchen-sink` and `/report` still render.
   - `GET /api/compare/oracle_defect_hip3/` still returns its old shape.
5. Screenshots go to `docs/screenshots/phase6/` (gitignored). For
   `oracle_defect_hip3` and `macro_cascade`, capture mid-crash (cursor ≈ T+160s)
   and at the close. Also capture one of the Oracle table showing the clamped
   ADR source in `oracle_defect_hip3` at T+160s.
6. Look at your own screenshots and say plainly what still looks unfinished.

## 8. Commit, update, report, stop

- Update the ARCHITECTURE.md phase marker to "PHASE 6 — SIMULATOR SURFACE
  (complete)" and "NEXT: PHASE 7 — War room. Await instructions." Mark row 6
  Done in the status table, and add a short "Simulator" note describing the
  derivations in §6.1.
- Commit, e.g. `Phase 6: simulator surface`, with a plain-language body: what
  was built, what was measured, and any deviation. No AI attribution. Do not
  push.
- **Report:**
  - commit hash(es)
  - backend and web test counts
  - fps at 10× and 30×
  - the screenshot list
  - every deviation from this brief, with the reason
  - any questions triggered by the stop-and-ask list in §0
- Then **stop**. Do not begin Phase 7.
