import { Badge } from "../ui/Badge";

export type LegendMark = "line" | "thick" | "dashed" | "area" | "hatch" | "triangle";

export interface LegendItem {
  label: string;
  color: string;
  mark: LegendMark;
}

/** Each series is told apart by a drawn sample -- solid, thick, dashed, filled,
 * hatched or a marker shape -- as well as by colour, so the legend still works
 * for a reader who cannot separate the hues. */
function Sample({ color, mark }: { color: string; mark: LegendMark }) {
  switch (mark) {
    case "area":
      return <svg width="14" height="10" aria-hidden><rect x="0" y="1" width="14" height="8" rx="2" fill={color} fillOpacity={0.35} stroke={color} /></svg>;
    case "hatch":
      return (
        <svg width="14" height="10" aria-hidden>
          <rect x="0" y="1" width="14" height="8" rx="2" fill="none" stroke={color} />
          <path d="M2 9 L7 1 M6 9 L11 1 M10 9 L14 3" stroke={color} strokeWidth="1.2" />
        </svg>
      );
    case "triangle":
      return <svg width="14" height="10" aria-hidden><path d="M3 2 L11 2 L7 9 Z" fill={color} /></svg>;
    default:
      return (
        <svg width="18" height="10" aria-hidden>
          <line
            x1="0" y1="5" x2="18" y2="5" stroke={color}
            strokeWidth={mark === "thick" ? 2.5 : 1.5}
            strokeDasharray={mark === "dashed" ? "3 3" : undefined}
          />
        </svg>
      );
  }
}

export function ChartLegend({ items }: { items: LegendItem[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-2" aria-label="Legend">
      {items.map((item) => (
        <li key={item.label}>
          <Badge icon={<Sample color={item.color} mark={item.mark} />}>{item.label}</Badge>
        </li>
      ))}
    </ul>
  );
}
