"""DRF serializers.

Every serializer declares its fields explicitly. `fields = "__all__"` is banned
here, because the public status feed sits in this file next to the internal
incident payload and a wildcard is exactly how an internal field ends up on a
public page.

Money convention, which is deliberate and not uniform:

- Ledger figures a human reads or a report quotes -- losses, exposure, claim
  amounts -- serialise as DECIMAL STRINGS. JSON numbers are IEEE doubles and a
  compensation figure must not shift in its last place because it crossed
  JavaScript.
- Frame series values are chart samples, sampled 300 to a run. They stay
  numeric. Float drift of a pixel is not a problem worth a string parse per
  point.

`web/src/lib/types.ts` mirrors this file exactly. If a field changes shape here,
that file changes in the same commit.
"""
from __future__ import annotations

from rest_framework import serializers

from .models import (
    Claim,
    CommsUpdate,
    Incident,
    IncidentAction,
    Instrument,
    PolicyInstrumentTier,
    PolicyMarginTier,
    RiskPolicy,
    Scenario,
    SimRun,
)
from .runner import money


# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------

class MarginTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyMarginTier
        fields = ("ordering", "notional_floor", "notional_ceiling", "max_leverage", "mm_pct")


class InstrumentTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyInstrumentTier
        fields = ("tier", "label", "nrr_pct", "nrr_offhours_pct", "dcb_variant_pct")


class RiskPolicySerializer(serializers.ModelSerializer):
    margin_tiers = MarginTierSerializer(source="margin_tier_rows", many=True, read_only=True)
    instrument_tiers = InstrumentTierSerializer(
        source="instrument_tier_rows", many=True, read_only=True
    )
    incident_reserve_inr = serializers.SerializerMethodField()
    per_incident_cap_inr_display = serializers.SerializerMethodField()

    class Meta:
        model = RiskPolicy
        fields = (
            "id", "version", "name", "is_active", "created_at", "notes",
            "outlier_clamp_pct", "majors_outlier_clamp_pct", "staleness_seconds",
            "basis_ma_seconds", "funding_period_seconds", "mark_max_deviation_bps",
            "composite_l1_min_sources", "composite_l2_min_sources",
            "composite_l3_min_sources",
            "velocity_window_seconds", "velocity_trigger_frac_of_dcb",
            "price_band_frac_of_dcb", "dcb_offhours_multiplier",
            "dcb_lookback_seconds", "dcb_pause_seconds",
            "twap_slice_ms", "twap_max_participation_pct",
            "twap_participation_band_pct", "backstop_threshold_frac",
            "partial_liq_target_mm_multiple", "clearance_fee_pct",
            "margin_grace_seconds", "upi_prefunded_credit_cap_inr",
            "max_leverage_rth", "max_leverage_offhours", "max_leverage_degraded",
            "ape_reversion_frac", "ape_reversion_seconds",
            "provisional_credit_minutes", "reserve_funding_share_of_fees",
            "reserve_target_multiple_of_worst_loss",
            "incident_reserve_inr", "per_incident_cap_inr_display",
            "margin_tiers", "instrument_tiers",
        )

    def get_incident_reserve_inr(self, obj: RiskPolicy) -> str:
        return money(obj.incident_reserve_opening_inr)

    def get_per_incident_cap_inr_display(self, obj: RiskPolicy) -> str:
        return money(obj.per_incident_cap_inr)


# --------------------------------------------------------------------------
# Instruments and scenarios
# --------------------------------------------------------------------------

class InstrumentSerializer(serializers.ModelSerializer):
    asset_class_display = serializers.CharField(source="get_asset_class_display", read_only=True)
    layer_display = serializers.CharField(source="get_layer_display", read_only=True)

    class Meta:
        model = Instrument
        fields = (
            "symbol", "display_name", "layer", "layer_display", "tier",
            "asset_class", "asset_class_display", "has_rth", "rth_open_ist",
            "rth_close_ist", "base_price", "tick_size", "max_leverage",
            "maintenance_margin_pct",
        )


class ScenarioListSerializer(serializers.ModelSerializer):
    instrument_symbol = serializers.CharField(source="instrument.symbol", read_only=True)

    class Meta:
        model = Scenario
        fields = (
            "slug", "name", "description", "instrument_symbol", "seed",
            "shock_pct", "is_offhours", "oracle_fault", "broker_fault",
            "engine_key",
        )


class ScenarioDetailSerializer(ScenarioListSerializer):
    instrument = InstrumentSerializer(read_only=True)

    class Meta(ScenarioListSerializer.Meta):
        fields = ScenarioListSerializer.Meta.fields + (
            "instrument", "shock_duration_s", "total_duration_s", "book_depth_inr",
            "depth_collapse_pct", "n_accounts", "leverage_distribution",
            "long_share_pct", "broker_fault_window_s", "assumed_scale_note",
        )


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------

