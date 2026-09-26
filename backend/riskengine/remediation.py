"""Counterfactual equity, make-whole sizing and the funding waterfall.

Policy: trades stand, people get made whole. Never reverse, always compensate,
decide by a rule published first. Four reasons, all citable: fills are on-chain
and non-custodial so reversal is literally unavailable; reversal creates a
second set of victims among legitimate counterparties (JELLY); Indian precedent
is hostile to annulment (SAT/Emkay, where the tribunal held that the annulment
clause "is not intended to give relief to a trader guilty of negligence"); and
CFTC/FIA best practice is that all trades stand, with price adjustment
preferred over cancellation.

Responsibilities
----------------
- Counterfactual equity: re-run each affected account against the Reference
  Composite Price instead of the disputed mark, and take the difference.
- Apply the remedy matrix by class, including the explicit exclusion for
  customers who experienced trading losses under normal circumstances (the OKX
  Jan 2019 notice is the template: name the exact windows, set a crediting
  deadline, exclude normal losses, do not roll back).
- The speed clause, which is the thing that actually keeps users: for clear-cut
  C/D/E signatures, push provisional credit within 60 minutes as locked trading
  credit, converted to withdrawable cash after a published reconciliation. Do
  not make a liquidated user file a ticket to get their own money back.
- The funding waterfall, drawn down in order:
      1. recovery from the at-fault party (attacker / vendor SLA / PSP)
      2. Incident Reserve - ring-fenced, publicly visible balance, funded by
         10% of builder-code fee revenue until it reaches 2x the worst modelled
         30-day loss
      3. corporate treasury, up to a published per-incident cap
      4. tech E&O insurance
      5. beyond the cap, pro-rata by a published formula plus a non-cash
         make-good, announced as pro-rata and never paid silently short
- Report the India tax overlay: VDA gains are taxed at a flat 30% with no loss
  set-off, plus 1% TDS, so a wiped-out Indian trader eats 100% of the loss with
  zero deductibility. The trust damage from an identical event is strictly
  worse here, and compensation credits themselves carry characterisation risk
  and may need grossing up.

The published formulas
----------------------
Make-whole, per class:

    C  counterfactual equity at the Reference Composite, minus equity now.
       The engine's counterfactual already excludes normal losses: an account
       that breaches even at the honest price is valued where that price would
       have closed it (OKX, Jan 2019).
    D  equity when our outage locked the user out, at the Reference Composite
       of that second, minus equity now. The loss taken while unable to act.
    E  as C, with the deposit counted from the moment it was sent: the engine's
       counterfactual credits the deposit to the restored position.
    G  equity when the push began, at the Reference Composite of that second,
       minus equity now. Fronted from the Incident Reserve; recovery pursued.
    B  no cash. The account's liquidation fees are rebated.
    A  none. F: no MochaTrade cash; the evidence pack is filed with the venue.

The cap is the published maximum cash paid on one incident, from all sources
together. Inside it, the waterfall decides who funds the payout. Beyond it,
every eligible claim is paid the same fraction, cap / total, in cash; the rest
of each claim is a non-cash make-good, and the payout is announced as pro-rata.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence

from .classifier import AccountVerdict, Classification
from .indian import inr_text
from .engine import Frame
from .liquidation import Account, LiquidationEvent
from .params import RiskParams

CASH_CLASSES = frozenset({"C", "D", "E", "G"})
PROVISIONAL_CLASSES = frozenset({"C", "D", "E"})
"""Clear-cut signatures that get provisional credit inside the speed clause. G
is cash too, but a manipulation claim waits for the IC: freezing and reporting
come first, and the reserve fronts it only once the IC signs."""


@dataclass(frozen=True, slots=True)
class Remedy:
    account_id: str
    category: str
    kind: str
    """"cash", "fee_rebate" or "none"."""
    make_whole: float
    """The full claim under the published formula, before any cap."""
    fee_rebate: float
    basis: str
    """The formula, in words, with this account's numbers in it."""
    equity_now: float
    reference_equity: float | None
    """What the formula restores the account to."""
    provisional: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Tranche:
    step: int
    source: str
    drawn: float
    available: float | None
    note: str


