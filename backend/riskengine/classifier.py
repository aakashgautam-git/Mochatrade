"""Abnormal Price Event test and root-cause classification.

The APE test (publish this in the T&Cs, before the event, not after). A fill or
liquidation is an Abnormal Price Event only if all three hold:

 1. Deviation  - the execution price differs from the Reference Composite Price
                 in the same 1-second window by more than the Non-Reviewable
                 Range for that tier
 2. Reversion  - the deviation retraces >=50% within 60 seconds, i.e. it was a
                 wick and not a repricing
 3. Counterfactual survival - the account held sufficient margin to survive at
                 the Reference Composite Price

Non-Reviewable Ranges, per tier (proposed parameters, seeded into RiskPolicy):
    Tier 1  BTC, ETH, SPY, mega-cap US equities        3%   off-hours 5%
    Tier 2  SOL, gold, large-cap equities, indices     5%   off-hours 8%
    Tier 3  long-tail crypto, pre-IPO perps           10%   off-hours 15%

Root-cause classes, which decide who pays (research brief 5.2):
    A  genuine move, healthy oracle, adequate depth   -> no remedy, publish tape
    B  thin book / venue-local wick, mark tracked      -> fee rebate + dated fix
    C  oracle or index defect on our HIP-3 market      -> FULL make-whole
    D  our app/API outage blocked top-up or close      -> make-whole in window
    E  UPI/PSP delay on a funded deposit               -> make-whole
    F  venue defect or ADL                             -> no cash liability;
                                                          file evidence pack,
                                                          publish the response,
                                                          goodwill at a cap
    G  identifiable manipulation                       -> freeze, report to
                                                          FIU-IND and the venue,
                                                          Incident Reserve

The classifier must return the evidence that produced the verdict, not just the
letter, because the report has to show its working and the whole policy stands
on being replicable by the user.

How the tape is read
--------------------
"Reference Composite" here is the frame's `reference`: the published ladder
rebuilt from the per-source tape with our own defects taken out, which is what
a post-incident reviewer (or a user with the tape) can recompute. `composite` is
what our oracle actually published at the time. The gap between the two is the
oracle-defect signature.

Per account, the first matching rule wins, in this order:

    F  any fill was an ADL close                      (venue mechanism)
    D  cut off by our outage, first forced close inside the outage window
    E  UPI deposit initiated before the first forced close, settled after it
    G  force-closed on the side a coordinated cross-venue push hurt, inside it
    -  otherwise the APE test on the account's decisive fill:
         pass, and the mark was the last traded price   -> C (mark methodology)
         pass, and our published composite was off      -> C (oracle defect)
         pass, the mark tracked the composite           -> B (the book wicked)
         fail                                           -> A, with the failed
                                                           criterion as reason

The decisive fill is the account's fill furthest from the Reference Composite,
measured on the fill price or on the mark that triggered it, whichever is
further. It is the reading most favourable to the user; a user holding the
tape would pick the same one.

Per incident, the most liable signature on the tape wins, in this order:

    G  two or more trading venues deviate beyond the NRR in the same direction
       at the same time, and our book moves with them
    C  the composite we published deviated from the Reference Composite beyond
       the NRR -- or accounts were liquidated on a last-traded-price mark
    D  our own outage overlapped the event
    E  UPI deposits were in flight during the event
    B  accounts passed the APE test on a book wick, or the book dislocated
       beyond the mark band while the underlying's primary market was closed
       (our users were the only flow: the thin book the class describes)
    A  none of the above

No thresholds are invented here. Every number comes from RiskParams: the NRR
per tier, the reversion fraction and window, and the mark's maximum deviation
band.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Iterable, Mapping, Sequence

from .engine import Frame
from .liquidation import Account, LiquidationEvent, LiquidationStage, Side
from .params import TICK_SECONDS, RiskParams
from .scenario import Layer, Scenario

CATEGORIES = ("A", "B", "C", "D", "E", "F", "G")

LABELS = {
    "A": "Genuine market move",
    "B": "Thin book, venue-local wick",
    "C": "Oracle or index defect on our market",
    "D": "Our outage blocked top-up or close",
    "E": "UPI delayed a funded deposit",
    "F": "Venue defect or ADL",
    "G": "Identifiable manipulation",
}

REMEDY = {
    "A": "No remedy. Publish the evidence tape.",
    "B": "No cash remedy. Fee rebate, and the fix ships with a date.",
    "C": "Full make-whole to counterfactual equity at the Reference Composite. No rollback.",
    "D": "Make-whole for the loss attributable to the outage window.",
    "E": "Make-whole: the deposit was initiated before the liquidation and settled after it.",
    "F": "No MochaTrade cash liability. File the evidence pack, publish the venue's response, goodwill at a published cap.",
    "G": "Freeze what we can, report to FIU-IND and the venue, fund from the Incident Reserve, pursue recovery.",
}

FAULT = {
    "A": "Nobody",
    "B": "Market structure",
    "C": "MochaTrade",
    "D": "MochaTrade",
    "E": "Shared, but we chose the rail",
    "F": "Venue",
    "G": "Attacker",
}

LAYER_OF = {
    "A": Layer.VENUE, "B": Layer.VENUE, "F": Layer.VENUE, "G": Layer.VENUE,
    "C": Layer.MARKET, "D": Layer.BROKER, "E": Layer.BROKER,
}

VENUE_KINDS = frozenset({"spot_venue", "perp_venue"})
"""Sources that are markets someone can trade on, and so can be pushed. An
index future feed or an ETF NAV proxy printing wrong is a data defect; two
venues printing the same wrong price at once is somebody trading them there."""


def clock(tick: int) -> str:
    seconds = int(round(tick * TICK_SECONDS))
    return f"T+{seconds // 60:02d}:{seconds % 60:02d}"


def _bps(price: float | None, reference: float | None) -> float:
    if not price or not reference:
        return 0.0
    return (price / reference - 1.0) * 1e4


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Criterion:
    passed: bool | None
    """None when it cannot be decided yet: the 60-second reversion window runs
    past the end of the tape recorded so far."""
    value: float | None
    threshold: float
    detail: str


@dataclass(frozen=True, slots=True)
class AccountVerdict:
    account_id: str
    category: str
    reason: str
    side: str
    leverage: float
    entry_price: float
    collateral: float
    entry_notional: float

    first_tick: int
    tick: int
    """The decisive fill's tick: the one furthest from the Reference Composite."""
    stage: str
    executed_price: float
    reference_price: float
    mark: float
    mark_source: str
    composite: float | None
    book_mid: float
    deviation_bps: float
    """Signed, on whichever of fill price or mark was further from the reference."""
    deviation_basis: str
    nrr_bps: float
    fills: int
    liquidated_notional: float
    fees: float
    closed: bool
    ape: bool
    pending: bool
    criteria: dict[str, dict[str, object]]
    outage: dict[str, object] | None = None
    upi: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class Classification:
    category: str
    label: str
    layer: str
    fault: str
    remedy: str
    headline: str
    evidence: list[str]
    signals: dict[str, object]
    provisional: bool
    at_tick: int
    nrr_bps: float
    counts: dict[str, int]
    accounts: list[AccountVerdict] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        out = asdict(self)
        out["accounts"] = [a.as_dict() for a in self.accounts]
        return out