class TickSerializer(serializers.Serializer):
    """One frame. Numeric on purpose -- see the money note in the module docstring."""

    tick = serializers.IntegerField()
    t_seconds = serializers.FloatField()
    true_price = serializers.FloatField()
    composite = serializers.FloatField(allow_null=True)
    composite_rung = serializers.IntegerField()
    oracle_health = serializers.CharField()
    reference = serializers.FloatField(allow_null=True)
    book_mid = serializers.FloatField()
    spread_bps = serializers.FloatField()
    depth_pct_of_baseline = serializers.FloatField()
    mark = serializers.FloatField()
    mark_source = serializers.CharField()
    divergence_bps = serializers.FloatField()
    reduce_only = serializers.BooleanField()
    liquidations_paused = serializers.BooleanField()
    trading_paused = serializers.BooleanField()
    halted = serializers.BooleanField()
    max_leverage = serializers.FloatField()
    stage = serializers.CharField()
    liquidated_this_tick = serializers.IntegerField()
    cum_liquidated_accounts = serializers.IntegerField()
    cum_liquidated_notional = serializers.FloatField()
    adl_accounts = serializers.IntegerField()
    insurance_balance = serializers.FloatField()
    unnecessary_liquidations = serializers.IntegerField()
    accounts_open = serializers.IntegerField()
    aggregate_equity = serializers.FloatField()


class RunSummarySerializer(serializers.Serializer):
    """Headline figures. Money as strings."""

    scenario_key = serializers.CharField()
    seed = serializers.IntegerField()
    policy_version = serializers.CharField()
    ticks = serializers.IntegerField()
    accounts_total = serializers.IntegerField()
    accounts_liquidated = serializers.IntegerField()
    unnecessary_liquidations = serializers.IntegerField()
    adl_accounts = serializers.IntegerField()
    trough_mark_pct = serializers.FloatField()
    peak_mark_pct = serializers.FloatField()
    max_divergence_bps = serializers.FloatField()
    min_depth_pct_of_baseline = serializers.FloatField()
    saved_by_grace = serializers.IntegerField()
    upi_credits_issued = serializers.IntegerField()
    open_interest_inr = serializers.SerializerMethodField()
    liquidated_notional_inr = serializers.SerializerMethodField()
    unnecessary_notional_inr = serializers.SerializerMethodField()
    adl_notional_inr = serializers.SerializerMethodField()
    user_loss_inr = serializers.SerializerMethodField()
    attributable_loss_inr = serializers.SerializerMethodField()
    insurance_drawn_inr = serializers.SerializerMethodField()

    def get_open_interest_inr(self, obj: dict) -> str:
        return money(obj.get("open_interest_start"))

    def get_liquidated_notional_inr(self, obj: dict) -> str:
        return money(obj.get("liquidated_notional"))

    def get_unnecessary_notional_inr(self, obj: dict) -> str:
        return money(obj.get("unnecessary_notional"))

    def get_adl_notional_inr(self, obj: dict) -> str:
        return money(obj.get("adl_notional"))

    def get_user_loss_inr(self, obj: dict) -> str:
        return money(obj.get("user_loss"))

    def get_attributable_loss_inr(self, obj: dict) -> str:
        return money(obj.get("attributable_loss"))

    def get_insurance_drawn_inr(self, obj: dict) -> str:
        return money(obj.get("insurance_drawn"))


class RunSerializer(serializers.ModelSerializer):
    summary = serializers.SerializerMethodField()
    scenario_slug = serializers.CharField(source="scenario.slug", read_only=True)
    policy_version = serializers.CharField(source="policy.version", read_only=True)

    class Meta:
        model = SimRun
        fields = (
            "id", "scenario_slug", "policy_version", "controls_enabled", "seed",
            "status", "current_tick", "total_ticks", "created_at", "summary",
        )

    def get_summary(self, obj: SimRun) -> dict:
        return RunSummarySerializer(obj.result_summary or {}).data


class RunRequestSerializer(serializers.Serializer):
    scenario_slug = serializers.SlugField()
    controls_enabled = serializers.BooleanField(default=True)
    seed = serializers.IntegerField(required=False, allow_null=True)
    policy_id = serializers.IntegerField(required=False, allow_null=True)


class CompareRequestSerializer(serializers.Serializer):
    scenario_slug = serializers.SlugField()
    seed = serializers.IntegerField(required=False, allow_null=True)


# --------------------------------------------------------------------------
# Incidents
# --------------------------------------------------------------------------

class IncidentActionSerializer(serializers.ModelSerializer):
    action_type_display = serializers.CharField(source="get_action_type_display", read_only=True)

    class Meta:
        model = IncidentAction
        fields = (
            "id", "tick", "wall_clock", "actor", "action_type",
            "action_type_display", "params", "rationale", "reversible",
        )


class IncidentSerializer(serializers.ModelSerializer):
    scenario_slug = serializers.CharField(source="run.scenario.slug", read_only=True, default=None)
    classification_display = serializers.CharField(
        source="get_classification_display", read_only=True
    )
    owes_cash_remedy = serializers.BooleanField(read_only=True)
    minutes_open = serializers.FloatField(read_only=True)
    aggregate_exposure_inr_display = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = (
            "code", "scenario_slug", "severity", "status", "declared_at",
            "resolved_at", "minutes_open", "incident_commander", "ops_lead",
            "comms_lead", "classification", "classification_display",
            "root_cause_layer", "owes_cash_remedy", "affected_accounts_count",
            "aggregate_exposure_inr_display",
        )

    def get_aggregate_exposure_inr_display(self, obj: Incident) -> str:
        return money(obj.aggregate_exposure_inr)


