import { ChevronDown } from "lucide-react";
import { useId } from "react";

import { cn } from "./cn";

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  onChange: (next: string) => void;
  options: SelectOption[];
  label: string;
  hideLabel?: boolean;
  disabled?: boolean | undefined;
  mono?: boolean;
  className?: string | undefined;
}

/** A native select, styled closed. The open menu stays the operating system's,
 * which is the accessible choice and the honest one. */
export function Select({ value, onChange, options, label, hideLabel = false, disabled, mono = false, className }: SelectProps) {
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <label
        htmlFor={id}
        className={cn("text-xs font-medium uppercase tracking-[0.12em] text-text-dim", hideLabel && "sr-only")}
      >
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className={cn(
            "ui-select h-9 w-full appearance-none rounded-control border border-line bg-surface pl-3 pr-9 text-sm text-text",
            "transition-colors duration-fast ease-out hover:bg-surface-2",
            "disabled:cursor-not-allowed disabled:opacity-40",
            mono && "num",
          )}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <ChevronDown aria-hidden className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-dim" />
      </div>
    </div>
  );
}
