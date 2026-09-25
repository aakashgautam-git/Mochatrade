"""Persistence for MochaTrade Crisis Command.

Two rules govern this module.

1. **RiskPolicy is a generated mirror of `riskengine.params.RiskParams`.**
   Not a copy of it. Every parameter field takes its default AND its `help_text`
   from the dataclass and from `FIELD_SOURCES`, so a number and its citation
   exist in exactly one place in the repo. `RiskPolicy.to_params()` is the ONLY
   route by which the engine ever receives configuration -- nothing constructs
   a `RiskParams` by hand outside tests and the seeder.
   `tests/test_policy_mirror.py` fails the build if the two field sets drift
   apart in either direction.

2. **This layer holds no risk logic.** It stores, serialises and audits. The
   simulation lives in `riskengine/`, which imports nothing from here.

Numeric types are chosen deliberately. RiskPolicy uses FloatField throughout,
because its values round-trip into a frozen float dataclass and a Decimal
detour could perturb a seeded run. Ledger-ish models -- accounts, claims,
exposure -- use DecimalField, because those are money.
"""
from __future__ import annotations

from dataclasses import fields as dataclass_fields
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from riskengine.params import (
    DEFAULT_PARAMS,
    FIELD_SOURCES,
    InstrumentTier as EngineInstrumentTier,
    MarginTier as EngineMarginTier,
    RiskParams,
)

# --------------------------------------------------------------------------
# The mirror
# --------------------------------------------------------------------------

#: RiskParams fields that are ladders, stored as related rows rather than
#: JSON so they are editable, validatable and inspectable in the admin.
RELATED_PARAM_FIELDS: dict[str, str] = {
    "margin_tiers": "margin_tier_rows",
    "instrument_tiers": "instrument_tier_rows",
}

#: RiskPolicy fields that are record-keeping, not risk parameters.
ADMIN_ONLY_FIELDS: frozenset[str] = frozenset(
    {"id", "name", "is_active", "created_at", "notes"}
)

SCALAR_PARAM_NAMES: tuple[str, ...] = tuple(
    f.name
    for f in dataclass_fields(RiskParams)
    if f.name not in RELATED_PARAM_FIELDS and f.name != "version"
)


def _param(field_cls, name: str, **kwargs):
    """A model field whose default and help_text come from the dataclass.

    Retyping either by hand is how a policy document and its implementation
    quietly stop agreeing, which is the one failure this project cannot afford
    to have on stage.
    """
    kwargs.setdefault("default", getattr(DEFAULT_PARAMS, name))
    kwargs["help_text"] = FIELD_SOURCES[name]
    return field_cls(**kwargs)


