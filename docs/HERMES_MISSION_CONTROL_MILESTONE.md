# Hermes Mission Control — data contract and first product milestone

**Branch:** `feat/db-foundation`. **Public repository:** backend API and architecture only. The user-supplied private Hermes marketing source, footage and Google waitlist configuration have **not** been committed here.

## One decision loop

Start with the problem that needs attention, not an undifferentiated risk dashboard:

Public observation -> potential supplier exposure -> explicit private path ->
customer commitment -> missing evidence -> deterministic recovery choices ->
human approval -> versioned operational change -> replan and memory.

An open incident is not a confirmed factory shutdown. Connected company value is not a realized loss.

## New read-only Hermes API routes

All return real PostgreSQL/PostGIS data, no presentation fixtures.

1. `GET /app-data/map/facilities?west=-180&south=-85&east=180&north=85&limit=1000`
   - Query by geographic bounding box, with date-line crossing allowed.
   - Returns up to 2500 public site records with coordinates and identity provenance.
   - Distinguishes public identities from simulated-private operational links.
   - Counts only records in the bounding box; `truncated` warns the browser.
2. `GET /app-data/facilities/{network_facility_id}?max_products=25`
   - Shows public identity, matching operational-facility IDs, explicit assembly/upstream material links and a paged product shortlist.
   - Product counts and connected modeled revenues come from the database.
   - No geographical proximity may invent a SKU, closure or loss.
3. `GET /app-data/incidents?limit=50`
   - Prioritized open incidents with counts of unresolved evidence tasks, published event title and LIVE/REPLAY mode.
   - This is the app inbox; arbitrary source events without business paths do not become invented urgent incidents.
4. `GET /app-data/events/{event_id}`
   - Source event, geometry point, origin and mode, current incident ID, confirmed scenario if any, and exact missing evidence tasks.
   - The UI may separately ask `/events/{event_id}/impact` for calculated business exposure.
5. Existing `GET /products/{sku}/graph` supplies actual private BOM, sourcing, assembly and customer edges.
6. Existing `POST /investigations/tasks/{id}/prepare-outreach` produces a **review-only** draft, never dispatch.

All app data routes are read-only except the clearly separate review-draft endpoint.

## Private local frontend delivery

An owner-local ZIP contains the source-audited Hermes React+Vite marketing page **plus** a multipage `/app/` product experience. It preserves original brand/footage and does not replace the marketing site.

- Five views: Natural Disasters, Geopolitics & Trade, Logistics & Ports, Supplier Operations, Materials & Dependencies.
- Real geographic clusters and draggable/zoomable public map via MapLibre when CDN access works; safe local map fallback.
- Real dependency graph via Cytoscape and a draggable/zoomable fallback.
- Facility search and linked-sites filter, read-only source inspector, prioritized incident queue, product graph trace, review-only evidence tasks.
- `/app/` is implemented as a separate Vite multi-page entry; existing `/dashboard` remains an operator console.
- Vite proxies `/app-data`, `/events`, `/products`, `/investigations` and other existing FastAPI routes to 127.0.0.1:8000.
- **This is a local research/demo build**, not a public multi-user application. The current FastAPI loopback write exception means publishing this proxy or backend to the internet would be unsafe.

## Milestone acceptance

The backend CI checks:

- a global map query returns **770** public geocoded sites;
- an arbitrary public site can drill down to a linked generated-private SKU;
- event context retains public provenance and missing-fact separation;
- SQL-backed incident inbox and no invented loss.

The private site source has passed HTML ID/routing validation, JavaScript syntax and TypeScript syntax parsing. The npm registry was unreachable in this build environment; **full Vite compile and Windows browser-to-PostgreSQL testing are still required**. Do not claim a deployed app.

A proper three-click acceptance on the user's local database:

1. `/` -> `See how it works` -> `/app/` opens Hermes, not the previous control-tower page.
2. Select `GDACS-WF-1032942`. The inspector should show a potentially exposed product IU7704, 6000 units and EUR360000 *simulated-private connected revenue*, plus the verified public event and CONFIRM_FACILITY_STATUS task for ADI26-0239. Do not imply confirmed damage.
3. Select IU7704 -> Trace. Inspect the product's actual sources and commitments; pan/zoom/drag the graph. Draft evidence if needed, with no external dispatch.

Seeded Cianjur replay remains the flagship full recovery. No browser UI controls should hardcode its output; every change comes from SQL/Python recomputation.

## Build the next three pieces, in order

**P0. Make demo work locally, end to end.** Verify the new Vite multipage output and all real API responses on Windows; bundle MapLibre/Cytoscape and legal map assets so connectivity loss cannot spoil the demo. Add object-focused search and stateful deep links. Validate 770 sites and bounded graph performance.

**P0. Make recovery feasibility defensible.** Current portfolio jointly limits confirmed facility capacity but only audits shared upstream material contention. Build a true multi-material allocation optimizer across all competing SKUs and PO delivery windows. Plans with missing evidence remain provisional, and no LLM output can override feasibility.

**P0. Make human evidence-to-action real.** Drafts exist, but authenticated supplier delivery/replies, source expiry, role-specific approval and exact execution audit are incomplete. Close these gaps in one testable action path. Ensure users can clearly see what changed, not just an agent's explanation.

Then: verified official trade policy feeds, source freshness/noise suppression, managed Aiven streaming and secure public deployment. Do not add more risk categories without data sources and usable decisions.

## Source safety and ASD-STE100-style wording

- Avoid invented 0–100 Cyber/Finance/ESG scores. The five risk domains are navigational views, not claims that each has a trained probability model.
- Label `VERIFIED_PUBLIC`, `PUBLIC_DERIVED`, `INFERRED` and `SIMULATED_PRIVATE` visibly where they change interpretation.
- Use simple, direct instructions: `Select a site`, `Open linked products`, `Request evidence`, `Review a recovery plan`, `Approve an action`.
- Never call a nearby supplier damaged unless private confirmation exists.
- Never put the private Hermes website ZIP, waitlist form settings or secret assets in this public repo without user approval.