class DeclareIncidentSerializer(serializers.Serializer):
    scenario_slug = serializers.SlugField()
    controls_enabled = serializers.BooleanField(default=True)
    seed = serializers.IntegerField(required=False, allow_null=True)
    severity = serializers.CharField(required=False, default="SEV1")
    incident_commander = serializers.CharField(required=False, allow_blank=True, default="")
    ops_lead = serializers.CharField(required=False, allow_blank=True, default="")
    comms_lead = serializers.CharField(required=False, allow_blank=True, default="")


class StepRequestSerializer(serializers.Serializer):
    ticks = serializers.IntegerField(min_value=1, max_value=600, default=30)


class ActionRequestSerializer(serializers.Serializer):
    action_type = serializers.CharField()
    params = serializers.DictField(required=False, default=dict)
    rationale = serializers.CharField(allow_blank=True, default="")
    actor = serializers.CharField(required=False, default="IC")


class IncidentStateSerializer(serializers.Serializer):
    """Current war-room state: where the clock is and what is switched on."""

    incident = IncidentSerializer()
    elapsed_seconds = serializers.FloatField()
    current_tick = serializers.IntegerField()
    total_ticks = serializers.IntegerField()
    finished = serializers.BooleanField()
    snapshot = TickSerializer(allow_null=True)
    active_controls = serializers.DictField()
    flags = serializers.DictField()


class PriceObservationSerializer(serializers.Serializer):
    """The evidence tape, one row per source per tick."""

    tick = serializers.IntegerField()
    source = serializers.CharField()
    price = serializers.FloatField(allow_null=True)
    is_stale = serializers.BooleanField()
    weight = serializers.FloatField()
    excluded_reason = serializers.CharField(allow_blank=True)


class ClaimSerializer(serializers.ModelSerializer):
    account_handle = serializers.CharField(source="account.handle", read_only=True)
    claimed_inr_display = serializers.SerializerMethodField()
    approved_inr_display = serializers.SerializerMethodField()
    shortfall_inr_display = serializers.SerializerMethodField()

    class Meta:
        model = Claim
        fields = (
            "id", "account_handle", "category", "status", "executed_price",
            "reference_composite_price", "deviation_pct",
            "counterfactual_equity_inr", "claimed_inr_display",
            "approved_inr_display", "provisional_credit_inr",
            "shortfall_inr_display", "decided_by", "decided_at", "reason",
        )

    def get_claimed_inr_display(self, obj: Claim) -> str:
        return money(obj.claimed_inr)

    def get_approved_inr_display(self, obj: Claim) -> str:
        return money(obj.approved_inr)

    def get_shortfall_inr_display(self, obj: Claim) -> str:
        return money(obj.shortfall_inr)


class ClaimDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["APPROVED", "REJECTED", "PAID"])
    approved_inr = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False, allow_null=True
    )
    reason = serializers.CharField(allow_blank=True, default="")
    decided_by = serializers.CharField(required=False, default="IC")


class CommsUpdateSerializer(serializers.ModelSerializer):
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)

    class Meta:
        model = CommsUpdate
        fields = (
            "id", "sequence", "channel", "channel_display", "headline", "body",
            "published_at", "next_update_at", "is_published",
        )


class CommsCreateSerializer(serializers.Serializer):
    """Input for a new update. The server assigns the sequence when it is left
    out, so COMMS never has to count updates while an incident is running."""

    channel = serializers.ChoiceField(
        choices=["STATUS_PAGE", "X", "WHATSAPP", "TELEGRAM", "EMAIL"], default="STATUS_PAGE"
    )
    headline = serializers.CharField(max_length=200)
    body = serializers.CharField()
    sequence = serializers.IntegerField(required=False, min_value=1)
    next_update_at = serializers.DateTimeField(required=False, allow_null=True)
    is_published = serializers.BooleanField(default=True)


class PublicStatusUpdateSerializer(serializers.ModelSerializer):
    """The public status page feed.

    A separate, minimal serializer on purpose. It exposes what a user needs to
    read and nothing about our internal state: no classification, no exposure,
    no root-cause layer, no draft updates, no incident internals. What you say
    during an incident creates more liability than the incident -- Robinhood's
    $70M FINRA penalty was for misleading statements as much as for downtime --
    so this payload is narrow by construction rather than by filtering.
    """

    incident_code = serializers.CharField(source="incident.code", read_only=True)
    severity = serializers.CharField(source="incident.severity", read_only=True)
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)

    class Meta:
        model = CommsUpdate
        fields = (
            "incident_code", "severity", "sequence", "channel", "channel_display",
            "headline", "body", "published_at", "next_update_at",
        )
