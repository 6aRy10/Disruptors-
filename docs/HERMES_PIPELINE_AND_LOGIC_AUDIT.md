# HERMES — pipeline, event-feed and decision-truth audit
Date: 2026-10-22. Backend branch: feat/db-foundation. Public brand: HERMES.

## What was observed in the source
1. The old frontend ran `refresh()` once on startup and on explicit Refresh. It fetched `/events` but did not render an incoming-event timeline, did not subscribe to new source receipts, and showed no collector status. This made USGS/GDACS activity invisible.
2. `scripts/run_live_stack.py` supports `--watch` but does **not** run automatically with Uvicorn. `python -m scripts.run_live_stack` runs only one cycle. It polls USGS (nominally once a minute), GDACS (five minutes), processes a local outbox worker (five seconds), and only checks IMF PortWatch with the explicit `--portwatch` option.
3. USGS uses an official one-hour earthquake GeoJSON feed. GDACS supplies recorded earthquake/cyclone/flood/volcano/wildfire features (the normal watch selects four types). These are public reports, not authenticated supplier disruption records. A GDACS record's `mode='LIVE'` refers to collection mode, not proof of an active disaster.
4. `external_events.ingested_at` is updated on repeat polls, so its latest value **cannot** be used as a stream of *new* hazards. The `external.events` transactional outbox is inserted only on first receipt per event ID. The event stream now uses `event_outbox.created_at` for first receipt and preserves the original `occurred_or_effective_at` separately.
5. Local worker processing and Aiven Kafka publishing have separate state. `event_consumptions.status='SUCCESS'` means the PostgreSQL worker processed a message; `event_outbox.published_at IS NULL` means no Kafka publication is recorded. A high unpublished count is not a local processing failure. Aiven broker reachability remains **NOT_VERIFIED** until its independent preflight and networking test passes.
6. Previously there was no durable record that a source was actually checked. The added *idempotent* migration `005_collector_checks.sql` records USGS, GDACS and PORTWATCH poll results without touching inventory, supplier network, operational state or the existing commercial twin. This status is recorded only when `run_live_stack` executes. Direct one-off watch scripts need separate status integration.
7. PortWatch event attribution is `IMF PortWatch` while the watcher's identifier is `PORTWATCH`. The activity response merges their health identity for source status while retaining the public report's original attribution.

## Implemented in this milestone
- `GET /app-data/activity?limit=80` (optional `source` and offset-aware `since`) provides real, bounded event receipts, source dates/first receipt dates, local consumption outcome, linked incident/task state, independent outbox counters and source poll health. No simulated events or fake moving hazard dots.
- Public source status distinguishes `RECENT_SUCCESS`, `RECENT_ERROR`, `STALE`, and `NOT_VERIFIED`. A recent successful poll can have **zero** new events. It does NOT prove no hazards exist.
- Private frontend v8 code-only overlay adds a persistent three-event glimpse plus full **Event feed** workspace. It refreshes the read-only endpoint about every twelve seconds while the page is visible; it filters sources and opens existing event objects using their real IDs.
- Existing historical Cianjur rehearsal remains separate from public source receipts. An older observed hazard first received today displays **both** dates.
- Reporter visibility does not start a worker. A report with proximity to 770 public sites is not evidence of operational impact; connected simulated-private economics are potential exposure, not confirmed loss.
- Unit tests cover deduplication contract, source stale/not-verified state, parameterized SQL, local/Kafka counts, PortWatch partial failure handling and watcher isolation. Frontend Node/Chromium tests use mocked responses and verify a genuinely new entry appears without a manual page reload.

## Running the real source pipeline on the owner's Windows DB
- **Never run** `scripts/load_seed_data.py`, `reset_demo_state()`, or a destructive database command against the user's existing `Disruptors` database.
- Pull latest `feat/db-foundation` and run `python -m scripts.apply_migrations` once. Its SQL files use idempotent additive schema operations. This creates the collector-check log without erasing the 770 public sites or modeled 266,737-row private twin.
- Terminal 1: `python -m uvicorn dependency.api.main:app --reload --host 127.0.0.1 --port 8000`.
- Terminal 2: `python -m scripts.run_live_stack --watch`. No paid agents or external messages by default. Consider `--portwatch` only when its extra official network calls are explicitly wanted and provider usage is appropriate.
- Terminal 3: private Vite app `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`.
- Query `http://127.0.0.1:8000/app-data/activity?limit=20` to inspect source check status. If all sources are `NOT_VERIFIED`, confirm the watch terminal is running and the migration has been applied. If there are zero new events, inspect recent successful source poll results rather than inventing a sample event.

## Structural issues still open — not disguised as done
- Live source coverage: not yet a broad world-risk data platform. Official policy/tariff ingestion by date, logistics shipping ETAs, verified capacity/ERP integrations, supplier-authenticated response, route disruption and continual managed collection are unfinished. PortWatch signals are derived activity changes, not verified shipment failure.
- Feed completeness: the current source ledger lists **first receipts**. Later revisions to the *same* provider event are overwritten in `external_events`; we still need a versioned observation history and change-detection outbox to display meaningful evolving storm/disaster updates without duplicates.
- Failure isolation: error classes are logged, not sensitive endpoint details. Source poll receipts tell the operator freshness, but robust retry/backoff, metrics retention and managed workers remain open.
- Graph: supplier-material overview arrows group destination routes; the data retains allocations but the graph still needs route-specific materials/lanes by time, hop-based server pagination and proof that alternative factory paths are material-feasible.
- Solver: shared factory capacity is constrained, shared materials receive deterministic priority repair, but the result is NOT a globally optimal, dated multi-material MILP; non-partial commitments and independently confirmed material arrival/transport still require work.
- Expeditor: `/app-data/ask` is a bounded read-only, largely rule-based retriever by default, with optional paid model wording. It does not have authenticated general enterprise retrieval, multi-turn plan execution, fine-grained permissions or evaluation against realistic query sets.
- Production: the private frontend is not in this GitHub repo; backend CI works against a disposable PostGIS fixture and cannot prove the owner's live Windows Postgres/browser instances. No claim of Aiven, multi-user security or commercial deployment.

## Acceptance criteria for the team
1. With Uvicorn running but watcher **stopped**, the page must say source poll is stale/not verified; it must **never** say the source is live merely because the API responds.
2. With watcher running, successful poll metadata appears even when zero new source events exist.
3. The event feed sorts by first source receipt, not event age; clicking any entry opens the matching stored event ID.
4. Retrying the same provider event cannot create a second new-event entry.
5. An outbox message processed locally but unpublished to Kafka must show both outcomes separately.
6. All read-only views remain operational if the collector-check migration has not yet been applied (status is not verified).
7. The owner's populated database must retain its existing public sites, private products, material allocations and commitments after the additive migration.