# --------------------------------------------------------------------------
# Tape signatures
# --------------------------------------------------------------------------

@dataclass(slots=True)
class _Episode:
    """A run of ticks where a signature held, plus what it looked like."""

    start: int
    end: int
    peak_bps: float
    peak_tick: int
    sources: tuple[str, ...] = ()
    direction: int = 0
    fp_start: int | None = None
    fp_end: int | None = None
    """For a push: where the cross-venue fingerprint itself shows, inside the
    wider episode that starts when the price first left its opening level."""


def _composite_defect(frames: Sequence[Frame], nrr_bps: float) -> _Episode | None:
    """Our published composite against the Reference Composite, beyond the NRR."""
    hits = [
        (f.tick, _bps(f.composite, f.reference))
        for f in frames
        if f.composite is not None and f.reference
        and abs(_bps(f.composite, f.reference)) > nrr_bps
    ]
    if not hits:
        return None
    peak_tick, peak = max(hits, key=lambda h: abs(h[1]))
    bad: Counter[str] = Counter()
    for f in frames:
        if not (hits[0][0] <= f.tick <= hits[-1][0]) or not f.reference:
            continue
        for o in f.sources:
            if o.raw_price is not None and abs(_bps(o.raw_price, f.reference)) > nrr_bps:
                bad[o.source] += 1
    return _Episode(
        start=hits[0][0], end=hits[-1][0], peak_bps=peak, peak_tick=peak_tick,
        sources=tuple(s for s, _ in bad.most_common()),
        direction=1 if peak > 0 else -1,
    )


