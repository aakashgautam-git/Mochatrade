"""Django admin for MochaTrade Crisis Command.

This surface gets demoed, so it is built to be read rather than merely to work.
Two things it has to communicate on sight:

- **Every risk parameter shows where it came from.** `help_text` is generated
  from `riskengine.params.FIELD_SOURCES`, so the citation next to a number in
  the admin is the same string the policy page and the T&Cs render.
- **The action log cannot be edited.** `IncidentAction` refuses add, change and
  delete. A log you can rewrite after the fact is not a log, and the whole
  "trades stand, people get made whole" position depends on the record being
  trustworthy.
"""
from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from riskengine.indian import inr_text

from .models import (
    Claim,
    ClaimStatus,
    CommsUpdate,
    DepthSnapshot,
    LiquidationRecord,
    Incident,
    IncidentAction,
    Instrument,
    PolicyInstrumentTier,
    PolicyMarginTier,
    PriceObservation,
    RiskPolicy,
    Scenario,
    SimAccount,
    SimRun,
)

admin.site.site_header = "MochaTrade Crisis Command"
admin.site.site_title = "MochaTrade Crisis Command"
admin.site.index_title = "Trades stand. People get made whole."


def _chip(label: str, colour: str) -> str:
    """A small coloured status pill. Colour is never the only signal -- the
    label carries the meaning on its own."""
    return format_html(
        '<span style="display:inline-block;padding:2px 8px;border-radius:6px;'
        'font-size:11px;font-weight:600;background:{}1f;color:{};'
        'border:1px solid {}3d;">{}</span>',
        colour, colour, colour, label,
    )


def _rupees(amount) -> str:
    """Indian-scale money reads in lakh and crore, not in millions."""
    return inr_text(float(amount or 0))


# --------------------------------------------------------------------------
# Risk policy
# --------------------------------------------------------------------------

class PolicyMarginTierInline(admin.TabularInline):
    model = PolicyMarginTier
    extra = 0
    ordering = ("ordering",)
    fields = ("ordering", "notional_floor", "notional_ceiling", "max_leverage", "mm_pct")


class PolicyInstrumentTierInline(admin.TabularInline):
    model = PolicyInstrumentTier
    extra = 0
    ordering = ("tier",)
    fields = ("tier", "label", "nrr_pct", "nrr_offhours_pct", "dcb_variant_pct")


@admin.register(RiskPolicy)
class RiskPolicyAdmin(admin.ModelAdmin):
    list_display = ("version", "name", "active_chip", "reserve", "cap", "created_at")
    list_filter = ("is_active",)
    search_fields = ("version", "name", "notes")
    inlines = (PolicyMarginTierInline, PolicyInstrumentTierInline)
    readonly_fields = ("created_at", "provenance")

    fieldsets = (
        ("Policy", {
            "fields": ("version", "name", "is_active", "created_at", "notes", "provenance"),
            "description": (
                "A policy change is a new version, not an edit. The active policy "
                "is the only configuration the engine ever reads."
            ),
        }),
        ("Pricing", {
            "fields": (
                "outlier_clamp_pct", "majors_outlier_clamp_pct", "staleness_seconds",
                "basis_ma_seconds", "funding_period_seconds",
                "composite_l1_min_sources", "composite_l2_min_sources",
                "composite_l3_min_sources", "mark_max_deviation_bps",
            ),
            "description": (
                "Never liquidate on last-traded price. Mark = median(Price1, "
                "Price2, Contract Price) over a weight-normalised index, with an "
                "outlier clamp and a staleness kill."
            ),
        }),
        ("Circuit ladder", {
            "fields": (
                "velocity_window_seconds", "velocity_trigger_frac_of_dcb",
                "velocity_cooldown_seconds", "velocity_escalation_multiplier",
                "price_band_frac_of_dcb", "dcb_offhours_multiplier",
                "dcb_lookback_seconds", "dcb_pause_seconds",
            ),
            "description": (
                "Four layers, designed to be used together because no single "
                "control can do the job: pre-trade price bands, velocity logic, "
                "dynamic circuit breakers, daily limits. Per-tier DCB variants "
                "are in the instrument tier table below."
            ),
        }),
        ("Liquidation", {
            "fields": (
                "twap_slice_ms", "twap_max_participation_pct",
                "twap_participation_band_pct", "backstop_threshold_frac",
                "partial_liq_target_mm_multiple", "clearance_fee_pct",
                "margin_grace_seconds", "upi_prefunded_credit_cap_inr",
            ),
            "description": (
                "An unthrottled liquidation engine is a self-inflicted crash. "
                "The maintenance-margin ladder is in the margin tier table below."
            ),
        }),
        ("Leverage", {
            "fields": ("max_leverage_rth", "max_leverage_offhours", "max_leverage_degraded"),
            "description": (
                "Time-of-day caps apply to equity perps, which have an RTH to be "
                "outside of. Crypto trades 24/7 and is unaffected."
            ),
        }),
        ("Remediation", {
            "fields": (
                "ape_reversion_frac", "ape_reversion_seconds",
                "incident_reserve_opening_inr", "per_incident_cap_inr",
                "provisional_credit_minutes", "reserve_funding_share_of_fees",
                "reserve_target_multiple_of_worst_loss",
            ),
            "description": (
                "Trades stand, people get made whole. The per-incident cap is "
                "published in advance and is deliberately finite: an honest "
                "finite promise beats an implied infinite one you will break."
            ),
        }),
    )

    @admin.display(description="Active")
    def active_chip(self, obj: RiskPolicy) -> str:
        return _chip("ACTIVE", "#5FA37A") if obj.is_active else _chip("superseded", "#6B625B")

    @admin.display(description="Incident reserve")
    def reserve(self, obj: RiskPolicy) -> str:
        return _rupees(obj.incident_reserve_opening_inr)

    @admin.display(description="Per-incident cap")
    def cap(self, obj: RiskPolicy) -> str:
        return _rupees(obj.per_incident_cap_inr)

    @admin.display(description="Provenance")
    def provenance(self, obj: RiskPolicy) -> str:
        # Static literal, no interpolation: mark_safe rather than format_html.
        return mark_safe(
            '<div style="max-width:60em;line-height:1.5">'
            "Every field's help text is generated from "
            "<code>riskengine.params.FIELD_SOURCES</code>, so a number and its "
            "citation live in exactly one place. The parameters are our "
            "proposal; the mechanisms are Binance's, CME's and Hyperliquid's "
            "published specs. Three values are marked DERIVED because the brief "
            "specifies the mechanism but publishes no number."
            "</div>"
        )


