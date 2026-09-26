/**
 * The research brief's published content, as data, so the Playbook and every
 * Report quote the same words. Transcribed from MOCHATRADE_PS3_RESEARCH.md;
 * nothing here is new. Type-only imports, so node --test can load it.
 */
import type { RemedyClass } from "./types";

export interface Precedent {
  key: string;
  event: string;
  when: string;
  what: string;
  lesson: string;
  /** Where MochaTrade's answer to it lives. */
  answer: string;
}

/** Research 3: the case file, seven precedents and the one lesson each. */
export const PRECEDENTS: Precedent[] = [
  {
    key: "bitmex",
    event: "BitMEX",
    when: "12–13 Mar 2020",
    what: "Liquidation death spiral; a 25-minute outage at the bottom; price bounced 36% the moment the engine stopped. Celsius's estate later sued over 6,360 BTC of liquidations.",
    lesson: "Throttle your own liquidation engine. An unthrottled engine is a self-inflicted crash.",
    answer: "The liquidation TWAP throttle: at most 20% of resting depth within 1% of the mark, per 250 ms slice.",
  },
  {
    key: "binance-us",
    event: "Binance.US",
    when: "21 Oct 2021",
    what: "BTC printed $8,200 (−87%) on one venue while global spot was ~$66k. Cause: a bug in one institutional client's algo.",
    lesson: "A catastrophic venue-local wick can come from one customer's software. Pre-trade price bands would have stopped it at the gate.",
    answer: "Pre-trade price bands around the Reference Composite, and a mark that never follows the last trade.",
  },
  {
    key: "emkay",
    event: "NSE / Emkay (India)",
    when: "5 Oct 2012",
    what: "Fat-finger sell of 17 lakh Nifty units; index −15.5%; the circuit breaker misfired; NSE refused annulment. SAT upheld the refusal: clause 5(a) \"is not intended to give relief to a trader… guilty of negligence\", and annulling for margin breaches would \"frustrate the objects with which margin money norms have been framed.\" SEBI later censured NSE anyway.",
    lesson: "Annulment is legally fragile and politically radioactive. Indian precedent says trades stand. Whatever you do, have the rule written before the event.",
    answer: "Trades stand. The APE test and the remedy matrix are published before any event.",
  },
  {
    key: "dydx",
    event: "dYdX v3",
    when: "Nov 2023",
    what: "Targeted YFI manipulation drained $9M from the insurance fund. Response: raise margin requirements on long-tail markets.",
    lesson: "Long-tail perps are an attack surface, not just a listing opportunity.",
    answer: "Isolated margin by default on long-tail markets, the widest Non-Reviewable Range for tier 3, and class G.",
  },
  {
    key: "jelly",
    event: "Hyperliquid JELLY",
    when: "26 Mar 2025",
    what: "An attacker self-liquidated a $4.1M short into HLP, then pumped thin spot so the mark followed, taking HLP ~$13.5M underwater. Validators voted to delist and force-settle at the attacker's entry price. Arthur Hayes compared it to CEX behaviour; Bitget's CEO called it \"immature, unethical, unprofessional.\"",
    lesson: "The intervention costs more than the loss. Turn the emergency into a published procedure.",
    answer: "Class G: freeze what we can, report to FIU-IND and the venue, fund from the Incident Reserve, pursue recovery. Never reverse.",
  },
  {
    key: "oct-2025",
    event: "October 10–11, 2025 — the big one",
    when: "10–11 Oct 2025",
    what: "A 100% China tariff post took BTC from $122k to $105k. $19.3B liquidated, 1.62M accounts, 87% longs. Binance's UI froze and its APIs failed; Coinbase halted briefly; Robinhood paused crypto; Lighter DEX was offline 36 minutes. Binance burned ~$188M of insurance fund and paid ~$283M in compensation. Hyperliquid stayed up through $10.3B of liquidations but fired cross-margin ADL for the first time.",
    lesson: "The cascade was survivable; the infrastructure failure was not. People forgive a crash. They do not forgive being locked out of their own position while it liquidates.",
    answer: "Class D is ours, and reduce-only (not a halt) lets people leave. A published per-incident cap, because MochaTrade cannot spend $283M.",
  },
  {
    key: "robinhood",
    event: "Robinhood → FINRA",
    when: "Mar 2020 → 2021",
    what: "Multi-day outages during peak volatility. $70M, the largest FINRA penalty ever, for \"widespread and significant harm\", and for misleading statements as much as the downtime.",
    lesson: "What you say during the incident creates more liability than the incident. Vague reassurance is the expensive option.",
    answer: "The comms guardrails: no \"market conditions\", no \"your funds are safe\" before solvency is verified, no number before it is computed.",
  },
];

