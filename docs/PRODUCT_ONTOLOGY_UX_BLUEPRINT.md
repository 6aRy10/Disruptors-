# Dependency — Object-centered product and UX blueprint

Status: **design contract, not an implemented interface**.
Do not start the full frontend replacement until the existing marketing website source has been reviewed.
This page aligns product, graph data, backend, and interaction teams. Use direct language in approximately ASD-STE100 style.

## What Dependency is

**An operational supply-chain recovery system.** An event is a starting point. The outcome is an evidence-backed decision that protects real customer commitments.

For one selected incident, an operator must be able to answer:
1. What happened, where, when, and which source reported it?
2. Which of our known supplier sites, materials, products, and customer orders have a verified graph path to it?
3. What is potentially exposed? What operational harm is confirmed?
4. Which fact is missing, and who can confirm it?
5. Which recovery choices are feasible across shared material and factory capacity?
6. Which authorized action was taken, and which commitments are now protected?

No standalone risk score should replace this sequence.

## Navigation: five risk domains, not arbitrary business headings

1. **Natural Disasters** — earthquake, flood, wildfire, cyclone, volcano. Geographic exposure is not an operational shutdown.
2. **Geopolitics & Trade** — tariffs, sanctions, export restrictions, policy changes. Official version and applicability are required; a demo policy scenario is not a new live law.
3. **Logistics & Ports** — port calls, closures, shipment delays, alternative lanes. A derived port-call anomaly is not proof a given shipment is late.
4. **Supplier Operations** — verified facility operating state, capacity, source quality, and production/ETA deviations. Private confirmation is required.
5. **Materials & Dependencies** — BOM, common upstream material sources, sole-sourcing, inadequate stock, and correlated backup routes.

Domains are FILTERS over one connected set of facts, not separate databases. A wildfire may show up under Natural Disasters; a later confirmed capacity drop also belongs under Supplier Operations. Both point to one incident and the same facility.

Optional cross-domain layer: **Commercial Exposure & Recovery**, showing connected revenue, protected units, shortage, margin, and approved recovery. This is an outcome, not another public hazard source.

Do not add Cyber, Finance, ESG or other generic headings until each has real source, rule, and operator action.

## Ontology-inspired object contract (do not install or claim Palantir)

Objects:
- Public event: event_id, source, time, geometry, source URL, publication status.
- Public supplier identity: network_facility_id, name, coordinate provenance, source list.
- Private operational facility: facility_id, linked public identity, role and confirmed state.
- Material: material_id, units, BOM family, approved allocation and sources.
- Product/SKU: sku, production assignment, BOM and commercial commitments.
- Customer commitment: order ID, due date, priority, quantity, revenue/margin model.
- Transport lane/shipment: lane ID, exact endpoint, transit time, ETA and verified status.
- Incident: incident ID, evidence gaps, state, connected graph and change history.
- Evidence task/response: task ID, target, required fact, requester, source, approval.
- Recovery plan: plan ID, scenario, state version, rejected alternatives, resource use, trade-offs.
- Approval/execution: actor, permission, proposed edit, decision, state transition and audit reference.

Links:
- event near public facility (derived distance only, never damage);
- public identity linked to operational facility (explicit, labeled simulated if relevant);
- operational facility makes SKU;
- upstream supplier provides material to facility for SKU;
- SKU consumes material and serves customer commitment;
- shipment or lane carries a specific leg;
- incident concerns event/facility/order;
- evidence confirms or refutes one operational fact;
- recovery plan allocates actual capacity/inventory to commitments;
- approved action changes operational state and invalidates prior plans.

Link retrieval must preserve identity, edge type, provenance and time. No geographic, country, or common-parent guess may invent a private business link.

Actions:
- Open/triage incident.
- Expand dependency neighborhood.
- Request evidence and prepare a **review-only** draft.
- Record independently verified operational facts with explicit source.
- Compare alternative recovery scenarios.
- Request/record approval.
- Execute only allowed changes, track execution and replan.

Keep model analysis separate from deterministic SQL/Python decisions. Use operator permissions, audit and idempotency for writes.

## Target application flow

