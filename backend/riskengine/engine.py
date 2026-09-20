"""The deterministic tick loop. Holds all simulation state.

One step() call advances the world by one tick and returns a frame. The client
polls or steps over plain REST and animates between frames; there is no
websocket, no Channels and no background worker anywhere in this project.

Order of operations within a tick (fixed, because it is the thing that must be
byte-identical across runs):
    1. advance the exogenous shock and the per-source oracle inputs
    2. rebuild the Reference Composite, evaluate oracle health
    3. update the book (liquidity withdrawal, resting orders, price bands)
    4. compute the mark
    5. apply any operator actions queued for this tick
    6. evaluate accounts, run the liquidation waterfall under active controls
    7. emit the frame and append to the evidence tape

Determinism contract: same seed + same params + same action sequence produces a
byte-identical frame sequence. No wall-clock reads, no unseeded randomness, no
dict-ordering dependence, no floating-point accumulation that depends on
iteration order. Asserted in tests.

Every frame carries enough state to render the war room and, later, to
reconstruct the incident report without re-running the simulation.
"""
