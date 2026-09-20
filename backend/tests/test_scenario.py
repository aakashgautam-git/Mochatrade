"""Scenarios: the shock path, the population, and the library."""
from __future__ import annotations

import statistics

import pytest

from riskengine.params import DEFAULT_PARAMS as P
from riskengine.rng import Rng
from riskengine.scenario import (
    Layer,
    PopulationSpec,
    ShockSpec,
    Session,
    library,
    by_key,
)

LAKH = 1_00_000.0


# -- the shock path --------------------------------------------------------

def test_path_is_calm_before_the_crash() -> None:
    """The AR(1) noise is normalised so vol_bps is the STATIONARY deviation.
    Un-normalised, a phi=0.98 process amplifies it about fivefold, and the
    resulting 1%+ of 'calm' noise liquidates the 50x cohort on its own --
    igniting the cascade before the shock has even started."""
    path = ShockSpec(pre_ticks=200, vol_bps=22.0).path(200, Rng(1))
    deviations = [(p - 1.0) * 100.0 for p in path]
    assert statistics.pstdev(deviations) < 0.35
    assert max(abs(d) for d in deviations) < 1.0


def test_path_reaches_its_trough_and_reverts() -> None:
    spec = ShockSpec(pre_ticks=20, crash_ticks=40, trough_pct=-15.0,
                     hold_ticks=10, recovery_ticks=60, recovery_frac=0.8,
                     vol_bps=0.0)
    path = spec.path(200, Rng(1))
    assert min(path) == pytest.approx(0.85, abs=0.01)
    assert path[-1] == pytest.approx(0.85 + 0.15 * 0.8, abs=0.01)


def test_reversion_above_half_is_a_wick_not_a_repricing() -> None:
    """APE criterion 2 exists to separate the two."""
    wick = ShockSpec(trough_pct=-15.0, recovery_frac=0.8, vol_bps=0.0).path(600, Rng(1))
    repricing = ShockSpec(trough_pct=-15.0, recovery_frac=0.1, vol_bps=0.0).path(600, Rng(1))
    assert (wick[-1] - min(wick)) / (1.0 - min(wick)) > 0.5
    assert (repricing[-1] - min(repricing)) / (1.0 - min(repricing)) < 0.5


def test_path_is_deterministic() -> None:
    spec = ShockSpec()
    assert spec.path(300, Rng(5)) == spec.path(300, Rng(5))


# -- the population --------------------------------------------------------

def build(ceiling: float = 50.0, **kw: object) -> list:
    return PopulationSpec(**kw).build(  # type: ignore[arg-type]
        Rng(7), price=36_000.0, leverage_ceiling=ceiling, tier_leverage=P
    )


def test_population_matches_the_published_preset() -> None:
    accounts = build()
    assert len(accounts) == 1200
    notionals = sorted(a.qty * a.entry_price for a in accounts)
    assert 1.6 * LAKH < statistics.median(notionals) < 2.0 * LAKH
    assert notionals[0] >= 25_000.0 * 0.999
    assert notionals[-1] <= 40.0 * LAKH * 1.001
    longs = sum(1 for a in accounts if int(a.side) > 0)
    assert 0.76 < longs / len(accounts) < 0.84


def test_leverage_mix_follows_the_bands() -> None:
    levs = [a.leverage for a in build()]
    low = sum(1 for x in levs if 3.0 <= x <= 5.0) / len(levs)
    mid = sum(1 for x in levs if 10.0 <= x <= 20.0) / len(levs)
    assert 0.35 < low < 0.45
    assert 0.30 < mid < 0.40
    assert max(levs) <= 50.0


def test_a_leverage_cap_shrinks_the_position_not_the_capital() -> None:
    """A cap does not hand the user more money. Getting this backwards makes
    every cap look like it INCREASES losses, because it inflates the capital at
    risk and the loss is measured against it."""
    uncapped, capped = build(ceiling=50.0), build(ceiling=5.0)
    capital_a = sum(a.collateral for a in uncapped)
    capital_b = sum(a.collateral for a in capped)
    oi_a = sum(a.qty * a.entry_price for a in uncapped)
    oi_b = sum(a.qty * a.entry_price for a in capped)
    assert capital_a == pytest.approx(capital_b, rel=1e-9)
    assert oi_b < oi_a * 0.7
    assert max(a.leverage for a in capped) <= 5.0


