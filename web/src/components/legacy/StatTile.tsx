interface Props {
  label: string;
  on: string;
  off: string;
  deltaPct: number;
  /** Lower is better for every stat on this page. */
  caption: string;
}

export function StatTile({ label, on, off, deltaPct, caption }: Props) {
  const improved = deltaPct > 0;
  return (
    <article className="rounded-card border border-line bg-surface p-6">
      <h3 className="text-xs uppercase tracking-[0.14em] text-text-faint">{label}</h3>
      <div className="mt-4 flex items-baseline gap-3">
        <span className="num text-4xl font-semibold leading-none tracking-tight">{on}</span>
        <span
          className="num text-lg text-text-faint line-through decoration-text-faint/60"
          title="Without controls"
        >
          {off}
        </span>
      </div>
      <div className="mt-4 flex items-center gap-2">
        <span
          className={`num rounded-chip border px-2 py-0.5 text-xs font-medium ${
            improved
              ? "border-pos/30 bg-pos/10 text-pos"
              : "border-line bg-surface-2 text-text-dim"
          }`}
        >
          {improved ? `−${deltaPct.toFixed(0)}%` : "no change"}
        </span>
        <span className="text-xs text-text-faint">{caption}</span>
      </div>
    </article>
  );
}
