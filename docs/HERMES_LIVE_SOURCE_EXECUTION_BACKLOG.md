# HERMES LIVE DATA SOURCES — IMPLEMENTATION BACKLOG
**Date: 2026-10-22. Canonical machine-readable catalog: `config/live_source_registry.json`.**

Use `python -m scripts.list_source_registry` to list all sources, or
`python -m scripts.list_source_registry --priority P0` for near-term work.

## What has already been wired into HERMES

| Feed | Mechanism | Reality check |
| --- | --- | --- |
| USGS | `src/dependency/ingest/usgs.py` + `scripts/watch_usgs.py`; included in `run_live_stack --watch` | Actual continuous operation depends on starting watcher |
| GDACS | `src/dependency/ingest/gdacs.py` + `scripts/watch_gdacs.py`; same watcher | Original event ID; source reports don't establish closure |
| IMF PortWatch | `src/dependency/ingest/portwatch.py` + `scripts/watch_portwatch.py` | Optional `--portwatch`; port-call change is derived, not shipment delay |
| NASA FIRMS (NEW) | `src/dependency/ingest/firms.py` + `scripts/watch_firms.py` and migration `006_source_observations.sql` | Opt-in MAP_KEY; raw satellite fire *pixels* remain separate from incident queue; no false closures |
| Official Adidas + OS Hub | Public normalized CSVs in `data/normalized/`, 770 mapped geocoded sites | Source snapshots; public identities, not authenticated enterprise operations |
| Internal private digital twin | 2,500 modeled products, 170,018 material allocations, 20,018 commitments at initial load | Simulated, NOT authenticated brand ERP, worker or supplier facts |

**This is not a claim that all connected sources are polling now.** Check `/app-data/activity` for receipts, `collector_checks` for USGS/GDACS/PortWatch poll status and the watcher process log.

## P0 immediate priority, ordered by marginal recovery value

1. **USGS/GDACS: fix versioned source updates**. Old `upsert_external_event` overwrites `raw_json` and `ingested_at` on repeat source polls. Keep source revisions and emit `external.event.updated` when severity/footprint changes; do not duplicate first receipts.
2. **NASA FIRMS: independent Indonesian wildfire observations**. Record stable pixel IDs, observation UTC time, sensor and quality; overlay against public supplier coordinates. Do **not** run an incident on one pixel; require a second official source or operational confirmation before claiming a wildfire disrupts a facility.
3. **NOAA/NHC forecast tracks and geographic polygons**. Official RSS links to changing forecast GIS products, not merely one static cyclone coordinate. HERMES must preserve bulletin/forecast valid-time and track revisions. NOAA NHC covers its designated basins, not all Indonesia; GDACS and regional agencies cover Indo-Pacific.
4. **IMF PortWatch: finalize shipment/transport joins**. The existing anomalies are port-call statistics. To infer impact, cross-check modeled transport `lane_id`, port UN/LOCODE, explicit shipment, PO, customer due date. No order join → `UNASSESSED`.
5. **US OFAC + EU financial sanctions + US Consolidated Screening List**. Versioned entity designations and source timestamps; fuzzy matches become review candidates, not automatic legal conclusions. Avoid broad indiscriminate raw data duplication.
6. **EU TARIC + US Federal Register + CBP**. Store effective dates, origin/destination, HS/CN codes, exceptions, affected material/SKU classification and direct source passage. The initial UI must show "needs classification" if a modeled SKU has no verified tariff code.
7. **Authenticated enterprise operations**. Build import schemas for BOM/customer commitments, supplier capacity/time windows and ETA, WMS safety reserves, MES downtime, shipment milestone and engineering substitution approval. For judges use the existing modeled private twin plus reviewed simulated confirmation, never claim direct Adidas API access.
8. **Aiven**. Once credentials, quotas and security are approved, publish transactional outbox events to one managed Kafka topic, then independently verify publish/consume. Aiven is transport/storage, not a source of facts.

## P1 as soon as baseline is robust

- Copernicus GloFAS/GFM, ECMWF open global forecasts, Meteoalarm, national Indonesia/Japan disaster agencies; all with geospatial and validity times.
- Port authority notices, DCSA-compatible carrier APIs, actual shipping bookings; private access is needed.
- GLEIF identity enrichment, OS Hub API only with subscription/trial, UN/LOCODE and OSM base geography.
- Power and electricity outage feeds in affected supplier countries.
- Country-specific trade restrictions and export controls.

## P2 / licensed or nonreal-time

- ACLED political events: **do not ingest** for our commercial/AI-facing product without approved license. Its published EULA restricts commercial use and AI access. See https://acleddata.com/eula .
- GDELT 15-minute news event stream: early lead/hypothesis only, not a verified hazard; research scope and terms first.
- AIS ship positions, commodity market real-time benchmarks and paid port/transport indexes: commercial terms; not hackathon critical path.
- ECB FX, CISA KEV, NVD and other peripheral indicators: enrich confirmed operational scenarios only when matched to actual asset/SKU/contract records.
- UN Comtrade: historical published trade statistics, **NOT** an active disruption stream and not a substitute for tariffs.
- Reference lists and company filings refresh on publication rather than every few minutes.

## NASA FIRMS read-only/stored start NOW

NASA documentation: https://firms.modaps.eosdis.nasa.gov/api/area

