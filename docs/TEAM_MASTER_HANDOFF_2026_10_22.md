# HERMES / DEPENDENCY — MASTER TEAM BRIEF
**22 October 2026 | Share with every teammate before coding**

**Public product:** HERMES. **Repository / Python package:** Dependency.
**Source of truth:** https://github.com/6aRy10/Disruptors- — branch `feat/db-foundation`.
**Verified starting point:** commit `87f13717c521c924f067d5152b74c3952b95603e` and passing GitHub workflow https://github.com/6aRy10/Disruptors-/actions/runs/39730743566.
**Frontend:** private HERMES landing page and app, with latest delivered v10 code overlay. NOT in the public GitHub backend repository. Teammates require a secure copy of the owner's current frontend project (not an obsolete v1/v2 ZIP).
**This document supersedes old setup advice** where a previous document tells people to run seed loaders or reset commands on the populated owner's PostgreSQL database. Read the latest `docs/SESSION_CONTINUITY.md` current checkpoint for changes since this brief.

---

## 1. The 30-second pitch — memorize this

**HERMES is an AI-assisted supply-chain investigation and recovery operating system.** It detects an external event, discovers which **explicitly connected** suppliers, materials, factories, products and customer commitments may be affected, asks for evidence that is missing, calculates feasible recovery choices under shared capacity and material constraints, and sends protected actions to authorized people. When reality changes, it versions the operational state, invalidates old plans, replans and records what happened.

**We are NOT building a map of disasters, a generic risk dashboard, an LLM chat demo, an ERP replacement, or a slide deck.** Maps, graphs and natural-language answers are the interface to a working operational decision system. The prize-winning moment is that a plausible backup plan turns out to share a hidden material source, or a supplier capacity confirmation invalidates a previously promising plan, and HERMES correctly reallocates scarce supply across competing customer commitments.

In one sentence for judges: **"HERMES turns external disruption signals into evidence-backed recovery decisions that protect customer commitments."**

### The customer and why they pay

Primary user: a supply-chain expeditor, procurement operations manager, recovery planner, or supply-chain control-tower analyst at a global manufacturer/brand. The buyer could be a VP of supply chain or operations. They currently switch between weather/port feeds, supplier spreadsheets, ERP orders, BOMs, email, messaging, planning files and people. They cannot quickly answer: *Which of our commitments depend on this one factory? Can the backup really make the same materials? If capacity falls, who gets the remaining units? Who can confirm the missing number?* Days of delay cost orders, margin, penalties and trust.

HERMES sits **across** an ERP/WMS/TMS and external signals. It does not replace those systems. In a real customer deployment, synthetic private-twin tables would be replaced with authorized company ERP, sourcing, inventory, order and supplier records. We need an honest path to a venture-scale business: start with disruption investigations and recovery for one brand, then expand to multi-customer agent-assisted procurement/expediting and proactive planning, with enterprise security and confirmed integrations.

### Quality bar

Functional end-to-end proof first; excellent, simple, consumer-grade interactions second, never as a substitute. Design references: object and action-centered workflows from Palantir-like tools; quiet typography, direct assistant input and specialist workflow surfaces inspired by FurtherAI. **Do not copy their code, branding, imagery or commercial claims.** Avoid generic AI slop, arbitrary colored risk cards, hardcoded outputs and broad unsupported promises. Use plain, precise technical English (~80% ASD-STE100).

---

## 2. What judges must see in the product

A complete investigation has this logical sequence:

1. **Observe:** a sourced public earthquake, flood, cyclone, wildfire, port anomaly or official policy change arrives with event ID, observed date, received date, geometry/source document and original payload.
2. **Match geography or policy:** PostGIS/SQL finds nearby public supplier identities, affected ports or relevant trade paths. Geographic proximity is a *lead*, not a verified loss.
3. **Trace explicit dependency:** move from public identity through an explicitly mapped private operational facility → **destination-specific material allocations** → approved assembly → SKU/BOM → customer commitment, preserving quantities, dates, approvals and provenance. Do not join by mere similar names, country, common material or parent company.
4. **Calculate potential exposure:** identify modeled order units, committed revenue/margin and deadline exposure. These are **connected simulated values, not confirmed loss**.
5. **Investigate missing facts:** create durable tasks (facility operating status, capacity, source material availability, inbound ETA, tariffs, shipment status, identity mapping) and select who/what can confirm them.
6. **Confirm operational reality:** accept separately authorized, source-cited evidence that changes facility capacity or state. A model-generated sentence or public disaster map cannot do this.
7. **Plan recovery:** generate alternatives, reject invalid backups/substitutes, apply cross-product shared capacity and BOM constraints, check dates, inventory, WIP, inbound material, lead times and safety stock; show protected units, late units, cost, revenue/margin and the assumptions.
8. **Approve and execute:** explicit human approval for protected changes; authorized execution must produce an audit record and state event. The agent may propose and explain; it may not secretly release safety stock or contact a supplier.
9. **Replan and learn:** new evidence increments operational state, invalidates previous plans and changes outcomes across affected products; save an evidence-backed incident history for later retrieval.

The major product value is steps **3 through 9**, not the size of the map.

### Product states and semantics

