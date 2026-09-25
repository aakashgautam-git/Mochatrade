/** REST client. Plain fetch against /api, proxied to Django by Vite in dev. */
import type { Comparison, CompareResponse, MoneyString, RiskPolicy, ScenarioListItem } from "./types";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return (await response.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return (await response.json()) as T;
}

export const fetchCompare = (scenario_slug: string) =>
  post<CompareResponse>("/api/runs/compare/", { scenario_slug });

export const fetchActivePolicy = () =>
  get<RiskPolicy[]>("/api/policies/?active=true").then((list) => {
    const policy = list[0];
    if (!policy) throw new Error("No active RiskPolicy. Run `make seed`.");
    return policy;
  });

/** GET /api/scenarios/ returns a bare list, read from the database. */
export const fetchScenarios = () => get<ScenarioListItem[]>("/api/scenarios/");

export const fetchComparison = (slug: string) =>
  get<Comparison>(`/api/compare/${slug}/`);

/** For DISPLAY only. Do arithmetic on the string's decimal value server-side. */
export function parseMoney(value: MoneyString): number {
  return Number.parseFloat(value);
}

/** Indian-scale money. A judge reads lakh and crore, not millions. */
export function rupees(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_00_00_000) return `₹${(value / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `₹${(value / 1_00_000).toFixed(1)} L`;
  return `₹${Math.round(value).toLocaleString("en-IN")}`;
}
