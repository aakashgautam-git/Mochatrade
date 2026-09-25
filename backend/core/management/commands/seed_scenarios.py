"""Load riskengine.scenario.library() into Scenario and Instrument rows.

The library stays the source of the definitions; the database becomes the source
the app reads. Instrument leverage and margin readouts are taken from the ACTIVE
RiskPolicy rather than typed in, so this command introduces no risk number of its
own -- run seed_policy first.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    AssetClass,
    BrokerFault,
    Instrument,
    Layer,
    OracleFault,
    RiskPolicy,
    Scenario,
)
from riskengine.oracle import FaultKind
from riskengine.params import TICK_SECONDS
from riskengine.scenario import Scenario as EngineScenario
from riskengine.scenario import library

# US cash equities: 09:30-16:00 ET is 19:00-01:30 IST.
US_RTH_OPEN_IST = dt.time(19, 0)
US_RTH_CLOSE_IST = dt.time(1, 30)

ASSET_CLASS = {"TSLA": AssetClass.EQUITY, "BTC": AssetClass.CRYPTO, "PREIPO": AssetClass.PREIPO}
DISPLAY = {
    "TSLA-PERP": "Tesla perpetual (US equity)",
    "BTC-PERP": "Bitcoin perpetual",
    "PREIPO-PERP": "Pre-IPO perpetual (long-tail)",
}


def _oracle_fault(s: EngineScenario) -> str:
    deviating = [f for f in s.oracle_faults if f.kind is FaultKind.DEVIATE]
    if len(deviating) >= 2:
        return OracleFault.DIVERGENT
    if len(deviating) == 1:
        return OracleFault.SINGLE_SOURCE_DEPEG
    if any(f.kind is FaultKind.STALE for f in s.oracle_faults):
        return OracleFault.STALE
    return OracleFault.NONE  # a CLOSED cash market is structure, not a fault


def _broker_fault(s: EngineScenario) -> tuple[str, int]:
    if s.outage is not None:
        return BrokerFault.APP_FROZEN, int(s.outage.duration_ticks * TICK_SECONDS)
    if s.upi_delay is not None:
        window = s.upi_delay.settles_tick - s.upi_delay.initiated_tick
        return BrokerFault.UPI_DELAY, int(window * TICK_SECONDS)
    return BrokerFault.NONE, 0


def _leverage_distribution(s: EngineScenario) -> dict[str, float]:
    out: dict[str, float] = {}
    for band in s.population.leverage_bands:
        label = f"{band.low:g}x" if band.low == band.high else f"{band.low:g}-{band.high:g}x"
        out[label] = band.share
    return out


class Command(BaseCommand):
    help = "Load the engine's scenario library into the database."

    @transaction.atomic
    def handle(self, *args: object, **options: object) -> None:
        policy = RiskPolicy.objects.filter(is_active=True).first()
        if policy is None:
            raise CommandError("No active RiskPolicy. Run `manage.py seed_policy` first.")
        first_rung = policy.margin_tier_rows.order_by("ordering").first()

        scenarios = library()
        prices: dict[str, float] = {}
        for s in scenarios:
            prices.setdefault(s.instrument, s.initial_price)
        layers = Counter()

        instruments: dict[str, Instrument] = {}
        for s in scenarios:
            if s.instrument in instruments:
                continue
            root = s.instrument.split("-")[0]
            instruments[s.instrument], _ = Instrument.objects.update_or_create(
                symbol=s.instrument,
                defaults=dict(
                    display_name=DISPLAY.get(s.instrument, s.instrument),
                    layer=Layer.MARKET if s.has_cash_session else Layer.VENUE,
                    tier=s.instrument_tier,
                    asset_class=ASSET_CLASS.get(root, AssetClass.CRYPTO),
                    has_rth=s.has_cash_session,
                    rth_open_ist=US_RTH_OPEN_IST if s.has_cash_session else None,
                    rth_close_ist=US_RTH_CLOSE_IST if s.has_cash_session else None,
                    base_price=Decimal(str(prices[s.instrument])),
                    max_leverage=policy.max_leverage_rth,
                    maintenance_margin_pct=first_rung.mm_pct if first_rung else 0.0,
                ),
            )

        for s in scenarios:
            broker_fault, window = _broker_fault(s)
            layers[s.layer.value] += 1
            Scenario.objects.update_or_create(
                slug=s.key,
                defaults=dict(
                    name=s.title,
                    description=s.summary,
                    instrument=instruments[s.instrument],
                    seed=s.seed,
                    shock_pct=s.shock.trough_pct,
                    shock_duration_s=int(s.shock.crash_ticks * TICK_SECONDS),
                    total_duration_s=int(s.n_ticks * TICK_SECONDS),
                    book_depth_inr=Decimal(str(s.book.depth_1pct_notional)),
                    depth_collapse_pct=round((1.0 - s.book.min_liquidity_frac) * 100.0, 1),
                    n_accounts=s.population.n_accounts,
                    leverage_distribution=_leverage_distribution(s),
                    long_share_pct=round(s.population.long_share * 100.0, 1),
                    oracle_fault=_oracle_fault(s),
                    broker_fault=broker_fault,
                    broker_fault_window_s=window,
                    is_offhours=s.offhours,
                    assumed_scale_note=s.assumed_scale_note,
                    engine_key=s.key,
                ),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(scenarios)} scenarios on {len(instruments)} instruments "
                f"({', '.join(f'{n} {layer}' for layer, n in sorted(layers.items()))})."
            )
        )