Conceptual states are: OBSERVED → POTENTIALLY_EXPOSED → PRIVATE_DEPENDENCY_LINKED → AWAITING_EVIDENCE → OPERATIONALLY_CONFIRMED → PLANNING → APPROVAL_REQUIRED → EXECUTED → REPLANNED / CLOSED. These are **product concepts**, not a claim that one complete enforced database state machine already exists.

Public facts `VERIFIED_PUBLIC`, derived geographic/policy matches `PUBLIC_DERIVED`, missing-fact hypotheses `INFERRED`, and private digital-twin data `SIMULATED_PRIVATE` must remain distinct. Show provenance in object detail and important numbers, not a giant internal disclaimer covering the product.

**Color contract:** orange = source-reported hazard coordinate/geometry at its actual observation time; green = site with an **explicit potentially exposed modeled private connection**; white ring = UI selection. Selection does not create danger. Do not invent storm tracks, severity probabilities or closed factories.

---

## 3. The two types of data — critical honesty

### Real public network and signals

- **770** geocoded public Adidas supplier/network facility identities in the owner's working PostgreSQL/PostGIS, based on public contributing source data.
- **836** listed relationships in the July 2026 official Adidas-list layers according to repository documentation, including 455 primary/subcontractor, 243 licensee and 138 wet-process rows. An official-list relationship is not a secret purchase order.
- Official USGS earthquake source; official GDACS reports for several hazard categories. Source IDs, times, geometry and URLs stored; map overview may apply USGS M4.5 display-noise threshold.
- Optional IMF PortWatch public port-call activity anomalies are **derived** compared with baseline; they do not prove closure or a shipment delay.
- Government trade/tariff rules are a *planned* versioned-source integration and scenario capability, not a verified, fully live trade feed.

### Private enterprise **simulation** (NOT Adidas ERP)

The owner's local twin contained at original generation:
- **2,500** generated private products/SKUs;
- **170,018** modeled material-allocation rows;
- **20,018** modeled customer commitments;
- **266,737** generated private-twin rows in total across related tables (not 266k verified real relationships);
- additional BOM materials, supplier capacities, factory assignments, inventory, production orders, POs, transport lanes, financial values and scenarios.

The current count of hazards/incidents/tasks changes as collectors run. The owner's screenshots show the incident queue grew from 3 to 7 cases and the overview reached approximately 129 source reports; treat these as **historical screen observations**, not perpetual counts. Use current `python -m scripts.team_status` and API responses for exact live counts.

**Do not rerun `scripts/load_seed_data.py`, `scripts.reset_demo`, `reset_demo_state()`, or `scripts.rehearse_control_loop` on the owner's populated DB.** Some old documents include those demo instructions. They are acceptable **only** on a separately configured, disposable test database. Do not share the owner's DB credentials.

### What data models

Public `network_facilities` and identity links; `external_events` and `event_outbox`; operational `facilities`, `products`, `materials`, `bom`, `material_allocations`, `product_facilities`, `fulfilment_commitments`, inventory, POs, supplier capacities, transport lanes, scenarios, incidents, evidence tasks, supplier requests/replies, approvals, executions, state-version events and operational memory. Check `sql/schema.sql` and migrations for the actual constraints/column names. Never infer a table's semantics from a user-facing label.

---

## 4. Three distinct demo scenarios (do not confuse them)

### Scenario A — flagship: Cianjur / Sukabumi earthquake, Indonesia, **21 November 2022**

**This is historical REPLAY, NOT a 2026 live earthquake.** Official USGS event is `us7000ir9t`. In the demo dataset the composite key used for the replay is `IDN-CIANJUR-2022-USGS-us7000ir9t`, with scenario `SCN-CIANJUR-REPLAY-01`. The current network is used as the **modeling backdrop**, not historical proof of 2022 real Adidas production.

Repo demo contracts report **4** public network sites within 50 km and **20** within 150 km. PostGIS location match is potential exposure only.

The private digital-twin graph connects to at least two relevant products:
- `JI2993`: Adizero SL2.
- `JQ6656`: Ultraboost 5.

Across the demo connected portfolio: **16,000** modeled commitment units; **€2,405,000** connected revenue; **€971,100** connected gross margin. Those are possible connected economic stakes, not actual disaster losses. Check current data when presenting.

**Critical hidden dependency — the "wow" discovery:** JI2993 nominal primary PGS and backup PGD share upstream source facilities for Coats Rejo thread (`ADI26-0751`), Dong Jin textile (`ADI26-0754`) and Paiho outsole (`ADI26-0758`). A backup that looks different at assembly level is not independent upstream. An option with correlated sources gets rejected or flagged depending on precise current planning policy. A substitute outsole is not approved / lacks engineering validation, so it is rejected by deterministic rules, never overruled by an LLM.

**Numerical recovery example for JI2993 (scenario-specific seeded values):**

| Stage | Calculation | Meaning |
| --- | --- | --- |
| Demand | 9,500 pairs | Modeled customer commitments |
| Ordinary inventory | 1,600 pairs | Excludes 500 protected safety-stock units |
| Initial independent backup usable capacity | 7,500 pairs | Provisional; its evidence is 72 hours old |
| Initial ordinary available | 1,600 + 7,500 = 9,100 | **400** units short without protected safety stock |
| Modeled supplier reply | "Capacity declines to 5,500 pairs/week until 2026-11-04" | A scenario/rehearsal reply, NOT a real 2022 supplier statement |
| After authorized confirmation | 5,500 gross - 2,000 prior commitments = 3,500 usable | Invalidates previous plan |
| Ordinary revised supply | 1,600 + 3,500 = 5,100 | **4,400** shortage |
| Emergency safety stock | +500 if explicitly approved and executed | 2,100 inventory + 3,500 backup = **5,600** |
| Final shortage | 9,500 - 5,600 = **3,900** | Still late; no miracle solution |

