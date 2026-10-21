# Config data contract

This directory contains the small, human-reviewable fixtures for the flagship
replay. It is not the enterprise-scale database.

Runtime data that the application loads:

- `facilities_demo.csv` — curated operational facilities for the flagship and
  secondary scenarios.
- `products.csv` — curated flagship product master.
- `materials.csv` — curated flagship material master.
- `bom.csv` — curated flagship private BOM.
- `product_facilities.csv` — explicit SKU-to-assembly relationships.
- `material_sources.csv` — approved material-source master.
- `material_allocations.csv` — exact source -> assembly -> SKU edges.
- `inventory.csv` — private inventory fixture.
- `purchase_orders.csv` — private inbound PO fixture.
- `production_orders.csv` — private production fixture.
- `customer_orders.csv` — private customer/distribution commitments.
- `supplier_capacity.csv` — private capacity fixture.
- `substitutions.csv` — engineering substitution state.
- `transport_lanes.csv` — private route assignments.
- `scenarios.csv` and `scenario_facility_state.csv` — replay operational state.
- `historical_event.json` — the real USGS Cianjur event fixture.
- `contacts.csv` — simulated private operational contacts.
- `incident_memory_seed.csv` — clearly labelled simulated prior-run memory.

Human-review reference files:

- `ground_truth_cases.csv` — readable expected cases. Executable tests remain
  the actual enforcement mechanism.
- `source_registry.csv` — source catalogue for judge/research review.
- `provenance.csv` — provenance policy reference.
- `warehouses.csv` — warehouse naming reference.

The large digital twin is generated from code under:

`data/generated/private_twin/`

Do not add precomputed impact, risk-score, event-exposure or recovery-result
files here. Those outputs must be calculated from PostgreSQL/PostGIS and the
solver at runtime.

Fixed data is allowed. Fixed reasoning is not.