1. Owner requests a free `FIRMS_MAP_KEY`, stores it in private backend environment, does not commit or send it in chat.
2. Pull `feat/db-foundation`, inspect `sql/migrations/006_source_observations.sql`, and apply via `python -m scripts.apply_migrations`. This schema addition does not reseed or change previous supplier/private tables.
3. `python -m scripts.watch_firms --dry-run` reads latest NASA NOAA20 VIIRS fire pixel CSV covering Indonesia by default (`95,-11,141,6`), without database writes.
4. `python -m scripts.watch_firms` stores the stable pixel IDs in `source_observations`; re-polling updates last_checked_at, preserving first_received_at.
5. Check counts, read-only:
   ```sql
   SELECT source, COUNT(*) AS pixels, min(observed_at), max(observed_at)
   FROM source_observations GROUP BY source;
   ```
6. The existing `external.events` consumer is **not** triggered by these satellite pixels. Backend teammate should next add source-pair corroboration and measured proximity to explicitly linked suppliers.
7. The source is not auto-started by `run_live_stack --watch` because its MAP_KEY is optional and sustained polling/false alerts need rate and source-confidence controls first.

At 2026-10-22 NASA FIRMS supports NOAA20/21 VIIRS NRT. It has announced the SNPP product will cease 2026-11-01, so do not build a new connector against `VIIRS_SNPP_NRT`.

## Standard normalized source contract for ALL new adapters

Each raw record must preserve:
```json
{
  "source_id": "NASA_FIRMS",
  "provider_event_id": "provider-stable-id",
  "provider_revision_id": "if published or computed payload hash",
  "observed_or_issued_at_utc": "2026-10-22T00:00:00Z",
  "first_received_at_utc": "written once",
  "last_checked_at_utc": "every successful poll",
  "effective_from_utc": null,
  "effective_to_utc": null,
  "geometry_or_applicability": "Point/Polygon/port/country/HS code",
  "provenance": "VERIFIED_PUBLIC / PUBLIC_DERIVED / SIMULATED_PRIVATE",
  "source_url": "official HTTPS link",
  "payload_hash": "SHA256 of normalized raw source data",
  "confidence_and_limitations": "source-specific interpretation",
  "entity_join_key": "OS_ID / UNLOCODE / LEI / facility ID / material HS code",
  "linked_private_object_verified": false
}
```

**Not all adapters yet implement this full versioned contract.** Stage incoming raw data in source-specific tables when an individual record is only a pixel, forecast point, headline or trade legal measure. Only normalized and sufficiently corroborated business incidents enter the incident pipeline.

Strict division: `OBSERVATION` != `POTENTIAL_EXPOSURE` != `CONFIRMED_OPERATIONAL_DISRUPTION` != `AUTHORIZED_ACTION`. Never infer one from the previous without an appropriate rule/evidence.

## Two engineers — immediate assignments

**Backend engineer / owner:**
- Audit and merge new NASA pixel observer on disposable PostGIS.
- Add one source revision table + update outbox on meaningful GDACS/USGS changes, with tests.
- Add spatial evidence join: fire pixel group near publicly geocoded supplier plus GDACS hazard → potentially exposed only; no invented private capacity.
- Add independently verifiable dated supplier/ETA confirmation that feeds the deterministic recovery engine.
- Prove real input change affects multiple commitments without double-spending factory/material capacity.

**Full-stack + agent engineer / owner:**
- Connect source status/revisions to the Event feed; do not call pixels "incidents".
- Add selected-event source provenance and independent corroboration panel.
- Support forecast polygons (not static storm dots), source update history, and source comparison.
- Make Ask HERMES link user question to actual incident, source refs, missing evidence and solver.
- Add browser tests for one reported event, one no-network event and one source correction.

**Lead / owner:**
- Authorize NASA FIRMS key and controlled usage; secure transfer of full modeled DB to teammates.
- Confirm business permissions for carrier/ERP/OS Hub APIs and any ACLED/GDELT reuse.
- Set up and check Aiven Kafka broker; one verified physical publish/consume flow or no streaming claim.
- Keep final judge demo focused on one deep Cianjur recovery with secondary live source scenario.

## What counts as a connected source

`CONFIGURED` (credentials + adapter) → `POLL_SUCCEEDED` (timestamp / input count) →
`STORED` (stable ID and version) → `CORROBORATED` where required →
`GRAPH_JOINED` (explicit entity link) → `CASE_CREATED` only with required evidence →
`ACTION_REVIEWED` → `EFFECT_MEASURED`.

A P0 entry in the catalog is **work priority**, not an assertion that a source is operational.

## Sources used to verify access and semantics

- https://earthquake.usgs.gov/earthquakes/feed/v1.0/
- https://www.gdacs.org/gdacsapi/api/Events/geteventlist/EVENTS4APP
- https://firms.modaps.eosdis.nasa.gov/api/area
- https://www.nhc.noaa.gov/gis/rss.php
- https://emergency.copernicus.eu/data/
- https://www.ecmwf.int/en/forecasts/datasets/open-data
- https://www.weather.gov/documentation/services-web-alerts
- https://portwatch.imf.org/
- https://ofac.treasury.gov/sanctions-list-service
- https://www.trade.gov/consolidated-screening-list
- https://taxation-customs.ec.europa.eu/online-services/online-services-and-databases-customs/eu-customs-tariff-taric_en
- https://info.opensupplyhub.org/resources/api-documentation
- https://www.gleif.org/en/lei-data/gleif-api/
- https://acleddata.com/eula
- https://www.gdeltproject.org/data.html

**Owner's populated database safety:** do not run `scripts/load_seed_data.py`, `reset_demo_state()`, or destructive replay on the existing machine.