class RiskPolicy(models.Model):
    """A versioned, published set of risk parameters.

    Immutable in spirit: a policy change is a new version, not an edit. Phase 12
    adds a Recalibrate action that reads the simulator and writes v2.
    """

    version = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120, default="MochaTrade published risk policy")
    is_active = models.BooleanField(
        default=False,
        help_text="Exactly one policy is active. The engine reads this one.",
    )
    created_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    # -- Pricing -----------------------------------------------------------
    outlier_clamp_pct = _param(models.FloatField, "outlier_clamp_pct")
    majors_outlier_clamp_pct = _param(models.FloatField, "majors_outlier_clamp_pct")
    staleness_seconds = _param(models.PositiveIntegerField, "staleness_seconds")
    basis_ma_seconds = _param(models.PositiveIntegerField, "basis_ma_seconds")
    funding_period_seconds = _param(models.PositiveIntegerField, "funding_period_seconds")
    composite_l1_min_sources = _param(models.PositiveSmallIntegerField, "composite_l1_min_sources")
    composite_l2_min_sources = _param(models.PositiveSmallIntegerField, "composite_l2_min_sources")
    composite_l3_min_sources = _param(models.PositiveSmallIntegerField, "composite_l3_min_sources")
    mark_max_deviation_bps = _param(models.FloatField, "mark_max_deviation_bps")

    # -- Circuit ladder ----------------------------------------------------
    velocity_window_seconds = _param(models.PositiveIntegerField, "velocity_window_seconds")
    velocity_trigger_frac_of_dcb = _param(models.FloatField, "velocity_trigger_frac_of_dcb")
    price_band_frac_of_dcb = _param(models.FloatField, "price_band_frac_of_dcb")
    dcb_offhours_multiplier = _param(models.FloatField, "dcb_offhours_multiplier")
    dcb_lookback_seconds = _param(models.PositiveIntegerField, "dcb_lookback_seconds")
    dcb_pause_seconds = _param(models.PositiveIntegerField, "dcb_pause_seconds")

    # -- Liquidation -------------------------------------------------------
    twap_slice_ms = _param(models.PositiveIntegerField, "twap_slice_ms")
    twap_max_participation_pct = _param(models.FloatField, "twap_max_participation_pct")
    twap_participation_band_pct = _param(models.FloatField, "twap_participation_band_pct")
    backstop_threshold_frac = _param(models.FloatField, "backstop_threshold_frac")
    partial_liq_target_mm_multiple = _param(models.FloatField, "partial_liq_target_mm_multiple")
    clearance_fee_pct = _param(models.FloatField, "clearance_fee_pct")
    margin_grace_seconds = _param(models.PositiveIntegerField, "margin_grace_seconds")
    upi_prefunded_credit_cap_inr = _param(models.FloatField, "upi_prefunded_credit_cap_inr")

    # -- Leverage ----------------------------------------------------------
    max_leverage_rth = _param(models.FloatField, "max_leverage_rth")
    max_leverage_offhours = _param(models.FloatField, "max_leverage_offhours")
    max_leverage_degraded = _param(models.FloatField, "max_leverage_degraded")

    # -- Remediation -------------------------------------------------------
    ape_reversion_frac = _param(models.FloatField, "ape_reversion_frac")
    ape_reversion_seconds = _param(models.PositiveIntegerField, "ape_reversion_seconds")
    incident_reserve_opening_inr = _param(models.FloatField, "incident_reserve_opening_inr")
    per_incident_cap_inr = _param(models.FloatField, "per_incident_cap_inr")
    provisional_credit_minutes = _param(models.PositiveIntegerField, "provisional_credit_minutes")
    reserve_funding_share_of_fees = _param(models.FloatField, "reserve_funding_share_of_fees")
    reserve_target_multiple_of_worst_loss = _param(
        models.FloatField, "reserve_target_multiple_of_worst_loss"
    )

    class Meta:
        ordering = ("-created_at", "-version")
        verbose_name = "risk policy"
        verbose_name_plural = "risk policies"

    def __str__(self) -> str:
        suffix = " (active)" if self.is_active else ""
        return f"RiskPolicy {self.version}{suffix}"

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)  # type: ignore[arg-type]
        if self.is_active:
            RiskPolicy.objects.exclude(pk=self.pk).filter(is_active=True).update(
                is_active=False
            )

    # -- the one route into the engine -------------------------------------

    def to_params(self) -> RiskParams:
        """Return the frozen dataclass the engine consumes.

        Ladders are ordered by their `ordering` column so the engine walks tiers
        smallest-notional-first, which is what `tier_for_notional` assumes.
        """
        scalars = {name: getattr(self, name) for name in SCALAR_PARAM_NAMES}
        return RiskParams(
            version=self.version,
            margin_tiers=tuple(
                row.to_dataclass() for row in self.margin_tier_rows.order_by("ordering")
            ),
            instrument_tiers=tuple(
                row.to_dataclass() for row in self.instrument_tier_rows.order_by("tier")
            ),
            **scalars,
        )

    # -- convenience readouts ----------------------------------------------
    # The NRR and DCB ladders live in related rows because they are ladders.
    # These read-only accessors keep the published per-tier figures addressable
    # by name, which is how the policy page and the T&Cs refer to them.

    def _tier(self, tier: int) -> "PolicyInstrumentTier | None":
        return self.instrument_tier_rows.filter(tier=tier).first()

    @property
    def nrr_tier1_pct(self) -> float | None:
        row = self._tier(1)
        return row.nrr_pct if row else None

    @property
    def nrr_tier2_pct(self) -> float | None:
        row = self._tier(2)
        return row.nrr_pct if row else None

    @property
    def nrr_tier3_pct(self) -> float | None:
        row = self._tier(3)
        return row.nrr_pct if row else None

    @property
    def nrr_offhours_multiplier(self) -> float:
        """The DCB widening factor. Note the NRR table is stored literally and
        NOT derived from this: its published off-hours values (5/8/15 against
        3/5/10) imply 1.67, 1.60 and 1.50, so a single multiplier would quietly
        contradict the table in the T&Cs."""
        return self.dcb_offhours_multiplier

    @property
    def reversion_window_s(self) -> int:
        return self.ape_reversion_seconds

    @property
    def reversion_threshold_pct(self) -> float:
        return self.ape_reversion_frac * 100.0


