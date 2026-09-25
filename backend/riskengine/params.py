"""Risk parameters — the numbers MochaTrade chooses.

This module is the pure-Python mirror of the versioned `RiskPolicy` Django
model (Phase 2). The model owns persistence and the admin surface; this owns
the shape and the v1 values. Nothing here is read from a database and nothing
downstream of here may hard-code a risk number.

Separation of concerns, which matters for the whole demo:

    RiskParams  what MochaTrade decides — margin tiers, throttles, bands,
                caps, the compensation policy. Versioned, publishable,
                and the thing a judge is invited to change.
    Scenario    what the world does — the shock, the book, the account
                population, the injected faults. See scenario.py.

Provenance: FIELD_SOURCES below carries a citation for every field. The Django
model renders those verbatim as `help_text`, so the source of a number is
visible in the admin, in the API and on the policy page. Three fields are
marked DERIVED: the research brief specifies the mechanism but not the value,
so we state the derivation rule rather than pretend the number is sourced.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

# One tick is one second. The Abnormal Price Event test compares an execution
# against the Reference Composite "in the same 1-second window", so the whole
# engine runs on that grain. Sub-second behaviour (the 250ms TWAP slice) is
# modelled as slices within a tick.
TICK_SECONDS: Final[float] = 1.0

LAKH: Final[float] = 1_00_000.0
CRORE: Final[float] = 1_00_00_000.0


@dataclass(frozen=True, slots=True)
class MarginTier:
    """One rung of the maintenance-margin ladder, by position notional in INR."""

    max_notional: float | None  # None == the top tier, unbounded
    max_leverage: float
    mm_rate: float

    def contains(self, notional: float) -> bool:
        return self.max_notional is None or notional <= self.max_notional


@dataclass(frozen=True, slots=True)
class InstrumentTier:
    """Per-instrument risk tier. Sets the Non-Reviewable Range for the APE test
    and the Dynamic Circuit Breaker variant."""

    tier: int
    label: str
    nrr_pct: float
    nrr_offhours_pct: float
    dcb_variant_pct: float


# Mirrors Hyperliquid's 1.25%-16.7% maintenance band with Binance-style tiering.
MARGIN_TIERS_V1: Final[tuple[MarginTier, ...]] = (
    MarginTier(max_notional=5 * LAKH, max_leverage=50.0, mm_rate=0.010),
    MarginTier(max_notional=25 * LAKH, max_leverage=25.0, mm_rate=0.020),
    MarginTier(max_notional=1 * CRORE, max_leverage=10.0, mm_rate=0.050),
    MarginTier(max_notional=5 * CRORE, max_leverage=5.0, mm_rate=0.100),
    MarginTier(max_notional=None, max_leverage=3.0, mm_rate=0.167),
)

# NRR values are the published table from the research brief. Note the implied
# off-hours multipliers are 1.67 / 1.60 / 1.50, which is why the table is stored
# literally rather than as a base value times one multiplier. The DCB does use a
# single 1.6x off-hours multiplier, as specified.
INSTRUMENT_TIERS_V1: Final[tuple[InstrumentTier, ...]] = (
    InstrumentTier(1, "BTC, ETH, SPY, mega-cap US equities", 3.0, 5.0, 2.5),
    InstrumentTier(2, "SOL, gold, large-cap equities, indices", 5.0, 8.0, 5.0),
    InstrumentTier(3, "Long-tail crypto, pre-IPO perps", 10.0, 15.0, 10.0),
)


@dataclass(frozen=True, slots=True)
class RiskParams:
    """RiskPolicy v1. Frozen: a policy change is a new version, not a mutation."""

    version: str = "v1"

    # --- Margin and liquidation -------------------------------------------
    margin_tiers: tuple[MarginTier, ...] = MARGIN_TIERS_V1
    backstop_threshold_frac: float = 2.0 / 3.0
    partial_liq_target_mm_multiple: float = 1.5  # DERIVED
    clearance_fee_pct: float = 0.005

    # --- Liquidation throttle ---------------------------------------------
    twap_slice_ms: int = 250
    twap_max_participation_pct: float = 0.20
    twap_participation_band_pct: float = 0.01

    # --- Margin call grace -------------------------------------------------
    margin_grace_seconds: int = 120
    upi_prefunded_credit_cap_inr: float = 50_000.0

    # --- Instrument tiers, NRR, DCB ---------------------------------------
    instrument_tiers: tuple[InstrumentTier, ...] = INSTRUMENT_TIERS_V1
    dcb_offhours_multiplier: float = 1.6
    dcb_lookback_seconds: int = 3600
    dcb_pause_seconds: int = 120
    velocity_window_seconds: int = 5
    velocity_trigger_frac_of_dcb: float = 0.5  # DERIVED
    velocity_cooldown_seconds: int = 10  # DERIVED, tuned (see FIELD_SOURCES)
    velocity_escalation_multiplier: float = 4.0  # DERIVED
    price_band_frac_of_dcb: float = 1.0  # DERIVED

    # --- Oracle and marking ------------------------------------------------
    mark_max_deviation_bps: float = 50.0
    outlier_clamp_pct: float = 0.03
    majors_outlier_clamp_pct: float = 0.01
    staleness_seconds: int = 300
    basis_ma_seconds: int = 30
    funding_period_seconds: int = 3600
    composite_l1_min_sources: int = 3
    composite_l2_min_sources: int = 1
    composite_l3_min_sources: int = 2

    # --- Leverage caps -----------------------------------------------------
    max_leverage_rth: float = 50.0
    max_leverage_offhours: float = 5.0
    max_leverage_degraded: float = 3.0

    # --- Abnormal Price Event test ----------------------------------------
    ape_reversion_frac: float = 0.50
    ape_reversion_seconds: int = 60

    # --- Compensation ------------------------------------------------------
    incident_reserve_opening_inr: float = 2 * CRORE
    per_incident_cap_inr: float = 1.5 * CRORE
    provisional_credit_minutes: int = 60
    reserve_funding_share_of_fees: float = 0.10
    reserve_target_multiple_of_worst_loss: float = 2.0

    # ----------------------------------------------------------------------
    def tier_for_notional(self, notional: float) -> MarginTier:
        for tier in self.margin_tiers:
            if tier.contains(abs(notional)):
                return tier
        return self.margin_tiers[-1]

    def mm_rate(self, notional: float) -> float:
        return self.tier_for_notional(notional).mm_rate

    def max_leverage_for_notional(self, notional: float) -> float:
        return self.tier_for_notional(notional).max_leverage

    def instrument_tier(self, tier: int) -> InstrumentTier:
        for spec in self.instrument_tiers:
            if spec.tier == tier:
                return spec
        raise ValueError(f"unknown instrument tier {tier}")

    def nrr_pct(self, tier: int, *, offhours: bool) -> float:
        spec = self.instrument_tier(tier)
        return spec.nrr_offhours_pct if offhours else spec.nrr_pct

    def dcb_variant_pct(self, tier: int, *, offhours: bool) -> float:
        variant = self.instrument_tier(tier).dcb_variant_pct
        return variant * self.dcb_offhours_multiplier if offhours else variant

    def velocity_trigger_pct(self, tier: int, *, offhours: bool) -> float:
        return self.dcb_variant_pct(tier, offhours=offhours) * self.velocity_trigger_frac_of_dcb

    def price_band_pct(self, tier: int, *, offhours: bool) -> float:
        return self.dcb_variant_pct(tier, offhours=offhours) * self.price_band_frac_of_dcb

    def clamp_pct_for(self, *, is_major: bool) -> float:
        return self.majors_outlier_clamp_pct if is_major else self.outlier_clamp_pct

    def backstop_threshold(self, mm_required: float) -> float:
        return mm_required * self.backstop_threshold_frac

    @property
    def twap_slices_per_tick(self) -> int:
        return max(1, int(round(TICK_SECONDS * 1000.0 / self.twap_slice_ms)))

    @property
    def basis_ma_ticks(self) -> int:
        return max(1, int(round(self.basis_ma_seconds / TICK_SECONDS)))

    @property
    def margin_grace_ticks(self) -> int:
        return max(0, int(round(self.margin_grace_seconds / TICK_SECONDS)))

    @property
    def dcb_lookback_ticks(self) -> int:
        return max(1, int(round(self.dcb_lookback_seconds / TICK_SECONDS)))

    @property
    def dcb_pause_ticks(self) -> int:
        return max(1, int(round(self.dcb_pause_seconds / TICK_SECONDS)))

    @property
    def velocity_window_ticks(self) -> int:
        return max(1, int(round(self.velocity_window_seconds / TICK_SECONDS)))

    @property
    def velocity_cooldown_ticks(self) -> int:
        return max(0, int(round(self.velocity_cooldown_seconds / TICK_SECONDS)))

    def velocity_pause_ticks(self, level: int) -> int:
        """Pause length at an escalation level: the base velocity pause times the
        multiplier per level, capped at the circuit breaker's own pause so the
        micro layer never outlasts the meso layer."""
        base = self.velocity_window_ticks * self.velocity_escalation_multiplier ** max(0, level)
        return max(1, min(int(round(base)), self.dcb_pause_ticks))

    @property
    def staleness_ticks(self) -> int:
        return max(1, int(round(self.staleness_seconds / TICK_SECONDS)))

    @property
    def ape_reversion_ticks(self) -> int:
        return max(1, int(round(self.ape_reversion_seconds / TICK_SECONDS)))

    def evolve(self, **changes: object) -> "RiskParams":
        """A new version with fields overridden. This is how a judge changes a
        parameter and watches the result move."""
        return replace(self, **changes)  # type: ignore[arg-type]


DEFAULT_PARAMS: Final[RiskParams] = RiskParams()


# Provenance for every field. Phase 2 renders these verbatim as `help_text`, so
# a reader can always see where a number came from. DERIVED means the brief
# specifies the mechanism but not the value.
FIELD_SOURCES: Final[dict[str, str]] = {
    "margin_tiers": (
        "Maintenance margin ladder by position notional (INR). Mirrors "
        "Hyperliquid's 1.25%-16.7% maintenance band with Binance-style tiering: "
        "<=5L 50x/1.0%, 5L-25L 25x/2.0%, 25L-1Cr 10x/5.0%, 1Cr-5Cr 5x/10.0%, "
        ">5Cr 3x/16.7%."
    ),
    "backstop_threshold_frac": (
        "Two-stage liquidation. Hyperliquid's model: below maintenance margin "
        "the position is worked at market and the trader keeps any residual "
        "collateral with no clearance fee; only below two-thirds of maintenance "
        "margin does the backstop liquidator vault take it and the maintenance "
        "margin is forfeited. Research brief 4.3."
    ),
    "partial_liq_target_mm_multiple": (
        "DERIVED. A partial liquidation closes only enough to restore margin "
        "(brief 4.3, 'close only enough to restore margin, sized by position "
        "tier'), but the brief gives no target multiple. We restore to 1.5x "
        "maintenance margin so the account is not re-liquidated on the next "
        "tick, which would reproduce the cascade the control exists to stop."
    ),
    "clearance_fee_pct": (
        "Charged only on the stage-two backstop path. Stage one is explicitly "
        "fee-free in Hyperliquid's design. Research brief 4.3."
    ),
    "twap_slice_ms": (
        "Liquidation TWAP throttle slice interval. Kills amplifier 1, the "
        "liquidation engine becoming the largest seller (BitMEX, 12-13 Mar 2020: "
        "the price recovered from ~$3,900 to ~$5,300 the moment a DDoS took the "
        "engine offline). Research brief 2 and 8, change #3."
    ),
    "twap_max_participation_pct": (
        "Maximum share of resting depth the liquidation engine may consume per "
        "slice. Research brief 8, change #3: 'liquidation TWAP throttle + max "
        "participation rate of resting depth'."
    ),
    "twap_participation_band_pct": (
        "The depth band the participation rate is measured against: resting "
        "depth within 1% of the mark."
    ),
    "margin_grace_seconds": (
        "Margin-call grace window before the engine fires, with a push "
        "notification. Sized to UPI p99 settlement, not to market risk: this "
        "control exists because of the rail, not because of the market. India "
        "saw 282 minutes of UPI outage across two incidents, so a user's ability "
        "to avoid liquidation must not depend on an NPCI leg settling. Research "
        "brief 4.3 and 7.3."
    ),
    "upi_prefunded_credit_cap_inr": (
        "Pre-funded instant margin credit against an initiated-but-unsettled UPI "
        "deposit, capped and risk-scored. The single most India-specific "
        "engineering control in the brief. Research brief 7.3."
    ),
    "instrument_tiers": (
        "Non-Reviewable Ranges per instrument tier, RTH and off-hours: tier 1 "
        "3%/5%, tier 2 5%/8%, tier 3 10%/15%. Published ex ante in the T&Cs so "
        "'abnormal' is defined before the event, not argued after it. Research "
        "brief 5.1."
    ),
    "dcb_offhours_multiplier": (
        "Off-hours widening of the Dynamic Circuit Breaker variant. Off-hours is "
        "when MochaTrade's flagship US equity perps are most exposed: US cash "
        "equities are open 19:00-01:30 IST, so an IST-morning wick has no cash "
        "market to reference. Research brief 1."
    ),
    "dcb_lookback_seconds": (
        "Dynamic Circuit Breaker rolling look-back window. CME DCB: rolling "
        "60-minute look-back high/low plus or minus the variant; the window "
        "restarts on resume. Research brief 4.2."
    ),
    "dcb_pause_seconds": (
        "Pause on a DCB breach, entered as a pre-open auction rather than a "
        "hard stop. CME DCB: 2-minute pre-open, reduced to 5s near the close. "
        "Research brief 4.2."
    ),
    "velocity_window_seconds": (
        "Velocity logic window. A brief pause to let participants reassess after "
        "a micro-scale move; CFTC/FIA cite ~5 seconds. Research brief 4.2."
    ),
    "velocity_trigger_frac_of_dcb": (
        "DERIVED. CFTC/FIA specify velocity logic as a layer and its ~5s pause, "
        "but publish no trigger threshold. We set it at half the DCB variant "
        "over the velocity window, so the micro layer fires before the meso "
        "layer, which is the ordering the four-layer design requires."
    ),
    "velocity_cooldown_seconds": (
        "DERIVED. After a velocity pause ends, the velocity check may not fire "
        "again for this long. Without it the protected macro cascade paused 56 "
        "times in 5-second bursts with 3 seconds of trading between them, and each "
        "reopen dumped queued liquidations back into the book: 83 price swings of "
        "50 bps or more against 4 with no controls at all. CFTC/FIA specify the "
        "layer and its ~5s pause but no re-arm rule. Tuned from 30s against all "
        "six scenarios with reopens through the call auction: from 20s up the "
        "throttle drains the queue in continuous trading before the layer re-arms, "
        "and controls-on loses to controls-off on unnecessary liquidations in "
        "upi_settlement_delay. 10s is the longest value that keeps the controls "
        "ahead everywhere. The deeper cause is that the 20% TWAP participation "
        "moves price ~88 bps/s against a velocity trigger of ~40 bps/s, so the "
        "engine's own permitted pace trips the layer; see ARCHITECTURE.md."
    ),
    "velocity_escalation_multiplier": (
        "DERIVED. If the price is still moving too fast when the cooldown ends, the "
        "next velocity pause is this many times longer than the last (5s, 20s, "
        "80s), capped at the circuit breaker's 120s pause. Repeating the same short "
        "pause into a market that has not calmed is what produced the zig-zag. The "
        "escalation resets once a full velocity window passes calm after cooldown."
    ),
    "price_band_frac_of_dcb": (
        "DERIVED. CME price bands are per-product and continuously recalculated, "
        "so there is no single published number. We set the band equal to the "
        "DCB variant, giving one replicable figure a participant can compute. A "
        "pre-trade band is what would have stopped Binance.US printing BTC at "
        "$8,200 (-87%) on 21 Oct 2021 from one client's algo bug. Brief 3, 4.2."
    ),
    "mark_max_deviation_bps": (
        "Mark-to-Reference-Composite divergence that trips the auto-pager at "
        "T+0..2. The playbook's first detection trigger, alongside liquidation "
        "rate per minute, API 5xx rate and ticket rate. Research brief 6."
    ),
    "outlier_clamp_pct": (
        "A source deviating more than this from the median is capped at "
        "1.03x/0.97x the median. Binance's published index method. Brief 4.1."
    ),
    "majors_outlier_clamp_pct": (
        "The tighter clamp Binance applies to BTC, ETH and SOL. Brief 4.1."
    ),
    "staleness_seconds": (
        "Staleness kill. Binance: if data from an exchange is unavailable or has "
        "not updated within the last five minutes, that exchange's weight is set "
        "to zero. Research brief 4.1."
    ),
    "basis_ma_seconds": (
        "Moving-average window for the basis leg of the mark price: 30 samples "
        "at 1s of mid minus index. Binance's published mark method. Brief 4.1."
    ),
    "funding_period_seconds": (
        "Funding period used by the Price1 leg of the mark. Hourly, matching "
        "Hyperliquid, the venue MochaTrade actually builds on. Brief 4.1."
    ),
    "composite_l1_min_sources": (
        "Reference Composite ladder L1 requires at least 3 major spot venues "
        "(crypto) or the US cash market (equities, RTH). Research brief 5.1."
    ),
    "composite_l2_min_sources": (
        "Ladder L2: index futures (ES/NQ) plus ADRs plus an ETF NAV proxy. "
        "Research brief 5.1."
    ),
    "composite_l3_min_sources": (
        "Ladder L3: median of at least 2 independent perp venues. Below this the "
        "market is force-flagged DEGRADED (L4). Research brief 5.1."
    ),
    "max_leverage_rth": (
        "Max leverage during US regular trading hours. MochaTrade's YC launch "
        "offers up to 50x. Research brief 0."
    ),
    "max_leverage_offhours": (
        "Time-of-day leverage cap for equity perps outside US cash hours: 50x "
        "RTH becomes 5x off-hours. Three days of engineering, and it addresses "
        "the product's own worst vector. Research brief 8, change #4."
    ),
    "max_leverage_degraded": (
        "Max leverage when the composite is at L4 or the Protect Switch is "
        "thrown: 3x, reduce-only, liquidations paused. Research brief 5.1, 6."
    ),
    "ape_reversion_frac": (
        "APE test criterion 2, reversion: the deviation must retrace at least "
        "50% within the reversion window, i.e. it was a wick and not a "
        "repricing. Research brief 5.1."
    ),
    "ape_reversion_seconds": (
        "The reversion window for APE criterion 2. Research brief 5.1."
    ),
    "incident_reserve_opening_inr": (
        "Incident Reserve opening balance. Ring-fenced and publicly visible, "
        "funded by 10% of builder-code fee revenue until it reaches 2x the worst "
        "modelled 30-day loss. Research brief 5.3."
    ),
    "per_incident_cap_inr": (
        "Published per-incident compensation cap. Deliberately set below the "
        "headline scenario's expected exposure so the pro-rata overflow path is "
        "reachable: beyond the cap, compensation is pro-rata by a published "
        "formula plus a non-cash make-good, announced as pro-rata and never paid "
        "silently short. Binance spent ~$188M of insurance fund and ~$283M total "
        "on one weekend; MochaTrade cannot, so an honest finite promise beats an "
        "implied infinite one. Research brief 5.3."
    ),
    "provisional_credit_minutes": (
        "Speed clause. For clear-cut class C/D/E signatures, provisional credit "
        "is pushed within 60 minutes as locked trading credit, converted to "
        "withdrawable cash after a published reconciliation. Research brief 5.2."
    ),
    "reserve_funding_share_of_fees": (
        "Share of builder-code fee revenue routed to the Incident Reserve until "
        "it reaches target. Research brief 5.3."
    ),
    "reserve_target_multiple_of_worst_loss": (
        "Reserve target: 2x the worst modelled 30-day loss. Circular until the "
        "simulator has run, which is the point: Phase 9's Recalibrate action "
        "recomputes it across all seeded scenarios and writes a new RiskPolicy "
        "version. Research brief 5.3."
    ),
}

DERIVED_FIELDS: Final[frozenset[str]] = frozenset(
    name for name, text in FIELD_SOURCES.items() if text.startswith("DERIVED")
)
