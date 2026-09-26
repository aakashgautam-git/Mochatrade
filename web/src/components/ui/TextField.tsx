import { useId } from "react";

import { cn } from "./cn";

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (next: string) => void;
  hint?: string | undefined;
  placeholder?: string | undefined;
  multiline?: boolean;
  rows?: number;
  mono?: boolean;
  disabled?: boolean | undefined;
  invalid?: string | undefined;
}

/** A labelled text input or textarea. Errors are stated in words, not only by a
 * red border. */
export function TextField({ label, value, onChange, hint, placeholder, multiline = false, rows = 3, mono = false, disabled, invalid }: TextFieldProps) {
  const id = useId();
  const described = invalid ? `${id}-err` : hint ? `${id}-hint` : undefined;
  const cls = cn(
    "w-full rounded-control border bg-surface px-3 text-sm text-text transition-colors duration-fast",
    "placeholder:text-text-dim disabled:cursor-not-allowed disabled:opacity-40",
    invalid ? "border-neg-edge" : "border-line hover:bg-surface-2",
    mono && "num",
  );
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">{label}</label>
      {multiline ? (
        <textarea id={id} rows={rows} value={value} placeholder={placeholder} disabled={disabled}
          aria-invalid={invalid ? true : undefined} aria-describedby={described}
          onChange={(e) => onChange(e.target.value)} className={cn(cls, "py-2 leading-relaxed")} />
      ) : (
        <input id={id} type="text" value={value} placeholder={placeholder} disabled={disabled}
          aria-invalid={invalid ? true : undefined} aria-describedby={described}
          onChange={(e) => onChange(e.target.value)} className={cn(cls, "h-9")} />
      )}
      {invalid ? <p id={`${id}-err`} className="text-xs text-neg-fg">{invalid}</p>
        : hint ? <p id={`${id}-hint`} className="text-xs text-text-dim">{hint}</p> : null}
    </div>
  );
}
