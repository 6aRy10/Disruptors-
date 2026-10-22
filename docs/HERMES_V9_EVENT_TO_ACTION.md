# HERMES v9 — event-to-action acceptance contract
Last updated: 2026-10-22
Branch: `feat/db-foundation`

## Goal
Show the operator what happened to one report. Do not confuse source activity, potential network exposure, verified operational damage or recovery authorization.

## Trace API
`GET /app-data/events/{event_id}/journey` is a read-only FastAPI route. It uses PostgreSQL rows from:
- `external_events`: source identity, observed event date, mode and provenance;
- `event_outbox`: first receipt and separate Kafka publication timestamp;
- `event_consumptions` for the `incident-orchestrator` consumer: local processing outcome;
- `incidents`: any recorded investigation and linked scenario;
- `incident_investigation_tasks`: open or resolved evidence tasks.

The API returns six stages: observation, first receipt, local triage, investigation, operational evidence and recovery decision. It also gives a machine-readable `next_action.code`. Common next actions are `RUN_LOCAL_WORKER`, `CHECK_PROCESSING`, `VERIFY_OPERATIONS`, `REVIEW_SCENARIO`, `MONITOR_SOURCE` and `REVIEW_CASE`. No stage claims an action was executed.

The worker stores its business result **directly** in `event_consumptions.result_json`. The trace reader accepts both this stored shape and any historical extra `result` wrapper. A successful local consumption is not Kafka delivery. An event with no linked confirmed operational scenario has recovery `BLOCKED`, even if it has modeled downstream commitments.

New events create one `external.events` outbox row. Repeated polls can update the stored event observation but must not create a second first-receipt entry. The trace uses the outbox row's original `created_at`, not the mutable event `ingested_at`.

## Private frontend integration
The code-only `hermes-v9-event-journey-overlay.zip` applies over the user's existing private v8 website source. In Event feed, choose **Trace journey** on a stored report. Its six checkpoints and next action come from the API above, not a hardcoded screen. The panel updates on background polling and remains open when the event list changes. **Inspect source report** is shown when there is no incident; **Open investigation** appears only when a case exists.

The private website source and its media are not published in this backend repository. The overlay only modifies `app/app.js`, `app/app.css`, adds a browser test and a read-only PowerShell diagnostic.

## Verification
Full backend GitHub CI uses a separate disposable PostgreSQL/PostGIS service. `tests/test_event_journey_e2e.py` injects a uniquely identified **synthetic rehearsal event**, finds the actual outbox row, invokes the idempotent local worker, checks that a linked facility produces an incident and evidence request, and confirms that repeat delivery does not duplicate the event or task. A second test uses a remote-ocean event to confirm that HERMES does **not** invent a business incident. An unknown-event test checks 404 semantics. The test methods cannot run on an ordinary local database: they skip unless `HERMES_CI_DISPOSABLE_DB=1` is explicitly set in the disposable CI workflow.

Local browser regression `tests/browser_event_journey_v9.py` uses controlled API responses and checks: pending event -> processed event -> evidence task, preserving selection on a 12-second feed refresh, accurate next action, and no automatic approval. Existing v8 event-feed, v7 graph and v5 recovery browser checks passed in the assistant's sandbox using mocks. **No claim** is made that the user's populated Windows PostgreSQL or production deployment has been exercised by those browser tests.

## Windows validation without reseeding
1. Keep the original private PostgreSQL database. Do **not** run `scripts/load_seed_data.py`, `reset_demo_state()`, or any test marked disposable-CI.
2. Pull the current backend branch and restart Uvicorn. The v9 trace adds no migration.
3. In a separate terminal, run `python -m scripts.run_live_stack --watch` to poll USGS and GDACS and process the PostgreSQL outbox. IMF PortWatch requires the optional `--portwatch` flag. No paid LLM agents run by default.
4. Apply the private v9 frontend overlay to the existing frontend, run UI tests, start Vite, then open Event feed -> Trace journey.
5. Use `scripts/check-journey.ps1` from the frontend directory for a read-only summary of the most recently recorded source receipt.

## Remaining work
- Versioned updates to existing source events, including meaningful changes in storm footprints.
- Managed always-on collectors, backoff, alert delivery and real Aiven Kafka proof.
- Route-specific dated material availability and global recovery optimization.
- Authenticated supplier evidence and human-approved operational execution.
- Enterprise access permissions, secure deployment, end-to-end load testing and verified browser acceptance on actual customer datasets.

**Decision boundary:** Public hazard proximity is potential exposure only; private supply-chain links and values in this project are simulated. A possible supplier constraint is not a verified closure, and a modeled protected margin is not a realized outcome.