class PolicyMarginTier(models.Model):
    """One rung of the maintenance-margin ladder. A related row, not JSON: it is
    the thing a judge is most likely to want to change live."""

    policy = models.ForeignKey(
        RiskPolicy, on_delete=models.CASCADE, related_name="margin_tier_rows"
    )
    ordering = models.PositiveSmallIntegerField(default=0)
    notional_floor = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))
    notional_ceiling = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Blank means the top tier, unbounded.",
    )
    max_leverage = models.FloatField()
    mm_pct = models.FloatField(help_text="Maintenance margin as a percent, e.g. 1.0 for 1%.")

    class Meta:
        ordering = ("policy", "ordering")
        verbose_name = "margin tier"
        unique_together = (("policy", "ordering"),)

    def __str__(self) -> str:
        ceiling = f"{self.notional_ceiling:,.0f}" if self.notional_ceiling else "unbounded"
        return f"<= Rs {ceiling}: {self.max_leverage:g}x, MM {self.mm_pct:g}%"

    def clean(self) -> None:
        if self.notional_ceiling is not None and self.notional_ceiling <= self.notional_floor:
            raise ValidationError("notional_ceiling must be above notional_floor.")
        if not 0.0 < self.mm_pct < 100.0:
            raise ValidationError("mm_pct is a percent between 0 and 100.")

    def to_dataclass(self) -> EngineMarginTier:
        return EngineMarginTier(
            max_notional=float(self.notional_ceiling) if self.notional_ceiling else None,
            max_leverage=self.max_leverage,
            mm_rate=self._mm_rate(),
        )

    def _mm_rate(self) -> float:
        """Percent to fraction, via Decimal.

        The obvious `self.mm_pct / 100.0` does not round-trip: 16.7 / 100.0 is
        0.16699999999999998, so a policy seeded from the engine's own defaults
        fails to reconstruct them and every seeded run shifts. Dividing through
        Decimal on the float's repr is exact for any value a human would type
        into this field.
        """
        return float(Decimal(repr(self.mm_pct)) / Decimal(100))


class PolicyInstrumentTier(models.Model):
    """Per-instrument-tier Non-Reviewable Range and circuit-breaker variant.

    The NRR is the published definition of "abnormal", set ex ante. Storing the
    off-hours column literally rather than deriving it keeps the model honest
    against the table in the T&Cs.
    """

    policy = models.ForeignKey(
        RiskPolicy, on_delete=models.CASCADE, related_name="instrument_tier_rows"
    )
    tier = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=160)
    nrr_pct = models.FloatField(help_text="Non-Reviewable Range during RTH, percent.")
    nrr_offhours_pct = models.FloatField(help_text="Non-Reviewable Range off-hours, percent.")
    dcb_variant_pct = models.FloatField(help_text="Dynamic circuit breaker variant, percent.")

    class Meta:
        ordering = ("policy", "tier")
        verbose_name = "instrument tier"
        unique_together = (("policy", "tier"),)

    def __str__(self) -> str:
        return f"Tier {self.tier}: NRR {self.nrr_pct:g}%/{self.nrr_offhours_pct:g}%"

    def clean(self) -> None:
        if self.nrr_offhours_pct < self.nrr_pct:
            raise ValidationError("Off-hours NRR cannot be tighter than the RTH NRR.")

    def to_dataclass(self) -> EngineInstrumentTier:
        return EngineInstrumentTier(
            tier=self.tier,
            label=self.label,
            nrr_pct=self.nrr_pct,
            nrr_offhours_pct=self.nrr_offhours_pct,
            dcb_variant_pct=self.dcb_variant_pct,
        )