def _push(frames: Sequence[Frame], nrr_bps: float, band_bps: float) -> _Episode | None:
    """Two or more tradeable venues printing beyond the NRR on the same side at
    the same moment, with our own book moving the same way. One venue printing
    wrong is a glitch; several agreeing on a price the majors do not have is
    somebody trading them there."""
    ticks: list[tuple[int, int, float, tuple[str, ...]]] = []
    for f in frames:
        if not f.reference:
            continue
        for direction in (1, -1):
            names = tuple(
                o.source for o in f.sources
                if o.kind in VENUE_KINDS and o.raw_price is not None and not o.is_stale
                and direction * _bps(o.raw_price, f.reference) > nrr_bps
            )
            book = direction * _bps(f.book_mid, f.reference)
            if len(names) >= 2 and book > band_bps:
                ticks.append((f.tick, direction, book * direction, names))
    if not ticks:
        return None
    direction = Counter(t[1] for t in ticks).most_common(1)[0][0]
    ticks = [t for t in ticks if t[1] == direction]
    peak = max(ticks, key=lambda t: abs(t[2]))
    fp_start, fp_end = ticks[0][0], ticks[-1][0]
    names = tuple(sorted({n for t in ticks for n in t[3]}))

    # The push starts where the price first left its opening level in the
    # push's direction, not where the fingerprint first shows: in JELLY the
    # spot pump came first and the perp venues followed.
    ref0 = next((f.reference for f in frames if f.reference), None) or frames[0].mark
    by_tick = {f.tick: f for f in frames}
    start = fp_start
    while start - 1 in by_tick:
        prev = by_tick[start - 1]
        level = prev.reference or prev.mark
        if direction * _bps(level, ref0) <= band_bps:
            break
        start -= 1
    end = fp_end
    last = frames[-1].tick
    while end + 1 <= last:
        nxt = by_tick[end + 1]
        level = nxt.reference or nxt.mark
        if direction * _bps(level, ref0) <= band_bps and direction * _bps(nxt.book_mid, ref0) <= band_bps:
            break
        end += 1
    return _Episode(
        start=start, end=end, peak_bps=peak[2], peak_tick=peak[0],
        sources=names, direction=direction, fp_start=fp_start, fp_end=fp_end,
    )


def _closed_primary(frames: Sequence[Frame]) -> tuple[str, ...]:
    names: set[str] = set()
    for f in frames:
        for o in f.sources:
            if o.price is None and o.excluded_reason.startswith("market closed"):
                names.add(o.source)
    return tuple(sorted(names))


def _thin_book_wick(frames: Sequence[Frame], band_bps: float) -> _Episode | None:
    """The book away from the Reference Composite by more than the mark band,
    at moments the mark itself stayed inside it: the mark refused to follow."""
    hits = [
        (f.tick, _bps(f.book_mid, f.reference))
        for f in frames
        if f.reference and abs(_bps(f.book_mid, f.reference)) > band_bps
        and abs(_bps(f.mark, f.reference)) <= band_bps
    ]
    if not hits:
        return None
    peak_tick, peak = max(hits, key=lambda h: abs(h[1]))
    return _Episode(start=hits[0][0], end=hits[-1][0], peak_bps=peak, peak_tick=peak_tick,
                    direction=1 if peak > 0 else -1)


# --------------------------------------------------------------------------
# The APE test on one fill
# --------------------------------------------------------------------------

def _decisive(events: Sequence[LiquidationEvent], frames: Sequence[Frame]) -> tuple[LiquidationEvent, float, str]:
    best: tuple[LiquidationEvent, float, str] | None = None
    for e in events:
        f = frames[e.tick]
        ref = f.reference or e.reference_price
        fill = _bps(e.fill_price, ref)
        mark = _bps(f.mark, ref)
        dev, basis = (fill, "fill") if abs(fill) >= abs(mark) else (mark, "mark")
        if best is None or abs(dev) > abs(best[1]):
            best = (e, dev, basis)
    assert best is not None
    return best


