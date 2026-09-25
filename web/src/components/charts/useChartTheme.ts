import { useEffect, useState } from "react";

/**
 * Chart colours, read from the live token values.
 *
 * Recharts writes colours into SVG attributes and tooltip styles, so it needs
 * concrete strings rather than var(--x). Reading them from the computed style
 * keeps tokens.css the single source, and a MutationObserver on data-theme
 * means every chart follows the light palette on Report and Playbook without
 * any chart knowing that palette exists.
 */
export interface ChartTheme {
  text: string;
  textDim: string;
  line: string;
  grid: string;
  bg: string;
  surface: string;
  surface2: string;
  accent: string;
  pos: string;
  neg: string;
  warn: string;
  halt: string;
  mono: string;
}

function read(): ChartTheme {
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string) => cs.getPropertyValue(name).trim();
  return {
    text: v("--text"),
    textDim: v("--text-dim"),
    line: v("--line"),
    grid: v("--line"),
    bg: v("--bg"),
    surface: v("--surface"),
    surface2: v("--surface-2"),
    accent: v("--accent"),
    pos: v("--pos"),
    neg: v("--neg"),
    warn: v("--warn"),
    halt: v("--halt"),
    mono: v("--font-mono"),
  };
}

export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = useState<ChartTheme>(read);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(read()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

export function axisTick(theme: ChartTheme) {
  return { fill: theme.textDim, fontSize: 11, fontFamily: theme.mono };
}

/** Even minute ticks for a time axis in seconds -- 1, 2 or 5 minutes apart,
 * whichever gives at most seven labels. Recharts' own spacing lands on 0, 3, 7,
 * 12, which reads as noise on a clock. */
export function minuteTicks(maxSeconds: number): number[] {
  const minutes = maxSeconds / 60;
  const step = [1, 2, 5, 10].find((s) => minutes / s <= 7) ?? 15;
  const ticks: number[] = [];
  for (let m = 0; m * 60 <= maxSeconds; m += step) ticks.push(m * 60);
  return ticks;
}
