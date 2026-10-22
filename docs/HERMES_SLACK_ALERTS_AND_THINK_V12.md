# HERMES v12 — Slack cyclone alert + supplier reply + Think HERMES
**22 October 2026 | owner and engineering handoff | branch feat/db-foundation**

## Current implementation (not deployment proof)

1. **Outgoing cyclone warning to internal Slack operations channel.**
   New module `dependency.notifications.cyclone_alerts`, additive
   `sql/migrations/007_slack_cyclone_alerts.sql`. The existing
   `python -m scripts.run_live_stack --watch` checks for **newly locally
   processed** GDACS tropical-cyclone incidents after the worker cycle.
   Must be LIVE, source occurred in last 72 hours, and attached to an existing
   modeled/public supplier-network incident. Historical replay and events with
   no incident cannot trigger a message.
   Dedup ledger records SENDING/SENT/FAILED per event; failure retry after
   10 minutes, never resend a successfully marked SENT alert. A process crash
   during SENDING requires human review; webhooks cannot prove exactly-once
   delivery. This is a **reported cyclone hazard**, NOT proof of landfall,
   destroyed inventory or factory shutdown. No speculative loss numbers.
2. **Supplier capacity request + inbound reply.**
   Already available Slack bot via `dependency.notifications.slack` and
   `dependency.services.supplier_outreach`. Routes:
   `POST /supplier-confirmations/capacity` to create a durable review-only
   request (dispatch:false);
   `POST /supplier-confirmations/{request_id}/dispatch` after explicit
   operator decision and external-message opt-in;
   `POST /integrations/slack/events` to receive Slack Events API callback.
   Slack signature + timestamp verified, bot messages ignored; replies must
   be **in the original thread**, from the explicitly authorized Slack user
   in direct-message mode or `SLACK_SUPPLIER_ALLOWED_USER_IDS` allowlist for
   shared-channel mode. Reply is parsed and stored; it does **not** change
   capacity. `POST /supplier-confirmations/{request_id}/confirm` must be
   completed by a human planner before state update/replan. Supplier identities
   in seeded data are **simulated**.
3. **Think HERMES.**
   `POST /app-data/think` uses `answer_expeditor` and explicit DB
   `event_context`, `trace_business_event_impact`,
   `product_dependency_graph`. Returns factual `answer`, sources,
   `metrics`, `visualizations`, `evidence` and `truth_contract`.
   Event view: connected SKU units, modeled economic values, evidence tasks.
   Selected SKU: modeled demand by market and approved destination-specific
   source→material→factory allocations. No arbitrary SQL. Models only used
   if existing `DEPENDENCY_EXPEDITOR_MODEL=1` explicitly enabled.
   Private v12 frontend overlay provides responsive bar/route views;
   /app/ needs the ZIP applied, not just a backend pull.

## Slack setup — YOU must create these two distinct flows

**A: Operations alerts → private #hermes-incidents channel**

1. Open https://api.slack.com/apps and create a Slack app for **your**
   test workspace. Add an internal private channel `#hermes-incidents`,
   invite the app/bot as needed.
2. Enable **Incoming Webhooks**. Click **Add New Webhook to Workspace** and
   choose `#hermes-incidents`. Copy URL privately. Official:
   https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/
3. Put these ONLY in your local backend `.env` (not GitHub or chat):
   ```dotenv
   DEPENDENCY_DATABASE_TARGET=local
   SLACK_INCIDENT_WEBHOOK_URL=https://hooks.slack.com/services/<real-parts>
   DEPENDENCY_ALLOW_EXTERNAL_MESSAGES=0
   ```
   Keep `DEPENDENCY_ALLOW_EXTERNAL_MESSAGES=0` until tested/reviewed. An
   incoming webhook sends messages only, it cannot subscribe to replies.
4. Pull current branch, `python -m scripts.apply_migrations` (additive,
   non-reset). Use read-only `GET /integrations/slack/cyclone-preview/{event_id}`
   for a stored tropical-cyclone event; no Slack message is sent. If none of
   the source events meets requirements, do NOT inject a false real event
   into the owner's populated DB just to force an alert.
5. After explicitly authorizing real Slack operations-channel alerts, set
   `DEPENDENCY_ALLOW_EXTERNAL_MESSAGES=1` and **restart the background
   source watcher** so it picks up new settings. It will send only for
   eligible, locally processed, fresh source events. With no new relevant
   hazard, 0 notifications is the correct outcome.

**B: Supplier requests/replies → Slack bot + signed Events API**

