"""Three-layer triage, computed from the live engine.

Minute one of an incident is not "what did the market do" but "which of our
three layers broke" (research brief section 0). Each layer gets a status and the
signals that produced it, so the war room shows its working:

    L3 VENUE   Hyperliquid: the shared book, HLP, ADL. No control -- observe
               and document.
    L2 MARKET  The HIP-3 dex MochaTrade deploys: oracle, margin tiers, bands.
               Full control, full liability: 500k HYPE slashable.
    L1 BROKER  MochaTrade's app, API, order router, UPI rails. Full control.

Reads engine objects only; no Django, no database. Thresholds come from the
active policy via the engine's params or from the scenario, never typed here.
"""
from __future__ import annotations

from typing import Any

from riskengine.engine import Engine

OK, WARN, FAIL = "ok", "warn", "fail"
_RANK = {OK: 0, WARN: 1, FAIL: 2}


def _worst(statuses: list[str]) -> str:
    return max(statuses, key=lambda s: _RANK[s]) if statuses else OK


def _signal(label: str, value: str, status: str) -> dict[str, str]:
    return {"label": label, "value": value, "status": status}


def triage(engine: Engine) -> list[dict[str, Any]]:
    """Status and signals for each layer at the engine's current tick."""
    if not engine.frames:
        return [
            {"layer": "venue", "tier": "L3", "name": "Venue — Hyperliquid", "control": "No control",
             "status": OK, "headline": "Waiting for the first tick.", "signals": []},
            {"layer": "market", "tier": "L2", "name": "Market — our HIP-3 dex", "control": "Full control, full liability",
             "status": OK, "headline": "Waiting for the first tick.", "signals": []},
            {"layer": "broker", "tier": "L1", "name": "Broker — MochaTrade stack", "control": "Full control",
             "status": OK, "headline": "Waiting for the first tick.", "signals": []},
        ]

    f = engine.frames[-1]
    scenario = engine.scenario
    params = engine.params
    tick = f.tick

    # --- L3 venue ----------------------------------------------------------
    depth = f.depth_pct_of_baseline
    venue = [
        _signal("Resting depth vs calm baseline", f"{depth * 100:.0f}%",
                FAIL if depth < 0.2 else WARN if depth < 0.5 else OK),
        _signal("Spread", f"{f.spread_bps:.1f} bps",
                FAIL if f.spread_bps > 60 else WARN if f.spread_bps > 20 else OK),
        _signal("ADL: winners force-closed", f"{f.adl_accounts}",
                FAIL if f.adl_accounts > 0 else OK),
        _signal("Accounts liquidated so far", f"{f.cum_liquidated_accounts}",
                WARN if f.cum_liquidated_accounts > 0 else OK),
    ]
    venue_status = _worst([s["status"] for s in venue])

    # --- L2 market ---------------------------------------------------------
    offhours_nrr = scenario.has_cash_session and scenario.offhours
    nrr_bps = params.nrr_pct(scenario.instrument_tier, offhours=offhours_nrr) * 100.0
    clamped = sum(1 for o in f.sources if o.clamped)
    stale = sum(1 for o in f.sources if o.is_stale)
    health_status = {"healthy": OK, "sources_degraded": WARN}.get(f.oracle_health, FAIL)
    market = [
        _signal("Oracle health", f"{f.oracle_health.replace('_', ' ')} · ladder L{f.composite_rung}", health_status),
        _signal("Mark vs clean reference", f"{f.divergence_bps:+.0f} bps (NRR ±{nrr_bps:.0f})",
                FAIL if abs(f.divergence_bps) > nrr_bps else WARN if abs(f.divergence_bps) > params.mark_max_deviation_bps else OK),
        _signal("Sources clamped / stale", f"{clamped} / {stale}", FAIL if clamped else WARN if stale else OK),
        _signal("Trading", "paused" if f.trading_paused else "continuous",
                WARN if f.trading_paused else OK),
    ]
    market_status = _worst([s["status"] for s in market])

    # --- L1 broker ---------------------------------------------------------
    broker: list[dict[str, str]] = []
    if scenario.outage is not None:
        active = scenario.outage.active(tick)
        broker.append(_signal(
            "App and order API",
            f"{scenario.outage.label}: {scenario.outage.affected_frac:.0%} of users" if active else "reachable",
            FAIL if active else (WARN if tick >= scenario.outage.end_tick else OK),
        ))
    else:
        broker.append(_signal("App and order API", "reachable", OK))
    in_flight = sum(
        1 for a in engine.accounts
        if a.upi_deposit_inr > 0
        and a.upi_initiated_tick is not None and a.upi_initiated_tick <= tick
        and not a.upi_settled
    )
    broker.append(_signal("UPI deposits initiated, not settled", f"{in_flight}",
                          FAIL if in_flight > 50 else WARN if in_flight else OK))
    margin_calls = sum(1 for a in engine.accounts if a.open and a.state.value == "margin_call")
    broker.append(_signal("Margin calls in grace window", f"{margin_calls}", WARN if margin_calls else OK))
    broker_status = _worst([s["status"] for s in broker])

    def headline(status: str, layer: str) -> str:
        if status == OK:
            return "No fault on this layer."
        return {
            "venue": "Venue stress. We cannot act here; document it for the evidence pack.",
            "market": "Our market is showing a fault. This layer is ours and carries the liability.",
            "broker": "Our own stack is failing users. This is the most likely 'we caused this'.",
        }[layer]

    return [
        {"layer": "venue", "tier": "L3", "name": "Venue — Hyperliquid", "control": "No control",
         "status": venue_status, "headline": headline(venue_status, "venue"), "signals": venue},
        {"layer": "market", "tier": "L2", "name": "Market — our HIP-3 dex", "control": "Full control, full liability",
         "status": market_status, "headline": headline(market_status, "market"), "signals": market},
        {"layer": "broker", "tier": "L1", "name": "Broker — MochaTrade stack", "control": "Full control",
         "status": broker_status, "headline": headline(broker_status, "broker"), "signals": broker},
    ]