# --------------------------------------------------------------------------
# Choice vocabularies
# --------------------------------------------------------------------------

class Layer(models.TextChoices):
    """The three-layer triage. Minute one is deciding which of these broke."""

    VENUE = "VENUE", "L3 Venue — Hyperliquid (no control)"
    MARKET = "MARKET", "L2 Market — our HIP-3 dex (full control, full liability)"
    BROKER = "BROKER", "L1 Broker — our app, API, UPI rails (full control)"


class AssetClass(models.TextChoices):
    EQUITY = "EQUITY", "US equity perp"
    CRYPTO = "CRYPTO", "Crypto perp"
    COMMODITY = "COMMODITY", "Commodity perp"
    INDEX = "INDEX", "Index perp"
    PREIPO = "PREIPO", "Pre-IPO perp"


class OracleFault(models.TextChoices):
    NONE = "NONE", "None"
    SINGLE_SOURCE_DEPEG = "SINGLE_SOURCE_DEPEG", "One source depegs (clamped)"
    STALE = "STALE", "Source stops updating"
    DIVERGENT = "DIVERGENT", "Correlated sources diverge (median poisoned)"


class BrokerFault(models.TextChoices):
    NONE = "NONE", "None"
    API_DOWN = "API_DOWN", "Order API returning 5xx"
    APP_FROZEN = "APP_FROZEN", "App frozen — cannot top up or close"
    UPI_DELAY = "UPI_DELAY", "UPI deposit settles late"


class RunStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    DONE = "DONE", "Done"


class Side(models.TextChoices):
    LONG = "LONG", "Long"
    SHORT = "SHORT", "Short"


class Classification(models.TextChoices):
    """The remedy matrix. Root cause decides who pays."""

    UNCLASSIFIED = "UNCLASSIFIED", "Unclassified"
    A = "A", "A — genuine move, healthy oracle: no remedy, publish the tape"
    B = "B", "B — thin book, mark tracked: fee rebate + a dated fix"
    C = "C", "C — our oracle defect: full make-whole at Reference Composite"
    D = "D", "D — our outage blocked top-up or close: make-whole in window"
    E = "E", "E — UPI/PSP delayed a funded deposit: make-whole"
    F = "F", "F — venue defect or ADL: no cash liability, goodwill at a cap"
    G = "G", "G — identifiable manipulation: reserve, report, pursue"


class Severity(models.TextChoices):
    SEV1 = "SEV1", "SEV-1"
    SEV2 = "SEV2", "SEV-2"
    SEV3 = "SEV3", "SEV-3"


class IncidentStatus(models.TextChoices):
    DECLARED = "DECLARED", "Declared"
    CONTAINED = "CONTAINED", "Contained"
    DIAGNOSED = "DIAGNOSED", "Diagnosed"
    REMEDIATING = "REMEDIATING", "Remediating"
    RESOLVED = "RESOLVED", "Resolved"