/** Research 3: the two published-policy templates. */
export const POLICY_TEMPLATES = [
  {
    key: "okx",
    event: "OKX",
    when: "Jan 2019",
    what: "An index-system upgrade produced a bad ETH spot index across two ~10-minute windows. OKX did not roll back — it compensated, named the exact windows, set a deadline (Feb 4) for crediting, and explicitly excluded \"customers who experienced trading losses under normal circumstances.\"",
  },
  {
    key: "cftc-fia",
    event: "CFTC/FIA best practice",
    when: "Sept 2023",
    what: "\"The ultimate goal of any error trade policy should be to promote a marketplace where all trades stand as executed,\" with price adjustment preferred over cancellation, a hard review window (CME: 8 minutes), and determinations that are \"consistent and predictable.\"",
  },
];

/** Which precedents speak to an incident of each class. */
export const PRECEDENTS_FOR: Record<RemedyClass, string[]> = {
  A: ["oct-2025", "bitmex"],
  B: ["binance-us", "bitmex"],
  C: ["okx", "emkay"],
  D: ["robinhood", "oct-2025"],
  E: ["oct-2025", "emkay"],
  F: ["oct-2025", "jelly"],
  G: ["jelly", "dydx"],
};

export interface IndiaAngle {
  key: string;
  title: string;
  text: string;
}

/** Research 7: the India layer. */
export const INDIA: IndiaAngle[] = [
  {
    key: "tax",
    title: "A liquidated Indian trader has no tax relief",
    text: "VDA gains are taxed at a flat 30% with no loss set-off, plus 1% TDS on transfers. A user wiped out by a scam wick eats 100% of it with zero deductibility. The trust damage from an identical event is strictly worse in India than anywhere else — which is why compensation policy, not just risk policy, is a competitive weapon here.",
  },
  {
    key: "sebi",
    title: "Hold ourselves to SEBI's broker glitch framework, voluntarily",
    text: "A malfunction of 5 minutes or more is a reportable technical glitch; notify within 1 hour; preliminary report T+1; RCA within 14 days; installed capacity at least 1.5x peak; alerting at 70% utilisation; DR site at least 250 km away or in a different seismic zone; glitch data retained 2 years; the glitch and its RCA are published. It maps one-to-one onto the playbook, for a compliance-first company with FIU-IND registration in flight.",
  },
  {
    key: "upi",
    title: "UPI is a dependency we do not control",
    text: "India saw 282 minutes of UPI outage across two incidents. If a user's ability to avoid liquidation depends on a UPI leg settling, we have imported NPCI's uptime into our margin system. The fix: a pre-funded instant margin credit against an initiated-but-unsettled deposit, capped and risk-scored.",
  },
  {
    key: "grievance",
    title: "Grievance redressal with published SLAs, in two languages",
    text: "Mirroring SCORES/ODR norms, plus bilingual comms on WhatsApp and Telegram — where Indian F&O traders actually are, not just X.",
  },
  {
    key: "characterisation",
    title: "Compensation has tax characterisation risk",
    text: "Credits to Indian users may be treated as income; document the treatment and, where feasible, gross up.",
  },
];

