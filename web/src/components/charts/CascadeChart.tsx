import { useId } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartLegend } from "./ChartLegend";
import { rupees } from "../../lib/api";
import { ChartTooltip } from "./ChartTooltip";
import { axisTick, minuteTicks, useChartTheme } from "./useChartTheme";

export interface CascadePoint {
  t: number;
  partial: number;
  market: number;
  backstop: number;
  adl: number;
}

/**
 * Liquidations per tick, stacked by where in the waterfall they happened.
 * Market closes at the bottom, the punitive backstop above, ADL on top and
 * HATCHED -- because ADL closes the winners, and the one layer that is a trust
 * problem rather than a user problem should look different, not just be a
 * different colour.
 */
export function CascadeChart({ data, cursor, height = 220 }: { data: CascadePoint[]; cursor?: number | undefined; height?: number }) {
  const theme = useChartTheme();
  const hatch = `hatch-${useId().replace(/:/g, "")}`;

  return (
    <div>
      <div className="mb-4">
        <ChartLegend
          items={[
            { label: "Partial — stage one, fee-free", color: theme.pos, mark: "area" },
            { label: "Market", color: theme.accent, mark: "area" },
            { label: "Backstop", color: theme.warn, mark: "area" },
            { label: "ADL — winners closed", color: theme.neg, mark: "hatch" },
          ]}
        />
      </div>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <defs>
              <pattern id={hatch} patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
                <rect width="6" height="6" fill={theme.neg} fillOpacity={0.18} />
                <line x1="0" y1="0" x2="0" y2="6" stroke={theme.neg} strokeWidth="2" />
              </pattern>
            </defs>
            <CartesianGrid stroke={theme.grid} vertical={false} />
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
              tick={axisTick(theme)}
              tickLine={false}
              axisLine={false}
              width={56}
              // At least a lakh tall, so an empty cascade does not print 0.0L four times.
              domain={[0, (max: number) => Math.max(max, 1_00_000)]}
              tickFormatter={(v: number) => (v === 0 ? "0" : `${(v / 1_00_000).toFixed(1)}L`)}
            />
            <Tooltip
              cursor={{ stroke: theme.line }}
              content={<ChartTooltip theme={theme} format={rupees} />}
            />
            {cursor !== undefined ? (
              <ReferenceLine x={cursor} stroke={theme.textDim} strokeDasharray="4 4" isFront />
            ) : null}
            <Area type="stepAfter" dataKey="partial" name="Partial" stackId="w" stroke={theme.pos} fill={theme.pos} fillOpacity={0.3} isAnimationActive={false} />
            <Area type="stepAfter" dataKey="market" name="Market" stackId="w" stroke={theme.accent} fill={theme.accent} fillOpacity={0.3} isAnimationActive={false} />
            <Area type="stepAfter" dataKey="backstop" name="Backstop" stackId="w" stroke={theme.warn} fill={theme.warn} fillOpacity={0.3} isAnimationActive={false} />
            <Area type="stepAfter" dataKey="adl" name="ADL" stackId="w" stroke={theme.neg} fill={`url(#${hatch})`} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
