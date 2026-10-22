# HERMES — COMPETITIVE STRATEGY AND JUDGING PLAN
**Final product decision | 22 October 2026 | Founder / backend / full-stack**

Read **docs/TEAM_MASTER_HANDOFF_2026_10_22.md** first for all data, architecture, scenario values, files, user setup and safety rules. This file is the **winning strategy and execution decision**; it does not replace the master handoff.

## Decision: what are we shipping?

**HERMES is the Recovery Feasibility Commander.** It investigates real public signals, maps explicit modeled dependencies, challenges recovery alternatives, gathers missing operational evidence, and explains *which customer commitments are actually protectable under shared physical constraints*. The differentiating proof is its ability to catch the failure of an intuitive recovery alternative **before an expeditor promises the customer**, then recalculate when verified evidence changes.

Do not describe this as the world's first autonomous supply-chain agent. It is neither defensible nor required. Demonstrate one surprising, independently recomputed **contradiction → evidence → feasible reallocation** sequence better than other hackathon teams.

**Target user:** supply-chain expeditor/recovery planner for global footwear/consumer-goods brands. **Buyer:** head of supply-chain operations or procurement. **Adoption trigger:** one disruptive event forces many teams to reconcile external hazards, BOM, backup suppliers, inventory, factory capacity and customer orders. **Value proposition:** fewer manual investigation steps, faster evidence-backed plan, fewer impossible delivery promises, clearer priority/margin tradeoffs. We need actual timed measurements in our rehearsal rather than invented ROI numbers.

**One-sentence pitch:** "Other systems tell you that a disruption might hurt you. HERMES tests whether your escape plan is physically possible, identifies what must be verified, and reallocates scarce supply to protect customer promises."

### Competitive landscape — existing products already do much of the easy part
- **SAP Joule supply-chain assistants:** supply-chain exceptions, planning, logistics, manufacturing and supplier network workflows, including multi-agent coordination. https://news.sap.com/2026/10/joule-assistants-agents-advance-autonomous-scm/
- **project44:** AI agents for disruption management, carrier communications, shipment exceptions and resolution, built on shipment networks. https://www.project44.com/press-releases/project44-launches-ai-agent-portfolio-at-decision44-built-on-a-decade-of-context-skills-and-orchestration/
- **Altana:** AI-based multi-tier value-chain mapping, shared verified network and supplier collaboration, including sourcing risk. https://altana.ai/solutions/sourcing-and-procurement
- **Gartner agent-washing warning:** many "agentic" tools only improve querying or recommendations rather than the quality/feasibility of decisions. https://www.gartner.com/en/newsroom/press-releases/2026-05-20-gartner-warns-of-agent-washing-risks-in-supply-chain-planning-technology-market

**Our wedge is narrower:** *adversarial feasibility verification of an event-driven recovery decision*, with a tracked evidence loop and **cross-SKU** allocation. It is an attractive demo differentiator if the output is real and adversarial tests pass. It is not yet a proved market moat.

## Exact rubric from the organizer slide — five gates

| Criterion | What we MUST show, not merely say | Pass condition |
|---|---|---|
| 1. Customer problem and product value | Expeditor gets a real order-level decision during a disruption. Clearly identify buyer, job-to-be-done and first deployment wedge. | One selected event → at-risk orders → recommended next authorized action, without explanation from the founder. |
| 2. Agent capability | A tool-using expeditor makes **conditional** multi-step decisions: inspect event; traverse qualified graph; check backup dependence; ask for evidence; call solver; examine failed plan; revisit after new evidence. Stop when proof is missing. | Recorded tool trace with ≥3 relevant, varied tool calls; a branch changes when the case/answer changes; human approval remains separate. Do NOT fake a scripted tool chain as autonomous reasoning. |
| 3. Data at the core | USGS/GDACS official reports, 770 public sites, private simulated twin with 2,500 SKUs / 170,018 allocations / 20,018 commitments, PostGIS graph joins, event outbox, real timestamps, provenance, state memory, optional Kafka. | Judge changes event or cap: displayed paths, constraints, orders and economics recompute from PostgreSQL. Duplicates do not create new events. Aiven marked unverified unless an actual broker round-trip passes. |
| 4. Evidence it works | Measured correctness, response latency, token/API costs and automation outcomes; audit state versions and negative cases. | Baseline against same task without agent, timed trial, solver invariant tests, zero invented private links across negative cases, at least one capacity-perturbation test, no fake loss claims. Report actual metrics even when weak. |
| 5. Execution and pitch | Working product end-to-end in three minutes, memorable contradiction, polished inquiry/recovery screens, business wedge, expansion. | Can repeat without refreshing seeded state and without hand-waving. Video/fallback for CDN/source outage; stable version pinned and tested. |

