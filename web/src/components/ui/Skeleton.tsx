import { cn } from "./cn";

/**
 * A placeholder block. Static on purpose: a pulsing skeleton is continuous
 * motion, and the motion rule allows 150-200ms transitions, not loops.
 */
export function Skeleton({ className }: { className?: string | undefined }) {
  return <div aria-hidden className={cn("rounded-control bg-surface-2", className)} />;
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  const widths = ["w-full", "w-11/12", "w-4/5", "w-3/5"];
  return (
    <div aria-hidden className="space-y-2">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={cn("h-3", widths[i % widths.length])} />
      ))}
    </div>
  );
}
