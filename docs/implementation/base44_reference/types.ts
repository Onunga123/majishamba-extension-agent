// Type definitions for the Kachieng' /api/v1/ client.
//
// These match the ACTUAL response shapes returned by the API as built on
// feature/base44-api (commit 04efc61), NOT the idealized {"ok","data"} envelope
// sketched in roadmap §A4. See docs/implementation/09_phase3_base44_integration.md
// for the full contract and the deviation table.

/** Terminal run statuses — stop polling once status is one of these. */
export type RunStatus =
  | "queued"
  | "running"
  | "waiting_for_model"
  | "validating"
  | "completed"
  | "completed_with_fallback"
  | "failed";

/** GET /api/v1/health/ — no auth. */
export interface HealthStatus {
  status: "ok" | "degraded";
  database: "ok" | "error";
  migrations_pending: boolean;
  llm_provider: string;
  weather_provider: string;
  version: string;
}

/** One farmer cluster (roadmap §A4 — the seven reference fields). */
export interface Cluster {
  cluster_id: string;
  name: string;
  locality: string;
  ward: string | null;
  centroid_lat: number | null;
  centroid_lon: number | null;
  coordinates_verified: boolean;
}

/** GET /api/v1/clusters/ — page-based pagination (default 25, ceiling 100). */
export interface ClusterPage {
  count: number;
  page: number;
  page_size: number;
  next: string | null;
  previous: string | null;
  results: Cluster[];
}

/** POST /api/v1/advisories/ — 201 if a new run was created, 200 if a recent
 *  in-flight run was reused (30-min dedup). `created` distinguishes the two. */
export interface AdvisoryRequestResponse {
  run_id: string;
  status: RunStatus;
  created: boolean;
}

/** GET /api/v1/runs/<uuid>/. Poll until `status` is terminal. */
export interface RunStatusResponse {
  run_id: string;
  status: RunStatus;
  cluster_id: string;
  current_message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result_advisory_id: number | null;
  error_message: string;
  generation_mode: string;
}

/** One piece of evidence attached to an advisory draft. */
export interface AdvisoryEvidence {
  source_type: string;
  source_ref: string;
  claim: string;
  is_stale: boolean;
  retrieved_at: string | null;
  source_observed_at: string | null;
  source_url: string | null;
}

/** GET /api/v1/advisories/<pk>/. The draft an officer reviews. */
export interface AdvisoryDetail {
  id: number;
  status: string;
  cluster_id: string;
  recommendation_type: string;
  summary: string;
  body: string;
  confidence: string;
  limitations: string;
  content_version: number;
  evidence: AdvisoryEvidence[];
  crop: string | null;
  season: string | null;
  county: string | null;
  sub_county: string | null;
  ward: string | null;
  model_name: string | null;
  generation_mode: string;
  created_at: string;
  updated_at: string;
}

/** Error body returned on any 4xx / 5xx. `extra` carries per-code detail
 *  (e.g. nothing additional today; reserved for the future duplicate_run code). */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    [extra: string]: unknown;
  };
}

/** Typed error thrown by the client on a non-2xx response. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly body: ApiErrorBody;

  constructor(status: number, body: ApiErrorBody) {
    super(`${body.error.code}: ${body.error.message}`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error.code;
    this.body = body;
  }
}
