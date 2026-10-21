# Agent system

## Why agents exist

Agents are not used for arithmetic.

They are used where the workflow is open-ended:

- decide which event needs investigation;
- decide which evidence is missing;
- decide which graph/tool to inspect next;
- generate recovery alternatives;
- decide when a supplier or planner must be contacted;
- explain why the current plan is no longer valid.

## Why deterministic code exists

The model must not decide:

- distance;
- graph reachability;
- BOM quantity;
- available inventory;
- supplier capacity;
- PO timing;
- substitution approval;
- protected units;
- revenue;
- margin;
- feasibility.

Those values come from SQL/PostGIS/Python.

## Signal Investigator

Allowed tools:

- get_event
- find_facilities_near_event

Stopping condition:

- network intersection is known;
- potential facilities are named;
- confirmed facts are separated from unknowns;
- missing operational evidence is listed.

Forbidden behavior:

- claim that a nearby factory is shut down;
- invent a SKU or commercial impact.

## Impact Investigator

Allowed tools:

- trace_downstream_impact
- get_customer_commitments
- check_backup_independence
- get_open_purchase_orders

Stopping condition:

- explicit dependency paths are known;
- affected products/commitments are known;
- hidden shared dependencies are checked when relevant;
- missing evidence is clear.

Forbidden behavior:

- create an edge because two facilities share a country or parent;
- count potential exposure as confirmed loss.

## Recovery Planner

Allowed tools:

- generate_recovery_candidates
- get_recovery_plan
- get_supplier_capacity
- get_product_risk
- check_backup_independence

Stopping condition:

- multiple candidate actions exist;
- deterministic pass/fail reasons are available;
- required confirmations/approvals are clear;
- shortage and protected value are known.

Forbidden behavior:

- override an unapproved substitute;
- treat stale capacity as confirmed;
- silently release safety stock;
- overrule the deterministic solver.

## Tool trace

Each model-selected tool call is recorded.

The trace contains:

- tool name;
- arguments;
- deterministic result.

When incident persistence is enabled, agent outputs and tool traces are saved to agent_runs.

This lets a judge inspect what the agent did instead of trusting a polished final paragraph.

## Runtime

The runtime uses the OpenAI Responses API with function tools.

Configuration:

- OPENAI_API_KEY
- OPENAI_MODEL

The default model is configurable. The deterministic backend continues to work if no model key is present.

Run:

    python scripts/run_incident_agents.py

The script runs the three agents in order and prints the model output plus the tool trace.