def _reversion(
    e: LiquidationEvent, basis: str, frames: Sequence[Frame], params: RiskParams, finished: bool
) -> tuple[float | None, bool | None, int | None]:
    """How far the deviating price came back toward the Reference Composite
    within the window. Measured on the price that deviated, against where the
    reference stood at execution: if the reference instead moves to meet the
    price, that is a repricing, and the retrace stays near zero -- as it should."""
    f0 = frames[e.tick]
    ref = f0.reference or e.reference_price
    executed = e.fill_price if basis == "fill" else f0.mark
    if not ref:
        return None, None, None
    gap = ref - executed
    if abs(gap) < 1e-12:
        return 0.0, False, None
    window = params.ape_reversion_ticks
    best, best_tick = 0.0, None
    last = min(len(frames) - 1, e.tick + window)
    for u in range(e.tick + 1, last + 1):
        price = frames[u].book_mid if basis == "fill" else frames[u].mark
        retrace = (price - executed) / gap
        if retrace > best:
            best, best_tick = retrace, u
            if best >= params.ape_reversion_frac:
                return best, True, best_tick
    if not finished and e.tick + window > len(frames) - 1:
        return best, None, None
    return best, False, None


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def classify(
    scenario: Scenario,
    params: RiskParams,
    frames: Sequence[Frame],
    events: Sequence[LiquidationEvent],
    accounts: Iterable[Account],
    *,
    finished: bool = True,
) -> Classification:
    offhours = scenario.has_cash_session and scenario.offhours
    nrr_pct = params.nrr_pct(scenario.instrument_tier, offhours=offhours)
    nrr_bps = nrr_pct * 100.0
    band_bps = params.mark_max_deviation_bps
    at_tick = frames[-1].tick if frames else 0

    defect = _composite_defect(frames, nrr_bps)
    push = _push(frames, nrr_bps, band_bps)
    closed = _closed_primary(frames)
    wick = _thin_book_wick(frames, band_bps) if closed else None
    outage = scenario.outage if scenario.outage and scenario.outage.start_tick <= at_tick else None

    by_account: dict[str, list[LiquidationEvent]] = {}
    for e in events:
        by_account.setdefault(e.account_id, []).append(e)
    account_map = {a.id: a for a in accounts}

    verdicts: list[AccountVerdict] = []
    upi_in_flight = 0
    for a in account_map.values():
        if a.upi_initiated_tick is not None and a.upi_initiated_tick <= at_tick:
            upi_in_flight += 1

    for account_id in sorted(by_account, key=lambda k: (by_account[k][0].tick, k)):
        es = sorted(by_account[account_id], key=lambda e: e.tick)
        a = account_map.get(account_id)
        if a is None:
            continue
        verdicts.append(_classify_account(
            a, es, frames, params, nrr_bps, finished,
            defect=defect, push=push, outage=outage,
        ))

    counts = {c: 0 for c in CATEGORIES}
    for v in verdicts:
        counts[v.category] += 1

    ltp_c = sum(1 for v in verdicts if v.category == "C" and v.mark_source == "ltp")
    signals: dict[str, object] = {
        "nrr_bps": nrr_bps,
        "mark_band_bps": band_bps,
        "reversion_frac": params.ape_reversion_frac,
        "reversion_seconds": params.ape_reversion_seconds,
        "composite_defect": _episode(defect),
        "push": _episode(push),
        "closed_primary": list(closed),
        "thin_book_wick": _episode(wick),
        "outage": (
            {"start_tick": outage.start_tick, "end_tick": outage.end_tick,
             "affected_frac": outage.affected_frac, "label": outage.label}
            if outage else None
        ),
        "upi_in_flight": upi_in_flight,
        "ltp_marked_liquidations": ltp_c,
        "accounts_force_closed": len(verdicts),
        "ape_accounts": sum(1 for v in verdicts if v.ape),
    }

    category, headline, evidence = _incident_verdict(
        frames, verdicts, counts, nrr_bps, band_bps,
        defect=defect, push=push, outage=outage, upi_in_flight=upi_in_flight,
        wick=wick, closed=closed, ltp_c=ltp_c,
    )
    return Classification(
        category=category,
        label=LABELS[category],
        layer=LAYER_OF[category].value,
        fault=FAULT[category],
        remedy=REMEDY[category],
        headline=headline,
        evidence=evidence,
        signals=signals,
        provisional=not finished,
        at_tick=at_tick,
        nrr_bps=nrr_bps,
        counts=counts,
        accounts=verdicts,
    )


