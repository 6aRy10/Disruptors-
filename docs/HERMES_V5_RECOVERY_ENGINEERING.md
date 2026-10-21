# HERMES v5 — material-constrained recovery workbench
Date: 2026-10-22

## Verified engineering state
Branch `feat/db-foundation`, core backend commit `1d2c5587d0cb35e7ace4a7a50be7f701d6bee663`. Full GitHub workflow `39688108321` passed, including PostgreSQL tests and Cianjur control-loop rehearsal. This is **backend validation**, not proof that the user's separate Windows frontend/database instance is synchronized.

## New backend capability
`src/dependency/solver/material_allocation.py` adds `allocate_shared_materials()` to the existing deterministic joint recovery process. Factory sharing was already constrained; materials were previously only audited. This pass now:
- charges one modeled `(material_id,source_facility_id)` weekly limit across all competing products and destinations;
- checks *all* BOM materials and allocation-source share coverage for each proposed backup route;
- reduces existing production allocations priority-first and cost-adjusted-margin-second when modeled inputs are insufficient;
- reports the exact order IDs/quantities reduced, upstream material usage, missing routes, and unknown capacities;
- does not re-count materials for pre-existing finished inventory or currently in-progress production;
- does not treat simulated capacities as confirmed availability or authorization to execute.

`src/dependency/solver/joint_optimization.py` now returns both its original assembly/factory plan and `material_constrained_allocation` with `material_feasible_units`, `material_reduced_units`, and explanatory evidence. Existing factory solver numbers are intentionally retained as pre-material diagnostics.

`src/dependency/solver/portfolio.py` exposes corresponding event-level summary values and no longer labels a scenario as feasible when its new material constraint check fails. Material execution-readiness remains false without authenticated supply evidence. No new migrations, seed data, or external messages.

Ten adversarial standalone tests are in `tests/test_material_allocation.py` and run as part of the full backend workflow.

**Limit:** this deterministic stage repairs an already-selected set of factory allocations. It is *not* a globally optimal, multi-period material/factory/inventory MILP, does not optimize alternative inbound source routing and does not confirm transport ETA or supplier stock. Do not advertise it as one.

## Private frontend integration
The source remains with the owner for privacy and licensing. The new owner-held code-only file `hermes-v5-overlay.zip` applies over the existing `hermes-product-v3` folder after V4. It changes:
- `app/app.js`, `app/app.css`, `app/index.html`;
- adds `tests/browser_recovery_v5.py` and setup instructions.

The explicit **Cianjur earthquake · 2022** replay opens saved event `IDN-CIANJUR-2022-USGS-us7000ir9t` and scenario `SCN-CIANJUR-REPLAY-01`, then requests `GET /events/{event_id}/portfolio/{scenario_id}`. It presents factory-only planned units versus modeled material-constrained units, per-SKU shortages and order IDs, limiting shared materials, permitted candidates and rejection reasons. The live wildfire is NOT converted to a confirmed shutdown: without independent operational evidence, the UI directs the operator to its outstanding evidence task.

Frontend automated checks passed against mocked backend responses (Node syntax, regression harness, Chromium map/scroll/graph/evidence and recovery rehearsal). The user's Windows browser, Vite production build and populated local PostgreSQL are still to be verified in person. The code-only overlay does not expose private website media, waitlist settings, tokens or database data.

## Local synchronization — no reseeding
**Backend:** in the user's existing backend folder, switch to `feat/db-foundation`, run `git pull --ff-only origin feat/db-foundation`, then restart `python -m uvicorn dependency.api.main:app --reload --host 127.0.0.1 --port 8000`. Stop if the checkout has uncommitted changes that block safe pull. Do not run `scripts/load_seed_data.py` or `reset_demo_state()` against the owner's database.

**Frontend:** apply V5 ZIP files over `$HOME\Downloads\hermes-product-v3`, run `npm run test:ui`, `npm run build`, then Vite with `--strictPort`; select the historical Cianjur rehearsal inside `/app/`. Run `scripts/check-backend.ps1` to verify the hazard endpoint. HTTP 404 at `/app-data/map/hazards` indicates the old server/API checkout is still running, even if 770 facilities load.

## Next critical engineering work
1. Real global mixed-integer recovery allocation with facility time windows, shared dated BOM input, approved substitution, material inventory and inbound PO quantities, delivery ETA, and non-partial commitments; benchmarks and infeasibility explanations.
2. Authenticated, auditable supplier-response ingestion, confirmation validity and protected human authorization.
3. Frontend-to-backend integration tests against anonymized but realistic seeded PostgreSQL snapshots; secure deployment and controlled Aiven stream consumption.
