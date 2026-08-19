import type {
  Activity,
  Adaptation,
  AthleteProfile,
  CoachMessage,
  CoachReply,
  Digest,
  Feasibility,
  LoadDay,
  PacePoint,
  PlanDetail,
  SessionStatus,
  Prediction,
  RunAnalysis,
  Split,
  Summary,
} from "./types";

export class ApiError extends Error {
  // Explicit fields rather than constructor parameter properties: this project
  // builds with `erasableSyntaxOnly`, which forbids the shorthand.
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Request failed with ${res.status}`;
    try {
      const parsed = await res.json();
      if (parsed?.detail) detail = String(parsed.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const qs = params
    ? "?" + new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))
    : "";

  const res = await fetch(`/api${path}${qs}`, { headers: { Accept: "application/json" } });

  if (!res.ok) {
    // The backend returns a useful {detail} on 4xx — surface it rather than a
    // generic failure, since "no athlete connected" is an actionable state.
    let detail = `Request failed with ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* non-JSON error body; keep the default */
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

export const HALF_MARATHON_M = 21097.5;

export const api = {
  athlete: () => get<AthleteProfile>("/athlete"),
  summary: (from?: string, to?: string) =>
    get<Summary>("/analytics/summary", {
      ...(from ? { from } : {}),
      ...(to ? { to } : {}),
    }),
  load: (from?: string, to?: string) =>
    get<LoadDay[]>("/analytics/load", {
      ...(from ? { from } : {}),
      ...(to ? { to } : {}),
    }),
  curve: () => get<PacePoint[]>("/analytics/curve"),
  prediction: (distance = HALF_MARATHON_M) =>
    get<Prediction>("/analytics/prediction", { distance }),
  feasibility: () => get<Feasibility>("/analytics/feasibility"),
  plan: () => get<PlanDetail>("/plan/current"),
  adaptations: () => get<Adaptation[]>("/plan/adaptations"),
  digest: () => get<Digest>("/plan/digest"),
  coachHistory: () => get<CoachMessage[]>("/coach/history"),
  askCoach: (message: string) => send<CoachReply>("POST", "/coach/message", { message }),
  generatePlan: () => send<PlanDetail>("POST", "/plan/generate"),
  reconcilePlan: () => send<PlanDetail>("POST", "/plan/reconcile"),
  setSessionStatus: (id: number, status: SessionStatus) =>
    send<unknown>("PATCH", `/plan/session/${id}`, { status }),
  splits: (id: number) => get<Split[]>(`/activities/${id}/splits`),
  analysis: (id: number) => get<RunAnalysis>(`/activities/${id}/analysis`),
  fetchStreams: (id: number) =>
    send<{ status: string }>("POST", `/activities/${id}/streams/fetch`),
  activities: (params: { from?: string; to?: string; type?: string; limit?: number } = {}) =>
    get<Activity[]>("/activities", params as Record<string, string | number>),
};