@dataclass(slots=True)
class Waterfall:
    total_claims: float
    cap: float
    payable: float
    pro_rata: bool
    ratio: float
    """Cash paid per rupee claimed. 1.0 unless the cap binds."""
    shortfall: float
    """Claimed beyond the cap: paid as a non-cash make-good, announced as pro-rata."""
    reserve_opening: float
    reserve_available: float
    reserve_after: float
    fee_rebates: float
    tranches: list[Tranche] = field(default_factory=list)
    formula: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


# --------------------------------------------------------------------------
# Equity at a moment, rebuilt from the fill tape
# --------------------------------------------------------------------------

def equity_at(account: Account, events: Sequence[LiquidationEvent], frames: Sequence[Frame], tick: int) -> float:
    """The account's equity at the start of `tick`, valued at that second's
    Reference Composite: collateral, plus what its forced fills before `tick`
    realised, plus the rest of the position marked to the reference."""
    side = int(account.side)
    restored = account.qty + account.liquidated_qty
    realised = 0.0
    closed_qty = 0.0
    for e in events:
        if e.tick >= tick:
            continue
        realised += side * e.qty * (e.fill_price - account.entry_price) - e.fee
        closed_qty += e.qty
    frame = frames[min(max(tick, 0), len(frames) - 1)]
    reference = frame.reference or frame.mark
    open_qty = max(0.0, restored - closed_qty)
    return account.collateral - account.deposits_credited + realised + side * open_qty * (reference - account.entry_price)


# --------------------------------------------------------------------------
# Per-account remedies
# --------------------------------------------------------------------------

def remedies(
    classification: Classification,
    accounts: Mapping[str, Account],
    events: Sequence[LiquidationEvent],
    frames: Sequence[Frame],
    valuations: Mapping[str, tuple[float, float]],
) -> list[Remedy]:
    """One remedy per classified account, by the published formula for its class."""
    by_account: dict[str, list[LiquidationEvent]] = {}
    for e in events:
        by_account.setdefault(e.account_id, []).append(e)
    push = classification.signals.get("push")
    out: list[Remedy] = []
    for v in classification.accounts:
        a = accounts[v.account_id]
        equity, counterfactual = valuations[v.account_id]
        out.append(_remedy(v, a, by_account.get(v.account_id, []), frames, equity, counterfactual, push))
    return out


def _remedy(
    v: AccountVerdict,
    a: Account,
    fills: list[LiquidationEvent],
    frames: Sequence[Frame],
    equity: float,
    counterfactual: float,
    push: object,
) -> Remedy:
    c = v.category
    if c in ("C", "E"):
        amount = max(0.0, counterfactual - equity)
        what = "counterfactual equity at the Reference Composite"
        if c == "E":
            what += ", with the deposit counted from the moment it was sent"
        return Remedy(v.account_id, c, "cash", amount, 0.0,
                      f"Restore to {what}: {inr_text(counterfactual)} against {inr_text(equity)} now.",
                      equity, counterfactual, True)
    if c == "D" and v.outage:
        start = int(v.outage["start_tick"])  # type: ignore[call-overload]
        before = equity_at(a, fills, frames, start)
        amount = max(0.0, before - equity)
        return Remedy(v.account_id, c, "cash", amount, 0.0,
                      f"Restore to equity when our outage locked the user out: {inr_text(before)} at the "
                      f"Reference Composite of that second, against {inr_text(equity)} now.",
                      equity, before, True)
    if c == "G" and isinstance(push, dict):
        start = int(push["start_tick"])
        before = equity_at(a, fills, frames, start)
        amount = max(0.0, before - equity)
        return Remedy(v.account_id, c, "cash", amount, 0.0,
                      f"Restore to equity when the push began: {inr_text(before)} at the Reference Composite "
                      f"of that second, against {inr_text(equity)} now. Fronted from the Incident Reserve; "
                      f"recovery is pursued from the attacker.",
                      equity, before, False)
    if c == "B":
        rebate = sum(e.fee for e in fills)
        return Remedy(v.account_id, c, "fee_rebate", 0.0, rebate,
                      f"No cash remedy. Liquidation fees of {inr_text(rebate)} rebated; the depth fix ships with a date.",
                      equity, None, False)
    if c == "F":
        return Remedy(v.account_id, c, "none", 0.0, 0.0,
                      "No MochaTrade cash liability. The evidence pack is filed with the venue on the user's behalf "
                      "and the venue's response is published.",
                      equity, None, False)
    return Remedy(v.account_id, c, "none", 0.0, 0.0,
                  "No remedy: the trade stands and the evidence tape is published.", equity, None, False)


