import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "./cn";

/** 1px hairline, 10px radius, no shadow. Depth comes from the surface step. */
export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-card border border-line bg-surface", className)} {...rest} />;
}

interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  actions?: ReactNode | undefined;
}

export function CardHeader({ className, children, actions, ...rest }: CardHeaderProps) {
  return (
    <div className={cn("flex items-start justify-between gap-4 px-6 pt-6", className)} {...rest}>
      <div className="min-w-0 space-y-1">{children}</div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function CardEyebrow({ className, ...rest }: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("text-xs font-medium uppercase tracking-[0.12em] text-text-dim", className)}
      {...rest}
    />
  );
}

export function CardTitle({ className, ...rest }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-base font-medium tracking-tight text-text", className)} {...rest} />;
}

export function CardDescription({ className, ...rest }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm leading-relaxed text-text-dim", className)} {...rest} />;
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-6 pb-6 pt-4", className)} {...rest} />;
}
