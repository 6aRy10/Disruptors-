# HERMES v4 — private frontend and backend compatibility
Date: 2026-10-22

## Scope and delivery
The user-held Hermes v3 React/Vite source is still private and is NOT included in this public backend repository. V4 is an incremental code-only ZIP overlay onto the existing `hermes-product-v3` folder. The owner must obtain the private source and overlay separately. Do not copy private hero footage, font files, waitlist configuration or credentials into this repository.

This milestone follows the screenshot of the previous V3 layout: 770 public Adidas network sites loaded locally but the fixed three-column UI was cramped and the general hazard layer reported unavailable. The exact backend failure cause was not shown in the screenshot and is **not** assumed.

## Read contracts used by V4
- `GET /app-data/map/facilities?limit=2500` — source-backed facility identities, with `business_linked` only for explicit modeled relationships.
- `GET /app-data/map/hazards?days=90&limit=1000` — valid GeoJSON FeatureCollection with stored source geometries. The new UI supports query periods of 7, 30, 90, and 365 days and does not fabricate radius buffers.
- `GET /app-data/incidents?limit=100` — case triage, with cases that have SKU-linked evidence work prioritized.
- `GET /app-data/events/{event_id}` and `GET /events/{event_id}/impact?radius_km=150` — source event, actual incident, evidence tasks, and explicitly connected modeled commercial exposure.
- `GET /products/{sku}/graph` — source, material, assembly, SKU and commitment relationships; `shared_upstream_sources` computed from real database joins. Selected node and edge data preserve their provenance.
- `POST /investigations/tasks/{task_id}/prepare-outreach` — only user-initiated, internal review-only drafts; **no external dispatch**.

A source-feed failure is shown separately from the other working data sources. An independently selected event with source-backed point coordinates can still show that *observed event location*, never an invented footprint or current-active claim. The UI discloses the graph preview limit; it does not pretend to display every node or link.

## V4 UI behavior
1. Light, full-width main workspace with narrow navigation; details are in an optional drawer, not a permanent third column.
2. A selected-case strip maintains context while the operator moves between Map, Dependency graph, Evidence and Recovery. An `?event=...` and `?view=...` URL is retained.
3. Evidence is now a task queue for the selected incident; operator-triggered review-only draft action is available.
4. The graph lays out upstream suppliers -> BOM material -> assembly -> product -> customer commitments. Node and edge selections expose stored fields and a shared-source control exposes genuine backend results.
5. Recovery remains blocked until an independently confirmed operational scenario exists. The public event does not change supply-chain capacity.

## Tests and limitations
- V4 Node regression tests passed for the first map fetch, source GeoJSON polygons, error reporting, inspector controls, task rendering and graph selection.
- Headless Chromium testing with **mocked** read responses passed for map loading, normal page scroll, actual evidence task, inspector and product graph, with no JavaScript exceptions.
- V4 production Vite build was NOT verified in the assistant runtime because Vite dependencies were not fully installed; it must be run on the owner's Windows machine.
- Owner's actual browser, local PostgreSQL contents, real backend hazard endpoint, and production CDN map remain unverified for this v4 overlay.
- This overlay makes no changes to PostgreSQL, migrations, seed data, Aiven brokers or recovery execution.
- Important unfinished engineering: joint multi-material allocation and feasibility, authenticated supplier responses, always-on collectors and streaming, strong authorization, dated official policy application, workspace-level graph pagination, secure live deployment and team-controlled private frontend versioning.

## Team validation (read-only)
The v4 overlay ships a PowerShell script `scripts/check-backend.ps1`. Run it from the private v3 frontend source directory after applying the overlay. It reads the three endpoint groups above and surfaces a missing source-report route. If 404 appears, check out and pull `feat/db-foundation` and restart the backend; do not seed or reset any database. If 500 appears, inspect FastAPI traceback and do not assert the cause from the screenshot alone.

Historical GDACS wildfire `GDACS-WF-1032942` (2026-10-15) remains an investigation, not a confirmed shutdown; modeled IU7704 potential connected revenue of EUR 360,000 is not actual loss. The Cianjur 2022 full-control-loop recovery replay is distinct from the arbitrary live wildfire.