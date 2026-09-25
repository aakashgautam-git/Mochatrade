import { Badge } from "./Badge";
import { cn } from "./cn";
import { DOT, type Tone } from "./tone";

export interface TimelineItem {
  id: string | number;
  /** Simulation clock, e.g. "T+120s". */
  time: string;
  /** Optional wall clock, e.g. "02:17:04 IST". */
  wall?: string | undefined;
  actor: string;
  action: string;
  rationale?: string | undefined;
  tone?: Tone;
  irreversible?: boolean | undefined;
}

/**
 * The action log, vertical. An irreversible decision gets a different SHAPE of
 * node -- a diamond, not a circle -- and a text label, so it never rests on
 * colour alone.
 */
export function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <ol className="relative">
      {items.map((item, i) => {
        const last = i === items.length - 1;
        const tone = item.irreversible ? "neg" : item.tone ?? "neutral";
        return (
          <li key={item.id} className="grid grid-cols-[88px_24px_minmax(0,1fr)] gap-x-3">
            <div className="pt-0.5 text-right">
              <p className="num text-xs text-text">{item.time}</p>
              {item.wall ? <p className="num mt-0.5 text-xs text-text-dim">{item.wall}</p> : null}
            </div>
            <div className="relative flex justify-center" aria-hidden>
              {!last ? <span className="absolute bottom-0 top-5 w-px bg-line" /> : null}
              <span
                className={cn(
                  "relative mt-1.5 h-2.5 w-2.5",
                  item.irreversible ? "rotate-45 rounded-[2px]" : "rounded-full",
                  DOT[tone],
                )}
              />
            </div>
            <div className={cn(last ? "pb-0" : "pb-6")}>
              <div className="flex flex-wrap items-center gap-2">
                <Badge mono>{item.actor}</Badge>
                <span className="text-sm text-text">{item.action}</span>
                {item.irreversible ? <Badge tone="neg">Irreversible</Badge> : null}
              </div>
              {item.rationale ? (
                <p className="mt-2 max-w-prose text-sm leading-relaxed text-text-dim">{item.rationale}</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
