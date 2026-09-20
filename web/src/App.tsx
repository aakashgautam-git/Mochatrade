import { useEffect, useState } from "react";

import { StatTile } from "./components/StatTile";
import { fetchComparison, fetchScenarios, rupees } from "./lib/api";
import type { Comparison, ScenarioRow } from "./lib/types";

const DEFAULT_SLUG = "oracle_defect_hip3";

export function App() {
  const [scenarios, setScenarios] = useState<ScenarioRow[]>([]);
  const [slug, setSlug] = useState(DEFAULT_SLUG);
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchScenarios().then(setScenarios).catch(() => setScenarios([]));
  }, []);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    fetchComparison(slug)
      .then((d) => live && setData(d))
      .catch(() => live && setError("Could not reach the simulator."))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [slug]);

  return (
    <div className="min-h-screen">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-4 px-6 py-6">
          <div>
            <p className="num text-xs uppercase tracking-[0.18em] text-text-faint">
              ACM MarketSphere 2026 — PS3
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">
              MochaTrade Crisis Command
            </h1>
            <p className="mt-1 text-sm text-text-dim">Trades stand. People get made whole.</p>
          </div>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs uppercase tracking-[0.14em] text-text-faint">Scenario</span>
            <select
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              className="min-w-[22rem] rounded-control border border-line bg-surface px-3 py-2 text-sm text-text outline-none transition-colors duration-fast hover:bg-surface-2 focus-visible:border-accent"
            >
              {scenarios.length === 0 && <option value={DEFAULT_SLUG}>Loading…</option>}
              {scenarios.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">
        {error && (
          <p className="rounded-card border border-neg/30 bg-neg/10 p-4 text-sm text-neg">
            {error} Is the Django server running on :8000?
          </p>
        )}

        {!error && data && (
          <>
            <section className="mb-8">
              <div className="flex flex-wrap items-center gap-2">
                <span className="num rounded-chip border border-line bg-surface-2 px-2 py-0.5 text-xs text-text-dim">
                  {data.scenario.instrument}
                </span>
                <span className="num rounded-chip border border-line bg-surface-2 px-2 py-0.5 text-xs text-text-dim">
                  {data.scenario.ist_label}
                </span>
                <span className="num rounded-chip border border-line bg-surface-2 px-2 py-0.5 text-xs text-text-dim">
                  seed {data.scenario.seed}
                </span>
                <span className="num rounded-chip border border-accent/30 bg-accent-soft px-2 py-0.5 text-xs text-accent">
                  layer: {data.scenario.layer.toUpperCase()}
                </span>
              </div>
              <p className="mt-4 max-w-4xl text-sm leading-relaxed text-text-dim">
                {data.scenario.summary}
              </p>
            </section>

            <Verdict data={data} />

            <section className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile
                label="Accounts liquidated"
                on={data.on.liquidated.toLocaleString("en-IN")}
                off={data.off.liquidated.toLocaleString("en-IN")}
                deltaPct={data.delta.liquidated_pct}
                caption={`of ${data.on.accounts_total.toLocaleString("en-IN")}`}
              />
              <StatTile
                label="User loss"
                on={rupees(data.on.user_loss_inr)}
                off={rupees(data.off.user_loss_inr)}
                deltaPct={data.delta.loss_pct}
                caption="capital destroyed"
              />
              <StatTile
                label="Unnecessary liquidations"
                on={data.on.unnecessary.toLocaleString("en-IN")}
                off={data.off.unnecessary.toLocaleString("en-IN")}
                deltaPct={data.delta.unnecessary_pct}
                caption="solvent at the composite"
              />
              <StatTile
                label="ADL events"
                on={data.on.adl.toLocaleString("en-IN")}
                off={data.off.adl.toLocaleString("en-IN")}
                deltaPct={data.delta.adl_pct}
                caption="winners force-closed"
              />
            </section>

            <p className="mt-8 max-w-4xl text-xs leading-relaxed text-text-faint">
              {data.assumed_scale_note}
            </p>
          </>
        )}

        {loading && !data && (
          <p className="num text-sm text-text-faint">Running both simulations…</p>
        )}
      </main>
    </div>
  );
}

function Verdict({ data }: { data: Comparison }) {
  return (
    <section className="rounded-card border border-line bg-surface p-8">
      <p className="text-xl font-light leading-relaxed tracking-tight text-text sm:text-2xl">
        Same shock, same seed:{" "}
        <span className="num font-medium text-neg">
          {data.off.liquidated.toLocaleString("en-IN")}
        </span>{" "}
        accounts liquidated and{" "}
        <span className="num font-medium text-neg">{rupees(data.off.user_loss_inr)}</span> lost
        without controls, versus{" "}
        <span className="num font-medium text-pos">
          {data.on.liquidated.toLocaleString("en-IN")}
        </span>{" "}
        and <span className="num font-medium text-pos">{rupees(data.on.user_loss_inr)}</span> with
        them.
      </p>
      <p className="mt-4 max-w-4xl text-sm leading-relaxed text-text-dim">
        {data.scenario.liable_layer_note}
      </p>
    </section>
  );
}
