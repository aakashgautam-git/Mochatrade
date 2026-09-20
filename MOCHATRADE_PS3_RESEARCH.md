# PS3 — The Flash-Crash Simulation
## Deep research brief + strategy for ACM MarketSphere 2026 (MochaTrade, YC S26)

> This is the domain file. Drop it into the repo at `docs/DOMAIN_RESEARCH.md` so the build agent reads it while building, and use it as the source of truth for the deck/submission.

---

## 0. The insight that should win this track

**MochaTrade does not run an exchange. It is a non-custodial broker/front-end built on Hyperliquid.**

From MochaTrade's own YC launch: 50+ perps on US stocks, pre-IPO names, commodities and crypto, up to 50x, non-custodial wallets, INR in/out via UPI, and it is **"built on Hyperliquid infrastructure."** Front-ends monetise through **builder codes**, where the agent wallet "can only execute trades and cannot move user funds."

That single fact rewrites the entire answer, and almost every competing team will miss it:

| Lever the generic answer assumes | Does MochaTrade actually have it? |
|---|---|
| Pause the matching engine | **No.** HyperCore keeps matching. |
| Roll back / bust trades | **No.** Fills are on-chain and final. |
| Halt the venue | Only for a market **it** deployed under HIP-3 — and `haltTrading` "cancels all orders and settles positions to the current mark price", which is the nuclear option, not step one. |
| Change the mark price | Only on its own HIP-3 market, where it sets the oracle — and where it is **slashable up to 100% of a 500k HYPE stake** for a bad oracle or downtime. |
| Its own app, API, leverage menu, margin UI, UPI rails, INR ledger, comms, money | **Yes — 100%.** |

So the correct framing for the first 60 minutes is a **three-layer triage**, not a single incident:

```
  LAYER 3  VENUE     Hyperliquid / HyperCore, HLP, ADL, the shared book
  LAYER 2  MARKET    The HIP-3 dex MochaTrade deploys: oracle, margin tiers, max leverage, haltTrading
  LAYER 1  BROKER    MochaTrade's app, API, order router, margin display, UPI on-ramp, INR ledger, support
```

**Minute one is not "what did the market do." It is "which of our three layers broke."** The answer determines everything downstream — whether you owe money, whether you can act at all, and what you're allowed to say.

And here's the uncomfortable part, which is also the most credible thing you can put in front of a founder-judge: **for a 3-person team, the most likely "we caused this" failure is not the matching engine. It is Layer 1** — the app froze, the API rate-limited, or a UPI top-up didn't settle before the liquidation fired. That's the failure mode nobody's slide deck covers, and it's the one that actually happens.

---

## 1. Second insight: the "compare it to Binance" test breaks on this product

The reference answer says: check whether the wick printed on Binance/global spot. That works for BTC. **It does not work for MochaTrade's core product.**

MochaTrade's flagship is **US stock perps, trading 24/7, in IST.** The Indian retail day-trader's active hours are the *worst* hours for these instruments:

- US cash equities are open 19:00–01:30 IST. Outside that, **there is no spot market to compare against.**
- Hyperliquid's equity perps (deployed by trade.xyz under HIP-3) keep "marking through the weekend while the cash market is shut", and the guide's own warning is that "during off-hours, trade.xyz becomes the primary venue — liquidity may be different."
- So a 15% wick on a TSLA perp at 04:00 IST on a Sunday has **no external reference price at all.** You cannot prove it was abnormal by pointing at another venue, because there isn't one.
- Meanwhile a US stock can legitimately gap 20% on an earnings release or a headline while the cash market is closed. Some off-hours moves are *real*.

**Consequence:** MochaTrade must define "abnormal" **ex ante, against a Reference Composite it publishes**, not ex post against whatever venue makes the argument convenient. That composite has to degrade gracefully when the cash market is shut (index futures → ADRs → ETF proxies → other perp venues), and when it can't be built, **the correct action is to cut leverage and widen bands before the event, not to argue about it after.**

This is the sharpest, most product-specific point available in this problem statement.

---

## 2. The physics: why flash crashes amplify

