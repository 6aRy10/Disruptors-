# HERMES v10 — geographic availability and exact allocation paths

## Verified backend
Branch `feat/db-foundation`; CI workflow 39725029460 passed after the graph/expeditor changes.

`GET /products/{sku}/graph` now includes `allocation_routes`: one row per approved modeled `source_facility_id + material_id + destination_facility_id + sku` route, with modeled share, BOM units per SKU (if present), source and destination names, and provenance. The original node/edge overview remains available. This is a compatibility-preserving additive response, not a database migration.

A MATERIAL overview node is **not** proof that every upstream source of that material supplies every destination factory. It merely connects the high-level diagram. Only `allocation_routes` gives destination-qualified modeled connections. No supplier route proves a real shipment, verified capacity, inbound ETA, or assignment of a customer order to a factory or supplier.

`POST /app-data/ask` now retrieves those qualified routes when a supplier, material, or assembly factory is selected. For upstream suppliers, it labels downstream orders **SKU-level potential commitments (not assigned to this supplier)**. It does not claim physical supplier-to-order fulfillment. `tests/test_expeditor_route_truth.py` verifies that when Source A only supplies Factory A, the expeditor does not fabricate Source A -> Factory B even if both factories consume the same shared material node. This test runs in GitHub CI.

## Private website v10
The owner's private `hermes-v10-map-and-routes-overlay.zip` is held outside the public repo. It replaces the unusable blank-grid fallback that was triggered when MapLibre/CDN tiles were unavailable.

The v10 overlay:
- ships bundled coarse GSHHG/WDBII coastlines and borders for a usable offline map;
- preserves all public supplier and source observation coordinates fetched from FastAPI;
- groups dense point markers and provides zoom, pan, reset, direct event selection, and case-focused map navigation;
- distinguishes model-linked public sites from source observations and selected case;
- shows the returned destination-qualified allocations when inspecting a supplier/material/factory;
- handles coincident source-report and supplier markers with an object chooser;
- displays read-only per-case factual counts rather than substituting fixed UI totals;
- keeps the expeditor input accessible through Ctrl+K while clearing obstructive floating controls.

The map layer is geographic reference only. Its underlying GSHHG data is LGPL-3.0-or-later, with attribution and license included in the private overlay. It does not include any synthetic hazards.

## Verification boundary
Node UI regression and headless Chromium tests passed with controlled API fixtures, including 770 public locations and 129 hazard observations. This is not a test against the owner's Windows database. An npm/Vite production build remains to be verified on the owner's computer because the assistant runtime's npm offline cache lacked needed packages.

No loader, schema reset, local PostgreSQL mutation, supplier contact, or paid AI invocation was used for this v10 iteration.

## Still open
- Global material and assembly optimization with dated source capacities and transport arrivals.
- Assignment of actual supplier/plant routes to orders, authenticated responses and permissioned evidence.
- Versioned public source updates, managed workers, Aiven Kafka proof and durable operational alerting.
- Server-paged cross-SKU dependency graph, authenticated enterprise connectors, and real-world product validation.
