import type { ReactNode } from "react";

import { cn } from "./cn";
import { TINT, type Tone } from "./tone";

interface BadgeProps {
  tone?: Tone;
  /** Required. A badge always carries a text label -- never colour alone. */
  children: ReactNode;
  icon?: ReactNode | undefined;
  mono?: boolean;
  className?: string | undefined;
  title?: string | undefined;
}

export function Badge({ tone = "neutral", children, icon, mono = false, className, title }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-chip border px-2 text-xs font-medium",
        TINT[tone],
        mono && "num",
        className,
      )}
    >
      {icon ? <span className="flex shrink-0 items-center [&>svg]:h-3.5 [&>svg]:w-3.5" aria-hidden>{icon}</span> : null}
      {children}
    </span>
  );
}
