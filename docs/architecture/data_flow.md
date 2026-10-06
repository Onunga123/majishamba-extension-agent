# Data flow — Kachieng AI Agent

## End-to-end request flow

```text
1. Officer logs in (/accounts/login/)
   → Django authenticates via the custom User model (apps.accounts).
   → Audit middleware logs the login POST.

2. Officer opens dashboard (/dashboard/)
   → Dashboard view queries FarmerCluster, Advisory, AuditEvent, WeatherSignal, PestSignal, FollowUpTask.
   → Renders dashboard/home.html with cluster stats, recent advisories, audit events, weather/pest summary.

3. Officer clicks "Request advisory" → /advisories/request/
   → GET renders a small form with the cluster select (KACH-01 / KACH-02 / KACH-03).
   → POST triggers apps.agents.runner.run_advisory_pipeline(cluster_id=...).

4. Agent (LangGraph) runs in-process:
   validate_request
     → check cluster_id exists; pull ward/sub_county/county from FK chain
   fetch_plot_history
     → call apps.mcp_tools.tools.get_cluster_plot_history
     → logs AuditEvent
   fetch_crop_calendar
     → call get_crop_calendar
     → logs AuditEvent
     → if source_date > 730 days, sets is_stale=true and warning
   fetch_weather
     → call get_weather_and_rainfall_context twice (last_30_days, 10_day_forecast)
     → logs two AuditEvents
     → checks is_fresh(); if stale, adds warning
   fetch_pest_alerts
     → call get_pest_alerts (maize, Migori, Nyanza)
     → logs AuditEvent
   fetch_market_prices
     → call get_market_price_context (maize, Migori-Town)
     → logs AuditEvent
   validate_evidence
     → call validate_advisory_evidence with the gathered evidence
     → logs AuditEvent
     → flags missing_required (plot_history, crop_calendar, weather) if absent
   draft_advisory
     → build prompt with the evidence (sanitised)
     → try Ollama qwen2.5:7b-instruct
     → if Ollama unreachable → fallback template (deterministic)
     → sets state.generation_mode = "ollama_qwen" or "fallback_template"
   validate_output_schema
     → strip code fence, parse JSON, validate against AdvisoryDraft (Pydantic)
     → if invalid and was Ollama → route back to draft_advisory (template)
     → if invalid and was template → route to officer_approval_gate (terminal)
     → if valid → save_draft
   save_draft
     → call apps.mcp_tools.tools.create_draft_advisory_record (ACTION)
     → creates Advisory(status=DRAFT) + AdvisoryEvidence rows
     → logs AuditEvent with approval_status="draft"
   officer_approval_gate (terminal)
     → adds "Awaiting officer approval" warning
     → graph ends

5. Agent returns advisory_id to the runner → runner redirects to /advisories/<id>/

6. Officer reviews DRAFT at /advisories/<id>/ (read-only) or /advisories/<id>/edit/ (officer-only).

7. Officer goes to /approvals/<advisory_id>/ and submits decision.
   → ApprovalGateView requires user.can_approve()
   → Creates OfficerApproval row
   → Updates Advisory.status (APPROVED / REJECTED / DEFERRED / NEEDS_EVIDENCE)
   → Logs AuditEvent(action="officer_approval")
   → If APPROVED and "create_followup" was checked:
       → calls apps.tasks.service.create_follow_up_task_after_approval
       → service verifies OfficerApproval(decision=APPROVED) exists for (advisory, officer)
       → if pass: creates FollowUpTask(status=ASSIGNED); logs AuditEvent
       → if fail: returns error dict; officer sees error message; no task created

8. Officer sees approved advisory + follow-up task on the dashboard and at /tasks/.

9. Audit trail at /dashboard/audit/ and /audit/ shows every action with timestamp, actor, tool, approval status.
```

## Tool call ordering

```text
   get_cluster_plot_history
                ↓
       get_crop_calendar
                ↓
   get_weather_and_rainfall_context  (×2 — last_30_days, 10_day_forecast)
                ↓
        get_pest_alerts
                ↓
   get_market_price_context
                ↓
   validate_advisory_evidence
                ↓
   (draft_advisory — model call)
                ↓
   create_draft_advisory_record  ← action, logs "draft" approval_status
                ↓
   officer_approval_gate (terminal)
                ↓
   ... officer reviews in UI ...
                ↓
   create_follow_up_task_after_approval  ← action, approval-gated, only after APPROVED
```

## State transitions for an Advisory

```text
   DRAFT
     │
     │ officer decision
     ├──APPROVED──→ (follow-up task can be created)
     ├──REJECTED──→ (terminal)
     ├──DEFERRED──→ (officer can re-evaluate later)
     └──NEEDS_EVIDENCE──→ (officer re-runs agent after fixing data)
```

## What is never sent automatically

- SMS / USSD / WhatsApp messages
- Phone calls
- Orders for inputs
- Credit flags
- Emails

The agent creates: an Advisory row (DRAFT) and AdvisoryEvidence rows. The officer creates: OfficerApproval rows, optionally a FollowUpTask row. Nothing else.
