# Hermes website + Dependency — user journey and integration contract

**Status:** Source-audited design and local-only handoff prototype. The new product interior has NOT been built. The uploaded private Hermes website source is NOT copied to this public repository.

## Verified website implementation
- Private uploaded source is a React 18 + TypeScript + Vite site, single `src/App.tsx`, single CSS file, hero MP4/poster, brand H route-mark, dark/ivory/teal design.
- Public-facing name: **Hermes**. Internal backend/repo still uses **Dependency**. Do not mix labels in the visible product.
- "See how it works" previously linked to `#how`, which only scrolls to a static description. There was no `/app` product entry.
- Waitlist uses a Google Forms `no-cors` POST. A resolved request does not prove the form accepted a submission. Do not claim confirmed signup success until there is an acknowledged backend.
- Claims about 2% monitored, 98% invisible, $2.5 trillion, and weeks to hours are unverified in the website README. Cite strong sources or remove.
- The current footage attribution/credits should be reconciled with the README and asset licenses. Modal needs focus management, reduced motion, and a real submission outcome. Keep the original owner's private form IDs out of this repository.

## The operator's full path

0. **Discover:** Landing page explains who Hermes is for: planners who must protect customer promises when suppliers or routes change.
1. **Try before registering:** Hero "See how it works" opens `/app`, with a clearly labeled guided replay. Early access remains secondary; do not force signup before value.
2. **Choose a path:** A first-time user can explore the Cianjur replay or examine live public alerts. An enterprise user can later connect company data; don't fake a live ERP connection.
3. **See what needs action:** Start with sorted incidents/evidence tasks, their time-to-impact and linked customer commitments. A global map remains the interactive canvas; it must not replace the priority queue.
4. **Filter domains:** Natural Disasters; Geopolitics & Trade; Logistics & Ports; Supplier Operations; Materials & Dependencies. These are views over ONE shared operational graph.
5. **Explore the world:** Map pan, pinch/wheel zoom, cluster 770 real public network facilities, filter by real provenance and current observation. Never invent large network counts.
6. **Inspect event:** Show what happened, at what time, reported by whom, nearby facilities, whether the company has explicit graph paths, what remains unknown. Distinguish live, historical replay and simulated private facts.
7. **Expand dependencies:** Facility -> actual upstream material sources -> assigned SKU -> customer commitment. Pan/zoom and drag diagram *layout* nodes only, inspect link provenance; do not alter real geography.
8. **Review economic exposure:** Connected revenue/margin is POTENTIAL exposure. Separate confirmed shortage, simulation results and unverified damage.
9. **Resolve missing facts:** An explicit task requests factory capacity, material quantity or shipment ETA. Permit review-only request drafts. No automatic supplier message without an approved channel.
10. **Simulate:** Show at least three alternatives and clear rejected options. Recompute from BOM, orders, material source and shared capacities; never let AI fabricate a feasible outcome.
11. **Approve and act:** Show before/after, model/solver evidence, human authorization and versioned state change. Execution cannot rely on a model sentence.
12. **Return:** Keep the incident timeline, saved context, confirmed facts, source freshness and result visible. Provide understandable errors, incomplete data states and recovery from failed actions.

## Minimum app architecture

- `/` = existing Hermes marketing site and waitlist.
- `/app` = protected interactive app, using same Hermes brand.
- `/api` = real FastAPI/PostgreSQL engine behind a server-side gateway.
- In a LOCAL-ONLY prototype, Vite `/app` can proxy to current `/dashboard`, and API/asset paths proxy to FastAPI on 127.0.0.1:8000. This is route handoff, NOT the final UX.
- Current backend allows loopback writes for local demos. **Never expose a Vite proxy or backend via a public reverse proxy without real authentication, role checks, anti-CSRF measures and a disabled public reset.** Otherwise its loopback allowance is unsafe.
- Production app should use same-origin authorized API calls and a deliberate demo/read-only mode, not a browser direct call to localhost.
- Map: evaluate MapLibre GL JS and server-side PostGIS viewport queries.
- Graph: evaluate Cytoscape.js for scoped dependency exploration and drag-to-arrange. All 170k material edges belong in PostgreSQL, not one giant DOM/SVG.
- One selected event/factory/SKU context persists across domain filters, map, graph and recovery.

## Screens before colors

1. **Mission Control:** priority queue + global map; last refreshed, live/replay.
2. **Risk Domain:** filtered actual hazards/policy/logistics/operations/materials with explained status. For unmeasured domains show "Not assessed," not invented scores.
3. **Object Inspector:** selected event/facility/product with provenance, freshness, graph links and connected orders.
4. **Dependency Explorer:** expand/collapse, path comparison, shared source detection, edge evidence.
5. **Recovery Workbench:** action candidates, hard constraints, what-if edits, cost/shortage impact, human approval.
6. **Investigation Inbox:** evidence tasks, contact status, review-only drafts and confirmed response records.
7. **History:** timeline, source snapshots, decision audit, outcome.

## Data work before visual claims

- Public facility identities and source facts are real where verified; private ERP/BOM/order/capacity and economics are generated, explicitly `SIMULATED_PRIVATE`.
- The generic live GDACS wildfire `GDACS-WF-1032942` reached one linked private facility (`ADI26-0239`), product IU7704, 6k committed units and EUR360k connected simulated-private revenue; an evidence task now exists. No confirmed factory damage or EUR360k actual loss.
- The Cianjur 2022 event remains the only full replay/demo recovery.
- Remaining gaps: joint multi-material optimization (current contention component is an AUDIT), supplier evidence authentication, official trade-policy ingestion and temporal validity, realistic source freshness and noisy event filtering, live worker deployment, data completeness checks and secure write roles.
- Risk labels must distinguish source severity, potential exposure, urgency, confirmed operational impact, recovery confidence, and simulated business economics. Avoid an unexplained 0–100 score.

## Experience rules for a modern enterprise product

- First session must demonstrate value within three clicks without account creation.
- Every risk card should offer one clear next action, not five ambiguous buttons.
- Search across facilities/SKUs/incidents; deep-link to a selected object; preserve context when changing view.
- Use rich interactivity for discovery, not decorations. Motion must respect reduced-motion preference.
- Make uncertainties visible, show freshness, errors and partial data without hiding the rest of the workflow.
- Support keyboard navigation and accessible tooltips, high-density desktop design and responsive read-only mobile triage.
- Existing Hermes visual language is retained; choose exact app colors/typography after a clickable content-first prototype is reviewed.
- Brand promise must be defensible: "Know what is exposed. Decide what to do next." is safer than claiming to eliminate all risk.

## Team handoff

The owner's private ZIP can be patched locally (without committing its assets or waitlist identifiers publicly). Two localhost processes are needed:
- FastAPI on 127.0.0.1:8000 with existing loaded PostgreSQL (do NOT run seed loader).
- Vite on 127.0.0.1:5173 with the website source and local proxy.
- Clicking hero CTA `See how it works` opens `/app` (current legacy dashboard), until the new interactive frontend is built.

The private website ZIP and local-only prototype are held by the owner, not deployed and not copied into this public code repository.

References: Palantir ontology-aware object explorer and actions, MapLibre GL JS, Cytoscape.js official documentation.
