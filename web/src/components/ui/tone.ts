/**
 * The semantic tones every primitive shares. Class strings are spelled out in
 * full so Tailwind's scanner sees them -- never build a class name by string
 * concatenation, it will not be emitted.
 */
export type Tone = "neutral" | "accent" | "pos" | "neg" | "warn" | "halt";

/** Tinted chip or panel: soft fill, edge border, readable foreground. */
export const TINT: Record<Tone, string> = {
  neutral: "border-line bg-surface-2 text-text-dim",
  accent: "border-accent-edge bg-accent-soft text-accent-fg",
  pos: "border-pos-edge bg-pos-soft text-pos-fg",
  neg: "border-neg-edge bg-neg-soft text-neg-fg",
  warn: "border-warn-edge bg-warn-soft text-warn-fg",
  halt: "border-halt-edge bg-halt-soft text-halt-fg",
};

/** Foreground only, for text and icons on a plain surface. */
export const FG: Record<Tone, string> = {
  neutral: "text-text-dim",
  accent: "text-accent-fg",
  pos: "text-pos-fg",
  neg: "text-neg-fg",
  warn: "text-warn-fg",
  halt: "text-halt-fg",
};

/** Solid fill, for dots and markers that carry no text. */
export const DOT: Record<Tone, string> = {
  neutral: "bg-text-dim",
  accent: "bg-accent",
  pos: "bg-pos",
  neg: "bg-neg",
  warn: "bg-warn",
  halt: "bg-halt",
};