Priority-based modeled commitment allocation at 5,600 units:
- `ORD-JI-EU` → 4,000 protected, 0 late;
- `ORD-JI-NA` → 1,600 protected, 1,400 late;
- `ORD-JI-GC` → 0 protected, 2,500 late.
- Modeled protected revenue **€728,000**; protected gross margin **€300,000** before incremental recovery freight cost.

The real product must visibly show the initial plan, the external confirmation, state-version change (historically 1 → 2), invalidation, replan, approval and distinct execution (another version change). A fixed front-end table with these figures is **not** accepted. Recompute from scenario records after an authorized edit. Benchmarked numbers are demo fixtures; portfolio results may change as solver logic improves.

A full Cianjur rehearsal passes backend CI, but the owner's everyday Windows DB must not be reset to rerun it. Use CI disposable DB for destructive end-to-end replay tests. `scripts/plan_cianjur_recovery.py` and read-only API views can demonstrate current planning data without blindly altering state.

### Scenario B — real public signal, evidence-first: Indonesian GDACS wildfire, **15 October 2026**

Stored event: `GDACS-WF-1032942`. Last verified original local example:
- 3 public supplier sites within an investigation radius of 150 km;
- one explicit linked private facility `ADI26-0239`;
- connected SKU `IU7704`, 6,000 modeled commitment units;
- **€360,000** modeled connected revenue and **€144,500** gross margin;
- incident task `CONFIRM_FACILITY_STATUS` outstanding;
- **NO verified operating disruption and NO confirmed loss**.

Demo this live/public side to prove generalization: a real source report becomes a database event, enters the outbox, is triaged, produces a case and the correct targeted missing-evidence task. Do **not** show an automatic shutdown/recovery simply because a wildfire is near a site. The operational status requires separate credible private evidence and human confirmation.

### Scenario C — independent source, no-canned-output tests

Use an unfamiliar USGS earthquake, GDACS flood/cyclone, or optional IMF PortWatch anomaly. The exact live event **must not be hardcoded**: new event ID and coordinates should drive the query and result. If no explicit business connection exists, the correct result is **"public observation; no modeled private network exposure"**, not invented products.

- USGS / GDACS: genuine source observation, source coordinates/geometry, distance to public sites, explicit private linkage and evidence queue if applicable.
- PortWatch: recorded port-call anomalies. Only show a shipment impact if explicit transport-lane/commitment edges exist and shipment status is verified separately.
- Future trade policy: use versioned official text, country/HS-code applicability, effective dates/exemptions and item classification; do NOT invent live tariff events.
- Supplier operations: a documented capacity or ETA change should replan connected products, not only the SKU visible on screen.

**We need multiple source types for credibility, but only ONE deep flagship recovery.** Spend resources on an extraordinary Cianjur control loop, then prove a general live case and an unfamiliar negative case.

---

## 5. What is actually implemented as of this handoff

**Verified GitHub branch:** `feat/db-foundation`, last checked `87f13717` with passing CI. CI starts a separate seeded PostgreSQL/PostGIS fixture; CI green is not proof that every teammate's local frontend/DB works.

| Subsystem | Built and tested | What remains |
| --- | --- | --- |
| Storage | PostgreSQL, PostGIS, populated local twin, migrations, indexes, seeded CI fixture | Consistent shared team environment, secure managed deployment and backups |
| Sources | USGS/GDACS collectors; optional IMF PortWatch; first receipt ledger; poll-check status | Revision history of changing hazards, more verified sources, managed workers, retries/backoff |
| Event processing | Transactional outbox; idempotent local incident consumer; first-receipt vs source event dates; six-stage event journey | Kafka live proof, concurrent worker locking, versioned repeated-source updates |
| Exposure | PostGIS joins, 770 public sites, public→modeled private mappings and commercial totals | Real ERP/TMS data integration, authoritative identity resolution and richer permissions |
| Graph | SKU graph, source/material/destination route records, shared-source inspection, node/edge details | Correct time and quantity along full route, cross-SKU paged graph traversal and supplier-to-order allocation |
| Investigation | Incident inbox, inferred evidence tasks, task reconciliation, review-only outreach drafts | Authenticated supplier contact/reply, durable reply verification and secure approvals |
| Recovery | Cianjur deterministic candidates; rejected shared backups/substitutes; inventories, POs, lead-time; shared-factory solver and priority-based shared-material repair | Global multi-period solver with physically dated material receipts, alternative routing and non-partial orders |
| State/action | Confirmed operational state, state versions, plan invalidation, human approvals, idempotent execution and memory in demo backend | Production role permissions, trusted supplier identity, external write integrations |
| AI | Three tool-limited investigator/planner agents (opt-in), tool traces; Ask HERMES bounded read-only retrieval with optional paid model wording | Multi-step expeditor, evaluated question grounding, permissions and clear source-level answer citations |
| UI | Private HERMES v10 site/app; map with bundled offline geography; event feed and journey, graph, evidence, recovery, assistant composer | Real Windows end-to-end acceptance, route-aware exploration, reliable deployment, lower visual complexity |
| Aiven | Kafka adapters, one physical topic routing, preflight tests | Provisioned broker/topic/TLS connection, verified real Kafka messages; managed PostGIS data target |

