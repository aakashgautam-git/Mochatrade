"""Deterministic pseudo-randomness.

Every stochastic choice in a simulation run comes from here, and every draw is
reproducible from the run's seed alone. No module in riskengine may import
`random` directly or call an unseeded generator.

Two deliberate choices:

- We wrap `random.Random` for the uniform stream, because CPython guarantees
  that generator's output will not change across versions.
- We do NOT use `random.gauss`: it caches a spare deviate between calls, so the
  number of underlying uniform draws per call varies and the stream becomes
  order-dependent in a way that is easy to break by accident. `normal()` below
  is Box-Muller, which consumes exactly two uniforms every time.

Sub-streams are derived by label through BLAKE2b rather than `hash()`, whose
salt is randomised per process.
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Sequence, TypeVar

T = TypeVar("T")

_TWO_PI = 2.0 * math.pi


def derive_seed(seed: int, label: str) -> int:
    """A stable child seed. Same (seed, label) gives the same result forever."""
    digest = hashlib.blake2b(label.encode("utf-8"), digest_size=8).digest()
    return (seed ^ int.from_bytes(digest, "big")) & 0xFFFF_FFFF_FFFF_FFFF


class Rng:
    """A seeded generator with an explicit, auditable call surface."""

    __slots__ = ("seed", "_r")

    def __init__(self, seed: int) -> None:
        self.seed = int(seed)
        self._r = random.Random(self.seed)

    def spawn(self, label: str) -> "Rng":
        """An independent sub-stream, so adding a draw in one subsystem cannot
        shift the numbers another subsystem sees."""
        return Rng(derive_seed(self.seed, label))

    def uniform(self, low: float = 0.0, high: float = 1.0) -> float:
        return low + (high - low) * self._r.random()

    def normal(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        """Box-Muller. Exactly two uniform draws per call, always."""
        u1 = self._r.random()
        u2 = self._r.random()
        # random() can return 0.0; log(0) is not available to us.
        if u1 <= 0.0:
            u1 = 5e-324
        return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(_TWO_PI * u2)

    def lognormal(self, median: float, sigma: float) -> float:
        """Log-normal parameterised by its median, which is how a book of
        retail position sizes is actually described."""
        return median * math.exp(self.normal(0.0, sigma))

    def chance(self, probability: float) -> bool:
        return self._r.random() < probability

    def pick(self, items: Sequence[T]) -> T:
        if not items:
            raise ValueError("cannot pick from an empty sequence")
        return items[int(self._r.random() * len(items)) % len(items)]

    def pick_weighted(self, items: Sequence[T], weights: Sequence[float]) -> T:
        """Weighted choice over a fixed-order sequence. Deterministic because
        the caller controls the order; never pass a set or a dict view."""
        if len(items) != len(weights):
            raise ValueError("items and weights must be the same length")
        total = math.fsum(weights)
        if total <= 0.0:
            raise ValueError("weights must sum to a positive number")
        target = self._r.random() * total
        running = 0.0
        for item, weight in zip(items, weights):
            running += weight
            if target < running:
                return item
        return items[-1]
