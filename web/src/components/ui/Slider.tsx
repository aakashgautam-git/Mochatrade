import { useId, type CSSProperties } from "react";

import { cn } from "./cn";

interface SliderProps {
  value: number;
  onChange: (next: number) => void;
  min: number;
  max: number;
  step?: number;
  label: string;
  format?: (n: number) => string;
  disabled?: boolean | undefined;
  hint?: string | undefined;
}

/** A native range input, styled. Arrow keys, Home and End work because the
 * browser already implements them; reimplementing that is how sliders end up
 * inaccessible. */
export function Slider({ value, onChange, min, max, step = 1, label, format = String, disabled, hint }: SliderProps) {
  const id = useId();
  const fill = max === min ? 0 : ((value - min) / (max - min)) * 100;
  return (
    <div className={cn(disabled && "opacity-40")}>
      <div className="flex items-baseline justify-between gap-4">
        <label htmlFor={id} className="text-sm text-text">{label}</label>
        <output htmlFor={id} className="num text-sm text-text">{format(value)}</output>
      </div>
      <input
        id={id}
        type="range"
        className="ui-range mt-3"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-valuetext={format(value)}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ "--fill": `${fill}%` } as CSSProperties}
      />
      <div className="num mt-2 flex justify-between text-xs text-text-dim" aria-hidden>
        <span>{format(min)}</span>
        {hint ? <span className="font-sans">{hint}</span> : null}
        <span>{format(max)}</span>
      </div>
    </div>
  );
}
