// Reference Deno client for the Kachieng' /api/v1/ API.
//
// Copy this into the Base44 project's backend functions (Deno) and adapt to
// Base44's secrets + module conventions. It uses only the global `fetch`
// (no external dependencies) and matches the ACTUAL API on feature/base44-api.
//
// Usage:
//   import { KachiengApiClient } from "./apiClient.ts";
//   const client = new KachiengApiClient(
//     "https://kachieng-ai-agent.onrender.com",   // base URL
//     Deno.env.get("KACHIENG_API_TOKEN")!,         // stored in Base44 encrypted secrets
//   );
//   const clusters = await client.listClusters({ page_size: 50 });

import {
  ApiError,
  type AdvisoryDetail,
  type AdvisoryRequestResponse,
  type ClusterPage,
  type HealthStatus,
  type RunStatus,
  type RunStatusResponse,
} from "./types.ts";

const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set<RunStatus>([
  "completed",
  "completed_with_fallback",
  "failed",
]);

export interface ListClustersParams {
  page?: number;
  page_size?: number; // capped at 100 by the server
  q?: string; // case-insensitive substring on cluster_id / name / locality
}

export interface PollOptions {
  intervalMs?: number; // default 2500 (roadmap §A4: poll every 2–3 s)
  timeoutMs?: number; // default 180000 (matches the gunicorn --timeout 180 Render setting)
}

/** Result of a completed Superagent run (status completed[_with_fallback]). */
export interface CompletedRun {
  run: RunStatusResponse;
  advisory: AdvisoryDetail;
}

export class KachiengApiClient {
  private readonly baseUrl: string;
  private readonly token: string;

  /**
   * @param baseUrl  Origin with no trailing slash, e.g. "https://kachieng-ai-agent.onrender.com".
   * @param token    Raw API token as printed by `generate_api_token`
   *                 (starts with "majishamba_"). Store it in the Base44
   *                 encrypted secrets vault, never in source.
   */
  constructor(baseUrl: string, token: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.token = token;
  }

  /** GET /api/v1/health/ — no auth. Use to pre-warm / readiness-check before a demo. */
  async health(): Promise<HealthStatus> {
    return this.getJson<HealthStatus>("/api/v1/health/");
  }

  /** GET /api/v1/clusters/ — any active token. Page-based pagination. */
  async listClusters(params: ListClustersParams = {}): Promise<ClusterPage> {
    const qs = new URLSearchParams();
    if (params.page !== undefined) qs.set("page", String(params.page));
    if (params.page_size !== undefined) qs.set("page_size", String(params.page_size));
    if (params.q !== undefined) qs.set("q", params.q);
    const suffix = qs.toString() ? `?${qs}` : "";
    return this.getJson<ClusterPage>(`/api/v1/clusters/${suffix}`, true);
  }

  /** POST /api/v1/advisories/ — officer token. `created` is false if a recent
   *  in-flight run for the cluster was reused (30-min dedup); the returned
   *  run_id is the existing run's id in that case. */
  async requestAdvisory(clusterId: string): Promise<AdvisoryRequestResponse> {
    return this.postJson<AdvisoryRequestResponse>(
      "/api/v1/advisories/",
      { cluster_id: clusterId },
      true,
    );
  }

  /** GET /api/v1/runs/<run_id>/ — owner / any officer / system admin. */
  async getRunStatus(runId: string): Promise<RunStatusResponse> {
    return this.getJson<RunStatusResponse>(
      `/api/v1/runs/${encodeURIComponent(runId)}/`,
      true,
    );
  }

  /** GET /api/v1/advisories/<advisory_pk>/ — any active token. */
  async getAdvisory(advisoryId: number): Promise<AdvisoryDetail> {
    return this.getJson<AdvisoryDetail>(
      `/api/v1/advisories/${advisoryId}/`,
      true,
    );
  }

  /** Poll GET /api/v1/runs/<run_id>/ until the run reaches a terminal status.
   *  On `completed` / `completed_with_fallback`, fetches the advisory draft
   *  and returns it alongside the run. On `failed`, throws ApiError. */
  async pollUntilCompleted(runId: string, opts: PollOptions = {}): Promise<CompletedRun> {
    const intervalMs = opts.intervalMs ?? 2500;
    const timeoutMs = opts.timeoutMs ?? 180_000;
    const deadline = Date.now() + timeoutMs;
    let run: RunStatusResponse;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      run = await this.getRunStatus(runId);
      if (TERMINAL_STATUSES.has(run.status)) break;
      if (Date.now() > deadline) {
        throw new Error(
          `pollUntilCompleted timed out after ${timeoutMs}ms (last status: ${run.status})`,
        );
      }
      await sleep(intervalMs);
    }
    if (run.status === "failed") {
      throw new ApiError(200, {
        error: { code: "run_failed", message: run.error_message || "Advisory run failed." },
      });
    }
    if (run.result_advisory_id == null) {
      throw new Error(
        `Run ${runId} reached ${run.status} but has no result_advisory_id.`,
      );
    }
    const advisory = await this.getAdvisory(run.result_advisory_id);
    return { run, advisory };
  }

  // --- internals ---

  private authHeaders(auth: boolean): Record<string, string> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (auth) headers["Authorization"] = `Bearer ${this.token}`;
    return headers;
  }

  private async getJson<T>(path: string, auth: boolean): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      method: "GET",
      headers: this.authHeaders(auth),
    });
    return this.parse<T>(resp);
  }

  private async postJson<T>(path: string, body: unknown, auth: boolean): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: {
        ...this.authHeaders(auth),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    return this.parse<T>(resp);
  }

  private async parse<T>(resp: Response): Promise<T> {
    const text = await resp.text();
    let parsed: unknown = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        throw new Error(`Non-JSON response (HTTP ${resp.status}): ${text.slice(0, 200)}`);
      }
    }
    if (!resp.ok) {
      throw new ApiError(resp.status, parsed as import("./types.ts").ApiErrorBody);
    }
    return parsed as T;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
