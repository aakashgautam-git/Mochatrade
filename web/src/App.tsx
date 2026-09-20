/**
 * Phase 0 shell. Replaced by the router and the four surfaces in Phase 2+.
 * It exists so the toolchain, the fonts and the tokens can be verified.
 */

const LAYERS = [
  {
    id: "3",
    name: "Venue",
    scope: "Hyperliquid — the book, HLP, ADL",
    control: "No control",
  },
  {
    id: "2",
    name: "Market",
    scope: "Our HIP-3 dex — oracle, margin tiers, max leverage, haltTrading",
    control: "Full control, full liability",
  },
  {
    id: "1",
    name: "Broker",
    scope: "App, API, order router, margin display, UPI on-ramp, INR ledger",
    control: "Full control",
  },
] as const;

export function App() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-8 px-6 py-16">
      <header className="space-y-2">
        <p className="num text-xs uppercase tracking-[0.18em] text-text-faint">
          ACM MarketSphere 2026 — PS3
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">MochaTrade Crisis Command</h1>
        <p className="text-text-dim">Trades stand. People get made whole.</p>
      </header>

      <section aria-label="The three layers" className="space-y-2">
        {LAYERS.map((layer) => (
          <article
            key={layer.id}
            className="flex items-baseline gap-4 rounded-card border border-line bg-surface p-4"
          >
            <span className="num text-sm text-accent">L{layer.id}</span>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-medium">{layer.name}</h2>
              <p className="text-sm text-text-dim">{layer.scope}</p>
            </div>
            <span className="num shrink-0 text-xs text-text-faint">{layer.control}</span>
          </article>
        ))}
      </section>

      <footer className="num text-xs text-text-faint">Phase 0 — skeleton</footer>
    </main>
  );
}