### Actual data freshness and event feed

The backend watcher is a separate process: `python -m scripts.run_live_stack --watch`. Uvicorn on port 8000 does **not** start it. By default this polls USGS/GDACS and processes local outbox; PortWatch needs `--portwatch` and agents need deliberate `--agents`/model credentials. UI Event feed polls read-only activity approximately every 12 seconds while visible; that is **HTTP polling**, not proof of production push-streaming.

`external_events.ingested_at` can update on repeated polls. For new activity use the first `event_outbox.created_at` receipt per ID; show actual event occurrence time separately. The status `LIVE` may mean collected through live-source mode; it **does not prove the hazard is ongoing**.

Source checks are saved via additive migration `005_collector_checks.sql`; show RECENT_SUCCESS/ERROR/STALE/NOT_VERIFIED honestly. Local `event_consumptions.status=SUCCESS` and Kafka `event_outbox.published_at IS NOT NULL` are different outcomes. Do not say Aiven is working if only local consumption works.

### Graph correctness — important caveat

The overview node `material:M` may connect to several suppliers and factories for a SKU. That visual adjacency **must not imply** that every supplier can deliver to every factory, or that any supplier fulfilled a given customer order. The backend `GET /products/{sku}/graph` now returns **`allocation_routes`**, each with one modeled source facility, material, exact destination factory and allocation share. The expeditor labels orders as SKU-level potential commitments, NOT supplier-assigned orders.

Demand is connected to SKU via `fulfilment_commitments`; source→specific customer order fulfillment has **not** been independently assigned. Missing routes are missing; do not invent them through transitive layout edges.

### Material/capacity truth

Factory cap is **shared across SKUs**, not one fresh cap per product. Material capacity is shared across all products/routes using a source/material pair. For product units `x`, BOM requires `x × qty_per_unit`; source allocation share distributes that material demand. The current `material_allocation.py` is **priority-first deterministic repair after factory allocation**. It is not a globally optimal MILP and unknown/simulated capacities are not operationally verified. Previous `joint_optimization.py` factory-only result remains visible for comparison with `material_feasible_units` and `material_reduced_units`. Do not advertise this as optimal scheduling of arrivals.

### Agent truth and authorization

The default `POST /app-data/ask` mode is deterministic, read-only retrieval, not a general autonomous model. Model-assisted wording requires explicit `DEPENDENCY_EXPEDITOR_MODEL=1` plus API key and transmits selected modeled business context to the provider. Do not enable or send private/customer data without permission.

LLMs may choose tools, summarize source facts, propose hypotheses and draft supplier questions. **Only deterministic services decide:** distance, graph reachability, available units, BOM feasibility, due dates, optimization, capacity validity, authorized updates and approvals. No model may invent capacity, assert disaster damage, approve a substitution, send messages or release safety stock.

---

## 6. System architecture — know this before changing code

```text
USGS / GDACS / [opt-in IMF PortWatch] / future trade + ERP + supplier
               │ source IDs, timestamps, geometry, provenance
               ▼
        Python normalizers / collectors
               ▼
 PostgreSQL + PostGIS: external_events ── same-transaction event_outbox
               │                                    │
               │                               local worker
               │                           [optional Kafka transport]
               ▼                                    ▼
 Public facility & transport match ──── incident triage / dedup
               │                                    │
       Explicit modeled identities                  evidence tasks
               │                                    │
 Source + Material + Destination ────── confirmed private operational data
               │                                    │
       BOM / Factory / SKU / Orders ◄── state version / invalidation
               │
               ▼
      Deterministic feasibility + portfolio allocation
               │
               ▼
   Candidate plans → rejection reasons → human approval
               │                               │
               └──────────── authorized execution ───► outbox/memory/replan

     FastAPI read/write contracts ──► private HERMES website /app/
     bounded AI tools read same records and propose *review-only* work
```

Key modules (check current filenames before editing):
- `src/dependency/api/main.py` — FastAPI routing; `api/readiness.py` for read-only health.
- `src/dependency/db/connection.py` — explicit `local` vs `aiven` target.
- `src/dependency/ingest/` and `scripts/watch_usgs.py`, `watch_gdacs.py`, `watch_portwatch.py` — source adapters.
- `scripts/run_live_stack.py` and `src/dependency/automation/orchestrator.py` — watch/consume path.
- `src/dependency/graph/app_views.py`, `activity_stream.py`, `event_journey.py`, `dependency_view.py`, `event_impact.py` — UI and graph read models.
- `src/dependency/investigation/` — missing evidence and review-only outreach.
- `src/dependency/solver/` — candidates, feasibility, joint factory allocation, shared-material repair, portfolio.
- `src/dependency/assistant/expeditor.py` — bounded read-only question answering.
- `src/dependency/agents/` — opt-in multi-agent tools and runs.
- `src/dependency/services/` — capacity confirmation, operational updates, requests/replies, approvals, execution.
- `tests/` and `.github/workflows/test.yml` — disposable PostGIS and contract/negative-case gates.
- `web/` and backend `/dashboard` — **legacy console**, not the latest private HERMES frontend. Do not spend demo time polishing it unless explicitly required.