Five amplifiers, all observed in the real events below. Your simulator should model all five, because turning each one off is a demonstrable control.

1. **The liquidation engine becomes the largest seller.** BitMEX, March 2020: the engine "had lots of contracts to sell, but faced a worsening price leading to more liquidations and more contracts to sell." ~1.1B contracts liquidated in 21 hours. When a DDoS knocked BitMEX offline at 02:16 UTC, **the price immediately recovered from ~$3,900 to ~$5,300** — because the biggest forced seller vanished. The outage was a better circuit breaker than the circuit breaker.
2. **Liquidity evaporates exactly when needed.** October 2025: **BTC top-of-book depth shrank by more than 90%.** Market makers "widened their spreads dramatically or stepped away altogether." The book you stress-test against in calm markets does not exist in the crash.
3. **The price feed becomes the weapon.** Oct 2025: **USDe printed ~$0.65 on Binance while holding ~$1.00 everywhere else**; wBETH and BnSOL diverged 5–7% from their underlying on Binance's own index. Positions "that could have remained solvent under cross-venue pricing were liquidated" purely from a venue-local dislocation.
4. **Cross-margin turns one bad asset into a portfolio wipeout.** Unified accounts get "tied to their weakest assets." A depegged collateral token liquidated entire portfolios whose individual positions were healthy.
5. **ADL converts a user problem into a trust problem.** Auto-deleveraging force-closes *winning* positions at the bankruptcy price. It "converted a hedged portfolio into a naked one during periods of stress." And a December 2025 arXiv paper on ADL is brutal about the cost: analysis of 10 Oct 2025 found **Hyperliquid's queue-based ADL imposed roughly $653M in unnecessary haircuts on winning traders — about 28× overutilisation versus optimal policy — likely contributing to the subsequent ~50% loss of open interest.**

That paper also proves an **impossibility trilemma** worth quoting in the deck: no ADL policy can simultaneously deliver exchange solvency, trader fairness, and long-run revenue. You must choose, and say which you chose.

---

## 3. Case file — seven precedents and the one lesson each

| # | Event | What happened | The transferable lesson |
|---|---|---|---|
| 1 | **BitMEX, 12–13 Mar 2020** | Liquidation death spiral; 25-min outage at the bottom; price bounced 36% the moment the engine stopped. Celsius's estate later sued over 6,360 BTC of liquidations. | **Throttle your own liquidation engine.** An unthrottled engine is a self-inflicted crash. |
| 2 | **Binance.US, 21 Oct 2021** | BTC printed **$8,200 (−87%)** on one venue while global spot was ~$66k. Cause: a bug in one institutional client's algo. | A catastrophic venue-local wick can come from **one customer's software.** Pre-trade price bands would have stopped it at the gate. |
| 3 | **NSE / Emkay, 5 Oct 2012 (India)** | Fat-finger sell of 17 lakh Nifty units; index −15.5%; circuit breaker misfired; NSE refused annulment. SAT upheld the refusal: clause 5(a) "is not intended to give relief to a trader… guilty of negligence", and annulling for margin breaches would "frustrate the objects with which margin money norms have been framed." SEBI later censured NSE anyway. | **Annulment is legally fragile and politically radioactive.** Indian precedent says trades stand. Whatever you do, have the rule written *before* the event. |
| 4 | **dYdX v3, Nov 2023** | Targeted YFI manipulation drained **$9M** from the insurance fund. Response: raise margin requirements on long-tail markets. | Long-tail perps are an **attack surface**, not just a listing opportunity. |
| 5 | **Hyperliquid JELLY, 26 Mar 2025** | Attacker self-liquidated a $4.1M short into HLP, then pumped thin spot so the mark followed, taking HLP ~$13.5M underwater. Validators voted to **delist and force-settle at the attacker's entry price.** Arthur Hayes compared it to CEX behaviour; Bitget's CEO called it "immature, unethical, unprofessional." | **The intervention costs more than the loss.** Hyperliquid got the money back and paid in legitimacy. Afterwards they codified delisting as documented governance with evidence standards and notice windows — which is exactly the right lesson: *turn the emergency into a published procedure.* |
| 6 | **October 10–11, 2025 — the big one** | Trump's 100% China tariff post → BTC $122k→$105k. **$19.3B liquidated, 1.62M accounts, 87% longs.** Binance's UI froze and APIs failed; Coinbase halted briefly; Robinhood paused crypto; **Lighter DEX was fully offline 36 minutes.** Binance burned ~$188M of insurance fund and ultimately paid **~$283M** in compensation. Hyperliquid stayed up through $10.3B of liquidations but fired cross-margin ADL for the first time. | **The cascade was survivable; the infrastructure failure was not.** People forgive a crash. They do not forgive being locked out of their own position while it liquidates. |
| 7 | **Robinhood, Mar 2020 → FINRA 2021** | Multi-day outages during peak volatility. **$70M — the largest FINRA penalty ever** — for "widespread and significant harm," and critically, for *misleading statements* as much as the downtime. | **What you say during the incident creates more liability than the incident.** This is the answer to "transparency vs legal exposure": vague reassurance is the expensive option. |

