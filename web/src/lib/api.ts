/** REST client. Plain fetch against /api, proxied to Django by Vite in dev. */
import type { Comparison, ScenarioRow } from "./types";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return (await response.json()) as T;
}

export const fetchScenarios = () =>
  get<{ scenarios: ScenarioRow[] }>("/api/scenarios/").then((d) => d.scenarios);

export const fetchComparison = (slug: string) =>
  get<Comparison>(`/api/compare/${slug}/`);

/** Indian-scale money. A judge reads lakh and crore, not millions. */
export function rupees(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_00_00_000) return `₹${(value / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `₹${(value / 1_00_000).toFixed(1)} L`;
  return `₹${Math.round(value).toLocaleString("en-IN")}`;
}