class ActionType(models.TextChoices):
    """Everything the war room can do, in playbook order."""

    DECLARE = "DECLARE", "T+0 Declare — SEV-1, I am IC"
    REDUCE_ONLY = "REDUCE_ONLY", "T+2 Reduce-only"
    PAUSE_LIQUIDATIONS = "PAUSE_LIQUIDATIONS", "T+2 Pause liquidations (oracle suspect)"
    LIQ_THROTTLE = "LIQ_THROTTLE", "T+2 Liquidation TWAP throttle"
    LEVERAGE_CAP = "LEVERAGE_CAP", "T+2 Cut max leverage"
    WIDEN_BANDS = "WIDEN_BANDS", "T+2 Widen price bands"
    HALT_MARKET = "HALT_MARKET", "haltTrading — settles everyone at mark"
    SNAPSHOT_EVIDENCE = "SNAPSHOT_EVIDENCE", "T+3 Preserve evidence"
    PUBLISH_UPDATE = "PUBLISH_UPDATE", "T+5 Publish update"
    CLASSIFY = "CLASSIFY", "T+15 Classify A–G"
    OPEN_CLAIMS = "OPEN_CLAIMS", "T+30 Open claims portal"
    PROVISIONAL_CREDIT = "PROVISIONAL_CREDIT", "T+30 Push provisional credit"
    STAGED_REOPEN = "STAGED_REOPEN", "T+45 Staged reopen through auction"
    RESOLVE = "RESOLVE", "T+60 Handover"


class PriceSource(models.TextChoices):
    MOCHATRADE = "MOCHATRADE", "MochaTrade mark"
    BINANCE = "BINANCE", "Binance spot"
    OKX = "OKX", "OKX spot"
    COINBASE = "COINBASE", "Coinbase spot"
    US_CASH = "US_CASH", "US cash market"
    ES_FUT = "ES_FUT", "ES future"
    COMPOSITE = "COMPOSITE", "Reference Composite"


class ClaimStatus(models.TextChoices):
    AUTO_APPROVED = "AUTO_APPROVED", "Auto-approved"
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    PAID = "PAID", "Paid"


class Channel(models.TextChoices):
    STATUS_PAGE = "STATUS_PAGE", "Status page"
    X = "X", "X"
    WHATSAPP = "WHATSAPP", "WhatsApp"
    TELEGRAM = "TELEGRAM", "Telegram"
    EMAIL = "EMAIL", "Email"


# --------------------------------------------------------------------------
# Instruments and scenarios
# --------------------------------------------------------------------------

class Instrument(models.Model):
    symbol = models.CharField(max_length=32, unique=True)
    display_name = models.CharField(max_length=120)
    layer = models.CharField(
        max_length=16,
        choices=Layer.choices,
        default=Layer.VENUE,
        help_text="Which layer this instrument's risk sits on.",
    )
    tier = models.PositiveSmallIntegerField(
        default=1, help_text="Risk tier 1-3. Sets the NRR and the DCB variant."
    )
    asset_class = models.CharField(max_length=16, choices=AssetClass.choices)
    has_rth = models.BooleanField(
        default=False,
        help_text=(
            "True when an underlying cash market closes. US cash equities trade "
            "19:00-01:30 IST, so an equity perp is off-hours for most of the "
            "Indian day and has no spot market to reference. Crypto trades 24/7 "
            "and never has RTH."
        ),
    )
    rth_open_ist = models.TimeField(null=True, blank=True)
    rth_close_ist = models.TimeField(null=True, blank=True)
    base_price = models.DecimalField(max_digits=20, decimal_places=6)
    tick_size = models.DecimalField(max_digits=20, decimal_places=6, default=Decimal("0.01"))
    max_leverage = models.FloatField(default=50.0)
    maintenance_margin_pct = models.FloatField(default=1.0)

    class Meta:
        ordering = ("symbol",)

    def __str__(self) -> str:
        return f"{self.symbol} ({self.get_asset_class_display()})"


