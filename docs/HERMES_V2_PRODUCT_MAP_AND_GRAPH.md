# Hermes v2 — Map and investigation-first UX contract
Date: 2026-10-21

## Evidence from the actual Windows screen
- The original v1 map reported **0 sites** with a successful incident API connection. Root cause is a frontend initialization bug: the initial MapLibre load called `attachMapSources` but did not call `loadMapViewport`. The backend map endpoint has separately passed a PostgreSQL CI test with 770 sites. A "CONNECTED" badge for one endpoint does not imply the map endpoint succeeded.
- The fixed three-column shell left insufficient room for the product dependency graph and customer commitments.
- Automatic startup selected the incident with the most missing evidence tasks even when those tasks contained no connected SKUs. This is bad prioritization for a first-time user.
- The natural-disaster domain count includes low-magnitude earthquakes near public sites: "potential exposure" is not "confirmed damage"; alert quality still needs magnitude-aware suppression.

## Product behavior
1. Initial load fetches world sites **independently of map tile/script timing**. When the site API fails, display an explicit error in map and count. Do not show "0" as if it is a verified network size. Retry from Refresh.
2. Initial incident prioritization starts with actual linked products/commitments when evidence exists. Use `product_linked_evidence_tasks` from `/app-data/incidents` to sort before total pending tasks. Do not hardcode a country, SKU or event.
3. The map is a whole central workspace. The dependency graph is a **separate full-height central workspace**, not a 200px-high panel under the map. Context sidebars may collapse when a user needs more room.
4. Graph inspection opens a detail panel with object type, provenance, quantity/due date and connected edges. Dragging is only a visual layout choice and does not change SQL.
5. Five categories are navigation and filters, not five invented scores: Natural Disasters, Geopolitics & Trade, Logistics & Ports, Supplier Operations, Materials & Dependencies.
6. Provide explicit PUBLIC_VERIFIED / PUBLIC_DERIVED / INFERRED / SIMULATED_PRIVATE signals when relevant. Exposure revenue is not confirmed loss.

## One team workflow
- Versioned backend: this repository, `feat/db-foundation`. Do not reset the 266,737-row local twin.
- Frontend source: user-held Hermes ZIP **not in this public repository**. A teammate must get the zipped frontend code as well as the Git repo; a backend clone alone cannot recreate the experience.
- For full repeatability, the owner should add the frontend as a **private repository** and hand its URL to teammates, or explicitly authorize adding it to the current repository after checking licensing, embedded waitlist settings and assets. Do not distribute passwords or `.env`.
- Local backend: `python -m uvicorn dependency.api.main:app --reload --host 127.0.0.1 --port 8000`.
- Local frontend: `npm ci`, then `npm run dev` at `127.0.0.1:5173`. Keep local `postcss.config.cjs` to avoid inheriting an unrelated Windows home directory PostCSS configuration.
- Check `http://127.0.0.1:8000/app-data/map/facilities?limit=2500`: `total_in_view` should be 770 on the seeded local DB. If it is not, stop and diagnose before evaluating map visual design.
- Choose a linked incident, open the product graph, inspect evidence, and prepare a review-only draft. Do not assert supplier damage or send external messages.

## What is still P0
- Joint material allocation, not only shared-source contention audit.
- Authenticated supplier evidence and protected operational execution.
- Real-world event screening, verified trade-policy feeds and freshness.
- Local browser regression on Windows and a secure managed deployment.

## Hermes v3 hazard semantics and page flow (2026-10-21)

Backend now exposes `/app-data/map/hazards?days=90&limit=350`,
with recorded source geometry, type, event ID, published occurrence time, and
provenance. Orange denotes a **reported hazard observation**. It does not mean
the user selected a dot, or that a supplier is damaged, or that the incident
is currently active. Selection is a **white ring**; company graph paths at
potential exposure use a **green ring**. Draw polygon footprints only when
stored event geometry itself is polygonal; the current USGS/GDACS normalizer
stores POINT coordinates, so do not invent storm paths or impact circles.

USGS earthquakes with a numeric source magnitude below 4.5 are not shown as
orange hazard reports in the overview map. They remain in the event archive
and incident records. The cutoff is a *display noise filter*, not a guarantee
of no damage. The local source-backed map does not claim to predict storms.

A user-visible Hermes v3 patch upgrades the owner's **private** React+Vite
frontend without shipping fonts, landing-page footage or hidden waitlist
settings into the public repository. Its page is naturally scrollable, and
the main map and graph are separate work areas. Ordinary mouse wheel scrolls
the page; Ctrl+wheel explicitly zooms the map or graph. The map now leads
into a data-backed, scrollable incident brief. The graph can show details in
its own large workspace. The repeated internal `DEMO TRUTH RULE` banner has
been removed; uncertainty remains near each relevant fact.

Local user setup: checkout this backend branch and run FastAPI. Apply the
private `hermes-v3-overlay` patch over an existing Hermes v2 folder, then
run `npm run test:ui` and `npm run dev`. The script installs no new Python
packages and never reloads the PostgreSQL data. No deployment or broad public
write permissions are implied.