/** Research 5: why trades stand. */
export const WHY_TRADES_STAND = [
  { title: "We literally cannot reverse", text: "Fills are on-chain and non-custodial." },
  { title: "Reversal creates a second set of victims", text: "The counterparties who traded legitimately. JELLY showed the reputational bill." },
  { title: "Indian precedent is hostile to annulment", text: "SAT/Emkay, plus FSLRC's view that transactions \"should be final and not undone under any circumstances.\"" },
  { title: "Global best practice agrees", text: "CFTC/FIA: all trades stand; adjust or compensate rather than cancel." },
];

/** Research 5.2: the remedy matrix. */
export const REMEDY_MATRIX: Array<{ cls: RemedyClass; cause: string; fault: string; remedy: string }> = [
  { cls: "A", cause: "Genuine market move, healthy oracle, adequate depth", fault: "Nobody", remedy: "No remedy. Publish the evidence tape." },
  { cls: "B", cause: "Thin book, venue-local wick, but mark correctly tracked the oracle", fault: "Market structure", remedy: "No cash remedy. Fee rebate + the fix ships with a date." },
  { cls: "C", cause: "Oracle/index defect on a MochaTrade-deployed market", fault: "MochaTrade", remedy: "Full make-whole to counterfactual equity at the Reference Composite. No rollback." },
  { cls: "D", cause: "MochaTrade app/API outage prevented top-up or close", fault: "MochaTrade", remedy: "Make-whole for loss attributable to the outage window." },
  { cls: "E", cause: "UPI/PSP failure delayed a funded deposit", fault: "Shared — but we chose the rail", remedy: "Make-whole where the deposit was initiated pre-liquidation and settled later." },
  { cls: "F", cause: "Venue (Hyperliquid) defect, or ADL", fault: "Venue", remedy: "No MochaTrade cash liability. We file the evidence pack on users' behalf, publish the venue's response, and may credit goodwill at a published cap." },
  { cls: "G", cause: "Identifiable manipulation", fault: "Attacker", remedy: "Freeze what we can, report to FIU-IND and the venue, fund from the Incident Reserve, pursue recovery." },
];

/** Research 6: the first 60 minutes. */
export const FIRST_HOUR: Array<{ clock: string; phase: string; actions: string }> = [
  { clock: "0–2", phase: "Detect & declare", actions: "Auto-pager on any of: mark↔oracle divergence, liquidation rate per minute, API 5xx rate, ticket rate. Say \"SEV-1, I am IC\" out loud. The incident record opens itself." },
  { clock: "2–5", phase: "Contain — the Protect Switch", actions: "One switch, pre-authorised, no approval needed: risk-increasing orders → reduce-only; liquidation engine → TWAP throttle; max leverage → 3x; if the oracle is suspect → liquidations paused on that market only. haltTrading stays holstered — it settles everyone at mark." },
  { clock: "3", phase: "Preserve", actions: "Write-once snapshot: L2 book, trade tape, per-source oracle inputs, mark series, liquidation events, app/API telemetry, deposit queue. Also satisfies a 2-year retention standard." },
  { clock: "5", phase: "First public word", actions: "Status page → X → WhatsApp/Telegram. No cause. No blame. What we see, what we turned on, next update at HH:MM." },
  { clock: "5–15", phase: "Diagnose — all three layers", actions: "Run the APE detector: our mark vs the Reference Composite, per second, per venue. And check our own layer: app uptime, API error rate, order-reject rate, UPI settlement queue. Classify A–G." },
  { clock: "15", phase: "Update 2 + preliminary call", actions: "If it's C/D/E, say so at T+15. Owning it early is the highest-return trust action available, and the one thing a 3-person team can do faster than Binance." },
  { clock: "15–30", phase: "Quantify", actions: "Build the affected set and the counterfactual equity for each account. Get the number. Check the Incident Reserve covers it." },
  { clock: "30", phase: "Update 3 — the number", actions: "\"N users, ₹X aggregate, between HH:MM–HH:MM IST.\" Cite the APE policy that already existed." },
  { clock: "30–45", phase: "Remediate", actions: "Auto-push provisional credit to clear cases. Open the claims portal, 72-hour window. Auto-reply every open ticket with a link to their status, not a generic notice." },
  { clock: "45–60", phase: "Stabilise & reopen", actions: "Staged: reduce-only → post-only → full. Each gate requires the oracle healthy for 5 minutes and spread and depth back inside their gates. Reopen through a short auction, never straight into continuous trading." },
  { clock: "60", phase: "Handover", actions: "Publish: what happened, who's affected, what we're paying, when it lands, and the date of the full RCA." },
];

