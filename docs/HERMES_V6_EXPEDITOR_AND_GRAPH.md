# HERMES v6 — expeditor-first interface and graph selection

Date: 2026-10-22. Working branch: `feat/db-foundation`.

The frontend remains PRIVATE. The user-owned `hermes-v6-expeditor-overlay.zip` must be applied to the existing `hermes-product-v3` project after V5. The public backend clone does not include the private Hermes website or local database.

## Confirmed frontend issue and fix
The previous code registered the `data-workspace` click listener on **every** matching element, including `.application[data-workspace]`. Every inner click bubbled to the root, re-rendering the current workspace and losing graph selection. The fix registers workspace listeners only on `.workspace-tab[data-workspace]` and closes the blocking inspector when tracing an SKU. Fallback SVG uses pointer-down/release selection to survive pointer capture, with keyboard Enter/Space support.

Browser validation against mocked read-only responses passed for: opening a selected graph node, inspecting stored edges, asking a question carrying event/SKU/node identity, moving between inspector and workspaces, Cianjur portfolio view, map scrolling, and evidence queue. The populated Windows database and user browser have NOT been tested in this environment. Vite production build remains unverified here because the sandbox's local npm install is incomplete.

## Expeditor API
`POST /app-data/ask` accepts:
```json
{"question":"Which orders depend on this supplier?","event_id":"...","sku":"...","facility_id":null,"object_id":"facility:..."}
```

The endpoint uses existing read-only event, exposure, facility, graph and scenario portfolio functions. Exact object selection uses stored directed dependency edges to reach downstream customer commitments. Deterministic answers contain source links, modeled order IDs, material names and evidence gaps when present. No arbitrary SQL is generated or executed. No supplier messages, capacity edits, approvals or recovery execution are permitted.

The default does not require an LLM or API credits. Paid model-assisted wording is **off by default**. Explicit server-side opt-in requires `DEPENDENCY_EXPEDITOR_MODEL=1` and `OPENAI_API_KEY`, and transmits the selected case summary to the configured model provider. Never enable without authorization to transmit the simulated private data. Model-generated wording must never be treated as independently verified operational evidence.

The repository also contains `tests/test_expeditor.py` with no-DB grounding and safety cases; confirm these are executed in CI before relying on them as a full integration gate.

## FurtherAI-inspired design scope
Use the visual principles of a clean, question-first workspace: restrained contrast, open space, assistant composer, precise evidence links, simple workflows. Keep original HERMES brand, product semantics and data; do NOT copy FurtherAI imagery, code, branding, endorsements or insurance claims.

## Next high-priority backend milestones
- Strictly bounded safe read-only question tools with field-level access and user permissions; multi-turn context, retrieval ranking, latency benchmarks, and grounded-answer evaluation on a realistic data sample.
- True global multi-period joint material/factory optimization, supplier quantity/date confirmation, and non-partial customer-order handling.
- Authenticated supplier replies, durable action approvals, production-ready roles, deployable collectors and verified Aiven stream connectivity.
- Server-paged graph neighborhoods and product-grade selection persistence in the real Windows environment.

**No database migrations, seed loaders, outbox processing or state reset were run for v6.**