class Scenario(models.Model):
    """A saved, runnable crash configuration."""

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    instrument = models.ForeignKey(
        Instrument, on_delete=models.PROTECT, related_name="scenarios"
    )
    seed = models.BigIntegerField(help_text="Same seed + same params + same actions = same run.")

    shock_pct = models.FloatField(help_text="Peak move of the underlying, signed percent.")
    shock_duration_s = models.PositiveIntegerField()
    total_duration_s = models.PositiveIntegerField()

    book_depth_inr = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Resting notional per side within 1% of mid, in calm markets.",
    )
    depth_collapse_pct = models.FloatField(
        default=94.0,
        help_text=(
            "How much resting depth vanishes at the shock. 10 Oct 2025: BTC "
            "top-of-book depth shrank by more than 90% as makers widened or "
            "stepped away."
        ),
    )

    n_accounts = models.PositiveIntegerField(default=1200)
    leverage_distribution = models.JSONField(
        default=dict,
        help_text='Bands and shares, e.g. {"3-5x": 0.40, "10-20x": 0.35, "25-50x": 0.20, "50x": 0.05}.',
    )
    long_share_pct = models.FloatField(
        default=80.0,
        help_text="10 Oct 2025: 87% of the $19.3B liquidated was longs.",
    )

    oracle_fault = models.CharField(
        max_length=24, choices=OracleFault.choices, default=OracleFault.NONE
    )
    broker_fault = models.CharField(
        max_length=16, choices=BrokerFault.choices, default=BrokerFault.NONE
    )
    broker_fault_window_s = models.PositiveIntegerField(default=0)
    is_offhours = models.BooleanField(default=False)

    assumed_scale_note = models.TextField(
        blank=True,
        help_text=(
            "The platform scale this scenario models, stated on the simulator. "
            "The assumption gets labelled, not hidden: damage figures scale with "
            "it, the control deltas do not."
        ),
    )
    engine_key = models.CharField(
        max_length=64,
        blank=True,
        help_text="Key of the matching scenario in riskengine.scenario.library().",
    )

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------

class SimRun(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="runs")
    policy = models.ForeignKey(RiskPolicy, on_delete=models.PROTECT, related_name="runs")
    controls_enabled = models.BooleanField(
        default=True, help_text="The off-vs-on proof: identical shock, stack off or on."
    )
    seed = models.BigIntegerField()
    policy_fingerprint = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        help_text=(
            "Hash of the parameter values this run actually executed against. "
            "Part of the cache key, because editing a margin tier does not bump "
            "RiskPolicy.version -- keying on the version alone would serve a "
            "stale run after a policy edit and quietly contradict the admin."
        ),
    )
    created_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=12, choices=RunStatus.choices, default=RunStatus.PENDING)
    current_tick = models.PositiveIntegerField(default=0)
    total_ticks = models.PositiveIntegerField(default=0)
    result_summary = models.JSONField(default=dict, blank=True)
    tick_data = models.JSONField(
        default=list, blank=True, help_text="The full frame series. One entry per tick."
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "simulation run"
        indexes = [
            models.Index(
                fields=["scenario", "controls_enabled", "seed", "policy_fingerprint"],
                name="core_simrun_cachekey_idx",
            )
        ]

    def __str__(self) -> str:
        stack = "controls ON" if self.controls_enabled else "controls OFF"
        return f"Run #{self.pk} — {self.scenario.slug} ({stack}, seed {self.seed})"

    @property
    def progress_pct(self) -> float:
        if not self.total_ticks:
            return 0.0
        return round(100.0 * self.current_tick / self.total_ticks, 1)


class SimAccount(models.Model):
    """A synthetic trader inside a run. The unit a claim is decided about."""

    run = models.ForeignKey(SimRun, on_delete=models.CASCADE, related_name="accounts")
    handle = models.CharField(max_length=32)
    side = models.CharField(max_length=8, choices=Side.choices)
    notional_inr = models.DecimalField(max_digits=20, decimal_places=2)
    leverage = models.FloatField()
    entry_price = models.DecimalField(max_digits=20, decimal_places=6)
    collateral_inr = models.DecimalField(max_digits=20, decimal_places=2)

    liquidated_at_tick = models.PositiveIntegerField(null=True, blank=True)
    liquidation_price = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    realised_pnl_inr = models.DecimalField(
        max_digits=20, decimal_places=2, default=Decimal("0")
    )
    was_adl = models.BooleanField(
        default=False,
        help_text="Force-closed as a WINNING counterparty at the bankruptcy price.",
    )
    counterfactual_equity_inr = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Equity had this account been processed at the Reference Composite.",
    )

    class Meta:
        ordering = ("run", "handle")
        unique_together = (("run", "handle"),)
        verbose_name = "sim account"

    def __str__(self) -> str:
        return f"{self.handle} ({self.side} {self.leverage:g}x)"

    @property
    def was_liquidated(self) -> bool:
        return self.liquidated_at_tick is not None