Useful API reads:
`GET /health`; `GET /app-data/readiness`; `GET /app-data/map/facilities?limit=2500`; `GET /app-data/map/hazards?days=90&limit=350`; `GET /app-data/activity?limit=80`; `GET /app-data/incidents`; `GET /app-data/events/{event_id}`; `GET /app-data/events/{event_id}/journey`; `GET /app-data/facilities/{network_facility_id}`; `GET /products/{sku}/graph`; `GET /events/{event_id}/portfolio/{scenario_id}`; `POST /app-data/ask` (read-only semantic action, though HTTP POST). Review exact current API signatures in FastAPI OpenAPI. Protected mutations require explicit authorization.

---

## 7. Aiven and why it matters

Hackathon challenge asks agents to depend on rich stored/streamed information and deliver value. Aiven's useful role is:
- managed Kafka for normalized external observations and internal operational events;
- PostgreSQL/PostGIS as persistent enterprise graph/state **only if** provisioned service supports needed extension/size;
- transactional outbox ensuring business-state changes and messages remain consistent;
- repeat delivery / idempotent consumers for incident tasks and replan signals;
- event history and memory supporting future proactive agents.

There are multiple logical event types (external event, incident detected, supplier updated, state changed, plan invalidated, approval/execution etc). Free-tier Kafka supports few physical topics, so the transport maps eleven logical topic types to **one physical topic `dependency.events`**, retaining logical topic/key/outbox ID in each message.

**Current truthful status:** adapters and read-only broker preflight exist, but real Aiven broker connectivity/topic consumption on the owner's environment has **not** been proved. Do not claim a connected managed pipeline until `python -m scripts.aiven_preflight --probe-kafka` returns `READY_TO_STREAM` and one broker message is visibly published and consumed. Do not turn on two competing consumers before concurrency safety is established.

If both `DATABASE_URL` and `AIVEN_DATABASE_URL` exist, the app **refuses to pick silently**. Set `DEPENDENCY_DATABASE_TARGET=local` for the existing populated local database. Aiven PostgreSQL free quotas may not fit the full PostGIS dataset. Never silently switch DBs to make a CI or dashboard check green.

Other hackathon resources are the organizer-provided AI model credits and services (Modal, Vercel AI Gateway, Supabase, n8n Cloud Pro, Stripe, ElevenLabs, Lovable, Miro and Lightdash). Only adopt a resource if it provides a measurable part of the workflow, not to collect sponsor logos. Aiven is the main required demonstration infrastructure if integration time permits.

---

## 8. UI/product contract — what "world class" actually means here

Landing page remains HERMES-branded with its private original media/assets and `See how it works` opening `/app/`. The current owner-held frontend (v10 overlay on existing project) is a private React/Vite application, generally at `http://127.0.0.1:5173/app/` in development. **GitHub backend clone alone does not provide it.** Arrange private repo/access or a source ZIP safely; never commit hero footage, fonts, waitlist identifiers or credentials to public repo.

Core operator screens are one object-centered workflow, not disconnected dashboards:
- **Ask HERMES:** natural-language questions in context, follow stored graph data and evidence, cite exact records; no invented supplier-to-order edge. Ctrl+K opens composer.
- **Map / network:** world geography with local offline fallback, 770 public nodes, true source event markers, clustering, search, source/time filters, zoom/pan, selection and specific incident focus. No coordinate grid pretending to be a map when CDN fails.
- **Dependency explorer:** directional supplier→material→destination-specific factory→SKU→commitments; node/edge inspection, search, zoom, drag layout, shared upstream suppliers and route qualifiers. Graph layout position is not geographic position. Preserve case/SKU selection between views.
- **Event feed:** sourced new first receipts, original event date, processing status, collector freshness and separate Kafka/local counts; background HTTP polling while app visible. Do not invent activity between polls.
- **Trace journey:** six database checkpoints for each event (source, first receipt, processing, investigation, evidence, decision) and the actual next valid action.
- **Evidence:** durable tasks, required fact, target supplier/plant, missing source, human review-only draft.
- **Recovery:** factory-only vs material-constrained units, affected commitments, rejected alternatives, connected economics, confirmed vs modeled assumptions, before/after state, approval and execution history.

Five **filters over one ontology**, not separate silos: Natural Disasters; Geopolitics & Trade; Logistics & Ports; Supplier Operations; Materials & Dependencies. Unimplemented categories must say "Not assessed", not display fake signals.

A great UI removes uncertainty: *what changed, what is verified, why this order matters, what would happen under each plan, and what the operator should do next*. Visual polish matters, but dense dashboards, generic language, bloated map area, permanent inspectors and unreachable controls are not acceptable. Every button must work with backend data.

---

## 9. Teammate responsibilities — parallel plan

We have three people: **Team lead/product/demo** (current owner), **Backend Engineer**, and **Full-Stack Engineer** (backend + frontend). Assign actual names in your team chat. These responsibilities apply immediately.

### A. Backend Engineer — **data truth and recovery intelligence**

Own the hard correctness layer. Work in small branches off `feat/db-foundation` (for example `feat/recovery-time-phased`) and open focused PRs. Prioritized backlog:

**P0-A1: Reproducible case/contract audit.** Run backend tests against your own disposable DB. Trace an unfamiliar real source record through receipt, consumption, incident, task and graph. Check that no private edge appears without an allocation/approved link. Produce one reproducible counterexample and fix it if found.

