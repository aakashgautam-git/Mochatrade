import type { ReactNode } from "react";

import { cn } from "./cn";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description?: string | undefined;
  action?: ReactNode | undefined;
  className?: string | undefined;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center rounded-card border border-dashed border-line px-6 py-12 text-center", className)}>
      <div aria-hidden className="flex h-10 w-10 items-center justify-center rounded-control border border-line bg-surface-2 text-text-dim [&>svg]:h-5 [&>svg]:w-5">
        {icon}
      </div>
      <p className="mt-4 text-sm font-medium text-text">{title}</p>
      {description ? <p className="mt-2 max-w-md text-sm leading-relaxed text-text-dim">{description}</p> : null}
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  );
}
