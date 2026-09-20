const LAYERS = [
  {
    id: "3",
    name: "Venue",
    scope: "Hyperliquid — the shared book, HLP, ADL",
    power: "No control",
  },
  {
    id: "2",
    name: "Market",
    scope: "The HIP-3 dex we deploy — oracle, margin tiers, max leverage, haltTrading",
    power: "Full control, full liability",
  },
  {
    id: "1",
    name: "Broker",
    scope: "Our app, API, order router, margin display, UPI on-ramp, INR ledger",
    power: "Full control",
  },
];

export function HowThisWorks() {
  return (
    <section className="mt-10 rounded-card border border-line bg-surface p-8">
      <h2 className="text-sm uppercase tracking-[0.14em] text-text-faint">How this works</h2>

      <p className="mt-4 max-w-4xl text-sm leading-relaxed text-text-dim">
        MochaTrade is not an exchange. It is a non-custodial broker built on Hyperliquid, so it
        cannot pause a matching engine and it cannot roll back a trade — fills are on-chain and
        final. Minute one is not “what did the market do”, it is{" "}
        <span className="text-text">which of our three layers broke</span>, because that decides
        whether we can act at all and whether we owe anybody money.
      </p>

      <ul className="mt-6 space-y-2">
        {LAYERS.map((layer) => (
          <li
            key={layer.id}
            className="flex flex-wrap items-baseline gap-x-4 gap-y-1 rounded-control border border-line bg-surface-2 px-4 py-3"
          >
            <span className="num text-sm text-accent">L{layer.id}</span>
            <span className="text-sm font-medium">{layer.name}</span>
            <span className="min-w-0 flex-1 text-sm text-text-dim">{layer.scope}</span>
            <span className="num text-xs text-text-faint">{layer.power}</span>
          </li>
        ))}
      </ul>

      <p className="mt-8 text-lg font-light tracking-tight text-text">
        Trades stand. People get made whole.
      </p>
      <p className="mt-2 max-w-4xl text-sm leading-relaxed text-text-dim">
        Never reverse, always compensate, decide by a rule published first. Reversal is
        unavailable on-chain, it creates a second set of victims among the counterparties who
        traded legitimately, Indian precedent is hostile to annulment, and CFTC/FIA best practice
        is that all trades stand with price adjustment preferred over cancellation.
      </p>

      <p className="mt-6 max-w-4xl text-xs leading-relaxed text-text-faint">
        Both runs above use the same seed, the same shock and the same order book; the only
        difference is the risk-control stack. The parameters are our proposal — the mechanisms are
        the published specifications of Binance, CME/CFTC-FIA and Hyperliquid, and the engine is
        deterministic and unit-tested, so any parameter can be changed and the result recomputed.
      </p>
    </section>
  );
}
