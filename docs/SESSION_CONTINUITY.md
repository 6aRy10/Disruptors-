# HERMES / DEPENDENCY — CONTINUITY HANDOFF FOR A NEW CHAT AND TEAM
**Last reviewed:** 2026-10-21. **This is the starting point in a new conversation.**
**Source-of-truth repository:** https://github.com/6aRy10/Disruptors-
**Active working branch:** `feat/db-foundation`
**Verified engineering HEAD before this handoff commit:** `0ae44e5769f0ce9d200678348c1b79d5d4b336b1`
**Latest complete CI:** https://github.com/6aRy10/Disruptors-/actions/runs/39680634476 — successful.
**Important:** This document is a snapshot; always inspect the current branch HEAD, latest CI, and local output rather than assuming these IDs remain current.

## 1. Product goal, ambition and design principles

**Public name: HERMES.** Repo and Python packages use **Dependency**. Product is not a generic supply-chain risk dashboard. It is an **AI-assisted operational supply-chain recovery system**: receive trustworthy external reports, match explicitly modeled supplier network links, trace BOM -> materials -> factories -> finished product -> real/demo customer commitments, investigate unknowns, jointly evaluate recovery choices, reject impossible plans, request human approval, execute authorized actions, and retain incident memory.

Hackathon goal: a surprising, credible, working demo with the depth and polish to win a global Microsoft/Accel-class hackathon, and a believable expansion into a commercial product. The user wants a Palantir-level object model and powerful interactions, NOT a Palantir clone; unusually creative use of data; significant, auditable agent work; clear reason to use Aiven; serious economics, evidence and operational feasibility.

Think like an experienced product founder, architect, supply-chain planner and end user. Organize screens by **Discover -> Understand -> Decide -> Act and learn**, not by isolated backend features. Prioritize the actual user's path and decision over vanity KPI cards, generic buzzwords, slop labels, boxy three-column dashboards or decorative motion.

**Writing:** approximately 80% ASD-STE100 plain technical English: direct, logical, short labels, meaningful quantities, few slogans. User hates essays, jargon and unjustified certainty. Keep explanations concise and substantial.

**Five risk-domain views** (filters over the SAME graph; not independent data silos):
1. Natural Disasters (earthquake, wildfire, flood, cyclone, volcano).
2. Geopolitics & Trade (tariff/policy/sanction applicability).
3. Logistics & Ports (congestion, shipments, route disruption).
4. Supplier Operations (verified capacity, delay, site operating status).
5. Materials & Dependencies (BOM, shared sources, substitutability).
Do NOT copy Finance/Cyber/ESG headings or fabricate category scores to fill the layout.

One selected public event, facility, SKU, order, incident and recovery plan must have consistent IDs and state across all map/graph/inspector/workbench views. The graph should allow zoom, pan, drag-layout, edge details, expandable neighborhoods, object search and source/provenance inspection. Geo markers must not move when users rearrange GRAPH layout nodes. Show less at first; progressively reveal relations rather than dumping 170k edges.

**Crucial visual semantics**: orange = source-reported physical hazard at an actual observed coordinate/footprint and time, NOT 'selected'; white ring = currently selected object; green = public site that has an explicit modeled business dependency potentially exposed. Never invent an event radius or cyclone/storm path when source data only has a point. Historical event reports must not be treated as hazards that are currently ongoing. Source severity, proximity, inferred risk, confirmed operational harm and connected commercial value are different things.

**Provenance classes:** VERIFIED_PUBLIC, PUBLIC_DERIVED, INFERRED, SIMULATED_PRIVATE. Nearby Adidas supplier sites do not imply factory closure; connected revenue is **potential commercial exposure**, not confirmed loss. Agent suggestions do not establish operational facts. Private BOM/ERP/capacity/order economics and links are synthetic for the hackathon and must be clearly attributed where relevant, not repeatedly announced in full-screen 'DEMO TRUTH RULE' copy.

## 2. Verified data and real operational example

User's populated local PostgreSQL/PostGIS database is named `Disruptors`, on Windows localhost:5432. Do NOT reload seed data: this may reset the valuable current local operational state.

User locally loaded:
- **770** real/public Adidas supplier network facility identities.
- **2,500** modeled private products.
- **170,018** modeled material allocation rows.
- **20,018** modeled customer commitments.
- **266,737** total generated private-twin rows at original load (other BOM/order tables also exist).
Data is large enough for relational inference and stress tests; not proof that all factory relationships exist in the real world.

