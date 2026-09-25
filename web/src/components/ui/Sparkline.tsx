import { Line, LineChart, ReferenceDot, XAxis, YAxis } from "recharts";

import { useChartTheme } from "../charts/useChartTheme";
import type { Tone } from "./tone";

interface SparklineProps {
  data: number[];
  tone?: Exclude<Tone, "halt">;
  width?: number;
  height?: number;
  /** Required: a sparkline has no axes, so the label is its only description. */
  label: string;
}

/** A tiny trend line with no axes and an end marker. */
export function Sparkline({ data, tone = "accent", width = 96, height = 28, label }: SparklineProps) {
  const theme = useChartTheme();
  const color = tone === "neutral" ? theme.textDim : theme[tone];
  const points = data.map((v, i) => ({ i, v }));
  const last = points[points.length - 1];
  return (
    <span role="img" aria-label={label} className="inline-block align-middle">
      <LineChart width={width} height={height} data={points} margin={{ top: 3, right: 4, bottom: 3, left: 1 }}>
        <XAxis dataKey="i" type="number" domain={["dataMin", "dataMax"]} hide />
        <YAxis type="number" domain={["dataMin", "dataMax"]} hide />
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        {last ? <ReferenceDot x={last.i} y={last.v} r={2} fill={color} stroke="none" /> : null}
      </LineChart>
    </span>
  );
}
