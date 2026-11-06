// Superagent workflow — the Phase 3 advisory-generation flow a Base44 app drives.
//
// browse clusters -> request an advisory -> poll to completion -> return the
// draft + evidence for display. This is the reference implementation of the
// roadmap's Phase 3 acceptance ("Base44 retrieves clusters, submits an advisory,
// polls to completion, and displays the draft with evidence").
//
// Adapt the I/O (Base44 data sources, UI actions) to the Base44 project; the
// API interaction stays as written here.

import { KachiengApiClient, type CompletedRun, type Cluster } from "./apiClient.ts";

export interface SuperagentOptions {
  /** Cluster to request an advisory for. If omitted, the first cluster in the
   *  list is used (a real Base44 app lets the user pick). */
  clusterId?: string;
  /** Optional filter passed to GET /clusters/?q= (cluster_id / name / locality). */
  q?: string;
  /** Polling + advisory fetch pass through to pollUntilCompleted. */
  poll?: { intervalMs?: number; timeoutMs?: number };
}

export interface SuperagentResult {
  cluster: Cluster;
  run: CompletedRun["run"];
  advisory: CompletedRun["advisory"];
}

/**
 * Run the full Superagent flow against /api/v1/.
 *
 * @param client     an authenticated KachiengApiClient (officer token).
 * @param options    cluster selection + polling options.
 * @returns          the chosen cluster, the terminal run, and the advisory draft.
 */
export async function runSuperagentFlow(
  client: KachiengApiClient,
  options: SuperagentOptions = {},
): Promise<SuperagentResult> {
  // 2. Browse clusters (endpoint 2).
  const page = await client.listClusters({ q: options.q, page_size: 100 });
  if (page.results.length === 0) {
    throw new Error("No clusters available to request an advisory for.");
  }
  let cluster: Cluster | undefined;
  if (options.clusterId) {
    cluster = page.results.find((c) => c.cluster_id === options.clusterId);
    if (!cluster) {
      throw new Error(`Cluster '${options.clusterId}' not found.`);
    }
  } else {
    cluster = page.results[0];
  }

  // 3. Request an advisory for the chosen cluster (endpoint 3).
  const request = await client.requestAdvisory(cluster.cluster_id);
  // `created === false` is a dedup reuse (30-min window) — the run_id is the
  // existing run's; poll it the same way.

  // 4 + 5. Poll run status to completion and fetch the advisory (endpoints 4 + 5).
  const completed = await client.pollUntilCompleted(request.run_id, options.poll);

  return { cluster, run: completed.run, advisory: completed.advisory };
}
