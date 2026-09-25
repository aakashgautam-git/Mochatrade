import type { ChartTheme } from "./useChartTheme";

interface Row {
  name?: string | number;
  value?: number | string | Array<number | string>;
  color?: string;
}

interface Props {
  active?: boolean;
  payload?: Row[];
  label?: number | string;
  theme: ChartTheme;
  labelPrefix?: string;
  format?: (v: number) => string;
}

/** The one tooltip every chart uses. Not Recharts' default box. */
export function ChartTooltip({ active, payload, label, theme, labelPrefix = "T+", format }: Props) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-control border border-line px-3 py-2 text-xs"
      style={{ background: theme.surface2, color: theme.text }}
    >
      <p className="num text-text-dim">{labelPrefix}{label}s</p>
      <ul className="mt-1.5 space-y-1">
        {payload.map((row) => {
          const v = typeof row.value === "number" ? row.value : Number(row.value);
          return (
            <li key={String(row.name)} className="flex items-center justify-between gap-6">
              <span className="flex items-center gap-2 text-text-dim">
                <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ background: row.color }} />
                {row.name}
              </span>
              <span className="num text-text">
                {Number.isFinite(v) ? (format ? format(v) : v.toLocaleString("en-IN", { maximumFractionDigits: 2 })) : "—"}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
