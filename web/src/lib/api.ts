/** REST client. Plain fetch against /api, proxied to Django by Vite in dev. */
import type {
  ActionRequest,
  ActionResponse,
  Comparison,
  CompareResponse,
  CommsCreateRequest,
  CommsUpdate,
  DeclareIncidentRequest,
  Incident,
  IncidentState,
  MoneyString,
  RiskPolicy,
  ScenarioListItem,
  StepResponse,
  TicksResponse,
} from "./types";

export async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return (await response.json()) as T;
}

/** An API error carrying the server's human-readable `detail`. */
export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `${path} -> ${response.status}`;
    try {
      const data = (await response.json()) as { detail?: string };
      if (data.detail) detail = data.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail);
  }
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

// ---------------------------------------------------------------------------
// Incidents: the war room
// ---------------------------------------------------------------------------

export const listIncidents = () => get<Incident[]>("/api/incidents/");
export const declareIncident = (body: DeclareIncidentRequest) => post<IncidentState>("/api/incidents/", body);
export const incidentState = (code: string) => get<IncidentState>(`/api/incidents/${code}/state/`);
export const incidentTicks = (code: string, since = 0) => get<TicksResponse>(`/api/incidents/${code}/ticks/?since=${since}`);
export const stepIncident = (code: string, ticks: number) => post<StepResponse>(`/api/incidents/${code}/step/`, { ticks });
export const advanceClock = (code: string, toSeconds: number) =>
  post<IncidentState>(`/api/incidents/${code}/clock/`, { to_seconds: toSeconds });
export const incidentAction = (code: string, body: ActionRequest) =>
  post<ActionResponse>(`/api/incidents/${code}/action/`, body);
export const publishUpdate = (code: string, body: CommsCreateRequest) =>
  post<CommsUpdate>(`/api/incidents/${code}/comms/`, body);
