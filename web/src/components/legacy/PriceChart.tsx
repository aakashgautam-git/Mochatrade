import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { SeriesPoint } from "../../lib/types";

interface Props {
  title: string;
  caption: string;
  data: SeriesPoint[];
  domain: [number, number];
  accent: string;
}

const AXIS = "#6B625B";

export function PriceChart({ title, caption, data, domain, accent }: Props) {
  return (
    <figure className="rounded-card border border-line bg-surface p-5">
      <figcaption className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium" style={{ color: accent }}>
          {title}
        </h3>
        <p className="num text-xs text-text-faint">{caption}</p>
      </figcaption>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis
              dataKey="t"
              stroke={AXIS}
              tick={{ fill: AXIS, fontSize: 11, fontFamily: "JetBrains Mono" }}
              tickLine={false}
              axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
              tickFormatter={(t: number) => `${Math.round(t / 60)}m`}
            />
            <YAxis
              domain={domain}
              stroke={AXIS}
              tick={{ fill: AXIS, fontSize: 11, fontFamily: "JetBrains Mono" }}
              tickLine={false}
              axisLine={false}
              width={62}
              tickFormatter={(v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
            />
            <Tooltip
              contentStyle={{
                background: "#262220",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 8,
                fontSize: 12,
                fontFamily: "JetBrains Mono",
              }}
              labelStyle={{ color: "#A79E96" }}
              labelFormatter={(t) => `T+${t}s`}
              formatter={(v: number, name: string) => [
                v?.toLocaleString("en-IN", { maximumFractionDigits: 2 }),
                name,
              ]}
            />
            <Line
              type="monotone"
              dataKey="oracle"
              name="Reference composite"
              stroke="#5FA37A"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="mark"
              name="Mark"
              stroke="#C98A5E"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="ltp"
              name="Last traded"
              stroke="#D96A6A"
              strokeWidth={1}
              strokeDasharray="3 3"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

export function ChartLegend() {
  const items = [
    { label: "Reference composite", colour: "#5FA37A", dashed: false },
    { label: "Mark (what liquidates you)", colour: "#C98A5E", dashed: false },
    { label: "Last traded price", colour: "#D96A6A", dashed: true },
  ];
  return (
    <ul className="flex flex-wrap items-center gap-x-6 gap-y-2">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-2 text-xs text-text-dim">
          <span
            aria-hidden
            className="inline-block h-0 w-6 shrink-0"
            style={{
              borderTop: `2px ${item.dashed ? "dashed" : "solid"} ${item.colour}`,
            }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
