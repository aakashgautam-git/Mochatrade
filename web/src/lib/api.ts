/** REST client. Plain fetch against /api, proxied to Django by Vite in dev. */
import type {
  ActionRequest,
  ActionResponse,
  Claim,
  ClaimDecisionRequest,
  ClaimsResponse,
  Recalibration,
  ClassificationResponse,
  ClassifyRequest,
  IncidentReport,
  CommsCheckRequest,
  CommsCheckResponse,
  CommsTemplate,
  PublicStatusResponse,
  EvidenceResponse,
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

export const fetchClassification = (code: string) =>
  get<ClassificationResponse>(`/api/incidents/${code}/classify/`);
export const classifyIncident = (code: string, body: ClassifyRequest = {}) =>
  post<ClassificationResponse>(`/api/incidents/${code}/classify/`, body);
export const fetchEvidence = (code: string, from: number, to: number) =>
  get<EvidenceResponse>(`/api/incidents/${code}/evidence/?from=${from}&to=${to}`);

export const fetchClaims = (code: string) => get<ClaimsResponse>(`/api/incidents/${code}/claims/`);
export const openClaims = (code: string, body: { actor?: string; rationale?: string } = {}) =>
  post<ClaimsResponse>(`/api/incidents/${code}/claims/`, body);
export const decideClaim = (code: string, id: number, body: ClaimDecisionRequest) =>
  post<Claim>(`/api/incidents/${code}/claims/${id}/decide/`, body);
export const recalibrateReserve = (actor = "Risk") => post<Recalibration>("/api/policies/recalibrate/", { actor });

export const fetchComms = (code: string) => get<CommsUpdate[]>(`/api/incidents/${code}/comms/`);
export const createComms = (code: string, body: CommsCreateRequest) => post<CommsUpdate>(`/api/incidents/${code}/comms/`, body);
export const checkComms = (code: string, body: CommsCheckRequest) => post<CommsCheckResponse>(`/api/incidents/${code}/comms/check/`, body);
export const fetchTemplates = (code: string) => get<CommsTemplate[]>(`/api/incidents/${code}/comms/templates/`);
export const decideComms = (code: string, id: number, body: { decision: "APPROVE" | "REJECT"; approver?: string; note?: string }) =>
  post<CommsUpdate>(`/api/incidents/${code}/comms/${id}/approve/`, body);
export const publishComms = (code: string, id: number, publisher = "") =>
  post<CommsUpdate>(`/api/incidents/${code}/comms/${id}/publish/`, { publisher });
export const fetchPublicStatus = () => get<PublicStatusResponse>("/api/status/");
export const fetchReport = (code: string) => get<IncidentReport>(`/api/incidents/${code}/report/`);
