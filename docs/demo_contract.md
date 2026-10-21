# Judge demo contract

## The 3-minute story

### 0:00 - Real network

Show the current Adidas public network.

State clearly:

- 770 geocoded public network facilities are loaded;
- 836 official July 2026 Adidas list relationships are retained;
- public facts and private demo data are visibly labeled.

### 0:20 - Real event

Replay USGS event us7000ir9t.

Keep the original 2022 date.

PostGIS finds:

- 4 public network facilities within 50 km;
- 20 within 150 km.

Say "potentially exposed", not "damaged".

### 0:40 - Hidden dependency

Open JI2993.

The nominal PGD backup looks like another assembly site.

The graph reveals that primary PGS and nominal backup PGD both use the same three private digital-twin upstream material sources:

- Coats Rejo thread;
- Dong Jin textile;
- Paiho outsole.

Plan A is rejected as a correlated backup.

### 1:05 - Bad substitute

Plan B proposes alternate outsole material.

The substitution table says:

- approved = false;
- engineering validation = incomplete.

The deterministic engine rejects Plan B.

The LLM cannot override it.

### 1:25 - Conditional recovery

Plan C uses independent Hwa Seung backup plus finished inventory.

Before fresh supplier evidence:

- demand = 9,500;
- finished inventory usable without safety stock = 1,600;
- backup usable capacity = 7,500;
- supply = 9,100;
- shortage = 400.

Releasing 400 safety-stock units can cover demand, but that requires planner approval.

Backup capacity evidence is 72 hours old, so supplier confirmation is also required.

### 1:50 - Reality changes

Supplier replies:

"Capacity has declined to 5,500 pairs per week until 2026-11-04."

The parser extracts the value but does not change state until confirmation.

After confirmation:

- gross backup capacity = 5,500;
- already committed = 2,000;
- usable backup = 3,500;
- state version increments;
- old plan becomes stale.

### 2:20 - Replan

Best emergency supply:

- finished inventory including safety stock = 2,100;
- backup = 3,500;
- total = 5,600;
- demand = 9,500;
- shortage = 3,900.

Deterministic allocation protects:

- EUR 728,000 revenue;
- EUR 300,000 margin.

The remaining customer demand is late.

### 2:45 - Why this is an agent/data product

Show:

- the Signal Investigator tool trace;
- the Impact Investigator graph trace;
- the Recovery Planner candidate plans;
- deterministic rejection reasons;
- incident memory.

Closing idea:

"The product does not only tell a planner that the world changed. It finds which commitments are exposed, proves which recovery plans fail, asks for the missing fact, and replans when that fact changes."

## Judge interaction

Let the judge edit one operational variable, such as:

- supplier capacity;
- safety-stock approval;
- inventory;
- lead time;
- availability.

The old plan must visibly become stale and the system must recompute.

## Non-negotiable labels

Never hide:

- REPLAY vs LIVE;
- public vs private;
- potential exposure vs confirmed operational state;
- simulated economics/BOM quantities;
- plan approval requirements.
