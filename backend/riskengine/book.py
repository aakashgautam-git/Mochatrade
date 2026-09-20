"""L2 order book and the liquidity-evaporation model.

Amplifier 2 from the research brief: liquidity disappears exactly when it is
needed. On 10 Oct 2025 BTC top-of-book depth shrank by more than 90% as market
makers widened spreads or stepped away entirely. The book you stress-test
against in calm markets does not exist in the crash, so the simulator must
shrink the book as a function of realised volatility rather than replaying a
static ladder.

Responsibilities
----------------
- Represent resting bids/asks as price levels with size.
- Walk a market order through the book and return an average fill price plus
  the slippage and the depth consumed (this is what makes the cascade bite).
- Withdraw and re-post liquidity in response to stress, so the book thins as
  the cascade runs and heals as it stabilises.
- Report depth-within-X-bps as a percentage of calm baseline, which is one of
  the gates the operator must clear before reopening (T+45..60 in the playbook).
- Expose a deterministic snapshot for the write-once evidence capture at T+3.

Also hosts pre-trade price bands (CFTC/FIA "Pre-trade" layer): reject orders
outside reference +/- variant. Binance.US on 21 Oct 2021 printed BTC at $8,200,
-87%, from one client's algo bug; a price band stops that at the gate.
"""