def _episode(e: _Episode | None) -> dict[str, object] | None:
    if e is None:
        return None
    return {
        "start_tick": e.start, "end_tick": e.end, "peak_bps": round(e.peak_bps, 1),
        "peak_tick": e.peak_tick, "sources": list(e.sources), "direction": e.direction,
        "fingerprint_start_tick": e.fp_start, "fingerprint_end_tick": e.fp_end,
    }


def _classify_account(
    a: Account,
    es: list[LiquidationEvent],
    frames: Sequence[Frame],
    params: RiskParams,
    nrr_bps: float,
    finished: bool,
    *,
    defect: _Episode | None,
    push: _Episode | None,
    outage,
) -> AccountVerdict:
    first = es[0].tick
    decisive, dev, basis = _decisive([e for e in es if e.stage is not LiquidationStage.ADL] or es, frames)
    f = frames[decisive.tick]
    ref = f.reference or decisive.reference_price or f.mark
    retrace, reverted, reverted_at = _reversion(decisive, basis, frames, params, finished)

    c1 = Criterion(
        passed=abs(dev) > nrr_bps, value=round(dev, 1), threshold=nrr_bps,
        detail=(
            f"{'Fill' if basis == 'fill' else 'Mark'} {abs(dev):,.0f} bps "
            f"{'below' if dev < 0 else 'above'} the Reference Composite at {clock(decisive.tick)}; "
            f"the Non-Reviewable Range is {nrr_bps:,.0f} bps"
        ),
    )
    if reverted is None:
        c2_detail = (
            f"Window still open: {retrace or 0:.0%} back so far, needs "
            f"{params.ape_reversion_frac:.0%} by {clock(decisive.tick + params.ape_reversion_ticks)}"
        )
    elif reverted:
        c2_detail = (
            f"Came back {retrace:.0%} of the way by {clock(reverted_at or decisive.tick)}: "
            f"a wick, not a repricing"
        )
    else:
        c2_detail = (
            f"Only {max(0.0, retrace or 0.0):.0%} back within {params.ape_reversion_seconds}s "
            f"(needs {params.ape_reversion_frac:.0%}): the price repriced"
        )
    c2 = Criterion(passed=reverted, value=None if retrace is None else round(retrace, 3),
                   threshold=params.ape_reversion_frac, detail=c2_detail)
    c3 = Criterion(
        passed=decisive.survived_at_reference, value=None, threshold=0.0,
        detail=(
            f"Held enough margin to survive at the Reference Composite ({ref:,.2f})"
            if decisive.survived_at_reference else
            f"Would have breached maintenance at the Reference Composite ({ref:,.2f}) as well"
        ),
    )
    ape = bool(c1.passed and c2.passed and c3.passed)
    pending = bool(c1.passed and c3.passed and c2.passed is None)

    adl = any(e.stage is LiquidationStage.ADL for e in es)
    out_info = None
    upi_info = None
    if outage is not None and a.affected_by_outage:
        out_info = {"start_tick": outage.start_tick, "end_tick": outage.end_tick,
                    "inside": outage.active(first)}
    if a.upi_initiated_tick is not None:
        upi_info = {
            "amount": a.upi_deposit_inr, "initiated_tick": a.upi_initiated_tick,
            "settles_tick": a.upi_settles_tick, "credit_advanced": a.upi_credit_advanced,
        }

    side = "LONG" if a.side is Side.LONG else "SHORT"
    hurt = -1 if a.side is Side.LONG else 1

    if adl:
        category = "F"
        reason = (
            f"Auto-deleveraged at {clock(first)}: a profitable {side.lower()} closed by the "
            f"venue at a losing account's bankruptcy price. Venue mechanism (L3), no MochaTrade "
            f"cash liability; we file the evidence pack."
        )
    elif out_info and out_info["inside"]:
        category = "D"
        reason = (
            f"Our app and order API were down {clock(outage.start_tick)} to {clock(outage.end_tick)} "
            f"and this user was cut off. Force-closed at {clock(first)}, inside the window, with no "
            f"way to top up or close."
        )
    elif (
        upi_info and a.upi_deposit_inr > 0 and a.upi_initiated_tick is not None
        and a.upi_initiated_tick <= first
        and (a.upi_settles_tick is None or first < a.upi_settles_tick)
    ):
        category = "E"
        settles = "has not settled" if a.upi_settles_tick is None else f"settled at {clock(a.upi_settles_tick)}"
        reason = (
            f"UPI deposit of Rs {a.upi_deposit_inr:,.0f} sent at {clock(a.upi_initiated_tick)} "
            f"{settles}. Force-closed at {clock(first)}: after the money left the user's bank, "
            f"before it reached their margin."
        )
    elif push is not None and push.start <= first <= push.end and push.direction == hurt:
        category = "G"
        reason = (
            f"{side.title()} force-closed at {clock(first)} inside a coordinated push: "
            f"{', '.join(push.sources)} printed beyond the NRR on the same side at the same time "
            f"and our book followed ({push.peak_bps:+,.0f} bps at {clock(push.peak_tick)})."
        )
    elif ape:
        if f.mark_source == "ltp":
            category = "C"
            reason = (
                f"Liquidated on the last traded price, {abs(dev):,.0f} bps from the Reference "
                f"Composite: our market marked on LTP. It came back {retrace:.0%} within "
                f"{params.ape_reversion_seconds}s and the account would have survived at the reference."
            )
        elif defect is not None and f.composite is not None and abs(_bps(f.composite, ref)) > nrr_bps:
            category = "C"
            reason = (
                f"Liquidated on a mark that followed our own composite, "
                f"{abs(_bps(f.composite, ref)):,.0f} bps from the Reference Composite "
                f"({', '.join(defect.sources) or 'defective sources'}). Would have survived at the "
                f"reference; the deviation came back {retrace:.0%} within {params.ape_reversion_seconds}s."
            )
        else:
            category = "B"
            reason = (
                f"Filled {abs(dev):,.0f} bps from the Reference Composite in a thin book while the "
                f"mark tracked the composite. The print came back {retrace:.0%} within "
                f"{params.ape_reversion_seconds}s. Market structure: fee rebate, no cash remedy."
            )
    else:
        category = "A"
        if not c1.passed:
            reason = (
                f"Inside the Non-Reviewable Range: {abs(dev):,.0f} bps from the Reference Composite "
                f"against {nrr_bps:,.0f}. The trade stands; the tape is published."
            )
        elif c2.passed is None:
            reason = f"Pending: {c2_detail}."
        elif not c2.passed:
            reason = f"Not a wick: {c2_detail}."
        else:
            reason = (
                f"The move itself closed this account: it would have breached maintenance at the "
                f"Reference Composite too. Compensating it would pay for the market, not the defect."
            )

    return AccountVerdict(
        account_id=a.id,
        category=category,
        reason=reason,
        side=side,
        leverage=a.leverage,
        entry_price=a.entry_price,
        collateral=a.collateral,
        entry_notional=(a.qty + a.liquidated_qty) * a.entry_price,
        first_tick=first,
        tick=decisive.tick,
        stage=decisive.stage.value,
        executed_price=decisive.fill_price,
        reference_price=ref,
        mark=f.mark,
        mark_source=f.mark_source,
        composite=f.composite,
        book_mid=f.book_mid,
        deviation_bps=round(dev, 1),
        deviation_basis=basis,
        nrr_bps=nrr_bps,
        fills=len(es),
        liquidated_notional=sum(e.notional for e in es),
        fees=sum(e.fee for e in es),
        closed=not a.open,
        ape=ape,
        pending=pending,
        criteria={
            "deviation": asdict(c1),
            "reversion": asdict(c2),
            "survival": asdict(c3),
        },
        outage=out_info,
        upi=upi_info,
    )


