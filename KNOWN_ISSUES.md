# Known issues

What is still open after the review against the research (`REVIEW.md`). Every
item here is open for one of two reasons: fixing it needs a number the research
does not give (and no risk parameter is ever invented), or it is a calibration
the owner has asked not to be tuned without a decision. Each says what the
decision is and, where it was measured, what the options do.

## Needs a decision

- **Throttle vs velocity calibration (open by decision).** At 20% participation
  the liquidation engine's own pace (~88 bps/s) exceeds the velocity trigger
  (~40 bps/s), so the protected runs spend long stretches paused and show
  V-dips at reopen. Not tuned by instruction; every page that shows pauses
  says so. Options: keep 20% (today), or 8% participation (1 pause, 0 swings
  in the macro run, at the cost of more liquidations and ADL).

- **Pre-trade price bands in continuous trading (measured, not switched on).**
  The `pre_trade_price_bands` control exists, but continuous trading never
  applied it; the band only collars the reopening auction, on or off. Wiring
  it (liquidation orders fill only inside the Reference Composite ± the band,
  the rest waits a second) was built and measured on all six scenarios:
  - Alone it is the second most valuable control: ₹6.61 Cr of attributable
    loss and 2,202 liquidations saved across the six; the macro cascade's book
    trough goes from −31.5% to −18.3%.
  - Stacked on the throttle and the circuit breaker it holds closes the
    throttle would have filled, so accounts run past bankruptcy: the protected
    macro run goes from 31 liquidations and no ADL to 459 and 23 ADL, and
    classifies B (thin-book wick) instead of A, so "with the controls on the
    same crash owes nothing" stops holding. Broker outage 36 → 266, UPI 15 →
    166 liquidations. Controls on still beat controls off everywhere.
  The decision is a calibration: band width against throttle participation,
  or a backstop that takes held positions (research 4.3's backstop liquidity
  providers, which have no published numbers either). The attribution and the
  Playbook say the band is not wired.

- **Cross-margin contagion (amplifier 4).** Accounts carry a margin mode, but
  the engine trades one instrument against INR collateral, so cross margin
  cannot spread a loss and the isolated-margin default shows no effect (the
  attribution says so). Modelling it needs a collateral asset, the share of
  cross accounts holding it, and a depeg path. The research gives the event
  sizes (USDe ~$0.65 on one venue, wBETH/BnSOL 5–7%) but not the book's
  collateral mix, and vol-scaled haircuts (change #9) have no numbers.

- **Daily price limits (the macro volatility layer).** The research names the
  layer, with expanded limits after a limit settle, but publishes no limit.

- **Backstop liquidity providers.** Committed makers with quoting obligations
  in stress, paid in fee rebates (research 4.3): no committed depth or rebate
  is given.

- **UPI credit risk score.** The pre-funded credit is capped at ₹50,000 and
  works; the research says "capped and risk-scored" but gives no scoring rule,
  so every initiated deposit is advanced up to the cap.

- **Class F goodwill cap.** The research allows goodwill "at a published cap"
  and publishes none, so no goodwill is credited.

- **Grievance SLAs.** SCORES/ODR-style published SLAs have no numbers in the
  research.

- **DCB pause "reduced to 5 s near the close".** Perps trade 24/7 and have no
  close, and "how near" has no number. Not modelled.

## Not modelled, by scope

- **Order-reject rate** (playbook T+5–15 diagnose). The engine has no user
  order flow, only liquidations and makers, so there is nothing to reject.
- **Support tickets** (auto-pager on ticket rate; auto-reply to every ticket).
  Tickets are not modelled; every affected account gets its own message and
  status page instead.
- **Oracle source weights** are fixed per source, not liquidity-weighted.

## Environment

- Google Fonts cannot be fetched inside the cloud sandbox (its proxy refuses
  the TLS chain), so headless checks there render in system fonts. Not an app
  issue.