# --------------------------------------------------------------------------
# Instruments, scenarios, runs
# --------------------------------------------------------------------------

@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = ("symbol", "display_name", "asset_class", "tier", "layer",
                    "has_rth", "max_leverage")
    list_filter = ("asset_class", "tier", "layer", "has_rth")
    search_fields = ("symbol", "display_name")


@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    list_display = ("name", "instrument", "shock_pct", "n_accounts",
                    "oracle_fault", "broker_fault", "is_offhours")
    list_filter = ("is_offhours", "oracle_fault", "broker_fault", "instrument")
    search_fields = ("name", "slug", "description", "engine_key")
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("instrument",)
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "instrument", "engine_key", "seed")}),
        ("Shock", {"fields": ("shock_pct", "shock_duration_s", "total_duration_s", "is_offhours")}),
        ("Book", {"fields": ("book_depth_inr", "depth_collapse_pct")}),
        ("Population", {"fields": ("n_accounts", "leverage_distribution",
                                   "long_share_pct", "assumed_scale_note")}),
        ("Injected faults", {"fields": ("oracle_fault", "broker_fault", "broker_fault_window_s")}),
    )


class SimAccountInline(admin.TabularInline):
    model = SimAccount
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("handle", "side", "leverage", "notional_inr", "liquidated_at_tick",
              "was_adl", "realised_pnl_inr")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


@admin.register(SimRun)
class SimRunAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status_chip", "controls_chip", "progress", "created_at")
    list_filter = ("status", "controls_enabled", "scenario")
    list_select_related = ("scenario", "policy")
    readonly_fields = ("created_at", "result_summary", "tick_data")
    inlines = (SimAccountInline,)

    @admin.display(description="Status")
    def status_chip(self, obj: SimRun) -> str:
        colours = {"PENDING": "#6B625B", "RUNNING": "#D9A441", "DONE": "#5FA37A"}
        return _chip(obj.get_status_display(), colours.get(obj.status, "#6B625B"))

    @admin.display(description="Controls")
    def controls_chip(self, obj: SimRun) -> str:
        return (
            _chip("STACK ON", "#5FA37A") if obj.controls_enabled
            else _chip("STACK OFF", "#D96A6A")
        )

    @admin.display(description="Progress")
    def progress(self, obj: SimRun) -> str:
        return f"{obj.current_tick}/{obj.total_ticks} ({obj.progress_pct}%)"


@admin.register(SimAccount)
class SimAccountAdmin(admin.ModelAdmin):
    list_display = ("handle", "run", "side", "leverage", "notional_inr",
                    "liquidated_at_tick", "was_adl")
    list_filter = ("side", "was_adl", "run__scenario")
    search_fields = ("handle",)
    list_select_related = ("run", "run__scenario")


@admin.register(PriceObservation)
class PriceObservationAdmin(admin.ModelAdmin):
    list_display = ("run", "tick", "source", "price", "is_stale", "weight", "excluded_reason")
    list_filter = ("source", "is_stale", "run")
    list_select_related = ("run",)