### What the judge should *do*, not merely watch

Ask them to choose one of two changes:
1. Reduce usable backup factory capacity from modeled 7,500 to independently simulated 3,500 after confirmation; OR
2. Limit a shared upstream material source so two products cannot both receive their planned quantities.

Expected: old plan becomes invalid, exact constraints named, order allocation changes, shortage changes, alternatives are rejected for stored reasons, new result is traceable to input IDs. The solver, not a hand-coded UI, must cause the change. On the real populated owner DB do this only through an authorized **non-destructive sandbox/scenario edit**; NEVER reset the whole twin.

### Hero moment — precise script

1. Cianjur **2022 REPLAY** source → public supplier exposure, real historical date.
2. Click `JI2993`; recover dependencies and connect `JQ6656`. Show **the apparent backup isn't independent** because material sources overlap with the primary factory.
3. AI expeditor asks for proof and evaluates the proposed backup; deterministic rule returns a **specific failed resource/route** and why. Unapproved substitute fails too.
4. Independent backup is provisionally selected, but evidence is stale. Agent identifies exactly which capacity fact to confirm and prepares a review-only request.
5. A supplier/operator confirmation in the **modeled scenario** reduces backup availability. HERMES invalidates the old portfolio, jointly recalculates constrained material and factory units, and shows which customer promises remain protectable.
6. Human approves protected safety stock (distinct from execution); operational state changes; final units/late commitments/margin shown; past plan is visibly stale.
7. Ask HERMES: "Why did the original backup fail, what changed, and which order remains late?" The answer cites exact facility/material/order IDs and state version. AI cannot invent a missing shipment/order assignment.

**Expected existing demo fixture:** 9,500 JI2993 demand, ordinary inventory 1,600, nominal independent backup 7,500 → shortage 400; fresh modeled response 5,500 gross less 2,000 committed → 3,500 usable; approved 500 safety stock leads to 5,600 protected units, 3,900 late. Final modeled protection: €728k revenue, €300k gross margin before incremental freight. The broad Cianjur two-SKU connected portfolio has 16,000 modeled units and €2.405M potential connected revenue. **Never conflate these two figures or claim actual Adidas loss.** Results must be computed from backend scenario data, not hardcoded cards.

### Measurable evidence — instrument, don't invent

Capture at least:
- `ingest_to_case_seconds` (receipt to locally processed incident);
- `case_to_evidence_task_seconds`;
- `agent_elapsed_seconds`, `agent_tool_calls`, `agent_model_cost_usd` where available;
- `solver_elapsed_ms`, `planned_units_before`, `material_feasible_units`, `late_units_after`;
- `scenario_state_version`, `rejected_reason_codes`, `approved_action_count`;
- `false_business_link_count` over the negative test suite, target **zero**;
- `duplicate_source_receipts` over replay, target **zero**;
- time to answer the same Cianjur operator questions manually with source records and spreadsheets vs through HERMES, measured with same starting information.

**Do not publish invented percentages or extrapolate from one demo as field-proven ROI.** A clear measured 30–60 second proof with a trace beats unsupported "90% faster" marketing.

## Data access to every teammate — important

The public backend repo **does include normalized public-network CSVs** and generation code. The **266,737-row private enterprise twin is not included as a GitHub data dump**, and the owner's PostgreSQL currently has mutable investigation/approval records not appropriate to overwrite. Each engineer should:
- clone the repository and generate/load a **fresh disposable** private twin from the supplied scripts; OR
- obtain an **explicitly approved read-only CSV snapshot** of *only public + modeled private base tables* from the owner. Never circulate database passwords, private supplier contact information, source API tokens, waitlist settings or live execution records.
- use `scripts/export_team_model_snapshot.py` (added for this onboarding) from the owner's populated database, after reviewing the table allowlist, to build a data-only ZIP with a manifest and checksums. This is **data transfer**, not a database backup/restore.
- exchange the **private v10 frontend** securely; the public repo alone cannot reproduce the UI.
- use CI's disposable PostgreSQL fixture for destructive tests and full replay; do not run reset scripts on the populated owner database.

## Scope lock: what we will NOT build before judges