**P0-A2: Cross-product, route-qualified material feasibility.** Extend current `material_allocation.py` and joint portfolio so scarce `(material, source)` capacity is spent ONCE globally, each SKU requires all BOM materials, and each supply route respects the exact destination factory. Add capacity windows, existing commitments, arriving PO ETA and delivery deadlines. If time is too short for full optimization, implement an exact **small-instance** mixed-integer optimization with a deterministic benchmark and explain what is not covered, rather than presenting a greedy repair as global optimality.

**P0-A3: Recovery counterexamples.** Test two SKUs sharing one source, two factories sharing the same backup, incomplete BOM, unapproved substitution, expired evidence, insufficient 2026 inbound material, material arriving after customer deadline, order cannot be split, no route, negative/stale capacity and duplicate confirmations. Outputs must show infeasibility reasons and protected/late orders; no double count.

**P1-A4: Evidence and safe state transition.** Connect authenticated confirmation (or explicitly modeled operator proof for demo) to dated operational state, stale-plan invalidation, joint replan and audit. Check transaction/idempotency, not merely an API response. Never let a tool call send mail or authorize stock release by default.

**Deliverable / acceptance:** a specific new computed case where changing one source/factory fact changes ≥2 competing customer commitments; a test proves both resource accounting and rejection of an impossible alternative; the results are accessible via stable API fields. Document before/after state IDs and assumptions.

**Likely owned files:** `src/dependency/solver/*`, pertinent services, DB read models and backend tests. Coordinate before touching `api/main.py`, `graph/dependency_view.py` or shared schemas.

### B. Full-Stack Engineer — **investigation product and agent experience**

Own the user-visible end-to-end workflow and its integration boundary. Also contribute the backend read endpoints needed for that workflow. Separate branch such as `feat/expeditor-incident-workspace`.

**P0-B1: Obtain and version the private frontend safely.** Request current v10 project source from lead; install, run production build and UI tests. Create private shared repository or approved private subproject workflow, with clear configuration, lockfile, non-secret `.env.example` and CI. Public backend code and frontend must no longer drift via untracked ZIP overlays.

**P0-B2: Trace one case without a broken click.** From latest real GDACS/USGS event: open incident → see source geography → find exact linked supplier/material/factory/SKU → show exact next evidence task → inspect plans. Preserve event ID, scenario ID, SKU and selected object through navigation. Use full live FastAPI responses and automated browser acceptance, not a hardcoded fixture card.

**P0-B3: Make Ask HERMES genuinely useful.** Build a bounded, auditable expeditor that can answer: "Which customers have potential exposure from this supplier?", "Which backup routes share an upstream material?", "Which missing fact blocks recovery?", and "Why did a plan fail?" Use appropriate read-only tools, explicit route-qualified paths, provenance and numbers. First get deterministic retrieval RIGHT. Optional LLM summarization/tool selection may follow, with typed tool interfaces and recorded trace, never model-generated invented SQL or permissions. Make answer links jump to real selected objects. Test misleading cross-factory paths as negative cases.

**P0-B4: Event feed reliability.** Display receipt time vs occurred time, collector status, processing outcome, missing signal category and reason for no private exposure. Test when watcher is off, when a report updates, and when source service is unavailable. Show exact error and a useful remedy instead of a misleading empty state.

**P1-B5: Decision interaction:** operator compares recovery before/after evidence; sees shortage, priority, margin, rejected candidates, material cap and approvals, and can follow result IDs. Connect to backend engineer's new feasibility response; do not calculate business numbers in arbitrary frontend JavaScript.

**Deliverable / acceptance:** one browser-recorded walk-through using the same real selected event ID end to end, with working node clicks, a grounded question, a task and a changed plan. It must run against a seeded disposable PostGIS backend, not only mocked route responses.

**Likely owned files:** private `app/*`, frontend integration tests and narrow read-only API adapters. Do not edit the solver simultaneously with Backend Engineer.

### C. Team Lead — **integration, product truth, final demo and external dependencies**

- Keep the project goal and factual boundaries intact, own core scope and judge narrative.
- Arrange secure frontend project access and team-owned independent DB fixtures. Do not share a single mutable production local DB across teammates.
- Confirm API contracts, code ownership, integration windows, pull requests and CI. Merge from `feat/db-foundation` only when integration tests and a live walkthrough pass.
- Provide working scenarios and acceptance examples (Cianjur official event and modeled connected products, Indonesian wildfire task, one unfamiliar event).
- Set up Aiven console/broker if authorized, manage credentials outside GitHub, and verify real broker connectivity before using it in a live pitch. Model credit usage must be explicitly approved.
- Rehearse the judge-controlled 3-minute flow and a fallback with local PostGIS/outbox if an external source/Aiven fails.
- Reject false claims, fabricated data, missing provenance, hardcoded outcomes and changes that break the populated database.

### File/merge agreement

- **One PR = one verified capability.** Include behavior, files changed, tests, expected output and remaining limitations.
- Backend engineer owns recovery/optimization logic and related tests. Full-stack engineer owns UI/API consumer and expeditor read flow. Both coordinate on API schema in one written contract first.
- Don't have two people edit `src/dependency/api/main.py`, DB schema or the same frontend bundle at once.
- No force push to shared branch. Prefer short-lived feature branches + reviewed merge. Run CI before calling an item done.
- Report blockers with exact endpoint, input ID, expected vs actual output, failed test, logs without secrets and commit SHA.
- Do not create a second unrelated interface or rewrite the backend in another stack while the working graph and data exist.

