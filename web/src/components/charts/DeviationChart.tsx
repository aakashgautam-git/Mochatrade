import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartLegend } from "./ChartLegend";
import { ChartTooltip } from "./ChartTooltip";
import { axisTick, minuteTicks, useChartTheme } from "./useChartTheme";

export interface DeviationPoint {
  t: number;
  bps: number;
}

interface DeviationChartProps {
  data: DeviationPoint[];
  /** The Non-Reviewable Range, in basis points. From the active policy. */
  nrrBps: number;
  nrrLabel: string;
  cursor?: number | undefined;
  height?: number;
}

/**
 * Mark minus Reference Composite, in basis points, against the published
 * Non-Reviewable Range. Outside the dashed rules is APE criterion 1: a
 * deviation large enough to be reviewed at all. The shaded bands make "outside"
 * visible without relying on the line's colour.
 */
export function DeviationChart({ data, nrrBps, nrrLabel, cursor, height = 220 }: DeviationChartProps) {
  const theme = useChartTheme();
  const extreme = Math.max(nrrBps * 1.4, ...data.map((d) => Math.abs(d.bps)));
  const bound = Math.ceil(extreme / 100) * 100;
  const outside = data.filter((d) => Math.abs(d.bps) > nrrBps).length;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <ChartLegend
          items={[
            { label: "Mark − Reference Composite", color: theme.accent, mark: "thick" },
            { label: nrrLabel, color: theme.neg, mark: "dashed" },
            { label: "Outside the range", color: theme.neg, mark: "area" },
          ]}
        />
        <p className="num text-xs text-text-dim">
          {outside} of {data.length} ticks outside
        </p>
      </div>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid stroke={theme.grid} vertical={false} />
            <ReferenceArea y1={nrrBps} y2={bound} fill={theme.neg} fillOpacity={0.08} stroke="none" ifOverflow="hidden" />
            <ReferenceArea y1={-bound} y2={-nrrBps} fill={theme.neg} fillOpacity={0.08} stroke="none" ifOverflow="hidden" />
            <ReferenceLine y={0} stroke={theme.line} />
            <ReferenceLine y={nrrBps} stroke={theme.neg} strokeDasharray="4 4" />
            <ReferenceLine y={-nrrBps} stroke={theme.neg} strokeDasharray="4 4" />
            {cursor !== undefined ? (
              <ReferenceLine x={cursor} stroke={theme.textDim} strokeDasharray="4 4" isFront />
            ) : null}
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={axisTick(theme)}
              tickLine={false}
              axisLine={{ stroke: theme.line }}
              ticks={minuteTicks(data[data.length - 1]?.t ?? 0)}
              tickFormatter={(t: number) => `${Math.round(t / 60)}m`}
            />
            <YAxis
              domain={[-bound, bound]}
              tick={axisTick(theme)}
              tickLine={false}
              axisLine={false}
              width={72}
              tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v}`}
              label={{ value: "bps", angle: -90, position: "insideLeft", fill: theme.textDim, fontSize: 11 }}
            />
            <Tooltip cursor={{ stroke: theme.line }} content={<ChartTooltip theme={theme} format={(v) => `${v > 0 ? "+" : ""}${v.toFixed(0)} bps`} />} />
            <Line type="monotone" dataKey="bps" name="Mark − Reference" stroke={theme.accent} strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
