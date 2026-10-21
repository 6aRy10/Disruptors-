# Deterministic engine

The deterministic engine decides what the model must not guess.

## Scope

Python, SQL, and PostGIS own:

- event-to-facility distance;
- explicit graph reachability;
- BOM explosion;
- inventory and safety stock;
- purchase-order arrival timing;
- supplier capacity;
- setup lead time;
- material-source timing;
- transport timing and cost;
- substitution approval;
- shared-source dependency rejection;
- customer priority;
- due dates;
- revenue and gross margin;
- scarce-supply allocation;
- state versioning and plan invalidation.

The LLM can select tools and propose actions. It cannot override these checks.

## Core feasibility rules

### Finished inventory

Usable finished inventory without policy override:

```text
usable = max(0, on_hand - reserved - safety_stock)
```

If safety stock is released:

```text
usable = max(0, on_hand - reserved)
```

Safety-stock release requires human approval.

### Supplier capacity

```text
available_capacity =
    max(0, gross_capacity - committed_capacity)
    * scenario_capacity_multiplier
```

Stale capacity evidence makes a plan provisional.

A supplier reply is parsed first. It changes state only after explicit confirmation.

### BOM requirements

For SKU quantity `q`:

```text
material_required[m] = BOM_qty_per_unit[m] * q
```

A purchase order counts as confirmed component supply only when:

- its source is an explicit approved allocation for that SKU/facility;
- its status is active;
- ETA is on or before the need-by date.

Missing private source paths remain `INSUFFICIENT_DATA`. They are not converted into fake zero supply.

### Material-source timing

A modeled source contributes provisional capacity only after its lead time.

The engine keeps confirmed inbound supply separate from modeled supplier capacity.

### Hidden dependency rejection

A nominal backup is rejected when the primary and backup share an explicit upstream source for the same SKU.

Common country or common parent organization alone is not enough to create a hidden dependency.

### Transport feasibility

For a proposed recovery facility and a customer commitment:

```text
arrival_date =
    scenario_as_of
    + setup_lead_days
    + lane_transit_days
```

The lane is on time only when:

```text
arrival_date <= customer_due_date
```

Missing transport lanes remain unknown.

Backup capacity is capped by demand that can be reached on time.

## Scarce-supply optimizer

`optimize_recovery_allocation()` uses deterministic min-cost flow.

Resources can include:

- usable finished inventory;
- safety stock when explicitly enabled;
- available current production;
- non-rejected approved backup assembly capacity.

A backup resource is connected to a customer order only when the deterministic transport engine finds an explicit on-time lane.

Conditional backup resources can be excluded by setting:

```text
include_provisional = false
```

### Objective

Business priority is lexicographic.

First:

```text
protect priority 1 before priority 2
protect priority 2 before priority 3
...
```

Within the same priority level, maximize:

```text
protected gross margin
- incremental recovery transport cost
```

This is encoded with a priority reward that is larger than the maximum possible total financial improvement from all lower-priority demand.

The optimizer reports:

- protected units;
- late units;
- protected revenue;
- protected gross margin;
- incremental recovery transport cost;
- net protected margin after recovery transport;
- resource usage;
- order allocation;
- provisional resources used;
- approval-dependent resources used.

## State invalidation

Every confirmed mutable operational update increments:

```text
operational_state_version
```

The same transaction emits business-state and/or `plan.invalidated` events.

The local orchestrator, and later the Aiven Kafka consumer, can recompute open incidents from the new state.

## Current deliberate limitations

The optimizer currently assumes all included customer commitments permit partial allocation.

If a commitment has `partial_allowed = false`, the optimizer stops instead of silently dividing it.

A future mixed-integer layer can add:

- all-or-nothing commitments;
- fixed expedite costs;
- minimum order quantities;
- changeover binaries;
- multi-week capacity;
- shared capacity across several SKUs;
- transfer quantities between warehouses.

Until those constraints exist in data, the engine does not invent them.