def _incident_verdict(
    frames: Sequence[Frame],
    verdicts: list[AccountVerdict],
    counts: Mapping[str, int],
    nrr_bps: float,
    band_bps: float,
    *,
    defect: _Episode | None,
    push: _Episode | None,
    outage,
    upi_in_flight: int,
    wick: _Episode | None,
    closed: tuple[str, ...],
    ltp_c: int,
) -> tuple[str, str, list[str]]:
    evidence: list[str] = []
    ref0 = next((f.reference for f in frames if f.reference), None)
    refs = [f.reference for f in frames if f.reference]
    move = (min(refs) / ref0 - 1.0) * 100 if refs and ref0 else 0.0
    peak_move = (max(refs) / ref0 - 1.0) * 100 if refs and ref0 else 0.0
    n = len(verdicts)

    if push is not None:
        evidence.append(
            f"{' and '.join(push.sources)} printed beyond the {nrr_bps:,.0f} bps NRR on the same "
            f"side together, {clock(push.fp_start or push.start)} to {clock(push.fp_end or push.end)}; "
            f"our book followed to {push.peak_bps:+,.0f} bps at {clock(push.peak_tick)}. The episode "
            f"runs from {clock(push.start)}, when the price first left its opening level."
        )
        evidence.append("Our published composite held: the push came through the venues, not our oracle.")
        headline = (
            f"A coordinated push across venues moved our book; {counts['G']} "
            f"account{'s' if counts['G'] != 1 else ''} force-closed inside it."
        )
        category = "G"
    elif defect is not None:
        evidence.append(
            f"The composite we published was up to {abs(defect.peak_bps):,.0f} bps "
            f"{'below' if defect.peak_bps < 0 else 'above'} the Reference Composite, "
            f"{clock(defect.start)} to {clock(defect.end)} (NRR {nrr_bps:,.0f} bps)."
        )
        if defect.sources:
            evidence.append(
                f"Sources printing beyond the NRR in that window: {', '.join(defect.sources)}. "
                f"With two agreeing, the median itself moved and the honest source was clamped."
            )
        headline = (
            f"Our own oracle published a wrong price; {counts['C']} "
            f"account{'s' if counts['C'] != 1 else ''} liquidated on it."
            if counts["C"] else
            "Our own oracle published a wrong price. Liquidations were paused before it cost anyone."
        )
        category = "C"
    elif outage is not None:
        evidence.append(
            f"Our {outage.label} from {clock(outage.start_tick)} to {clock(outage.end_tick)}, "
            f"{outage.affected_frac:.0%} of users cut off. A malfunction of five minutes or more is "
            f"a reportable technical glitch under the SEBI framework we adopt voluntarily."
        )
        headline = (
            f"Our app and API went down mid-move; {counts['D']} "
            f"user{'s' if counts['D'] != 1 else ''} force-closed while locked out."
        )
        category = "D"
    elif upi_in_flight:
        evidence.append(
            f"{upi_in_flight} UPI deposit{'s' if upi_in_flight != 1 else ''} initiated during the "
            f"event settled late; the rail's delay became our margin system's delay."
        )
        headline = (
            f"UPI top-ups settled after the liquidation for {counts['E']} "
            f"user{'s' if counts['E'] != 1 else ''}."
        )
        category = "E"
    elif ltp_c:
        evidence.append(
            f"{ltp_c} account{'s' if ltp_c != 1 else ''} liquidated on the last traded price while "
            f"the Reference Composite said otherwise: the mark did not track the oracle."
        )
        headline = (
            f"Our market marked on the last trade; {ltp_c} accounts were liquidated on prints "
            f"the Reference Composite never reached."
        )
        category = "C"
    elif counts["B"] or wick is not None:
        if wick is not None:
            evidence.append(
                f"The book printed up to {abs(wick.peak_bps):,.0f} bps from the Reference Composite at "
                f"{clock(wick.peak_tick)} while the mark stayed within {band_bps:,.0f} bps of it."
            )
        if closed:
            evidence.append(
                f"{', '.join(closed)} closed: our users were the only flow, and the composite ran on "
                f"its published off-hours rung."
            )
        headline = (
            f"A venue-local wick in a thin book; the mark held. {counts['B']} "
            f"account{'s' if counts['B'] != 1 else ''} filled on it."
            if counts["B"] else
            "A venue-local wick in a thin book; the mark held, and nobody was liquidated on it."
        )
        category = "B"
    elif n and counts["F"] == n:
        headline = "Every forced close was a venue auto-deleverage."
        category = "F"
    else:
        headline = (
            f"A genuine move: the Reference Composite itself went {move:+.1f}%"
            + (f" / {peak_move:+.1f}%" if abs(peak_move) > abs(move) else "")
            + ", on a healthy ladder."
        )
        category = "A"

    # Evidence every verdict carries: what happened to the accounts.
    if n:
        survived = sum(1 for v in verdicts if v.criteria["survival"]["passed"])
        evidence.append(
            f"{n} account{'s' if n != 1 else ''} force-closed; {sum(1 for v in verdicts if v.ape)} "
            f"passed all three APE criteria; {survived} would have survived at the Reference Composite."
        )
    else:
        evidence.append("No account was force-closed.")
    if category == "A":
        evidence.append(
            f"The Reference Composite moved {move:+.1f}% with every source agreeing; "
            f"no defect on any of our three layers."
        )
    return category, headline, evidence
