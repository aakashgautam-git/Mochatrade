import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, useRef } from "react";
import { Play, Pause, RotateCcw } from "lucide-react";

import { fetchActivePolicy, fetchCompare, fetchScenarios, parseMoney, rupees } from "../lib/api";
import { useApp } from "../app/store";
import { Button, Badge, Select, Slider, Stat, Timeline, EmptyState, Skeleton, Toggle } from "../components/ui";
import { PriceChart, DeviationChart, CascadeChart, DepthLadder } from "../components/charts";
import {
  cascadeSeries,
  controlRegions,
  deviationSeries,
  eventsUpTo,
  ladderAt,
  liquidationBursts,
  nrrFor,
  prefixSum,
  priceSeries,
  sharedPriceDomain,
  stateAt,
  auctionMarkers,
} from "../lib/sim";

function usePlayback(max: number, speed: number, playing: boolean, setPlaying: (b: boolean) => void) {
  const [t, setT] = useState(0);
  const lastTime = useRef<number | null>(null);
  const accum = useRef<number>(0);

  useEffect(() => {
    if (!playing || max === 0) {
      lastTime.current = null;
      return;
    }

    let frame: number;
    const step = (now: number) => {
      if (lastTime.current !== null) {
        const dt = now - lastTime.current;
        accum.current += (dt / 1000) * speed;
        if (accum.current >= 1) {
          const ticks = Math.floor(accum.current);
          accum.current -= ticks;
          setT((curr) => {
            const next = curr + ticks;
            if (next >= max) {
              setPlaying(false);
              return max;
            }
            return next;
          });
        }
      }
      lastTime.current = now;
      frame = requestAnimationFrame(step);
    };

    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, max, setPlaying]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement || e.target instanceof HTMLButtonElement) {
        // Only ignore if the user is typing in a text input (but buttons/selects might eat space)
        if (e.target instanceof HTMLInputElement && e.target.type !== "radio" && e.target.type !== "checkbox") return;
      }
      if (e.key === " ") {
        e.preventDefault();
        if (t >= max && !playing) setT(0);
        setPlaying(!playing);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setPlaying(false);
        setT((curr) => Math.max(0, curr - (e.shiftKey ? 10 : 1)));
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setPlaying(false);
        setT((curr) => Math.min(max, curr + (e.shiftKey ? 10 : 1)));
      } else if (e.key === "Home") {
        e.preventDefault();
        setT(0);
      } else if (e.key === "End") {
        e.preventDefault();
        setT(max);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [playing, max, t, setPlaying]);

  return { t, setT };
}