Two published-policy precedents worth citing as the template for your own:
- **OKX, Jan 2019:** an index-system upgrade produced a bad ETH spot index across two ~10-minute windows. OKX **did not roll back — it compensated**, named the exact windows, set a deadline (Feb 4) for crediting, and explicitly excluded "customers who experienced trading losses under normal circumstances."
- **CFTC/FIA best practice (Sept 2023):** "The ultimate goal of any error trade policy should be to promote a marketplace where all trades stand as executed," with **price adjustment preferred over cancellation**, a hard review window (CME: 8 minutes), and determinations that are "consistent and predictable."

---

## 4. What the best venues actually run (the control catalogue)

### 4.1 Pricing — never liquidate on LTP

**Binance's published method** is the industry reference, and your spec should mirror it:

```
Price Index   = Σ ( weight_i × spot_price_i )     across 15+ venues, weight-normalised
Mark Price    = median( Price1, Price2, Contract Price )
  Price1 = Index × (1 + lastFundingRate × timeToNextFunding / fundingPeriod)
  Price2 = Index + MovingAverage(30s basis)     # 30 samples @1s of mid − Index
```

With two protections that matter more than the formula:
- **Outlier clamp:** a source deviating >3% from the median is capped at 1.03× / 0.97× the median — **1% for BTC, ETH, SOL.**
- **Staleness kill:** "if Binance is unable to access data from an exchange or the exchange has not updated its trading data within the last five minutes, the weight of that exchange will be set to zero."

Hyperliquid does the same thing structurally: liquidations use "the mark price, which combines external CEX prices with Hyperliquid's book state," which is "more robust than using a single instantaneous book price."

**Binance had this and still got hit on 10 Oct**, because the failure wasn't the formula — it was that *collateral* assets (USDe, wBETH, BnSOL) were marked off a venue-local price. FTI's recommendation is the fix: **"multi-venue, liquidity-weighted oracles with outlier controls."**

### 4.2 Volatility control mechanisms (from CFTC/FIA + CME)

Four layers, designed to be used together — "no single control can accomplish the goal":

| Layer | Mechanism | Real parameters |
|---|---|---|
| Pre-trade | **Price bands on orders** — reject orders outside reference ± variant. Must be "dynamic and regularly recalculated." | CME: per-product, recalculated continuously |
| Micro | **Velocity logic** — analyses moves over milliseconds/seconds; brief pause to let participants reassess | typically **5 seconds** |
| Meso | **Dynamic circuit breakers** — rolling **60-minute** look-back high/low ± (prev settle × DCB %); breach → **2-minute pre-open**, reduced to 5s near the close; look-back window restarts on resume | CME DCB |
| Macro | **Daily price limits**, with expanded limits after a limit settle | CME |

Plus the reopen discipline the same document insists on: come back through **an auction with indicative opening price and order-balance display**, not straight into continuous trading — otherwise you print a second wick on the reopen.

