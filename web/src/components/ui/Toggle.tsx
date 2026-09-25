import { useId } from "react";

import { cn } from "./cn";

interface ToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  description?: string | undefined;
  disabled?: boolean | undefined;
  /** Mono ON/OFF readout beside the switch, so state never rests on colour. */
  readout?: boolean;
}

/** A switch. Space and Enter toggle it, because it is a real button. */
export function Toggle({ checked, onChange, label, description, disabled, readout = true }: ToggleProps) {
  const id = useId();
  return (
    <div className={cn("flex items-start justify-between gap-6", disabled && "opacity-40")}>
      <div className="min-w-0">
        <p id={`${id}-label`} className="text-sm text-text">{label}</p>
        {description ? (
          <p id={`${id}-desc`} className="mt-1 text-xs leading-relaxed text-text-dim">{description}</p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {readout ? (
          <span aria-hidden className={cn("num w-7 text-right text-xs", checked ? "text-text" : "text-text-dim")}>
            {checked ? "ON" : "OFF"}
          </span>
        ) : null}
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          aria-labelledby={`${id}-label`}
          aria-describedby={description ? `${id}-desc` : undefined}
          disabled={disabled}
          onClick={() => onChange(!checked)}
          className={cn(
            "relative h-5 w-9 shrink-0 rounded-full border transition-colors duration-fast ease-out",
            "disabled:cursor-not-allowed",
            checked ? "border-accent bg-accent" : "border-line bg-surface-2",
          )}
        >
          <span
            aria-hidden
            className={cn(
              "absolute left-0.5 top-0.5 h-3.5 w-3.5 rounded-full transition-transform duration-fast ease-out",
              checked ? "translate-x-4 bg-bg" : "translate-x-0 bg-text-dim",
            )}
          />
        </button>
      </div>
    </div>
  );
}