export const ROLES = [
  { role: "IC — Incident Commander", who: "CEO", duty: "Owns decisions and the clock. Does not touch a keyboard." },
  { role: "OPS — Engineering", who: "CTO", duty: "System state, kill switches, evidence capture." },
  { role: "COMMS — Support & comms", who: "Third founder", duty: "Status page, social, macros, then the claims queue." },
];

/** Research 6: the three judgment calls to defend out loud. */
export const JUDGMENT_CALLS = [
  { title: "Reduce-only, not a full halt", text: "A halt traps people; reduce-only lets them leave. The honest cost: it also blocks the trader who wanted to add margin or fade the move. We accept that cost because \"trapped while liquidating\" is the failure that ends companies — the October 2025 Binance lesson." },
  { title: "Pause liquidations only if the price is suspect", text: "Pausing liquidations while the feed is healthy does not save users; it converts their losses into our insolvency. The trigger must be oracle health, not user pain." },
  { title: "Never reverse; compensate fast instead", text: "Trades stand. People get made whole, by a rule we published first." },
];

/** Research 6: what we explicitly do NOT do at 3am. */
export const DONTS = [
  "Rewrite risk parameters live.",
  "Argue on X.",
  "Answer tickets individually.",
  "Promise a number before we've computed it.",
  "Say \"your funds are safe\" before we've verified solvency.",
  "Say \"market conditions.\"",
];

/** Research 9: what would make a user stay. */
export const WHAT_KEEPS_USERS = [
  "A number and a deadline, inside the hour — not \"we're investigating.\"",
  "Money in the account before they have to ask. A claims form is a second insult.",
  "The raw tape, so they can check our story themselves.",
  "A named human who owns it, on camera.",
  "A shipped mechanism change with a date, and a follow-up post when it ships.",
  "Not being told it was their fault for using the 50x we sold them.",
];

/** Research 4.4: what running our own HIP-3 market costs us when the oracle is wrong. */
export const HIP3_STAKE =
  "We post 500k HYPE for at least 183 days and face validator-voted slashing: up to 100% for invalid state transitions or prolonged downtime, up to 50% for brief downtime, up to 20% for network degradation. Slashed stake is burned, not paid to users. A bad oracle is not just a refund problem for us; it is a slashing event.";

/** Research 0: the levers the generic answer assumes, and whether MochaTrade has them. */
export const LEVERS: Array<{ lever: string; answer: string; ours: boolean }> = [
  { lever: "Pause the matching engine", answer: "No. HyperCore keeps matching.", ours: false },
  { lever: "Roll back or bust trades", answer: "No. Fills are on-chain and final.", ours: false },
  { lever: "Halt the venue", answer: "Only for a market we deployed under HIP-3, and haltTrading \"cancels all orders and settles positions to the current mark price\": the nuclear option, not step one.", ours: false },
  { lever: "Change the mark price", answer: "Only on our own HIP-3 market, where we set the oracle, and where a bad oracle or downtime is slashable up to 100% of a 500k HYPE stake.", ours: false },
  { lever: "Our app, API, leverage menu, margin UI, UPI rails, INR ledger, comms, money", answer: "Yes, 100%.", ours: true },
];

