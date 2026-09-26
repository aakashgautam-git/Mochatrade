import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartLegend, type LegendItem } from "./ChartLegend";
import { ChartTooltip } from "./ChartTooltip";
import { axisTick, minuteTicks, useChartTheme } from "./useChartTheme";

export interface PricePoint {
  t: number;
  oracle: number | null;
  mark: number;
  ltp: number;
}

export interface ControlRegion {
  from: number;
  to: number;
  label: string;
  /** Halt for interventions (pauses, halts); warn for reduce-only. */
  tone: "halt" | "warn";
}

export interface LiquidationBurst {
  t: number;
  price: number;
  count: number;
}

interface PriceChartProps {
  data: PricePoint[];
  regions?: ControlRegion[] | undefined;
  bursts?: LiquidationBurst[] | undefined;
  cursor?: number | undefined;
  auctions?: { t: number; price: number }[] | undefined;
  height?: number;
  domain?: [number, number] | undefined;
  showLegend?: boolean;
}

const price = (v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 0 });

/** Round-number y ticks inside [lo, hi], so the lane above carries no label. */
function niceTicks(lo: number, hi: number, count = 5): number[] {
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
  return out;
}

/**
 * Oracle, mark and last-traded price on one clock.
 *
 * Control activity is drawn as a lane across the top of the plot, one segment
 * per real span. Full-height shading was tried first and was misleading: a
 * protected run can pause 56 times for five seconds each, and full-height bands
 * either stripe the whole chart like a barcode or, merged, claim a control was
 * on for eleven minutes when the market was stuttering. The lane shows the
 * rhythm without covering the prices.
 *
 * Downward markers are liquidation bursts, sized by accounts closed. The three
 * lines differ by weight and dash as well as colour: the mark is the thick line
 * because it is the price that actually liquidates people.
 */
export function PriceChart({ data, regions = [], bursts = [], cursor, auctions = [], height = 280, domain, showLegend = true }: PriceChartProps) {
  const theme = useChartTheme();

  const legend: LegendItem[] = [
    { label: "Reference composite", color: theme.pos, mark: "line" },
    { label: "Mark", color: theme.accent, mark: "thick" },
    { label: "Last traded", color: theme.neg, mark: "dashed" },
  ];
  for (const label of [...new Set(regions.map((r) => r.label))]) {
    const spans = regions.filter((r) => r.label === label);
    const tone = spans[0]?.tone === "warn" ? theme.warn : theme.halt;
    legend.push({ label: spans.length > 1 ? `${label} ×${spans.length}` : label, color: tone, mark: "area" });
  }
  if (auctions.length) legend.push({ label: "Reopening auction", color: theme.accent, mark: "diamond" as any });
  if (bursts.length) legend.push({ label: "Liquidation burst", color: theme.neg, mark: "triangle" });

  const biggest = Math.max(1, ...bursts.map((b) => b.count));

  // Own the y-domain so the control lane can sit above the highest price.
  const values = data.flatMap((d) => [d.oracle, d.mark, d.ltp]).filter((v): v is number => v !== null);
  const lo = domain ? domain[0] : Math.min(...values);
  const hi = domain ? domain[1] : Math.max(...values);
  const pad = (hi - lo) * 0.06 || hi * 0.01;
  const laneBottom = hi + pad;
  const laneTop = laneBottom + (hi - lo + 2 * pad) * 0.07;
  const maxT = data.length ? (data[data.length - 1]?.t ?? 0) : 0;

  return (
    <div>
      {showLegend ? <div className="mb-4"><ChartLegend items={legend} /></div> : null}
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 16, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid stroke={theme.grid} vertical={false} />
            {regions.length ? (
              <ReferenceArea y1={laneBottom} y2={laneTop} fill={theme.surface2} fillOpacity={1} stroke="none" />
            ) : null}
            {regions.map((r) => (
              <ReferenceArea
                key={`${r.label}-${r.from}`}
                x1={r.from}
                x2={r.to + 1}
                y1={laneBottom}
                y2={laneTop}
                fill={r.tone === "halt" ? theme.halt : theme.warn}
                fillOpacity={0.6}
                stroke="none"
                ifOverflow="hidden"
              />
            ))}
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={axisTick(theme)}
              tickLine={false}
              axisLine={{ stroke: theme.line }}
              ticks={minuteTicks(maxT)}
              tickFormatter={(t: number) => `${Math.round(t / 60)}m`}
            />
            <YAxis
              domain={regions.length ? [lo - pad, laneTop] : [lo - pad, hi + pad]}
              ticks={niceTicks(lo, hi)}
              tick={axisTick(theme)}
              tickLine={false}
              axisLine={false}
              width={72}
              tickFormatter={price}
            />
            <Tooltip
              cursor={{ stroke: theme.line }}
              content={<ChartTooltip theme={theme} format={price} />}
            />
            {cursor !== undefined ? (
              <ReferenceLine x={cursor} stroke={theme.textDim} strokeDasharray="4 4" isFront />
            ) : null}
            <Line type="monotone" dataKey="oracle" name="Reference composite" stroke={theme.pos} strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
            <Line type="monotone" dataKey="ltp" name="Last traded" stroke={theme.neg} strokeWidth={1} strokeDasharray="3 3" dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="mark" name="Mark" stroke={theme.accent} strokeWidth={2.25} dot={false} isAnimationActive={false} />
            {bursts.map((b) => {
              const size = 3 + 4 * Math.sqrt(b.count / biggest);
              return (
                <ReferenceDot
                  key={`burst-${b.t}`}
                  x={b.t}
                  y={b.price}
                  ifOverflow="extendDomain"
                  shape={(props: { cx?: number; cy?: number }) => {
                    const cx = props.cx ?? 0;
                    const cy = (props.cy ?? 0) - size - 4;
                    return (
                      <path
                        d={`M${cx - size} ${cy - size} L${cx + size} ${cy - size} L${cx} ${cy + size * 0.6} Z`}
                        fill={theme.neg}
                        stroke={theme.bg}
                        strokeWidth={1}
                      >
                        <title>{`${b.count} accounts liquidated at T+${b.t}s`}</title>
                      </path>
                    );
                  }}
                />
              );
            })}
            {auctions.map((a, i) => (
              <ReferenceDot
                key={`auction-${a.t}-${i}`}
                x={a.t}
                y={a.price}
                ifOverflow="extendDomain"
                shape={(props: { cx?: number; cy?: number }) => {
                  const cx = props.cx ?? 0;
                  const cy = props.cy ?? 0;
                  const s = 4.5;
                  return (
                    <path
                      d={`M${cx} ${cy - s} L${cx + s} ${cy} L${cx} ${cy + s} L${cx - s} ${cy} Z`}
                      fill={theme.accent}
                      stroke={theme.bg}
                      strokeWidth={1}
                    >
                      <title>{`Reopening auction at T+${a.t}s`}</title>
                    </path>
                  );
                }}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