class PriceObservation(models.Model):
    """The evidence tape. Per tick, per source, with the reason anything was
    excluded -- so a user can replay it and check our story rather than take it
    on trust."""

    run = models.ForeignKey(SimRun, on_delete=models.CASCADE, related_name="observations")
    tick = models.PositiveIntegerField()
    source = models.CharField(max_length=16, choices=PriceSource.choices)
    price = models.DecimalField(max_digits=20, decimal_places=6)
    is_stale = models.BooleanField(default=False)
    weight = models.FloatField(default=1.0)
    excluded_reason = models.CharField(
        max_length=160,
        blank=True,
        help_text="Why this source did not feed the composite: stale, down, clamped.",
    )

    class Meta:
        ordering = ("run", "tick", "source")
        indexes = [models.Index(fields=["run", "tick"])]
        verbose_name = "price observation"

    def __str__(self) -> str:
        return f"t+{self.tick} {self.source} {self.price}"


# --------------------------------------------------------------------------
# The incident record
# --------------------------------------------------------------------------

class Incident(models.Model):
    """The war-room record. Opens automatically at T+0 on the auto-pager."""

    code = models.CharField(max_length=24, unique=True, blank=True)
    run = models.ForeignKey(
        SimRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents"
    )
    severity = models.CharField(max_length=8, choices=Severity.choices, default=Severity.SEV1)
    declared_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Roles are pre-assigned in writing. At T+0 you assume them, you do not
    # discuss them. The IC owns decisions and the clock and does not touch a
    # keyboard.
    incident_commander = models.CharField(max_length=80, blank=True, verbose_name="IC")
    ops_lead = models.CharField(max_length=80, blank=True, verbose_name="OPS")
    comms_lead = models.CharField(max_length=80, blank=True, verbose_name="COMMS")

    classification = models.CharField(
        max_length=16, choices=Classification.choices, default=Classification.UNCLASSIFIED
    )
    root_cause_layer = models.CharField(
        max_length=16, choices=Layer.choices, blank=True,
        help_text="Which of the three layers actually broke.",
    )
    affected_accounts_count = models.PositiveIntegerField(default=0)
    aggregate_exposure_inr = models.DecimalField(
        max_digits=20, decimal_places=2, default=Decimal("0")
    )
    status = models.CharField(
        max_length=16, choices=IncidentStatus.choices, default=IncidentStatus.DECLARED
    )

    class Meta:
        ordering = ("-declared_at",)

    def __str__(self) -> str:
        return f"{self.code} — {self.get_status_display()} ({self.classification})"

    def save(self, *args: object, **kwargs: object) -> None:
        if not self.code:
            self.code = self._next_code()
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    @staticmethod
    def _next_code() -> str:
        """INC-YYYYMMDD-NN, sequential within the IST day."""
        today = timezone.localtime(timezone.now()).date()
        prefix = f"INC-{today:%Y%m%d}-"
        last = (
            Incident.objects.filter(code__startswith=prefix)
            .order_by("-code")
            .values_list("code", flat=True)
            .first()
        )
        nxt = int(last.rsplit("-", 1)[1]) + 1 if last else 1
        return f"{prefix}{nxt:02d}"

    @property
    def owes_cash_remedy(self) -> bool:
        """C, D and E are ours. A and B owe nothing, F is the venue's, G is the
        attacker's and comes out of the Incident Reserve."""
        return self.classification in {Classification.C, Classification.D, Classification.E}

    @property
    def minutes_open(self) -> float:
        end = self.resolved_at or timezone.now()
        return round((end - self.declared_at).total_seconds() / 60.0, 1)