NO fourth dashboard overhaul. NO more random providers or hazard cards. NO blanket claim of "fully autonomous enterprise supply chains." NO production ERP, tariff or SLA integration unless already verified. NO spreading effort across ten scenarios. NO unsupervised supplier contact or irreversible action. NO rework of public 770-site data unless tests prove a fault. NO fake self-learning claims; persisted incident evidence is not trained learning.

The strongest product is **one complete deep loop**, backed by two independent event types and one negative case. Design should focus on the Ask → Evidence → Recovery workbench; the map and graph are drill-down tools rather than the product itself.

## Division of labor: avoid collisions

**Engineer A — BACKEND (priority critical path):**
1. Prepare deterministic fixture with primary/backup correlated material, independent backup, shared SKU source and dated cap.
2. Check and fix material route qualification, capacity units and multi-SKU competition; instrument solver + rejection explanations.
3. Guarantee scenario input edit and state invalidation, then stable API output for before/after plan; commit tests with 2 competing products and at least one impossible backup.
4. Do not spend time on frontend polish. Own `src/dependency/solver/*`, read-only data selectors + solver tests.

**Engineer B — FULL-STACK and AGENTS:**
1. Put current v10 private app in a shared PRIVATE version-controlled workspace. The active backend branch is public, and should stay separate.
2. Build exact Ask → evidence task → recovery trace against backend `/app-data/ask`, `/products/{sku}/graph`, `/app-data/events/{id}/journey`, `/events/{id}/portfolio/{scenario}`; record context IDs and keep UI state.
3. Expose actual agent tool trace and a conditional action loop. If model is unavailable, show deterministic evidence trace and label it honestly; no fake autonomy.
4. Integrate Engineer A's new plan constraints once contract is agreed; make judge-edit interaction show new solver output with no static numbers.
5. Verify with real disposal Postgres + Chromium browser, not only mocked JSON.

**Lead — PRODUCT, INFRA and PITCH:**
1. Own user/buyer story, Cianjur truth boundaries, judge controls, presentation, one controlled stopwatch run and a one-page KPI scorecard.
2. Set up Aiven privately; only call it streaming if actual preflight `READY_TO_STREAM` and event publish/consume verification pass.
3. Pin test SHA and confirm both engineers' commits merge cleanly, no secret/data leaks; approve final scenario and failover.
4. Organize one timed demo with someone who has not seen the product: they should complete the core flow without the lead explaining every click.

### Execution order — event day

The organizer's published Paris schedule lists Top-8 pitches at **16:00 on 22 October 2026**. Work backward from that check-in. Exact remaining time must be checked on location; never assume this planning document sets or changes organizer deadlines.

**Gate 1, immediately:** freeze thesis and share master handoff/current private frontend; assign branch ownership; verify all three terminals/backend health.
**Gate 2:** Engineer A builds/validates one adversarial source-cap conflict; Engineer B builds the linked expeditor question + evidence-to-plan trace; lead prepares metrics capture.
**Gate 3:** integrate both branches; run full CI and browser acceptance with real disposable DB; verify arbitrary event and no-network control.
**Gate 4:** run demo twice, record metrics and fallback; freeze deployment. Do not add new features after freeze except blockers.
**Pitch:** open with the apparently safe backup that fails due to shared upstream dependency; show two plans side-by-side, change one confirmed constraint, show protected orders and approval. Close with market wedge and roadmap.

## Company roadmap if we win

**Beachhead:** paid pilot for consumer brand / contract manufacturer expediting; connect exports from the existing ERP, sourcing system, BOM, orders, inventory and supplier status into the same typed data model. Measure analyst hours, decision latency, impossible recovery promises detected, on-time commitment protection (attributed cautiously) and approved actions.

**Expansion:** multi-site/material optimization with dated capacities, richer carrier and port connections, authenticated supplier response loops and versioned trade policy; provide private tenant permissions, field lineage, audit and policy controls. Accumulate opt-in enterprise-specific operational memory to improve evidence workflows (not assume public data equals private customer truth). Enterprise software pricing around supported sites/decision volume/workflow seats is a **hypothesis**, not validated willingness to pay.

**Defensibility:** not a foundation model wrapper; rather validated operational graph, source/event lineage, physical constraint correctness, evidence-to-action feedback, integration depth and case-specific memory. Moat is **hypothesis pending customer adoption**, not already earned.

## The team agreement

Every status update answers four questions:
1. What real fact/relationship/constraint now works?
2. Which automated test and actual operator click proves it?
3. What exactly remains mocked, provisional or unverified?
4. Which team member owns the next integration step?

**We win only if HERMES does something consequential, not merely because it looks like an AI startup.**