---

## 10. Safe team setup (read carefully)

### Teammate: new clone, new disposable database

In PowerShell:
```powershell
git clone https://github.com/6aRy10/Disruptors-.git
cd Disruptors-
git switch feat/db-foundation
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip check
```

Set a PostgreSQL database with PostGIS that is **your own disposable test DB**, and set `DATABASE_URL` securely in your local environment. Use `.env.example` for keys, not real values. If both local and Aiven URLs are present, explicitly select the local target: `$env:DEPENDENCY_DATABASE_TARGET = "local"`.

**Only on a fresh, explicitly disposable DB:** validate the seed, load a test fixture and apply migrations according to repo scripts. This resets/creates DEMO state, not the owner's database:
```powershell
python scripts/validate_seed_data.py
python scripts/load_seed_data.py
python -m scripts.apply_migrations
python -m unittest discover -s tests -v
```
A full-scale generator may be resource-intensive; start from repository fixture/CI contract and expand in a separate disposable DB. Check the latest `docs/TEAM_START_HERE.md` for further setup context, but respect this safety rule.

**Never** point the seed loader at the team's main local `Disruptors` database, a shared server, or an Aiven customer-like environment.

### Existing owner's populated DB — no destructive commands

Read-only sanity (inside existing backend root and activated venv):
```powershell
python scripts/doctor.py
python -m scripts.team_status
powershell -ExecutionPolicy Bypass -File .\scripts\check_hermes_backend.ps1
```
Non-destructive migrations `python -m scripts.apply_migrations` only after reviewing what the branch adds and selecting the correct database. Do NOT run `load_seed_data`, `reset_demo`, `reset_demo_state`, or destructive rehearsal there.

### Local processes (three independent terminals)

1. API: `python -m uvicorn dependency.api.main:app --reload --host 127.0.0.1 --port 8000`
2. Sources/worker: `python -m scripts.run_live_stack --watch` (source polling + local worker; no LLM by default; PortWatch optional).
3. Private frontend: `npm ci` (in current private frontend root), `npm run build`, `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`; open `http://127.0.0.1:5173/app/`.

If APIs show HTTP 500, check `GET /app-data/readiness`, DB target, migration/schema and Uvicorn traceback before blaming the frontend. Some older docs imply setting Aiven URL causes an automatic switch; **current code refuses ambiguous targets**.

For live Kafka, run read-only `python -m scripts.aiven_preflight --probe-kafka` after safely provisioning credentials. No actual publishing or consumer cutover until team approves it.

---

## 11. Exact hard acceptance tests for the hackathon

Minimum gates, each with a repeatable test and an observable user result:

1. Real provider event ID and original event timestamp persist; a repeated poll does not create another "new event."
2. Source on map is tied to actual stored geometry; lack of map CDN still shows bundled geographic context. Source hazard is never colored by UI selection.
3. Unrelated/ocean event produces **no invented impacted order**. A public site with no private link does not gain an SKU.
4. A new arbitrary near-linked event creates one incident and the correct evidence task; duplicated worker messages create no extra tasks.
5. A supplier/material allocation only reaches its **approved destination factory**. Shared material overview must not imply a nonexistent route.
6. Ask HERMES can cite a SKU-level possible order, but cannot claim the named supplier actually fulfilled it without order-route assignment evidence.
7. Two SKUs competing for one backup facility respect a **single factory-wide cap**. Two SKUs consuming a shared material/source respect one material limit.
8. Unapproved substitute, expired evidence, absent ETA, incomplete BOM or late inbound material causes rejection/conditional result—not a green feasible badge.
9. Authorized capacity confirmation or relevant state edit changes state version and invalidates previous plans. Recalculated units/orders differ for a good reason.
10. Model text cannot change confirmed capacity, supplier identity, protected stock or approval state.
11. No supplier draft is dispatched by merely preparing it; execution and approval are separately audited and idempotent.
12. Source poll health, local consumption and Kafka publication show **three different** states; offline watcher is shown stale/not verified.
13. The private app uses current backend responses, not static Cianjur-specific cards. Selected event and SKU persist through Map → Graph → Evidence → Recovery → Ask.
14. The demo works from the selected tested branch after restart; teams can reproduce it on a second computer/CI fixture without touching the owner's live DB.
15. Underlying network, public source/provenance, inventory, purchase orders and competing commitments are drawn from Postgres; any missing fact displays **unknown / evidence required**, not invented data.

**If time is severely constrained:** pass gates 1, 3, 4, 5, 7, 9, 10, 13 and one complete scripted Cianjur control loop before adding more feeds or another redesign.

---

## 12. Next work sequence and shared milestones

### First alignment session
- Everyone reads this document, `docs/SESSION_CONTINUITY.md` current checkpoint, `docs/PRODUCT_CONTRACT_AND_BUILD_GATES.md` and the demo script.
- Team lead shows the current Windows v10 app and backend state with actual data. Show a failing part too.
- Each engineer checks out the exact branch, confirms a passing CI, and opens the required test suite without changing the owner's DB.
- Securely transfer the **latest private frontend project** to the full-stack engineer, not a stale screenshot or ZIP overlay alone.
- Agree on one API payload example for **qualified material allocation and post-evidence plan**.

