import { useEffect, useState } from "react";

import { useApp } from "../app/store";

import { HowThisWorks } from "../components/legacy/HowThisWorks";
import { ChartLegend, PriceChart } from "../components/legacy/PriceChart";
import { StatTile } from "../components/legacy/StatTile";
import { fetchComparison, fetchScenarios, rupees } from "../lib/api";
import type { Comparison, ScenarioListItem } from "../lib/types";

const DEFAULT_SLUG = "oracle_defect_hip3";

/**
 * The screening-round demo, preserved as the fallback if round 2 comes early.
 *
 * `/demo` renders it standalone, byte-for-byte as judged. Inside the shell it
 * renders `embedded`: the shell's top bar already carries the product name, so
 * the page drops its own masthead and page-level padding and nothing else.
 * Phase 6 replaces this with the real simulator.
 */
export function LegacyDemo({ embedded = false }: { embedded?: boolean }) {
  const [scenarios, setScenarios] = useState<ScenarioListItem[]>([]);
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

  const domain = sharedDomain(data);

  const body = (
    <>
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

            <section className="mt-10">
              <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
                <h2 className="text-sm uppercase tracking-[0.14em] text-text-faint">
                  Price formation, shared clock
                </h2>
                <ChartLegend />
              </div>
              <div className="grid grid-cols-1 gap-4">
                <PriceChart
                  title="Unprotected"
                  caption={`trough ${data.off.trough_pct.toFixed(1)}%`}
                  data={data.off.series}
                  domain={domain}
                  accent="#D96A6A"
                />
                <PriceChart
                  title="Protected"
                  caption={`trough ${data.on.trough_pct.toFixed(1)}%`}
                  data={data.on.series}
                  domain={domain}
                  accent="#5FA37A"
                />
              </div>
            </section>

            <HowThisWorks />

            <p className="mt-8 max-w-4xl text-xs leading-relaxed text-text-faint">
              {data.assumed_scale_note}
            </p>
          </>
        )}

        {loading && !data && (
          <p className="num text-sm text-text-faint">Running both simulations…</p>
        )}
    </>
  );

  const setInstrument = useApp((st) => st.setInstrument);
  useEffect(() => {
    if (embedded && data) setInstrument(data.scenario.instrument);
  }, [embedded, data, setInstrument]);

  if (embedded) {
    return (
      <div>
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Overview</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">Controls off vs on</h1>
            <p className="mt-2 text-sm text-text-dim">The identical seeded shock, run twice. Trades stand. People get made whole.</p>
          </div>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs uppercase tracking-[0.14em] text-text-dim">Scenario</span>
            <select
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              className="ui-select min-w-[22rem] rounded-control border border-line bg-surface px-3 py-2 text-sm text-text transition-colors duration-fast hover:bg-surface-2"
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
        {body}
      </div>
    );
  }

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

      <main className="mx-auto max-w-6xl px-6 py-10">{body}</main>
    </div>
  );
}

/** Both panels share one y-domain, or "protected" would merely look rescaled. */
function sharedDomain(data: Comparison | null): [number, number] {
  if (!data) return [0, 1];
  const values = [...data.off.series, ...data.on.series].flatMap((p) =>
    [p.oracle, p.mark, p.ltp].filter((v): v is number => v !== null),
  );
  if (values.length === 0) return [0, 1];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = (hi - lo) * 0.06 || hi * 0.01;
  return [lo - pad, hi + pad];
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