export function Simulator() {
  const setInstrument = useApp((s) => s.setInstrument);
  const [scenarioSlug, setScenarioSlug] = useState("oracle_defect_hip3");
  const [speed, setSpeed] = useState("10");
  const [playing, setPlaying] = useState(false);
  const [showProtectedLog, setShowProtectedLog] = useState(true);

  const policyReq = useQuery({ queryKey: ["policy", "active"], queryFn: fetchActivePolicy });
  const scenariosReq = useQuery({ queryKey: ["scenarios"], queryFn: fetchScenarios });
  const compareReq = useQuery({ queryKey: ["compare", scenarioSlug], queryFn: () => fetchCompare(scenarioSlug) });

  const detailReq = useQuery({
    queryKey: ["scenarios", scenarioSlug, "detail"],
    queryFn: async () => {
      const res = await fetch(`/api/scenarios/${scenarioSlug}/`);
      if (!res.ok) throw new Error("Failed to load scenario detail");
      return res.json();
    }
  });

  useEffect(() => {
    if (detailReq.data) {
      setInstrument(detailReq.data.instrument_symbol);
    }
  }, [detailReq.data, setInstrument]);

  // Derivations
  const derived = useMemo(() => {
    if (!compareReq.data) return null;
    const { on, off } = compareReq.data;
    return {
      len: Math.min(on.ticks.length, off.ticks.length) - 1,
      on: {
        price: priceSeries(on.ticks),
        deviation: deviationSeries(on.ticks),
        cascade: cascadeSeries(on.ticks),
        regions: controlRegions(on.ticks),
        bursts: liquidationBursts(on.ticks),
        auctions: auctionMarkers(on.ticks),
        unnec: prefixSum(on.ticks, "unnecessary_liquidations"),
        events: eventsUpTo(on.ticks, on.ticks.length, "on"),
        ticks: on.ticks,
        summary: on.summary,
      },
      off: {
        price: priceSeries(off.ticks),
        deviation: deviationSeries(off.ticks),
        cascade: cascadeSeries(off.ticks),
        regions: controlRegions(off.ticks),
        bursts: liquidationBursts(off.ticks),
        auctions: auctionMarkers(off.ticks),
        unnec: prefixSum(off.ticks, "unnecessary_liquidations"),
        events: eventsUpTo(off.ticks, off.ticks.length, "off"),
        ticks: off.ticks,
        summary: off.summary,
      },
      domain: sharedPriceDomain(off.ticks, on.ticks),
    };
  }, [compareReq.data]);

  const maxTicks = derived ? derived.len : 0;
  const { t, setT } = usePlayback(maxTicks, Number(speed), playing, setPlaying);

  if (policyReq.isError || scenariosReq.isError || compareReq.isError) {
    return (
      <div className="mx-auto max-w-4xl py-12">
        <EmptyState title="API Unreachable" description="Start Django and run `make seed`." icon={<Pause />} />
      </div>
    );
  }

  if (!derived || !policyReq.data || !detailReq.data) {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-20 w-full" />
        <div className="grid gap-6 xl:grid-cols-2">
          <Skeleton className="h-[800px] w-full" />
          <Skeleton className="h-[800px] w-full" />
        </div>
      </div>
    );
  }

  const { on, off, domain } = derived;
  const nrr = nrrFor(policyReq.data, detailReq.data);
  const onTick = on.ticks[t]!;
  const offTick = off.ticks[t]!;
  const onState = stateAt(onTick);
  const offState = stateAt(offTick);
  const onLadder = ladderAt(onTick);
  const offLadder = ladderAt(offTick);

  // Memoize chart props to throttle re-renders (at most 10Hz)
  const slicedOn = {
    price: on.price.slice(0, t + 1),
    deviation: on.deviation.slice(0, t + 1),
    cascade: on.cascade.slice(0, t + 1),
    auctions: on.auctions.filter((a) => a.t <= t),
    bursts: on.bursts.filter((b) => b.t <= t),
  };
  const slicedOff = {
    price: off.price.slice(0, t + 1),
    deviation: off.deviation.slice(0, t + 1),
    cascade: off.cascade.slice(0, t + 1),
    auctions: off.auctions.filter((a) => a.t <= t),
    bursts: off.bursts.filter((b) => b.t <= t),
  };

  const countDuration = playing ? Math.min(400, (1000 / Number(speed)) * 0.8) : 400;

  return (
    <div className="mx-auto max-w-7xl">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0 max-w-md">
          <Select
            label="Scenario"
            value={scenarioSlug}
            onChange={(val) => {
              setScenarioSlug(val);
              setT(0);
              setPlaying(false);
            }}
            options={scenariosReq.data?.map((s) => ({ value: s.slug, label: s.name })) ?? []}
          />
          <p className="mt-2 text-xs leading-relaxed text-text-dim">
            {detailReq.data.description}
            <br />
            <span className="opacity-70">{detailReq.data.assumed_scale_note}</span>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge mono>IST</Badge>
          <Badge mono>{detailReq.data.instrument.has_rth && detailReq.data.is_offhours ? "off-hours" : detailReq.data.instrument.has_rth ? "RTH" : "crypto"}</Badge>
          <Badge mono>{detailReq.data.layer} failure</Badge>
          <Badge mono>seed {detailReq.data.rng_seed}</Badge>
          <Badge mono>policy v{policyReq.data.version}</Badge>
        </div>
      </header>

      <div className="sticky top-[56px] z-20 mb-8 flex flex-wrap items-center gap-4 rounded-card border border-line bg-surface/95 px-6 py-4 backdrop-blur">
        <Button variant="primary" icon={playing ? <Pause /> : <Play />} onClick={() => { if (t >= maxTicks && !playing) setT(0); setPlaying(!playing); }}>
          {playing ? "Pause" : "Play"}
        </Button>
        <Button icon={<RotateCcw />} onClick={() => { setT(0); setPlaying(false); }}>Reset</Button>
        <Button size="sm" onClick={() => setT(Math.max(0, t - 10))}>−10</Button>
        <Button size="sm" onClick={() => setT(Math.max(0, t - 1))}>−1</Button>
        <div className="w-48 shrink-0">
          <Slider
            label=""
            value={t}
            min={0}
            max={maxTicks}
            onChange={(val) => { setT(val); setPlaying(false); }}
            format={(v) => `T+${v}s`}
          />
        </div>
        <Button size="sm" onClick={() => setT(Math.min(maxTicks, t + 1))}>+1</Button>
        <Button size="sm" onClick={() => setT(Math.min(maxTicks, t + 10))}>+10</Button>
        <div className="ml-auto w-32">
          <Select
            label=""
            value={speed}
            onChange={setSpeed}
            options={[
              { value: "1", label: "1×" },
              { value: "5", label: "5×" },
              { value: "10", label: "10×" },
              { value: "30", label: "30×" },
            ]}
          />
        </div>
      </div>

      <div className="grid gap-8 xl:grid-cols-2">
        {/* UNPROTECTED COLUMN */}
        <section className="space-y-6">
          <div className="flex items-center justify-between border-b border-line pb-4">
            <h2 className="text-lg font-semibold tracking-tight">Unprotected</h2>
            <Badge tone={offState.tone}>{offState.label}</Badge>
          </div>
          
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-card border border-line bg-surface p-4">
              <Stat label="Accounts liquidated" value={offTick.cum_liquidated_accounts} duration={countDuration} delta={{ pct: (offTick.cum_liquidated_accounts - onTick.cum_liquidated_accounts) / Math.max(1, onTick.cum_liquidated_accounts) * 100, goodWhen: "down" }} baseline={{ value: onTick.cum_liquidated_accounts, label: "protected" }} />
            </div>
            <div className="rounded-card border border-line bg-surface p-4">
              <Stat label="Unnecessary liquidations" value={off.unnec[t]!} duration={countDuration} delta={{ pct: (off.unnec[t]! - on.unnec[t]!) / Math.max(1, on.unnec[t]!) * 100, goodWhen: "down" }} baseline={{ value: on.unnec[t]!, label: "protected" }} />
            </div>
            <div className="rounded-card border border-line bg-surface p-4">
              <Stat label="ADL events" value={offTick.adl_accounts} duration={countDuration} delta={{ pct: (offTick.adl_accounts - onTick.adl_accounts) / Math.max(1, onTick.adl_accounts) * 100, goodWhen: "down" }} baseline={{ value: onTick.adl_accounts, label: "protected" }} />
            </div>
            <div className="rounded-card border border-line bg-surface p-4">
              <Stat label="Depth of baseline" value={Math.round(offTick.depth_pct_of_baseline * 100)} duration={countDuration} delta={{ pct: Math.round(offTick.depth_pct_of_baseline * 100) - Math.round(onTick.depth_pct_of_baseline * 100), goodWhen: "up" }} baseline={{ value: Math.round(onTick.depth_pct_of_baseline * 100), label: "protected" }} format={(n) => `${n}%`} />
            </div>
          </div>

          <div className="rounded-card border border-line bg-surface p-4">
            <h3 className="mb-4 text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Price & Control</h3>
            <PriceChart data={slicedOff.price} cursor={t} regions={off.regions} bursts={slicedOff.bursts} auctions={slicedOff.auctions} domain={domain} />
          </div>

          <div className="rounded-card border border-line bg-surface p-4">
            <h3 className="mb-4 text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Cascade (Lakh)</h3>
            <CascadeChart data={slicedOff.cascade} cursor={t} />
          </div>

          <div className="rounded-card border border-line bg-surface p-4">
            <h3 className="mb-4 text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Deviation</h3>
            <DeviationChart data={slicedOff.deviation} cursor={t} nrrBps={nrr.bps} nrrLabel={nrr.label} />
          </div>

          <div className="rounded-card border border-line bg-surface p-4">
            <h3 className="mb-4 text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Resting Depth</h3>
            {offLadder ? <DepthLadder levels={offLadder.levels} mid={offLadder.mid} spreadBps={offLadder.spreadBps} depthOfBaseline={offLadder.depthOfBaseline} /> : <div className="h-64 flex items-center justify-center text-text-dim">No depth</div>}
          </div>
        </section>

        {/* PROTECTED COLUMN */}
        <section className="space-y-6">
          <div className="flex items-center justify-between border-b border-line pb-4">
            <h2 className="text-lg font-semibold tracking-tight">Protected</h2>
            <Badge tone={onState.tone}>{onState.label}</Badge>
          </div>
          
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-card border border-line bg-surface p-4">
              <Stat label="Accounts liquidated" value={onTick.cum_liquidated_accounts} duration={countDuration} delta={{ pct: (onTick.cum_liquidated_accounts - offTick.cum_liquidated_accounts) / Math.max(1, offTick.cum_liquidated_accounts) * 100, goodWhen: "down" }} baseline={{ value: offTick.cum_liquidated_accounts, label: "unprotected" }} />
            </div>
            <div className="rounded-card border border-line bg-surface p-4">
              <Stat label="Unnecessary liquidations" value={on.unnec[t]!} duration={countDuration} delta={{ pct: (on.unnec[t]! - off.unnec[t]!) / Math.max(1, off.unnec[t]!) * 100, goodWhen: "down" }} baseline={{ value: off.unnec[t]!, label: "unprotected" }} />
            </div>
            <div className="rounded-card border border-line bg-surface p-4">
              <Stat label="ADL events" value={onTick.adl_accounts} duration={countDuration} delta={{ pct: (onTick.adl_accounts - offTick.adl_accounts) / Math.max(1, offTick.adl_accounts) * 100, goodWhen: "down" }} baseline={{ value: offTick.adl_accounts, label: "unprotected" }} />
            </div>
            <div className="rounded-card border border-line bg-surface p-4">
              <Stat label="Depth of baseline" value={Math.round(onTick.depth_pct_of_baseline * 100)} duration={countDuration} delta={{ pct: Math.round(onTick.depth_pct_of_baseline * 100) - Math.round(offTick.depth_pct_of_baseline * 100), goodWhen: "up" }} baseline={{ value: Math.round(offTick.depth_pct_of_baseline * 100), label: "unprotected" }} format={(n) => `${n}%`} />
            </div>
          </div>

          <div className="rounded-card border border-line bg-surface p-4">
            <h3 className="mb-4 text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Price & Control</h3>
            <PriceChart data={slicedOn.price} cursor={t} regions={on.regions} bursts={slicedOn.bursts} auctions={slicedOn.auctions} domain={domain} />
          </div>

          <div className="rounded-card border border-line bg-surface p-4">
            <h3 className="mb-4 text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Cascade (Lakh)</h3>
            <CascadeChart data={slicedOn.cascade} cursor={t} />
          </div>

          <div className="rounded-card border border-line bg-surface p-4">
            <h3 className="mb-4 text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Deviation</h3>
            <DeviationChart data={slicedOn.deviation} cursor={t} nrrBps={nrr.bps} nrrLabel={nrr.label} />
          </div>

          <div className="rounded-card border border-line bg-surface p-4">
            <h3 className="mb-4 text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Resting Depth</h3>
            {onLadder ? <DepthLadder levels={onLadder.levels} mid={onLadder.mid} spreadBps={onLadder.spreadBps} depthOfBaseline={onLadder.depthOfBaseline} /> : <div className="h-64 flex items-center justify-center text-text-dim">No depth</div>}
          </div>
        </section>
      </div>

      <div className="mt-12 space-y-8 border-t border-line pt-8">
        <div>
          <h2 className="mb-4 text-lg font-semibold tracking-tight">At the close</h2>
          <p className="text-base text-text">
            Same shock, same seed: {off.summary.accounts_liquidated.toLocaleString("en-IN")} accounts liquidated and {rupees(parseMoney(off.summary.user_loss_inr))} lost without controls, versus {on.summary.accounts_liquidated.toLocaleString("en-IN")} and {rupees(parseMoney(on.summary.user_loss_inr))} with them.
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-2">
          <div>
            <h2 className="mb-4 text-lg font-semibold tracking-tight">Oracle at T+{t}s</h2>
            <div className="rounded-card border border-line bg-surface overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-xs font-medium uppercase tracking-[0.12em] text-text-dim">
                    <th className="px-4 py-3">Source</th>
                    <th className="px-4 py-3">Rung</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Raw price</th>
                    <th className="px-4 py-3 text-right">Used price</th>
                  </tr>
                </thead>
                <tbody>
                  {onTick.sources.map((src, i) => (
                    <tr key={i} className="border-b border-line last:border-0">
                      <td className="px-4 py-3">{src.source}</td>
                      <td className="num px-4 py-3">{src.rung}</td>
                      <td className="px-4 py-3">
                        {src.weight > 0 ? (
                          src.clamped ? <Badge tone="warn">Clamped</Badge> : <Badge tone="pos">Used</Badge>
                        ) : (
                          <Badge tone="neg">{src.excluded_reason || "Excluded"}</Badge>
                        )}
                      </td>
                      <td className="num px-4 py-3 text-right text-text-dim">{src.raw_price !== null ? src.raw_price.toLocaleString("en-IN", { maximumFractionDigits: 1 }) : "—"}</td>
                      <td className="num px-4 py-3 text-right">{src.price !== null ? src.price.toLocaleString("en-IN", { maximumFractionDigits: 1 }) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold tracking-tight">Event Feed</h2>
              <Toggle checked={showProtectedLog} onChange={setShowProtectedLog} label="Show protected" readout={false} />
            </div>
            <div className="rounded-card border border-line bg-surface p-6">
              <Timeline items={(showProtectedLog ? on.events : off.events).filter((e) => e.tick <= t).map((e) => ({
                id: e.id,
                time: `T+${e.tick}s`,
                actor: "SYS",
                action: e.action,
                rationale: e.detail,
                tone: e.tone,
              }))} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