/** Research 0: how the business is built. */
export const BUILDER_CODES =
  "Front-ends on Hyperliquid earn through builder codes. The agent wallet \"can only execute trades and cannot move user funds.\"";

/** Research 1: why "check it against Binance" breaks on this product. */
export const OFF_HOURS =
  "Our flagship is US stock perps, trading 24/7, in IST. US cash equities are open 19:00–01:30 IST; outside that there is no spot market to compare against, and during off-hours trade.xyz becomes the primary venue. A 15% wick on a TSLA perp at 04:00 IST on a Sunday has no external reference price at all, and a stock can legitimately gap 20% on an earnings release while the cash market is shut. So \"abnormal\" is defined before the event, against a composite we publish, and when that composite cannot be built we cut leverage and widen bands before the event rather than argue after it.";

export interface Amplifier {
  n: number;
  title: string;
  evidence: string;
  /** The controls in the engine that act on it. */
  controls: string[];
}

/** Research 2: the five amplifiers. The simulator models each one, and each has a control that can be switched off. */
export const AMPLIFIERS: Amplifier[] = [
  { n: 1, title: "The liquidation engine becomes the largest seller",
    evidence: "BitMEX, March 2020: when a DDoS knocked the engine offline, the price recovered from ~$3,900 to ~$5,300, because the biggest forced seller vanished.",
    controls: ["liquidation_throttle", "two_stage_liquidation", "margin_grace_window"] },
  { n: 2, title: "Liquidity evaporates exactly when it is needed",
    evidence: "October 2025: BTC top-of-book depth shrank by more than 90%. The book you stress-test in calm markets does not exist in the crash.",
    controls: ["liquidation_throttle"] },
  { n: 3, title: "The price feed becomes the weapon",
    evidence: "October 2025: USDe printed ~$0.65 on Binance while holding ~$1.00 everywhere else; positions that were solvent at cross-venue prices were liquidated on a venue-local one.",
    controls: ["oracle_anchored_mark", "oracle_health_monitor"] },
  { n: 4, title: "Cross-margin turns one bad asset into a portfolio wipeout",
    evidence: "Unified accounts get tied to their weakest asset: a depegged collateral token liquidated whole portfolios whose individual positions were healthy.",
    controls: ["isolated_margin_default"] },
  { n: 5, title: "ADL turns a user problem into a trust problem",
    evidence: "Auto-deleveraging force-closes winning positions at the bankruptcy price, converting a hedged portfolio into a naked one during stress.",
    controls: ["two_stage_liquidation", "liquidation_throttle"] },
];

/** Research 2: the ADL findings and the trilemma. */
export const ADL_FINDINGS =
  "A December 2025 arXiv paper (2512.01112) found that on 10 October 2025 Hyperliquid's queue-based ADL imposed roughly $653M in unnecessary haircuts on winning traders — about 28× overutilisation against the optimal policy — likely contributing to the subsequent ~50% loss of open interest. It also proves a trilemma: no ADL policy can deliver exchange solvency, trader fairness and long-run revenue at the same time. You have to choose, and say which you chose.";

/** Research 4.4: the rest of what running a HIP-3 market means. */
export const HIP3_RULES = [
  "The deployer sets the oracle, the contract spec, max leverage and the fee share, and can call haltTrading, which cancels all orders and settles at the current mark.",
  "Enabling cross margin is irreversible, and it is prohibited for assets expected to move 50% in a day more than once a month. A move of more than 50% in a day triggers validator review for slashing.",
  "Each dex gets an on-chain backstop liquidator that absorbs undercollateralised positions, reducing the need for ADL.",
  "Our oracle quality is collateralised by 500,000 HYPE: we are the most exposed party to our own wick.",
];