Last direct local `scripts.team_status` reported READY, **107 events**, **3 open incidents**, **3 open evidence tasks**, **106 locally processed outbox messages**, **1 pending local message**, **0 failed incident consumptions**, **107 unpublished Kafka messages**, operational state version **1**. These are LOCAL data from the user's screenshot; may have changed. 'Unpublished Kafka' is not the same thing as local processing failure. Aiven Kafka is not proven connected.

**Real historical/live example:** GDACS wildfire `GDACS-WF-1032942`, Indonesia; public source event recorded 2026-10-15. Three public network facilities within 150 km, **one** explicit private operational facility `ADI26-0239`, one connected SKU **IU7704**, **6,000** modeled commitment units, **EUR 360,000** modeled connected revenue and **EUR 144,500** modeled connected gross margin. Incident: `INC-b468b7ac-eb34-44d9-b960-7e9e6bdf81ea` (INVESTIGATING, no confirmed operational scenario). Reconciled legacy evidence task `INV-48efc9eb-a739-44a3-a6e5-8148e711f73b` calls for CONFIRM_FACILITY_STATUS; there is NO verified damage or lost revenue. The user has seen all this through real local PostgreSQL and an interactive Hermes v2 map.

**Flagship closed-loop demo:** historical USGS **Cianjur earthquake 2022**, ID `us7000ir9t`; explicit modeled private business graph, multi-SKU recovery, supplier evidence, rejection of infeasible options, state changes, human approval/execution, incident memory. The Cianjur rehearsal passes CI, but the arbitrary live incident usually correctly stops at evidence gathering until separate private confirmation is entered.

## 3. Backend and integration status

Repository: `https://github.com/6aRy10/Disruptors-`; active branch `feat/db-foundation`. Connected GitHub tools can READ, EDIT, COMMIT and verify CI in the same repo. User is a Windows/PowerShell novice; give exact copy/paste commands and do not repeatedly ask for details already known.

Backend: Python FastAPI, PostgreSQL/PostGIS, 770 public site + simulated private twin, USGS/GDACS live ingestion, opt-in IMF PortWatch, transactional outbox and incident consumer, dynamic graph, evidence tasks, facility-state confirmation, dated shared factory capacity, joint portfolio solver, shared-material contention AUDIT, agent tool runtime, supplier review-only draft, human approval/execution, incident memory. Some official-policy feeds, authenticated supplier contact/response, full shared-material optimizer and production security are unfinished. Outbox ingestion/agent mode can be run locally only; no managed always-on deployment yet.

Key HTTP routes:
- `/app-data/map/facilities?limit=2500` returns the seeded 770 geocoded public sites.
- `/app-data/map/hazards?days=90&limit=350` returns stored source event geometry/time; no fabricated buffers.
- `/app-data/incidents` prioritized open investigation inbox; linked evidence prioritized.
- `/app-data/events/{event_id}` selected event, coordinates, investigation tasks.
- `/app-data/facilities/{network_facility_id}` public identity and explicit simulated-private operational links/products.
- `/products/{sku}/graph` real private dependency graph data.
- `/investigations/tasks/{task_id}/prepare-outreach` creates an internal review-only draft. Does NOT send supplier email/Slack.
- `/investigations/tasks/{task_id}/confirm-facility` records operator-supplied private evidence into operational state; must not use public hazard proximity as proof.
- `/dashboard` is an older backend operator console, not final app UX.

**Aiven**: user confirmed always-free tier and a 30-day trial. Aiven Free Kafka has a five-topic quota, so Dependency packs eleven logical event types into one physical topic `dependency.events`; envelope retains event IDs and topic. A read-only broker preflight exists. Aiven PostgreSQL 1 GB free may not fit PostGIS + the large twin; keep user's working local DB unless a managed option is verified. Repo explicitly fails closed when both local and Aiven DB URLs exist without explicit `DEPENDENCY_DATABASE_TARGET`. No credential should be committed. Do not claim Aiven connected until actual service setup and network probe succeeds.

Previously tested backend CI runs ~95 steps, PostgreSQL/PostGIS + seeded graph + Cianjur full recovery. **Most recent backend HEAD before this handoff was `0ae44e5769f0ce9d200678348c1b79d5d4b336b1`, CI https://github.com/6aRy10/Disruptors-/actions/runs/39680634476 passed.** It added correct derived event provenance in outbox and suppresses low-magnitude USGS source reports below M4.5 on the hazard overview map. This is a display noise threshold, not a safety claim or change to the event archive.

