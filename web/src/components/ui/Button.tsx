import { LoaderCircle } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { cn } from "./cn";

export type ButtonVariant = "primary" | "ghost" | "danger" | "halt";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "border border-accent-solid bg-accent-solid text-on-accent-solid hover:border-accent-fg hover:bg-accent-fg",
  ghost: "border border-line bg-transparent text-text hover:bg-surface-2",
  danger: "border border-neg-edge bg-neg-soft text-neg-fg hover:border-neg",
  // Halt/intervention actions only -- the one place --halt is allowed.
  halt: "border border-halt-edge bg-halt-soft text-halt-fg hover:border-halt",
};

const SIZE: Record<ButtonSize, string> = {
  sm: "h-8 gap-1.5 px-3 text-xs [&_svg]:h-3.5 [&_svg]:w-3.5",
  md: "h-9 gap-2 px-4 text-sm [&_svg]:h-4 [&_svg]:w-4",
  lg: "h-11 gap-2 px-5 text-sm [&_svg]:h-4 [&_svg]:w-4",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode | undefined;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "ghost", size = "md", icon, loading = false, disabled, className, children, type, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex select-none items-center justify-center whitespace-nowrap rounded-control font-medium",
        "transition-colors duration-fast ease-out",
        "disabled:cursor-not-allowed disabled:opacity-40",
        VARIANT[variant],
        SIZE[size],
        className,
      )}
      {...rest}
    >
      {loading ? <LoaderCircle className="ui-spin" aria-hidden /> : icon ? <span aria-hidden className="flex">{icon}</span> : null}
      {children}
    </button>
  );
});
