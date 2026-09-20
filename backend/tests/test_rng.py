"""The seeded generator. If this is not reproducible, nothing downstream is."""
from __future__ import annotations

import statistics

from riskengine.rng import Rng, derive_seed


def test_same_seed_same_stream() -> None:
    a, b = Rng(42), Rng(42)
    assert [a.normal() for _ in range(50)] == [b.normal() for _ in range(50)]
    assert [a.uniform(0, 10) for _ in range(50)] == [b.uniform(0, 10) for _ in range(50)]


def test_different_seeds_diverge() -> None:
    assert [Rng(1).normal() for _ in range(5)] != [Rng(2).normal() for _ in range(5)]


def test_sub_streams_are_stable_and_independent() -> None:
    """Sub-streams exist so that adding a draw in one subsystem cannot shift the
    numbers another subsystem sees."""
    assert Rng(7).spawn("book").seed == Rng(7).spawn("book").seed
    assert Rng(7).spawn("book").seed != Rng(7).spawn("oracle").seed
    assert derive_seed(7, "book") == derive_seed(7, "book")


def test_derive_seed_does_not_depend_on_process_hash_salt() -> None:
    """Pinned to literals. Uses BLAKE2b rather than hash(), whose salt is
    randomised per process -- with hash() these values would differ on every
    run and no simulation would ever replay."""
    assert derive_seed(0, "oracle-noise") == 8213610774713637523
    assert derive_seed(20251010, "population") == 15863952633151238959


def test_normal_consumes_a_fixed_number_of_uniforms() -> None:
    """Box-Muller, not random.gauss: gauss caches a spare deviate, so its draw
    count varies between calls and the stream becomes order-dependent."""
    a = Rng(9)
    a.normal()
    after_normal = a.uniform()
    b = Rng(9)
    b.uniform()
    b.uniform()
    assert after_normal == b.uniform()


def test_normal_is_roughly_standard() -> None:
    draws = [Rng(3).spawn(str(i)).normal(0.0, 1.0) for i in range(4000)]
    assert abs(statistics.fmean(draws)) < 0.06
    assert 0.94 < statistics.pstdev(draws) < 1.06


def test_lognormal_is_centred_on_its_median() -> None:
    draws = [Rng(11).spawn(str(i)).lognormal(1000.0, 0.8) for i in range(4000)]
    assert 930.0 < statistics.median(draws) < 1075.0


def test_pick_weighted_respects_weights() -> None:
    rng = Rng(17)
    items = ("a", "b", "c")
    counts = {k: 0 for k in items}
    for _ in range(6000):
        counts[rng.pick_weighted(items, (0.7, 0.2, 0.1))] += 1
    assert counts["a"] > counts["b"] > counts["c"]
    assert 0.66 < counts["a"] / 6000 < 0.74
