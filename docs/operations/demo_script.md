# Demo video script — MajiShamba Extension Agent (unedited, under 3 minutes)

> Total target: 2:55. Each shot is one continuous screen recording segment; no jump cuts, no voice-overs added after recording. Read the narration in a single take.

## Pre-recording checklist

1. Fresh repo: `git clone ... && cd majishamba && make demo` has been run; the Django dev server is up on `http://127.0.0.1:8000`.
2. Ollama running with `qwen2.5:7b-instruct` pulled (if available; otherwise the demo runs in `fallback_template` mode and you say so).
3. Browser open at the login page. Logged out.
4. Two terminal windows side-by-side:
   - Left: Django dev server log (shows audit events as they happen).
   - Right: a browser at http://127.0.0.1:8000.
5. Recording tool: OBS / QuickTime / screen record. Capture the full screen (both terminal and browser visible).

## Shot 1 — 0:00–0:20 · README + one-command setup + Kachieng context

**Camera.** Show the repo root `README.md` in the editor.

**Narration.** "MajiShamba is a climate-smart advisory agent built for the Nyatike Sub-County Agricultural Office in Migori County, Kenya, serving smallholder farmer clusters in Kachieng Ward. The challenge: an MCP-based agentic system with a custom MCP server, LangGraph orchestration, an open-weights model run, a logged tool call for every action, and a strict human approval gate. Setup is one command — `make demo` — and we're already running."

**Action.** Switch to the browser at `http://127.0.0.1:8000/dashboard/`. The login page appears.

## Shot 2 — 0:20–0:50 · Officer logs in + requests advisory for KACH-01

**Camera.** Browser at the login page.

**Narration.** "The named Nyatike extension officer logs in. Three demo users are seeded — officer, supervisor, viewer. We log in as the officer."

**Action.** Type `nyatike_officer` / `majishamba-demo-2025`. Click Login. Land on the dashboard showing KACH-01, KACH-02, KACH-03.

**Narration.** "Three synthetic Kachieng clusters. We click 'Request advisory' for KACH-01."

**Action.** Click "+ Request advisory". Select `KACH-01`. Click "Run agent".

## Shot 3 — 0:50–1:30 · Tool calls on screen

**Camera.** Watch the left terminal (Django dev server log) as audit events stream by.

**Narration.** "The LangGraph agent is running. Each line is an audit event for a tool call. We see: get_cluster_plot_history, get_crop_calendar, get_weather_and_rainfall_context (twice — last 30 days and 10-day forecast), get_pest_alerts, get_market_price_context, validate_advisory_evidence. That's six read-only MCP tools from our custom server `majishamba-extension-mcp` — all eight tools are registered, two are action tools."

**Action.** Wait for the redirect to the advisory detail page. Point at the "Mode: fallback_template" line if Ollama is not running, or "Mode: ollama_qwen" if it is.

**Narration.** "The advisory was drafted with [Qwen2.5-7B-Instruct via Ollama | the deterministic fallback] — that's our one full task on an open-weights model. If Ollama is not installed, the system says so and falls back; the demo still works."

## Shot 4 — 1:30–2:00 · Draft advisory with evidence, gaps, limitations

**Camera.** Browser at the advisory detail page.

**Narration.** "The DRAFT advisory. Recommendation: pest-monitoring — because the fall armyworm alert in Migori has high severity. Body cites sources: crop calendar, last 30 days rainfall, 10-day forecast, pest alert source. Limitations note the weather signal is stale. Evidence panel lists the cited sources. Status: DRAFT. Nothing has been sent to any farmer."

**Action.** Scroll through the body, evidence list, limitations.

## Shot 5 — 2:00–2:30 · Officer approves + follow-up task created

**Camera.** Browser still on the advisory detail page.

**Narration.** "The officer reviews. Click 'Review / Approve'."

**Action.** Click the button. Land on the approval gate. Select decision = "Approved". Check "On approval, also create a follow-up task". Task type = "Field visit to Kachieng cluster". Deadline = "2025-11-15". Click "Submit decision".

**Narration.** "The approval gate creates an OfficerApproval row, updates the Advisory to APPROVED, and only then — because the gate now sees a valid APPROVED approval — creates the follow-up task. The audit log shows the approval and the task creation. The agent never created the task; we did, after the gate."

**Action.** Show the success message. Open the dashboard audit view at `/dashboard/audit/`. Point at the `officer_approval` and `create_follow_up_task` rows.

## Shot 6 — 2:30–3:00 · Failure / retry + open-weights statement

**Camera.** Open a second browser tab at `/agents/graph/`.

**Narration.** "The LangGraph agent — 11 nodes. If the model output fails Pydantic validation, the graph routes back to `draft_advisory` once with the deterministic template. If a tool errors, it routes to `officer_approval_gate` and stops with the error visible to the officer."

**Action.** Open `/audit/` to show the audit trail. Point at the `agent_run:start` and `agent_run:end` events for the run we just did.

**Narration.** "Every tool call, every HTTP mutation, every agent run is in the audit log with the officer's name. The agent recommends; the officer decides. That's MajiShamba for Kachieng Ward."

**Action.** Cut to black. Show README link + ARCHITECTURE.md + EVALS.md + licence (MIT) for 5 seconds.

## Total runtime

| Shot | Time |
|---|---|
| 1 | 0:00–0:20 |
| 2 | 0:20–0:50 |
| 3 | 0:50–1:30 |
| 4 | 1:30–2:00 |
| 5 | 2:00–2:30 |
| 6 | 2:30–3:00 |
| **Total** | **2:55** |

## Things to avoid in the recording

- Do not edit the video. One take.
- Do not show real names or phone numbers (the fixtures are synthetic; verify before recording).
- Do not skip the audit-log shot — judges want to see the trail.
- Do not skip the approval gate shot — it's the headline governance feature.
- If Ollama is not running, say "fallback template" out loud so judges know it's the deterministic path.

## Things to emphasise

- Custom MCP server with 8 tools, 2 action tools, 1 approval-gated.
- Borrowed MCP server (filesystem) used in development for calendar PDFs.
- LangGraph orchestration, not a custom state machine.
- Qwen2.5-7B-Instruct via Ollama is the open-weights model run.
- Every tool call logged with sanitised inputs, summarised outputs, actor, approval status.
- Approval gate enforced in code (`apps/tasks/service.py`).
- Synthetic data only — clearly labelled in fixtures, README, dashboard footer.
- MIT licence.