1. Same Slack app is fine, or separate app for supplier communication.
   Install to your own Slack workspace. Bot OAuth scopes:
   `chat:write` for `chat.postMessage`; `im:write` if calling
   `conversations.open` to create a direct message; `im:history` for
   `message.im` subscriptions. If using private/public channels instead,
   add the appropriate `groups:history` / `channels:history` and
   `message.groups` / `message.channels` subscriptions.
   Official: https://docs.slack.dev/apis/events-api/ ;
   https://docs.slack.dev/reference/methods/conversations.open
2. Configure the **Event Subscriptions** Request URL:
   `https://<your-private-HTTPS-domain>/integrations/slack/events`.
   Slack requires reachable HTTPS; local `127.0.0.1` is not reachable by
   Slack. Route ONLY that signed webhook path through a secure gateway.
   **Do not publicly tunnel your entire development FastAPI server**:
   it contains operational and write APIs and is not a multi-tenant-secure
   product. Set a strong `DEPENDENCY_WRITE_TOKEN` and protect all other
   endpoints with authentication/network restrictions. If you cannot set
   a path-restricted HTTPS gateway, use local manual reply rehearsal until
   secure deployment is available.
3. Add to backend private `.env`:
   ```dotenv
   SLACK_BOT_TOKEN=xoxb-<real-bot-token>
   SLACK_SIGNING_SECRET=<real-signing-secret>
   SLACK_SUPPLIER_ALLOWED_USER_IDS=U<real-consented-supplier-test-user>
   DEPENDENCY_ALLOW_EXTERNAL_MESSAGES=0
   ```
   The Slack signing secret is **not** the bot token and is not the incoming
   webhook URL. Incoming event signatures are validated with HMAC SHA256.
4. Seeded `config/contacts.csv` includes
   `CNT-HS` (facility `ADI26-0240`, SKU `JI2993`) with fake Slack
   address `U_DEMO_SUPPLIER`. **That ID cannot receive messages.**
   For a demo, use a real consenting teammate's Slack U... ID and
   explicitly review/update the corresponding **modeled test contact** in
   your own disposable database. Do NOT send anything to an actual Adidas
   supplier or use the company's brand as if the request is authorized.
   Use the separate supplier test workspace or a Slack Connect channel in
   which the intended respondent has consented to the test.
5. While external messages disabled, use:
   ```http
   POST /supplier-confirmations/capacity
   Content-Type: application/json

   {"facility_id":"ADI26-0240","sku":"JI2993",
    "scenario_id":"SCN-CIANJUR-REPLAY-01",
    "recipient_contact_id":"CNT-HS","dispatch":false}
   ```
   This returns a durable `request_id`, current modeled capacity, a
   human-review message and status. Verify address, simulated private
   context and exact requested quantity/date. Only then set external opt-in
   and call `POST /supplier-confirmations/{request_id}/dispatch` deliberately.
   It stores Slack channel ID and thread timestamp.
6. Authorized teammate replies **in the message thread**:
   "Capacity is 5,500 pairs per week until 2026-11-04."
   Slack callback verifies signature, channel/thread and permitted sender.
   It writes a parsed reply only. `GET /supplier-confirmations/{request_id}`
   shows response, parsed capacity, and confirmation state.
   The human planner then reviews source/consent and calls
   `POST /supplier-confirmations/{request_id}/confirm` with `reply_id`
   and `confirmed_by`; the deterministic capacity service invalidates and
   replans via stored state events.
   **Do not auto-confirm user-sent text.**

## Only two terminals

Terminal 1 runs your backend FastAPI (port 8000) and existing
`HermesLiveFeeds` background PowerShell job. Put config in local `.env`,
stop the old background job and start it again after changing `.env`.
Terminal 2 runs private frontend Vite (port 5173).
No third terminal is necessary; never run two consumers against the same
database. See `docs/LOCAL_DATABASE_AND_FEEDS.md`.

## Verification / outstanding items

- Backend unit + CI tests are expected to validate permitted sender,
  read-only source-linked charts, default outbound block and correct cyclone
  uncertainty language. Passing unit/CI does NOT prove Slack workspace
  delivery. Verify one actual send and a signed inbound Slack reply before
  saying "live integrated".
- No real Slack webhook or bot token has been supplied, so neither outbound
  channel is active on the owner's machine.
- Alert criteria are **current cyclone report and incident**. Detecting
  actual cyclone landfall or future storm track crossing a site requires
  versioned forecast polygons and confirmation; current center-point
  proximity does not prove "hit".
- Think HERMES is grounded and chart-backed for selected event, supplier,
  SKU and orders. It cannot answer literally *every* enterprise question:
  missing graph edges, unverified ERP access, actual supplier shipments and
  permissions remain gaps. No arbitrary user SQL is permitted.
- For business metrics, everything based on the Adidas private demo twin
  remains SIMULATED_PRIVATE. Connected value != proven loss.
