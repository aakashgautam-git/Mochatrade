"""Mark price construction. Never liquidate on last-traded price.

Binance's published method, mirrored here because it is the industry reference:

    Price Index = sum(weight_i * spot_price_i), weight-normalised
    Mark Price  = median(Price1, Price2, Contract Price)
      Price1 = Index * (1 + lastFundingRate * timeToNextFunding / fundingPeriod)
      Price2 = Index + MovingAverage(30s basis)

Hyperliquid does the same thing structurally: liquidations use a mark that
combines external CEX prices with the venue's own book state, which is more
robust than any single instantaneous book price.

This module is the difference between amplifier 3 firing and not firing. With
LTP marking, a venue-local wick liquidates accounts that were solvent at the
composite. With median marking, the wick has to convince two of three inputs.

Responsibilities
----------------
- Compute the index, Price1, Price2 and the contract (book mid) price per tick.
- Take the median, and record which of the three was selected, so the report
  can show the moment the mark decoupled from the book.
- Track mark<->oracle divergence, which is the primary auto-pager trigger at
  T+0..2 in the playbook.
"""