## 4. Website/frontend state and visual problems

User SUPPLIED private Hermes React 18 + TypeScript + Vite source, landing page with brand/hero video/marketing content. Public website branding HERMES, ivory and teal accents on dark background. The original `See how it works` scrolled to text, but the local patched site routes to `/app/`. Frontend source/hero video/waitlist configuration have **NOT** been committed to the public GitHub backend repository for privacy/licensing reasons. A new chat will need the site ZIP reattached or the user-provided private repo URL; source is not guaranteed available from GitHub. Warn teammates that a backend clone does not recreate the website.

**Hermes Mission Control v1** was shipped as a private ZIP. User ran v1 and reported 0 public map sites and cramped static boxes.

**Hermes Mission Control v2** was shipped as a full private ZIP, local folder typically:
`$HOME\Downloads\hermes-mission-control-v2\hermes-product-v2`.
User ran it successfully:
- Screenshots show interactive clustered world map with **770** public sites, current wildfire, 1 linked SKU, simulated EUR360K potential revenue and 1 evidence task.
- Separate World map / Dependency graph / Evidence / Recovery tabs, focus workspace button.
- Still visually bad: fixed/boxed three-column layout, scrolling trapped by map, too little analysis space, generic internal disclaimer text.
- Most recent user critique: orange selected-event point is semantically wrong; it should reflect a reported hazard's presence/footprint, not which event user clicked. Stop generic dark box UI and internal-sounding "DEMO TRUTH RULE" copy. Consumer-centric, polished, responsive, map/graph exploration must feel natural.

**Hermes v3 overlay** was created within previous chat and is the NEXT frontend change; unlike v2, it is an OVERLAY patch for the existing v2 folder, not full replacement. It was saved in previous conversation as `hermes-v3-overlay.zip` with `README_FIRST.md`. The user has **not yet reported applying it** or supplied a v3 screenshot. The file may not transfer automatically to a new chat; re-upload if needed. The patch claims:
- new independent orange source hazard layer and time; selected object white outline, linked potential exposure green;
- page scroll restored and graph can use full workspace;
- zoom uses Ctrl+wheel so ordinary scrolling goes down the page;
- remove the intrusive "DEMO TRUTH RULE" banner, put important provenance next to the numbers;
- JS/source regression checks passed; Windows Vite build/browser verification of v3 NOT YET DONE.
Backend companion API `/app-data/map/hazards` was committed and passed CI.

**Local Windows pitfall:** another `C:\Users\AYUSH\postcss.config.js` installed globally requires Tailwind; Vite inherited it and failed with 'Cannot find module tailwindcss'. Creating a LOCAL `postcss.config.cjs` with `module.exports = { plugins: {} };` fixed this. Another issue: Vite package dependencies are per-folder (`npm ci` in new v2 folder). Old v1 Vite server on port 5173 caused confusion; use `--strictPort`, stop old server. Do not blindly tell user to regenerate data or use old frontend.

## 5. User's actual local startup (2 PowerShell windows)

**Backend window**, existing Python virtual environment:
```powershell
cd "$HOME\Downloads\disruptors\Disruptors-"
.\.venv\Scripts\Activate.ps1
git switch feat/db-foundation
git pull --ff-only origin feat/db-foundation
python -m uvicorn dependency.api.main:app --reload --host 127.0.0.1 --port 8000
```
Keep running. Database should stay untouched.

**Frontend window**, from v2 folder or v3 patched v2 folder:
```powershell
cd "$HOME\Downloads\hermes-mission-control-v2\hermes-product-v2"
npm ci
npm run test:ui
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```
Frontend: http://127.0.0.1:5173/app/
Local PostCSS workaround:
```powershell
Set-Content -Path .\postcss.config.cjs -Value 'module.exports = { plugins: {} };'
```
Data endpoint sanity: `(Invoke-RestMethod "http://127.0.0.1:8000/app-data/map/facilities?limit=2500").total_in_view` should return 770.
`python -m scripts.team_status` verifies data. Do NOT rerun `scripts/load_seed_data.py`.

## 6. Next engineering priorities (not mere UI polish)