And the transparency rule, which is the whole ballgame for a startup: parameters must be **"publicly available and replicable"** so participants can compute the triggers themselves, with market-wide notification when a control fires.

### 4.3 Liquidation engine design

- **Partial / tiered liquidation** — close only enough to restore margin, sized by position tier.
- **Two-stage liquidation (Hyperliquid's model):** below maintenance margin → market orders to the book, trader keeps any residual collateral, no clearance fee. Only below **⅔ of maintenance margin** does the backstop liquidator vault take the position and the maintenance margin is forfeited. This is a genuinely good design to copy: it gives the trader a chance to be liquidated *at market* before the punitive path.
- **Waterfall:** partial liquidation → market liquidation → backstop/insurance fund → **ADL last.** Binance's ADL rank = `PNL% × effective leverage` (profitable + highly levered go first), closing at the bankrupt trader's bankruptcy price.
- **Backstop liquidity providers** — pre-committed market makers with quoting obligations in stress, paid in fee rebates.
- **Margin-call grace window** — the widely-recommended post-Oct-2025 fix is a **2–5 minute delay with a push notification** so a user can add margin before the engine fires. For MochaTrade this is essential *because of UPI* (see §7).

### 4.4 What HIP-3 gives MochaTrade specifically

If MochaTrade deploys its own dex, the docs give it a real toolkit — and real liability:

- Sets **the oracle, the contract spec, max leverage, and fee share**; can `haltTrading` (cancels all orders, settles at current mark).
- Must post **500k HYPE for ≥183 days**, and faces **validator-voted slashing: up to 100%** for invalid state transitions or prolonged downtime, **up to 50%** for brief downtime, **up to 20%** for network degradation. Slashed stake is *burned*, not paid to users.
- **Cross-margin enablement is irreversible**, and is prohibited for assets expected to move 50% daily more than monthly — a >50% daily move triggers validator review for slashing.
- Each dex gets an **on-chain backstop liquidator** that absorbs undercollateralised positions, "reducing ADL necessity."

Read that again: **a bad oracle is not just a refund problem for MochaTrade, it is a slashing event.** That aligns incentives perfectly and is a fantastic thing to say on stage — "our oracle quality is collateralised by 500,000 HYPE; we are the most exposed party to our own wick."

---

## 5. The policy: **Trades stand. People get made whole.**

This is the position on abnormal-price liquidations, and it resolves the question the trader draft left fuzzy.

**Never reverse. Always compensate. Decide by a rule you published first.** Four reasons, all citable:
1. **You literally cannot reverse** — fills are on-chain and non-custodial.
2. **Reversal creates a second set of victims** — the counterparties who traded legitimately. JELLY showed the reputational bill.
3. **Indian precedent is hostile to annulment** — SAT/Emkay, plus FSLRC's view that transactions "should be final and not undone under any circumstances."
4. **Global best practice agrees** — CFTC/FIA: all trades stand; adjust/compensate rather than cancel.

### 5.1 The Abnormal Price Event (APE) test — publish this in the T&Cs

A fill or liquidation is an **Abnormal Price Event** if **all three** hold:

1. **Deviation** — execution price differs from the **Reference Composite Price** in the same 1-second window by more than the Non-Reviewable Range for that tier; and
2. **Reversion** — the deviation retraces **≥50% within 60 seconds** (it was a wick, not a repricing); and
3. **Counterfactual survival** — the account held sufficient margin to survive at the Reference Composite Price.

**Non-Reviewable Ranges** (publish per tier; these are our proposed parameters):

| Tier | Instruments | NRR | Off-hours NRR |
|---|---|---|---|
| 1 | BTC, ETH, SPY, mega-cap US equities | 3% | 5% |
| 2 | SOL, gold, large-cap equities, indices | 5% | 8% |
| 3 | Long-tail crypto, pre-IPO perps | 10% | 15% |

**Reference Composite Price** — a published, degrading ladder, so it exists at 04:00 IST on a Sunday:
`L1` ≥3 major spot venues (crypto) or the US cash market (equities, RTH) → `L2` index futures (ES/NQ) + ADRs + ETF NAV proxy → `L3` median of ≥2 independent perp venues → `L4` **no valid composite → market is force-flagged DEGRADED: max leverage 3x, reduce-only, liquidations paused.**

### 5.2 Remedy matrix — root cause decides who pays

| | Root cause | Fault | Remedy |
|---|---|---|---|
| **A** | Genuine market move, healthy oracle, adequate depth | Nobody | **No remedy.** Publish the evidence tape. |
| **B** | Thin book, venue-local wick, but mark correctly tracked the oracle | Market structure | No cash remedy. Fee rebate + the fix ships with a date. |
| **C** | **Oracle/index defect on a MochaTrade-deployed market** | **MochaTrade** | **Full make-whole** to counterfactual equity at Reference Composite. No rollback. |
| **D** | **MochaTrade app/API outage prevented top-up or close** | **MochaTrade** | Make-whole for loss attributable to the outage window. |
| **E** | **UPI/PSP failure delayed a funded deposit** | Shared — but we chose the rail | Make-whole where the deposit was initiated pre-liquidation and settled later. |
| **F** | Venue (Hyperliquid) defect, or ADL | Venue | **No MochaTrade cash liability.** We file the evidence pack on users' behalf, publish the venue's response, and may credit goodwill at a published cap. |
| **G** | Identifiable manipulation | Attacker | Freeze what we can, report to FIU-IND and the venue, fund from the Incident Reserve, pursue recovery. |

**Speed clause — the thing that actually keeps users:** for clear-cut C/D/E signatures, **provisional credit is pushed within 60 minutes**, as locked trading credit, converted to withdrawable cash after reconciliation, with the reconciliation published. Don't make a liquidated user file a ticket to get their own money back.

### 5.3 Funding waterfall

```
1. Recovery from the at-fault party (attacker / vendor SLA / PSP)
2. INCIDENT RESERVE      ring-fenced, publicly visible balance,
                         funded by 10% of builder-code fee revenue
                         until it reaches 2× the worst modelled 30-day loss
3. Corporate treasury     up to a published per-incident cap
4. Tech E&O insurance     (cheap at pre-seed; buy it before you need it)
5. Beyond the cap         pro-rata by a published formula + non-cash make-good
                          — announced as pro-rata, never paid silently short
```

Binance spent **~$188M of insurance fund and ~$283M total** on one weekend. MochaTrade cannot. **So the cap must exist and must be published in advance** — an honest, finite promise beats an implied infinite one you'll break.

---

## 6. The first 60 minutes — the playbook

Three founders. Roles are **pre-assigned in writing**; at T+0 you assume them, you don't discuss them.

- **IC — Incident Commander (CEO).** Owns decisions and the clock. **Does not touch a keyboard.**
- **OPS — Engineering (CTO).** System state, kill switches, evidence capture.
- **COMMS — Support & comms (3rd founder).** Status page, social, macros, then the claims queue.

| Clock | Phase | Actions |
|---|---|---|
| **0–2** | **DETECT & DECLARE** | Auto-pager on any of: mark↔oracle divergence, liquidation rate/min, API 5xx rate, ticket rate. Say "SEV-1, I am IC" out loud. Incident record auto-opens. |
| **2–5** | **CONTAIN — the Protect Switch** | One switch, pre-authorised, no approval needed: risk-increasing orders → **reduce-only**; liquidation engine → **TWAP throttle**; max leverage → 3x; if oracle suspect → **liquidations paused on that market only**. `haltTrading` stays holstered — it settles everyone at mark. |
| **3** | **PRESERVE** | Write-once snapshot: L2 book, trade tape, **per-source oracle inputs**, mark series, liquidation events, app/API telemetry, deposit queue. (Also satisfies a 2-year retention standard.) |
| **5** | **FIRST PUBLIC WORD** | Status page → X → WhatsApp/Telegram. No cause. No blame. What we see, what we turned on, **next update at HH:MM**. |
| **5–15** | **DIAGNOSE — all three layers** | Run the APE detector: our mark vs Reference Composite, per second, per venue. **And check our own layer**: app uptime, API error rate, order-reject rate, UPI settlement queue. Classify A–G. |
| **15** | **UPDATE 2 + preliminary call** | If it's C/D/E, **say so at T+15.** Owning it early is the highest-ROI trust action available and it is the one thing a 3-person team can do faster than Binance. |
| **15–30** | **QUANTIFY** | Build the affected set and the counterfactual equity for each account. Get the number. Check the Incident Reserve covers it. |
| **30** | **UPDATE 3 — the number** | "N users, ₹X aggregate, between HH:MM–HH:MM IST." Cite the APE policy **that already existed**. |
| **30–45** | **REMEDIATE** | Auto-push provisional credit to clear cases. Open claims portal, 72h window. Auto-reply every open ticket with a link to *their* status, not a generic notice. |
| **45–60** | **STABILISE & REOPEN** | Staged: reduce-only → post-only → full. Each gate requires oracle healthy 5 min, spread < X bps, depth > Y% of baseline. **Reopen through a short auction**, never straight into continuous. |
| **60** | **HANDOVER** | Publish: what happened, who's affected, what we're paying, when it lands, and the date of the full RCA. |

### The three judgment calls to defend out loud

1. **Reduce-only, not a full halt.** A halt traps people; reduce-only lets them leave. Name the cost honestly: it also blocks the trader who wanted to add margin or fade the move. You accept that cost because "trapped while liquidating" is the failure that ends companies — that's the Oct-2025 Binance lesson.
2. **Pause liquidations only if the *price* is suspect.** Pausing liquidations while the feed is healthy doesn't save users; it converts their losses into *your* insolvency. The trigger must be oracle health, not user pain.
3. **Never reverse; compensate fast instead.** §5.

### What you explicitly do NOT do at 3am
Rewrite risk parameters live. Argue on X. Answer tickets individually. Promise a number before you've computed it. Say "your funds are safe" before you've verified solvency. Say "market conditions."

---

## 7. The India layer — where this gets genuinely differentiated

1. **A liquidated Indian trader has no tax relief.** VDA gains are taxed at a flat 30% **with no loss set-off**, plus 1% TDS on transfers. A user wiped out by a scam wick eats 100% of it with zero deductibility. **The trust damage from an identical event is strictly worse in India than anywhere else** — which is precisely why compensation policy, not just risk policy, is a competitive weapon here.
2. **Hold yourself to SEBI's broker glitch framework even though you aren't a SEBI broker.** It is a ready-made, regulator-blessed 60-minute discipline: a malfunction ≥**5 minutes** is a reportable technical glitch; **notify within 1 hour**; **preliminary report T+1**; **RCA within 14 days**; installed capacity ≥**1.5× peak**; alerting at **70% utilisation**; DR site ≥**250 km** away or different seismic zone; glitch data retained **2 years**; exchanges must publish the glitch and its RCA. Adopting this voluntarily is an extraordinary line for a compliance-first company with **FIU-IND registration in flight** — and it maps one-to-one onto the playbook above.
3. **UPI is a dependency you don't control.** India saw **282 minutes of UPI outage across two incidents**. If a user's ability to avoid liquidation depends on a UPI leg settling, you have imported NPCI's uptime into your margin system. Fix: a **pre-funded instant margin credit** against an initiated-but-unsettled deposit, capped and risk-scored. This is the single most India-specific engineering control in the whole answer.
4. **Grievance redressal with published SLAs**, mirroring SCORES/ODR norms, plus bilingual comms on WhatsApp and Telegram — where Indian F&O traders actually are, not just X.
5. **Compensation has tax characterisation risk.** Credits to Indian users may be treated as income; document and, where feasible, gross up.

---

## 8. "A short set of changes" — ranked by damage reduction per engineering-week

| # | Change | Effort | Kills |
|---|---|---|---|
| 1 | Mark = oracle-anchored composite w/ clamp + staleness kill. **Never LTP.** | 1 wk | Amplifier 3 |
| 2 | Oracle health monitor → auto reduce-only + liquidation pause on degradation | 1 wk | Amplifier 3 |
| 3 | Liquidation TWAP throttle + max participation rate of resting depth | 2 wks | Amplifier 1 |
| 4 | **Time-of-day leverage caps** for equity perps (50x RTH → 5x off-hours) | 3 d | The product's own worst vector |
| 5 | Margin-call grace window + one-tap top-up + **pre-funded UPI buffer** | 2 wks | Amplifiers 1 & 5, and the UPI dependency |
| 6 | Two-stage partial liquidation (market first, backstop only below ⅔ MM) | 2 wks | Amplifier 1 |
| 7 | Published APE policy + funded Incident Reserve | 1 wk (legal/treasury) | The trust crisis |
| 8 | Status page + automated incident comms + evidence snapshotter | 3 d | The trust crisis |
| 9 | Isolated-margin default for long-tail; haircuts that scale with vol | 1 wk | Amplifier 4 |
| 10 | Quarterly game-day: run this exact playbook against the simulator | ongoing | Everything |

Note how many are **product decisions, not engineering**: #4 and #7 are the highest-leverage items and neither requires a matching engine. That is the honest answer to "realism for a small team."

---

## 9. "What would make me stay as a user"

Answer it in the first person, because the judges asked a human question:

1. A **number and a deadline**, inside the hour — not "we're investigating."
2. **Money in my account before I have to ask.** A claims form is a second insult.
3. **The raw tape**, so I can check your story myself. Self-custody means I can verify on-chain — use that as an asset, not a liability.
4. **A named human** who owns it, on camera. A 3-person team can put the CEO live in 20 minutes. Binance structurally cannot. That's your advantage — spend it.
5. **A shipped mechanism change with a date**, and a follow-up post when it ships.
6. **Not being told it was my fault for using the 50x you sold me.**

---

## 10. Likely judge questions — and the answers

- *"Isn't compensating just moral hazard?"* — It would be, if it were discretionary. It isn't: it's a published test with a counterfactual, a tier table, a cap, and an explicit exclusion for normal trading losses. OKX's 2019 notice did exactly this: compensate the error window, exclude "customers who experienced trading losses under normal circumstances."
- *"You can't afford Binance's $283M."* — Correct, which is why the cap is published in advance and the reserve is visible and pre-funded. An honest finite promise beats an implied infinite one.
- *"Why not just halt?"* — Because you don't own the engine, and because `haltTrading` settles everyone at the mark you're currently disputing. Halting is how you turn a pricing dispute into a settlement dispute.
- *"Why not roll back?"* — You can't (on-chain), you shouldn't (SAT/Emkay, CFTC/FIA), and JELLY shows what it costs when you do.
- *"Your simulator's numbers are made up."* — Say so plainly: the *parameters* are our proposal, the *mechanisms* are Binance's/CME's/Hyperliquid's published specs, and the engine is deterministic and unit-tested so any judge can change a parameter and watch the result move.

---

## Sources

- [Inside the $19B Flash Crash — insights4vc](https://insights4vc.substack.com/p/inside-the-19b-flash-crash)
- [Crypto Crash Oct 2025: Leverage Meets Liquidity — FTI Consulting](https://www.fticonsulting.com/insights/articles/crypto-crash-october-2025-leverage-met-liquidity)
- [Infrastructure Failures That Amplified The Crash — Medium](https://medium.com/@nicolakharvey/infrastructure-failures-that-amplified-the-crash-545656ab1c09)
- [Binance Pays $283 Million to Users After Token Depegs — Unchained](https://unchainedcrypto.com/binance-pays-283-million-to-users-after-token-depegs-trigger-major-losses/)
- [Locked Out And Liquidated — Forbes](https://www.forbes.com/sites/boazsobrado/2025/10/21/locked-out-and-liquidated-traders-blame-binance-for-19-billion-crash/)
- [What Are Mark Price and Price Index in USDⓈ-M Futures — Binance](https://www.binance.com/en/support/faq/what-are-mark-price-and-price-index-in-usd%E2%93%A2-margined-futures-360033525071)
- [What Is Auto-Deleveraging (ADL) — Binance](https://www.binance.com/en-ZA/support/faq/what-is-auto-deleveraging-adl-and-how-does-it-work-360033525471)
- [Autodeleveraging: Impossibilities and Optimization — arXiv 2512.01112](https://arxiv.org/html/2512.01112v2)
- [Best Practices for Exchange Volatility Control Mechanisms — CFTC GMAC / FIA, Sept 2023](https://www.cftc.gov/media/9581/gmac_FIA110623/download)
- [FAQ: Dynamic Circuit Breakers — CME Group](https://www.cmegroup.com/globex/trade-on-cme-globex/frequently-asked-questions-dynamic-circuit-breakers.html)
- [The BitMEX Liquidation Spiral — Coin Metrics State of the Network #43](https://coinmetrics.substack.com/p/coin-metrics-state-of-the-network-bf8)
- [DDoS attack, 13 March 2020 — BitMEX Blog](https://www.bitmex.com/blog/site-announcement/ddos-attack-13-march-2020)
- [Bitcoin Price Flash Crash on Binance.US Attributed to Trader Algorithm Bug — CoinDesk](https://www.coindesk.com/markets/2021/10/21/bitcoin-price-flash-crash-on-binanceus-attributed-to-trader-algorithm-bug)
- [SAT order on NSE's actions after the Emkay crash — The Leap Blog](https://blog.theleapjournal.org/2014/09/sat-order-on-nse-actions-after-emkay.html)
- [dYdX Hit by $9 Million Insurance Fund Breach — Unchained](https://unchainedcrypto.com/dydx-hit-by-9-million-insurance-fund-breach-amid-alleged-yfi-market-manipulation/)
- [The JELLY Incident: Anatomy of a Self-Manipulated Perp — perp.wiki](https://perp.wiki/risk-framework/jelly-incident-anatomy-2025)
- [HyperLiquid Delists JELLYJELLY After Vault Squeezed — CoinDesk](https://www.coindesk.com/markets/2025/03/26/hyperliquid-delists-jellyjelly-after-vault-squeezed-in-usd13m-tussle)
- [HIP-3: Builder-deployed perpetuals — Hyperliquid Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals)
- [Liquidations — Hyperliquid Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations)
- [Builder Codes — Hyperliquid Wiki](https://hyperliquid-co.gitbook.io/wiki/guide/builder-guide/hypercore/builder-codes)
- [Equity Perps on Hyperliquid — Hyperliquid Guide](https://hyperliquidguide.com/guides/trading/equity-perps-guide)
- [Launch YC: Mochatrade — US stock perps for Indian traders with up to 50x leverage](https://www.ycombinator.com/launches/QJd-mochatrade-us-stock-perps-for-indian-traders-with-up-to-50x-leverage)
- [Handling of ETH Futures Contracts Price Error — OKX](https://www.okx.com/en-us/help/handling-of-eth-futures-contracts-price-error)
- [Robinhood to pay $70 million after causing "widespread and significant harm" — CNBC](https://www.cnbc.com/2021/06/30/robinhood-to-pay-70-million-dollars-after-causing-users-significant-harm.html)
- [Framework to address 'technical glitches' in Stock Brokers' Electronic Trading Systems — SEBI (via TaxGuru)](https://taxguru.in/sebi/framework-address-technical-glitches-stock-brokers-electronic-trading-systems.html)
- [SEBI's New Framework for Technical Glitches — IndiaCorpLaw](https://indiacorplaw.in/2025/11/19/sebis-new-framework-for-technical-glitches-a-step-toward-balance-or-more-burden/)
- [UPI outages lasted 282 minutes across two incidents — Business Standard](https://www.business-standard.com/finance/news/upi-outages-lasted-282-minutes-across-two-incidents-in-2022-2025-125041300574_1.html)
- [Crypto Regulation in India 2026 — Sansa Legal](https://www.sansalegal.com/post/crypto-regulation-in-india-2026-tax-rules-sebi-framework-rbi-guidelines-and-legal-status-explain)