@admin.register(LiquidationRecord)
class LiquidationRecordAdmin(admin.ModelAdmin):
    list_display = ("run", "tick", "account", "stage", "price", "notional_inr", "via_auction", "closed")
    list_filter = ("stage", "via_auction", "closed", "survived_at_reference")
    search_fields = ("account",)
    list_select_related = ("run", "run__scenario")


@admin.register(DepthSnapshot)
class DepthSnapshotAdmin(admin.ModelAdmin):
    list_display = ("run", "tick", "mid", "depth_pct_of_baseline", "bucket_bps")
    list_select_related = ("run", "run__scenario")


# --------------------------------------------------------------------------
# The war room
# --------------------------------------------------------------------------

class IncidentActionInline(admin.TabularInline):
    """Read-only. The log is append-only and this is a viewport onto it."""

    model = IncidentAction
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("tick", "wall_clock", "actor", "action_type", "reversible", "rationale")
    readonly_fields = fields
    ordering = ("tick", "id")

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


class CommsUpdateInline(admin.StackedInline):
    model = CommsUpdate
    extra = 0
    ordering = ("sequence",)
    fields = ("sequence", "channel", "headline", "body", "next_update_at",
              "is_published", "published_at")


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("code", "status_chip", "classification_chip", "root_cause_layer",
                    "affected_accounts_count", "exposure", "declared_at")
    list_filter = ("status", "classification", "severity", "root_cause_layer")
    search_fields = ("code", "incident_commander", "ops_lead", "comms_lead")
    list_select_related = ("run", "run__scenario")
    inlines = (IncidentActionInline, CommsUpdateInline)
    readonly_fields = ("code", "timeline", "minutes_open")

    fieldsets = (
        ("Incident", {"fields": ("code", "run", "severity", "status",
                                 "declared_at", "resolved_at", "minutes_open")}),
        ("Roles", {
            "fields": ("incident_commander", "ops_lead", "comms_lead"),
            "description": (
                "Pre-assigned in writing. At T+0 you assume them, you do not "
                "discuss them. The IC owns decisions and the clock, and does not "
                "touch a keyboard."
            ),
        }),
        ("Classification", {
            "fields": ("classification", "root_cause_layer",
                       "affected_accounts_count", "aggregate_exposure_inr"),
            "description": "Root cause decides who pays. C, D and E are ours.",
        }),
        ("Timeline", {"fields": ("timeline",)}),
    )

    @admin.display(description="Status")
    def status_chip(self, obj: Incident) -> str:
        colours = {
            "DECLARED": "#D96A6A", "CONTAINED": "#D9A441", "DIAGNOSED": "#C98A5E",
            "REMEDIATING": "#C98A5E", "RESOLVED": "#5FA37A",
        }
        return _chip(obj.get_status_display(), colours.get(obj.status, "#6B625B"))

    @admin.display(description="Class")
    def classification_chip(self, obj: Incident) -> str:
        if obj.classification == "UNCLASSIFIED":
            return _chip("unclassified", "#6B625B")
        colour = "#D96A6A" if obj.owes_cash_remedy else "#5FA37A"
        suffix = "we pay" if obj.owes_cash_remedy else "no cash liability"
        return _chip(f"{obj.classification} — {suffix}", colour)

    @admin.display(description="Exposure")
    def exposure(self, obj: Incident) -> str:
        return _rupees(obj.aggregate_exposure_inr)

    @admin.display(description="Action log")
    def timeline(self, obj: Incident) -> str:
        actions = obj.actions.order_by("tick", "id")
        if not actions:
            return format_html('<em style="color:#6B625B">No actions recorded yet.</em>')
        rows = format_html_join(
            "",
            '<tr style="border-bottom:1px solid #e5e0da">'
            '<td style="padding:6px 12px;font-family:ui-monospace,monospace;'
            'white-space:nowrap">T+{}s</td>'
            '<td style="padding:6px 12px;white-space:nowrap"><b>{}</b></td>'
            '<td style="padding:6px 12px">{}</td>'
            '<td style="padding:6px 12px;color:#5c534c">{}</td>'
            '<td style="padding:6px 12px">{}</td></tr>',
            (
                (a.tick, a.actor, a.get_action_type_display(), a.rationale,
                 "reversible" if a.reversible else "IRREVERSIBLE")
                for a in actions
            ),
        )
        return format_html(
            '<table style="border-collapse:collapse;width:100%;font-size:13px">'
            '<thead><tr style="text-align:left;border-bottom:2px solid #1C1917">'
            '<th style="padding:6px 12px">Clock</th><th style="padding:6px 12px">Actor</th>'
            '<th style="padding:6px 12px">Action</th><th style="padding:6px 12px">Rationale</th>'
            '<th style="padding:6px 12px">Undo</th></tr></thead><tbody>{}</tbody></table>',
            rows,
        )