### Milestone 1 — prove a complete current-data investigation
One real live/public source report enters the event feed, links to a facility, creates or correctly refuses an incident, shows evidence and one contextual expeditor answer. Add a browser/DB integration test with IDs, no hardcoded output.

### Milestone 2 — make recovery decision hard to fake
A controlled material or factory capacity change affects multiple competing SKUs. Show before/after quantities, rejected backup, one limiting material, explicit confirmed vs modeled capacity, and customer-order effects from deterministic computation.

### Milestone 3 — complete the human/evidence/action gate
A sourced operator confirmation resolves an evidence task, increments state version, triggers joint replan and (in a disposable demo) supports distinct approval and execution with durable audit/memory. Agent tool traces explain, but never fabricate, steps.

### Milestone 4 — deploy a reliable team demo
Shared backend API, private frontend build/CI, safe local database fixture, one validated watcher, optional verified Aiven Kafka topic/consumer, automated smoke checks, incident replay script and a 3-minute rehearsal. Prepare a fallback when external feeds are unavailable.

### Future company milestones (NOT 30-minute hackathon scope)
Real ERP/WMS/TMS connectors; supplier authentication and consent; versioned hazard footprint updates; multi-period global MILP with shipping lead times and non-partial orders; role/tenant controls; per-node evidence freshness; enterprise SLAs; operational evaluations and measured avoided-late commitments; production observability; longitudinal incident-learning experiments.

---

## 13. The 3-minute judge story (speak to this, not slides full of slogans)

**0:00–0:25:** "Here is our sourced public supplier network. Here is the historical Cianjur USGS earthquake; we are replaying it, not claiming it happened today. PostGIS identifies potentially exposed sites."

**0:25–0:55:** "Follow the explicit private digital-twin links into the materials, factories and customer commitments. The apparent backup is correlated through shared upstream sources; we reject it."

**0:55–1:25:** "Demand is 9,500; ordinary planned supply 9,100; there is a 400-unit shortage, with 72-hour-old backup capacity evidence. The correct next action is supplier confirmation, not an AI guess."

**1:25–1:55:** "A modeled supplier reply cuts gross capacity to 5,500 and 2,000 units are already committed. A human confirms this test evidence; usable capacity becomes 3,500, old plan invalidates."

**1:55–2:30:** "We test safety stock but it is protected. Only separate approval and execution release 500 emergency units. Revised feasible supply is 5,600 against 9,500 demand."

**2:30–3:00:** "The system allocates scarce supply by clear priorities, leaves 3,900 units late, shows €728K modeled revenue / €300K modeled margin protected, and records the plan/evidence/outcome. This is a decision system, not a disaster dashboard."

At judge discretion, show a genuinely arbitrary live wildfire entering the evidence queue, or allow one capacity edit to recalculate the plan. **Do not pretend a staged 2022 replay is live observation.**

---

## 14. What to say and never say

**Say:** "Official source report"; "public supplier identity"; "explicit modeled dependency"; "potentially exposed"; "private simulation"; "requires verification"; "deterministic feasibility"; "approval required"; "the worker processed locally"; "Kafka connection not yet verified."

**Never say:** "The factory is closed because it is within 150 km"; "Adidas is losing €2.4M"; "Our model knows the supplier capacity"; "This material path proves that supplier fulfills order X"; "The agent executed it"; "Aiven live streaming is deployed" unless each is independently established and can be shown.

The winning demonstration can be ambitious **and** scientifically honest. The proper story is a system that refuses to make an unsafe decision while still identifying the exact next useful step.

---

## 15. Reading order and exact references

1. **This document:** `docs/TEAM_MASTER_HANDOFF_2026_10_22.md` — product vision, scenarios, roles, acceptance.
2. `docs/SESSION_CONTINUITY.md` — newest checkpoint first; older sections are historical.
3. `docs/PRODUCT_CONTRACT_AND_BUILD_GATES.md` — non-negotiable event-to-action invariants.
4. `docs/demo_contract.md` and `docs/demo_script.md` — Cianjur numerical and judge flow. **Never use their destructive pre-demo setup on owner's populated database.**
5. `docs/HERMES_PIPELINE_AND_LOGIC_AUDIT.md` and `docs/HERMES_V9_EVENT_TO_ACTION.md` — feed, first receipt, worker, evidence lifecycle.
6. `docs/HERMES_V10_ROUTE_AND_OFFLINE_MAP.md` and `docs/HERMES_V5_RECOVERY_ENGINEERING.md` — route truth and solver limits.
7. `docs/agent_system.md` and `docs/HERMES_V6_EXPEDITOR_AND_GRAPH.md` — tools, agent restrictions, Ask HERMES.
8. `docs/AIVEN_FREE_TIER_DEPLOYMENT.md` — transport plan; ignore any old statement about silently switching DBs.
9. `docs/TEAM_ENGINEERING_HANDOFF.md`, `docs/LOCAL_DATABASE_AND_FEEDS.md`, `.github/workflows/test.yml`, `src/dependency/`, `tests/`.

**One recurring team question:** "What real database row or verified tool output proves the on-screen claim?" If nobody can answer, the claim is not ready for the demo.