export interface RankedChange {
  rank: number;
  change: string;
  effort: string;
  /** Engineering weeks, a working week being five days. Null when ongoing. */
  weeks: number | null;
  kills: string;
  /** Controls in the engine that implement it. Empty for policy and product changes. */
  controls: string[];
}

/** Research 8: a short set of changes, ranked by damage reduction per engineering-week. */
export const RANKED_CHANGES: RankedChange[] = [
  { rank: 1, change: "Mark = oracle-anchored composite with clamp and staleness kill. Never LTP.", effort: "1 wk", weeks: 1, kills: "Amplifier 3", controls: ["oracle_anchored_mark"] },
  { rank: 2, change: "Oracle health monitor → automatic reduce-only and liquidation pause on degradation", effort: "1 wk", weeks: 1, kills: "Amplifier 3", controls: ["oracle_health_monitor"] },
  { rank: 3, change: "Liquidation TWAP throttle + maximum participation rate of resting depth", effort: "2 wks", weeks: 2, kills: "Amplifier 1", controls: ["liquidation_throttle"] },
  { rank: 4, change: "Time-of-day leverage caps for equity perps (50x RTH → 5x off-hours)", effort: "3 d", weeks: 0.6, kills: "The product's own worst vector", controls: ["time_of_day_leverage_caps"] },
  { rank: 5, change: "Margin-call grace window + one-tap top-up + pre-funded UPI buffer", effort: "2 wks", weeks: 2, kills: "Amplifiers 1 and 5, and the UPI dependency", controls: ["margin_grace_window", "upi_prefunded_credit"] },
  { rank: 6, change: "Two-stage partial liquidation (market first, backstop only below ⅔ MM)", effort: "2 wks", weeks: 2, kills: "Amplifier 1", controls: ["two_stage_liquidation"] },
  { rank: 7, change: "Published APE policy + funded Incident Reserve", effort: "1 wk (legal/treasury)", weeks: 1, kills: "The trust crisis", controls: [] },
  { rank: 8, change: "Status page + automated incident comms + evidence snapshotter", effort: "3 d", weeks: 0.6, kills: "The trust crisis", controls: [] },
  { rank: 9, change: "Isolated-margin default for long-tail; haircuts that scale with volatility", effort: "1 wk", weeks: 1, kills: "Amplifier 4", controls: ["isolated_margin_default"] },
  { rank: 10, change: "Quarterly game-day: run this exact playbook against the simulator", effort: "ongoing", weeks: null, kills: "Everything", controls: [] },
];

/** Research 8, the note under the table. */
export const RANKED_NOTE =
  "Note how many are product decisions, not engineering: #4 and #7 are the highest-leverage items and neither requires a matching engine. That is the honest answer to \"realism for a small team.\"";

/** Research 10: the questions a judge will ask, and the answers. */
export const JUDGE_QUESTIONS: Array<{ q: string; a: string }> = [
  { q: "Isn't compensating just moral hazard?",
    a: "It would be, if it were discretionary. It isn't: it's a published test with a counterfactual, a tier table, a cap, and an explicit exclusion for normal trading losses. OKX's 2019 notice did exactly this: compensate the error window, exclude \"customers who experienced trading losses under normal circumstances.\"" },
  { q: "You can't afford Binance's $283M.",
    a: "Correct, which is why the cap is published in advance and the reserve is visible and pre-funded. An honest finite promise beats an implied infinite one." },
  { q: "Why not just halt?",
    a: "Because we don't own the engine, and because haltTrading settles everyone at the mark we are currently disputing. Halting is how you turn a pricing dispute into a settlement dispute." },
  { q: "Why not roll back?",
    a: "We can't (on-chain), we shouldn't (SAT/Emkay, CFTC/FIA), and JELLY shows what it costs when you do." },
  { q: "Your simulator's numbers are made up.",
    a: "The parameters are our proposal; the mechanisms are Binance's, CME's and Hyperliquid's published specs; and the engine is deterministic and unit-tested, so any judge can change a parameter and watch the result move." },
];