@admin.register(IncidentAction)
class IncidentActionAdmin(admin.ModelAdmin):
    """Append-only audit log. Add, change and delete are all refused.

    Not a convention -- enforced. The record of what was decided and when is
    what a regulator, a user and a court all read afterwards, and a log that can
    be rewritten after the fact is worth nothing. SEBI's technical-glitch
    framework expects this retained for two years.
    """

    list_display = ("incident", "tick", "actor", "action_type", "reversible", "wall_clock")
    list_filter = ("action_type", "reversible", "actor")
    search_fields = ("rationale", "incident__code")
    list_select_related = ("incident",)
    readonly_fields = ("incident", "tick", "wall_clock", "actor", "action_type",
                       "params", "rationale", "reversible")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


# --------------------------------------------------------------------------
# Claims and comms
# --------------------------------------------------------------------------

@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("account_handle", "incident", "category", "status_chip",
                    "deviation", "claimed", "approved", "provisional")
    list_filter = ("category", "status", "incident")
    search_fields = ("account__handle", "incident__code", "reason")
    list_select_related = ("incident", "account")
    actions = ("approve_selected", "mark_paid")
    readonly_fields = ("shortfall_display",)

    @admin.display(description="Account", ordering="account__handle")
    def account_handle(self, obj: Claim) -> str:
        return obj.account.handle

    @admin.display(description="Status")
    def status_chip(self, obj: Claim) -> str:
        colours = {
            ClaimStatus.AUTO_APPROVED: "#5FA37A",
            ClaimStatus.APPROVED: "#5FA37A",
            ClaimStatus.PAID: "#C98A5E",
            ClaimStatus.PENDING: "#D9A441",
            ClaimStatus.REJECTED: "#D96A6A",
        }
        return _chip(obj.get_status_display(), colours.get(obj.status, "#6B625B"))

    @admin.display(description="Deviation", ordering="deviation_pct")
    def deviation(self, obj: Claim) -> str:
        return f"{obj.deviation_pct:+.2f}%"

    @admin.display(description="Claimed", ordering="claimed_inr")
    def claimed(self, obj: Claim) -> str:
        return _rupees(obj.claimed_inr)

    @admin.display(description="Approved", ordering="approved_inr")
    def approved(self, obj: Claim) -> str:
        return _rupees(obj.approved_inr)

    @admin.display(description="Provisional")
    def provisional(self, obj: Claim) -> str:
        return _rupees(obj.provisional_credit_inr)

    @admin.display(description="Shortfall (pro-rata)")
    def shortfall_display(self, obj: Claim) -> str:
        return _rupees(obj.shortfall_inr)

    @admin.action(description="Approve selected claims")
    def approve_selected(self, request: HttpRequest, queryset: QuerySet[Claim]) -> None:
        updated = 0
        for claim in queryset:
            claim.status = ClaimStatus.APPROVED
            claim.approved_inr = claim.claimed_inr
            claim.decided_by = request.user.get_username()
            claim.decided_at = timezone.now()
            claim.save(update_fields=["status", "approved_inr", "decided_by", "decided_at"])
            updated += 1
        self.message_user(
            request,
            f"Approved {updated} claim(s). The per-incident cap is applied when "
            f"the incident is settled, not here.",
            messages.SUCCESS,
        )

    @admin.action(description="Mark selected claims paid")
    def mark_paid(self, request: HttpRequest, queryset: QuerySet[Claim]) -> None:
        unapproved = queryset.filter(
            status__in=[ClaimStatus.PENDING, ClaimStatus.REJECTED]
        ).count()
        paid = queryset.exclude(
            status__in=[ClaimStatus.PENDING, ClaimStatus.REJECTED]
        ).update(status=ClaimStatus.PAID)
        self.message_user(request, f"Marked {paid} claim(s) paid.", messages.SUCCESS)
        if unapproved:
            self.message_user(
                request,
                f"Skipped {unapproved} claim(s) that are still pending or were "
                f"rejected. Approve them first.",
                messages.WARNING,
            )


@admin.register(CommsUpdate)
class CommsUpdateAdmin(admin.ModelAdmin):
    list_display = ("incident", "sequence", "channel", "headline",
                    "published_chip", "next_update_at")
    list_filter = ("channel", "is_published", "incident")
    search_fields = ("headline", "body", "incident__code")
    list_select_related = ("incident",)

    @admin.display(description="State")
    def published_chip(self, obj: CommsUpdate) -> str:
        return (
            _chip("published", "#5FA37A") if obj.is_published
            else _chip("draft", "#D9A441")
        )