def test_tier_ladder_caps_leverage_by_notional() -> None:
    """A 40L position cannot be 50x, because its tier says 10x."""
    for account in build():
        notional = account.qty * account.entry_price
        assert account.leverage <= P.max_leverage_for_notional(notional) + 1e-9


def test_population_is_deterministic() -> None:
    a, b = build(), build()
    assert [(x.id, x.qty, x.leverage, int(x.side)) for x in a] == [
        (y.id, y.qty, y.leverage, int(y.side)) for y in b
    ]


def test_isolated_default_applies_to_every_account() -> None:
    accounts = PopulationSpec().build(
        Rng(7), price=100.0, leverage_ceiling=50.0, tier_leverage=P,
        isolated_default=True,
    )
    assert all(a.mode.value == "isolated" for a in accounts)


# -- the library -----------------------------------------------------------

def test_library_covers_all_three_layers() -> None:
    """Minute one is 'which of our three layers broke', so the drill has to
    cover all three."""
    layers = {s.layer for s in library()}
    assert layers == {Layer.VENUE, Layer.MARKET, Layer.BROKER}


def test_library_keys_are_unique_and_addressable() -> None:
    scenarios = library()
    keys = [s.key for s in scenarios]
    assert len(keys) == len(set(keys)) == 6
    for key in keys:
        assert by_key(key).key == key
    with pytest.raises(KeyError):
        by_key("nope")


def test_every_scenario_states_who_is_liable() -> None:
    for scenario in library():
        assert scenario.liable_layer_note
        assert scenario.expected_class in set("ABCDEFG")
        assert scenario.summary


def test_equity_perps_have_a_cash_session_and_crypto_does_not() -> None:
    """The time-of-day leverage cap is defined for equity perps. Crypto trades
    24/7, so crediting the control there would claim damage reduction it has no
    business claiming."""
    for scenario in library():
        if scenario.instrument.startswith(("TSLA", "SPY")):
            assert scenario.has_cash_session
        else:
            assert not scenario.has_cash_session


def test_expected_rung_reflects_the_session() -> None:
    off_hours_equity = by_key("offhours_equity_wick")
    assert off_hours_equity.session is Session.WEEKEND
    assert off_hours_equity.expected_rung == 2
    # The class C scenario is deliberately off-hours too: the composite is
    # already on L2 as published, and the defect poisons the rung we fell back
    # to. That is the realistic shape of the failure for this product.
    assert by_key("oracle_defect_hip3").expected_rung == 2
    # Crypto has no cash session, so it is always expected on L1.
    assert by_key("macro_cascade").expected_rung == 1
    assert by_key("broker_outage").expected_rung == 1


def _oi_to_depth(key: str) -> float:
    scenario = by_key(key)
    accounts = scenario.population.build(
        Rng(scenario.seed), price=scenario.initial_price,
        leverage_ceiling=50.0, tier_leverage=P,
    )
    oi = sum(a.qty * a.entry_price for a in accounts)
    return oi / scenario.book.depth_1pct_notional


def test_no_market_is_so_thin_that_the_cascade_gridlocks() -> None:
    """Past roughly 600x, nothing can fill at all: the engine has orders to work
    and no book to work them in, so the run produces an enormous unfilled number
    and almost no liquidations. That is not a cascade, it is a modelling error."""
    for scenario in library():
        ratio = _oi_to_depth(scenario.key)
        assert ratio < 600.0, f"{scenario.key}: OI/depth = {ratio:.0f}x"


def test_depth_is_ordered_the_way_real_markets_are() -> None:
    """Crypto majors are deepest, an equity perp on our own dex is thinner, and
    the same equity perp outside US cash hours is thinner still. During
    off-hours 'trade.xyz becomes the primary venue -- liquidity may be
    different', which is the premise the whole off-hours scenario rests on."""
    major = _oi_to_depth("macro_cascade")
    equity_rth = _oi_to_depth("oracle_defect_hip3")
    equity_offhours = _oi_to_depth("offhours_equity_wick")
    assert major < equity_rth < equity_offhours