class IncidentAction(models.Model):
    """The immutable audit log of every war-room decision.

    Append-only by design and enforced in the admin. What you did and when you
    did it is the record a regulator, a user and a judge all read afterwards --
    a log that can be edited after the fact is not a log. SEBI's glitch
    framework expects this retained for two years.
    """

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="actions")
    tick = models.PositiveIntegerField(default=0, help_text="Simulation tick, i.e. T+N seconds.")
    wall_clock = models.DateTimeField(default=timezone.now)
    actor = models.CharField(max_length=80, help_text="IC, OPS, COMMS, or 'automation'.")
    action_type = models.CharField(max_length=24, choices=ActionType.choices)
    params = models.JSONField(default=dict, blank=True)
    rationale = models.TextField(
        help_text="Why, in the operator's own words. Written at the time, not afterwards."
    )
    reversible = models.BooleanField(
        default=True,
        help_text="False for anything that cannot be undone — haltTrading settles the book.",
    )

    class Meta:
        ordering = ("incident", "tick", "id")
        verbose_name = "incident action"

    def __str__(self) -> str:
        return f"T+{self.tick}s {self.actor}: {self.get_action_type_display()}"


class Claim(models.Model):
    """One account's compensation decision, against the published APE test."""

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="claims")
    account = models.ForeignKey(SimAccount, on_delete=models.CASCADE, related_name="claims")
    category = models.CharField(
        max_length=16, choices=Classification.choices, default=Classification.UNCLASSIFIED
    )
    status = models.CharField(
        max_length=16, choices=ClaimStatus.choices, default=ClaimStatus.PENDING
    )

    executed_price = models.DecimalField(max_digits=20, decimal_places=6)
    reference_composite_price = models.DecimalField(max_digits=20, decimal_places=6)
    deviation_pct = models.FloatField(
        help_text="APE criterion 1: deviation from the Reference Composite in the same 1s window."
    )

    counterfactual_equity_inr = models.DecimalField(max_digits=20, decimal_places=2)
    claimed_inr = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))
    approved_inr = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))
    provisional_credit_inr = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("0"),
        help_text=(
            "Pushed within 60 minutes for clear-cut C/D/E, as locked trading "
            "credit, converted to cash after a published reconciliation. Do not "
            "make a liquidated user file a ticket to get their own money back."
        ),
    )

    decided_by = models.CharField(max_length=80, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ("incident", "-claimed_inr")
        unique_together = (("incident", "account"),)

    def __str__(self) -> str:
        return f"Claim {self.account.handle} [{self.category}] {self.get_status_display()}"

    @property
    def shortfall_inr(self) -> Decimal:
        """Unpaid balance. Non-zero once the published per-incident cap binds and
        compensation goes pro-rata."""
        return max(Decimal("0"), self.claimed_inr - self.approved_inr)


class CommsUpdate(models.Model):
    """A published update. What you say during an incident creates more
    liability than the incident: Robinhood's $70M FINRA penalty was for
    misleading statements as much as for the downtime. Vague reassurance is the
    expensive option."""

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="updates")
    sequence = models.PositiveSmallIntegerField()
    published_at = models.DateTimeField(null=True, blank=True)
    channel = models.CharField(
        max_length=16, choices=Channel.choices, default=Channel.STATUS_PAGE
    )
    headline = models.CharField(max_length=200)
    body = models.TextField()
    next_update_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Always commit to a next time. 'We are investigating' with no clock is not an update.",
    )
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ("incident", "sequence", "channel")
        unique_together = (("incident", "sequence", "channel"),)
        verbose_name = "comms update"

    def __str__(self) -> str:
        state = "published" if self.is_published else "draft"
        return f"#{self.sequence} {self.get_channel_display()} ({state}): {self.headline}"
