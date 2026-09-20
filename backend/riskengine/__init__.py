"""MochaTrade risk engine — pure Python, deterministic, Django-free.

HARD RULE: no module in this package may import Django, DRF, or anything that
touches the database, the network or the clock. Time is a tick index passed in
by the caller. Randomness comes from a seeded generator threaded through the
scenario. Same seed + same params + same operator actions => byte-identical
output. `tests/test_determinism.py` asserts exactly that.

The credibility of the entire demo rests on this package being independently
testable, so a judge can change one parameter and watch the result move.

Module map
----------
book.py         L2 order book, depth model, liquidity withdrawal under stress
oracle.py       Reference Composite Price ladder (L1..L4), outlier clamp,
                staleness kill, per-source inputs for the evidence tape
marking.py      Mark price = median(Price1, Price2, Contract Price)
liquidation.py  Two-stage liquidation, waterfall, ADL, cascade accounting
controls.py     The togglable risk controls (the "off vs on" proof)
scenario.py     Scenario definitions: the shock, the book, the account set
engine.py       The tick loop that wires the above together and holds state
classifier.py   Abnormal Price Event test + root-cause classification A..G
remediation.py  Counterfactual equity, make-whole sizing, funding waterfall

Parameter provenance: every number consumed by this package originates in a
versioned RiskPolicy record, seeded from MOCHATRADE_PS3_RESEARCH.md. Nothing
in here may hard-code a risk parameter.
"""