# --------------------------------------------------------------------------
# The waterfall
# --------------------------------------------------------------------------

def waterfall(items: Sequence[Remedy], params: RiskParams, *, reserve_available: float, recovered: float = 0.0) -> Waterfall:
    """Fund one incident's cash claims, in the published order, up to the cap.

    `reserve_available` is the Incident Reserve's balance now -- the policy's
    opening balance less what earlier incidents drew -- and `recovered` is
    money already recovered from the at-fault party. Nothing is assumed to be
    recovered at payout time: an attacker or a PSP pays late or not at all, and
    the user should not wait for them.
    """
    total = sum(r.make_whole for r in items if r.kind == "cash")
    cap = params.per_incident_cap_inr
    payable = min(total, cap)
    pro_rata = total > cap + 1e-9
    ratio = payable / total if total > 0 else 1.0
    shortfall = max(0.0, total - payable)

    remaining = payable
    from_recovery = min(recovered, remaining)
    remaining -= from_recovery
    from_reserve = min(max(0.0, reserve_available), remaining)
    remaining -= from_reserve
    from_treasury = remaining

    at_fault = sorted({r.category for r in items if r.kind == "cash"})
    recovery_note = (
        "Pursued from the attacker; nothing is assumed recovered at payout time." if "G" in at_fault
        else "Pursued from the PSP under its SLA; nothing is assumed recovered at payout time." if "E" in at_fault
        else "The at-fault party is MochaTrade: nothing to recover from anyone else." if at_fault
        else "No cash claims."
    )
    tranches = [
        Tranche(1, "Recovery from the at-fault party", from_recovery, recovered, recovery_note),
        Tranche(2, "Incident Reserve", from_reserve, reserve_available,
                "Ring-fenced, publicly visible balance, funded by "
                f"{params.reserve_funding_share_of_fees:.0%} of builder-code fees until it reaches "
                f"{params.reserve_target_multiple_of_worst_loss:g}x the worst modelled 30-day loss."),
        Tranche(3, "Corporate treasury", from_treasury, max(0.0, cap - from_recovery - from_reserve),
                f"Tops the payout up to the published per-incident cap of {inr_text(cap)}."),
        Tranche(4, "Tech E&O insurance", 0.0, None,
                "Reimburses the treasury's share after payout, as far as the policy covers it. "
                "Users are not made to wait for the insurer."),
        Tranche(5, "Beyond the cap: pro-rata + non-cash make-good", shortfall, None,
                (f"Claims total {inr_text(total)} against a cap of {inr_text(cap)}: every eligible claim is paid "
                 f"{ratio:.1%} in cash and the rest as a non-cash make-good. Announced as pro-rata, never "
                 f"paid silently short.") if pro_rata else "Not reached: every claim is paid in full."),
    ]
    return Waterfall(
        total_claims=total,
        cap=cap,
        payable=payable,
        pro_rata=pro_rata,
        ratio=ratio,
        shortfall=shortfall,
        reserve_opening=params.incident_reserve_opening_inr,
        reserve_available=reserve_available,
        reserve_after=max(0.0, reserve_available) - from_reserve,
        fee_rebates=sum(r.fee_rebate for r in items),
        tranches=tranches,
        formula=(
            "cash_i = claim_i x min(1, cap / total claims); make_good_i = claim_i - cash_i. "
            f"Cap {inr_text(cap)} per incident, from all sources together."
        ),
    )


def reserve_target(worst_loss: float, params: RiskParams) -> float:
    """Research 5.3: the reserve is funded until it reaches this."""
    return params.reserve_target_multiple_of_worst_loss * worst_loss
