"""The public status page: what a user sees, in words a user reads.

Component states come from the live system, not from a person remembering to
flip a switch: the latest open incident's engine state and our own telemetry.
Nothing internal crosses this boundary -- no classification, no exposure, no
root-cause layer, no drafts, no names of internal controls a user cannot act
on. The words say what a user can and cannot do right now.
"""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from riskengine.classifier import inr_text

OPERATIONAL = "operational"
DEGRADED = "degraded"
PARTIAL = "partial_outage"
MAJOR = "major_outage"

ORDER = [OPERATIONAL, DEGRADED, PARTIAL, MAJOR]

LABEL = {
    OPERATIONAL: "Operational",
    DEGRADED: "Degraded",
    PARTIAL: "Partial outage",
    MAJOR: "Major outage",
}

PUBLIC_PHASE = {
    "DECLARED": "investigating",
    "CONTAINED": "investigating",
    "DIAGNOSED": "identified",
    "REMEDIATING": "monitoring",
    "RESOLVED": "resolved",
}


def _component(name: str, state: str, note: str) -> dict[str, Any]:
    return {"name": name, "state": state, "state_label": LABEL[state], "note": note}


def all_clear(instrument: str | None = None) -> list[dict[str, Any]]:
    market = f"Trading on {instrument}" if instrument else "Trading"
    return [
        _component(market, OPERATIONAL, "Open for trading."),
        _component("Liquidations", OPERATIONAL, "Running normally, priced off our published reference."),
        _component("Prices", OPERATIONAL, "Our price feed is healthy."),
        _component("App and order API", OPERATIONAL, "Up."),
        _component("UPI deposits", OPERATIONAL, "Credited on arrival."),
        _component("Hyperliquid (the venue)", OPERATIONAL, "Normal liquidity."),
    ]


def components(engine, *, resolved: bool) -> list[dict[str, Any]]:
    """Six components, from the engine's latest second."""
    scenario = engine.scenario
    if resolved or not engine.frames:
        return all_clear(scenario.instrument)
    f = engine.frames[-1]
    tick = f.tick
    out: list[dict[str, Any]] = []

    if f.halted:
        out.append(_component(f"Trading on {scenario.instrument}", MAJOR, "Halted. Open positions are settled at the mark."))
    elif f.trading_paused:
        out.append(_component(f"Trading on {scenario.instrument}", PARTIAL,
                              "Paused for a moment. It reopens through a short auction, never straight into a moving book."))
    elif f.reduce_only:
        out.append(_component(f"Trading on {scenario.instrument}", DEGRADED,
                              "Reduce-only: you can close or reduce positions and add margin. New risk is paused."))
    else:
        out.append(_component(f"Trading on {scenario.instrument}", OPERATIONAL, "Open for trading."))

    if f.liquidations_paused:
        out.append(_component("Liquidations", DEGRADED, "Paused on this market while we verify prices. Nobody is closed on a price we doubt."))
    elif engine.controls.oracle_anchored_mark:
        out.append(_component("Liquidations", OPERATIONAL, "Running, priced off our published reference, never the last trade."))
    else:
        out.append(_component("Liquidations", OPERATIONAL, "Running."))

    if f.oracle_health in ("suspect", "no_composite"):
        out.append(_component("Prices", MAJOR, "Our price feed is suspect. Liquidations on this market are paused until it is healthy."))
    elif f.composite_rung > scenario.expected_rung:
        out.append(_component("Prices", DEGRADED, "Running on backup price sources. Published and checkable."))
    elif scenario.expected_rung > 1:
        out.append(_component("Prices", OPERATIONAL, "US cash market closed: prices come from the published off-hours sources."))
    else:
        out.append(_component("Prices", OPERATIONAL, "Our price feed is healthy."))

    outage = scenario.outage
    if outage and outage.active(tick):
        out.append(_component("App and order API", MAJOR, "Down for some users. We are restoring it; you will not be charged for our outage."))
    elif outage and tick >= outage.end_tick:
        out.append(_component("App and order API", OPERATIONAL, "Restored."))
    else:
        out.append(_component("App and order API", OPERATIONAL, "Up."))

    in_flight = sum(
        1 for a in engine.accounts
        if a.upi_initiated_tick is not None and a.upi_initiated_tick <= tick
        and (a.upi_settles_tick is None or tick < a.upi_settles_tick)
    )
    if in_flight:
        cap = engine.params.upi_prefunded_credit_cap_inr
        front = (f" We front up to {inr_text(cap)} of a deposit you have already sent."
                 if engine.controls.upi_prefunded_credit else "")
        out.append(_component("UPI deposits", DEGRADED, f"Deposits are reaching us late.{front}"))
    else:
        out.append(_component("UPI deposits", OPERATIONAL, "Credited on arrival."))

    if f.depth_pct_of_baseline < 0.2:
        out.append(_component("Hyperliquid (the venue)", DEGRADED, "Thin liquidity on the venue. Orders may fill further from the price."))
    else:
        out.append(_component("Hyperliquid (the venue)", OPERATIONAL, "Normal liquidity."))
    return out


def overall(items: list[dict[str, Any]]) -> dict[str, str]:
    worst = max((c["state"] for c in items), key=ORDER.index, default=OPERATIONAL)
    words = {
        OPERATIONAL: "All systems operational",
        DEGRADED: "Some systems degraded",
        PARTIAL: "Partial outage",
        MAJOR: "Major outage",
    }
    return {"state": worst, "headline": words[worst]}


def as_of() -> str:
    return timezone.localtime().isoformat()