**Existing marketing page at /**. Retain the user's brand, content, components and assets.
The **See how it works** CTA routes to /app (or a named demo route after source review).
Do not launch a disconnected second website or link production browsers to localhost.
The backend is the existing FastAPI/PostgreSQL engine behind an authenticated or restricted API deployment.

**Application /app**:
- Top: product identity, live/replay indication, last update, search, saved views and operator role.
- Navigation: five risk domains, Incidents, Recovery Workbench, Network Explorer, Activity.
- Primary viewport: real interactive world map with point clusters. 770 public sites must be represented faithfully; do not present 9.8k facilities because the screenshot did.
- Right context inspector: selected event/factory/SKU/order, evidence, source, identity, time, connected commitments and actions.
- Expandable graph workspace: downstream/upstream links and shared suppliers; user can pan, zoom, drag graph *visualization* nodes and lock positions for their own analysis.
- Bottom/right decision workspace: missing-evidence queue, candidate plans, rejection reasons, before/after state, approvals and execution log.

One selected object context must survive switching map/graph/risk category/recovery tabs.

## Interaction contract

**Map**:
- Pan with drag, zoom with wheel/pinch, cluster at low zoom, expand clusters on select.
- Toggle five domain overlays. Filter by country, event type, date, status, tier, source and business-linked sites.
- Select a site: show true identity, linked private facility (if any), evidence age, incident and exact connected products.
- Click "Show upstream/downstream" to open filtered relation graph.
- Highlight only event paths supported by explicit joins. Show nonlinked public sites without inventing exposure.
- Facility geographic coordinates do not change when dragged. Geography is not an editable graph layout.
- Show stale-source markers, a visible LIVE/REPLAY label and UTC/locale time carefully.

**Dependency graph**:
- Expand one/two hops, pan, zoom, search and focus. Drag nodes for layout only; do not modify SQL graph links.
- Edge click shows link evidence, quantities, effective dates and provenance.
- Switch direction from "What depends on this site?" to "Where does this SKU come from?"
- Collapse shared material branches, compare current and candidate recovery routes, show rejected options.
- Use progressive graph neighborhood queries and explicit pagination. Never load 170,018 allocation edges into the browser.

**Profile / domain risk panel**:
- Keep hazard occurrence, possible exposure, confirmed operational effect, urgency, confidence, and recovery status separate.
- Score only domains with a defended feature set, current source and transparent calculation. The current weighted formulas are modeled heuristics, not calibrated failure probabilities.
- If a domain lacks data, show "Not assessed" or "Evidence required", never a decorative number like Cyber 70.
- Risk color must express a clearly named quantity: source event severity, potential commercial exposure or confirmed shortage. Do not mix semantics.

**Operator workbench**:
- Every alert card should have "Investigate", "View dependencies", "Request missing fact", or "Evaluate recovery", where valid.
- Every decision shows original plan, source data, version, updated plan, competing resource demands, evidence and audit.
- Human-approved actions are separate from freeform AI suggestions.

## Required example from local data

The real GDACS event GDACS-WF-1032942:
- three public network sites within 150 km;
- one explicit linked private facility ADI26-0239;
- private product IU7704 with 6,000 connected commitment units;
- €360,000 connected revenue, €144,500 connected margin (SIMULATED_PRIVATE economics);
- incident INC-b468b7ac-eb34-44d9-b960-7e9e6bdf81ea;
- open task CONFIRM_FACILITY_STATUS from live reconciliation;
- no confirmed loss or shutdown yet.

An operator clicking the wildfire should see the graph path, the correct provenance, and that specific outstanding task. It must **not** show a 100% shutdown, €360k loss, or automatic recovery action.
The seeded Cianjur replay is the sole full-control-loop flagship. Preserve the original 2022 occurrence date.

## Data and engineering gaps before polished interface

P0:
1. Define stable graph neighborhood and map viewport APIs; include node/edge types, facets, metadata, permission and source provenance.
2. Verify no double-counting in a genuine multi-material/multi-SKU solver. The existing shared-material component is an AUDIT, not a full allocation optimizer.
3. Make evidence-to-supplier confirmation operational and authenticated; currently drafts are review-only.
4. Make official policy/routing applicability time-bound and sourced; live tariff adapter is incomplete.
5. Make observable lifecycle state transition from incident to solved/approved/executed; one default snapshot cannot substitute an event timeline.
6. Validate per-domain risk semantics: severity != proximity != operational impact != connected commercial value != confirmed loss.
7. Verify frontend queries against arbitrary events as well as the Cianjur replay; test drilldowns, filters, and a realistic data volume.

P1:
- Reliable always-on collectors, per-source freshness and false-positive screening.
- Additional external source adapters only if they reach a real data entity and have actionable next evidence.
- Multi-party permissions and production-grade remote connectivity.
- Longitudinal commercial and event history, quality benchmarks and calibration.

## Visualization implementation proposal, pending website inspection

- MapLibre GL JS for a real pan/zoom interactive vector map and clustering.
- Cytoscape.js for data-driven upstream/downstream relationship graph with drag-to-arrange, collapse and expand.
- If the supplied site already uses React, evaluate React Flow only for focused workflow/candidate comparison canvases; it is not a reason to rebuild the site.
- Use current backend PostGIS for bounding-box/filter spatial queries, not browser-side scans.
- Render scoped, paged neighborhoods; put the large graph and full solver in PostgreSQL/Python.
- Defer CSS/animation/component architecture until the website ZIP or GitHub source is available.

Visual quality is important; decision validity is mandatory.

## Visual inspiration is not a product dependency

Take from Palantir-like systems the organization around linked business objects, geospatial exploration, and action-backed operational workflows.
Do not copy Palantir code or imply use of its platform.

Relevant official references:
- Palantir Ontology-aware applications: https://www.palantir.com/docs/foundry/ontology/applications
- Palantir actions: https://www.palantir.com/docs/foundry/action-types/overview/index.html
- MapLibre: https://maplibre.org/maplibre-gl-js/docs/
- Cytoscape.js: https://js.cytoscape.org/

## Website handoff

User should share the frontend repository URL OR upload source as ZIP.
Include source, assets, package manifest and lockfile, but exclude .env, tokens,
node_modules, build output and .git.
Before changing the app's markup or building routes: inspect that actual source,
select compatible framework and deployment, define /app and /api boundaries, and
make a UI milestone whose controls all work against live backend queries.