**Immediately:**
- Verify v3 overlay is present, applied to the user's ACTUAL v2 frontend, and works in Windows with both local services. Test page scroll and map selection, source-hazard geometry, sidebar and graph. Don't claim v3 done in the user's browser before seeing evidence. If overlay cannot be located in new chat, ask for that one artifact or recreate the patch from user-supplied v2 source.
- Keep backend and frontend versioned together: the user needs a cloneable **single reproducible project**. Plan private frontend repository or an explicitly authorized mono-repo. Include scripts for dependency install, DB schema/migrations, idempotent data fixture generation, dev startup, and tests. A full backend clone DOES NOT include the local seeded DB or private website source.
- Audit each user action and real data need, design a full-screen flexible map and interactive graph with contextual inspector rather than permanent hardcoded columns.
- Improve geographic hazard semantics: source geometry, time, forecast vs observed, different event types, proximity exposure classification and event-specific timeline. No fake orange points or proof-of-damage claims.
- Improve real demand and discovery flow: incident priority, discover relevant cases, persistent object context, deep links, map to graph to recovery workbench, inspect product/bom/commitment.
- Protect usability: page scrolling works normally, map gestures don't trap the user, map and graph can expand, keyboard/mobile viewport, explicit loading/error states.

**Next core product engineering:**
- Genuine global **joint material allocation**, not only an audit for upstream contention; include BOM, shared capacity, dated inbound material and ETA, customer commitments, constraints, alternatives and explanation.
- Integrate contact-linked evidence tasks with **actual authenticated/simulated controlled** supplier responses and protected human review; no uncontrolled external outreach. AI agents should use documented tools and leave audit traces; opt-in paid credits.
- Build trustworthy official tariff/trade-policy applicability by date and SKU/route; expand other reliable feeds when they lead to concrete changes, not just alerts.
- Security/auth, always-on collectors, Aiven streaming and staged production deployment, event reliability, provenance/freshness and observability.
- Product polish only after real interactions and recovery decision make sense.

## 7. Operating rules for the assistant in the new chat

- The user explicitly wants **rapid substantial engineering** (an ambitious product with commercial potential), not endless planning or superficial cards.
- **Read this file plus** `docs/PRODUCT_ONTOLOGY_UX_BLUEPRINT.md`, `docs/HERMES_WEBSITE_AND_USER_JOURNEY.md`, `docs/HERMES_MISSION_CONTROL_MILESTONE.md`, `docs/HERMES_V2_PRODUCT_MAP_AND_GRAPH.md`, `docs/TEAM_ENGINEERING_HANDOFF.md` and latest GitHub commit/CI BEFORE suggesting a new interface direction.
- Actually implement, commit and test meaningful changes when requested. State what is proven by PostgreSQL/CI vs local browser vs unverified.
- **Keep user informed** before deep build work and at regular checkpoints; do not disappear for minutes. Say when starting a substantial task and give specific progress. Never promise background work if the task is not scheduled.
- User is a PowerShell novice: one complete sequence of copy/paste commands and the exact folder; warn which terminal to keep open. Never tell them to reinstall everything or reset the seeded DB without necessity.
- When user asks about planning, design, or status, answer directly instead of automatically asking for more screenshots.
- Follow ~80% ASD-STE100 plain writing; avoid patronizing reassurances, endless paragraphs, filler, hardcoded fake metrics, caps-heavy provenance banners.
- Do not conflate HERMES website with the Python backend name Dependency.
- User's current priority: stop hardcoded boxed dashboard; fix hazard display semantics, scrolling, interactive spacious graph and comprehensive teammate handoff. v3 backend CI passed, frontend overlay not yet browser-verified.

## 8. Recovering context in a future chat

Suggested instruction to paste:

> Continue my HERMES / Dependency hackathon product exactly where the previous long conversation stopped. The complete handoff is in `6aRy10/Disruptors-`, branch `feat/db-foundation`, file `docs/SESSION_CONTINUITY.md`. Read it and its linked UX/engineering documents, inspect the latest CI and code, then continue real engineering. Public brand is HERMES; Python backend is Dependency. Keep our 770 Adidas facilities and 266,737-row simulated-private twin, do not reset PostgreSQL. The last work was a v3 private frontend overlay to fix orange hazard semantics, page scroll and boxed graph. The new frontend is NOT in the public repo; ask only if the actual ZIP is needed. Be ambitious and user-centric, follow 80% ASD-STE100, verify all changes, and send progress checkpoints. Do NOT restart project discovery or claim unfinished integrations are complete.

End of handoff.
