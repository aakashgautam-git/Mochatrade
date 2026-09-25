import { Badge } from "../ui/Badge";
import { useChartTheme } from "./useChartTheme";

export interface DepthLevel {
  price: number;
  /** Resting notional at this level, in INR. */
  size: number;
  side: "bid" | "ask";
}

interface DepthLadderProps {
  levels: DepthLevel[];
  mid: number;
  spreadBps: number;
  /** Resting depth as a fraction of the calm baseline, 0-1. */
  depthOfBaseline?: number | undefined;
}

const ROW = 24;
const W = 560;
const CENTER = 104;
const HALF = (W - CENTER) / 2;

const lakh = (n: number) => `${(n / 1_00_000).toFixed(1)}L`;
const px = (n: number) => n.toLocaleString("en-IN", { maximumFractionDigits: 0 });

/**
 * Resting depth, bids to the left of the price column and asks to the right.
 *
 * Bars grow from the centre with a transform, not a width change, so a tick
 * that thins the book animates in 200ms on every browser -- CSS transitions on
 * SVG geometry are not reliable in Safari, transforms are. Side is carried by
 * position and by the column headings, not only by colour.
 */
export function DepthLadder({ levels, mid, spreadBps, depthOfBaseline }: DepthLadderProps) {
  const theme = useChartTheme();
  const asks = levels.filter((l) => l.side === "ask").sort((a, b) => b.price - a.price);
  const bids = levels.filter((l) => l.side === "bid").sort((a, b) => b.price - a.price);
  const max = Math.max(1, ...levels.map((l) => l.size));
  const rows = [...asks, null, ...bids];
  const height = rows.length * ROW;

  const depthTone =
    depthOfBaseline === undefined ? "neutral" : depthOfBaseline < 0.2 ? "neg" : depthOfBaseline < 0.5 ? "warn" : "neutral";

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="grid flex-1 grid-cols-[1fr_auto_1fr] text-xs font-medium uppercase tracking-[0.12em] text-text-dim">
          <span>Bids</span>
          <span className="num normal-case tracking-normal">spread {spreadBps.toFixed(1)} bps</span>
          <span className="text-right">Asks</span>
        </div>
        {depthOfBaseline !== undefined ? (
          <Badge tone={depthTone} mono>{`depth ${Math.round(depthOfBaseline * 100)}% of baseline`}</Badge>
        ) : null}
      </div>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        width="100%"
        role="img"
        aria-label={`Order book around ${px(mid)}: ${bids.length} bid and ${asks.length} ask levels, spread ${spreadBps.toFixed(1)} basis points`}
      >
        {rows.map((level, i) => {
          const y = i * ROW;
          if (level === null) {
            return (
              <g key="mid">
                <line x1={0} x2={W} y1={y + ROW / 2} y2={y + ROW / 2} stroke={theme.line} />
                <rect x={HALF + 8} y={y + 3} width={CENTER - 16} height={ROW - 6} rx={6} fill={theme.surface2} stroke={theme.line} />
                <text x={W / 2} y={y + ROW / 2 + 4} textAnchor="middle" fontSize={12} fontFamily={theme.mono} fill={theme.text}>
                  {px(mid)}
                </text>
              </g>
            );
          }
          const bid = level.side === "bid";
          const scale = level.size / max;
          const color = bid ? theme.pos : theme.neg;
          return (
            <g key={`${level.side}-${level.price}`}>
              <rect
                x={bid ? 0 : HALF + CENTER}
                y={y + 3}
                width={HALF}
                height={ROW - 6}
                rx={3}
                fill={color}
                fillOpacity={0.22}
                style={{
                  transform: `scaleX(${scale})`,
                  transformBox: "fill-box",
                  transformOrigin: bid ? "right center" : "left center",
                  transition: "transform var(--dur-base) var(--ease)",
                }}
              />
              <text
                x={bid ? HALF - 8 : HALF + CENTER + 8}
                y={y + ROW / 2 + 4}
                textAnchor={bid ? "end" : "start"}
                fontSize={11}
                fontFamily={theme.mono}
                fill={theme.textDim}
              >
                {lakh(level.size)}
              </text>
              <text x={W / 2} y={y + ROW / 2 + 4} textAnchor="middle" fontSize={11} fontFamily={theme.mono} fill={theme.textDim}>
                {px(level.price)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
