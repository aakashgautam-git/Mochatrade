"""Create RiskPolicy v1 from the engine's own defaults.

Every value here is read from `riskengine.params.DEFAULT_PARAMS`. Nothing is
typed in. If a number appeared in this file it would immediately be a second
place where a risk parameter lives, and the two would drift.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    SCALAR_PARAM_NAMES,
    PolicyInstrumentTier,
    PolicyMarginTier,
    RiskPolicy,
)
from riskengine.params import DEFAULT_PARAMS


class Command(BaseCommand):
    help = "Seed RiskPolicy v1 from riskengine.params.DEFAULT_PARAMS and activate it."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--policy-version",
            dest="policy_version",
            default=DEFAULT_PARAMS.version,
            # Not --version: Django's base command already owns that flag.
            help="Policy version to create (default: the dataclass's own version).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rewrite the policy if this version already exists.",
        )

    @transaction.atomic
    def handle(self, *args: object, **options: object) -> None:
        version = str(options["policy_version"])
        force = bool(options["force"])
        params = DEFAULT_PARAMS

        existing = RiskPolicy.objects.filter(version=version).first()
        if existing and not force:
            existing.is_active = True
            existing.save()
            self.stdout.write(
                self.style.WARNING(
                    f"RiskPolicy {version} already exists; marked active. "
                    f"Pass --force to rewrite it."
                )
            )
            return
        if existing:
            existing.delete()

        policy = RiskPolicy(
            version=version,
            name="MochaTrade published risk policy",
            is_active=True,
            notes=(
                "Seeded from riskengine.params.DEFAULT_PARAMS. The parameters are "
                "MochaTrade's proposal; the mechanisms are the published specs of "
                "Binance (index and mark construction), CME and the CFTC/FIA "
                "(layered volatility controls) and Hyperliquid (two-stage "
                "liquidation, backstop vault, HIP-3). Three values are marked "
                "DERIVED in FIELD_SOURCES because the research brief specifies a "
                "mechanism but publishes no number for it."
            ),
            **{name: getattr(params, name) for name in SCALAR_PARAM_NAMES},
        )
        policy.save()

        floor = Decimal("0")
        for index, tier in enumerate(params.margin_tiers):
            ceiling = (
                Decimal(str(tier.max_notional)) if tier.max_notional is not None else None
            )
            PolicyMarginTier.objects.create(
                policy=policy,
                ordering=index,
                notional_floor=floor,
                notional_ceiling=ceiling,
                max_leverage=tier.max_leverage,
                mm_pct=tier.mm_rate * 100.0,
            )
            floor = ceiling if ceiling is not None else floor

        for tier in params.instrument_tiers:
            PolicyInstrumentTier.objects.create(
                policy=policy,
                tier=tier.tier,
                label=tier.label,
                nrr_pct=tier.nrr_pct,
                nrr_offhours_pct=tier.nrr_offhours_pct,
                dcb_variant_pct=tier.dcb_variant_pct,
            )

        # Prove the round trip before claiming success: what we just wrote must
        # reconstruct the dataclass we read from, exactly.
        rebuilt = policy.to_params()
        if rebuilt != params.evolve(version=version):
            raise RuntimeError(
                "Seeded policy does not round-trip back to RiskParams. "
                "RiskPolicy and RiskParams have drifted."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded and activated RiskPolicy {version}: "
                f"{len(params.margin_tiers)} margin tiers, "
                f"{len(params.instrument_tiers)} instrument tiers, "
                f"{len(SCALAR_PARAM_NAMES)} scalar parameters, "
                f"round-trip verified."
            )
        )
