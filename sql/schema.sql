CREATE EXTENSION IF NOT EXISTS postgis;

-- Core relational model. pgvector is optional and must not block the product.
-- Real-world identifiers are nullable because they are not always public.
CREATE TABLE IF NOT EXISTS legal_entities (
  entity_id text PRIMARY KEY,
  legal_name text NOT NULL,
  lei varchar(20),
  parent_entity_id text REFERENCES legal_entities(entity_id),
  country_code char(2),
  provenance_class text NOT NULL,
  source_url text
);

CREATE TABLE IF NOT EXISTS facilities (
  facility_id text PRIMARY KEY,
  name text NOT NULL,
  country text,
  country_code char(2),
  city text,
  province text,
  tier text,
  product_categories text,
  parent_organization text,
  legal_entity_id text REFERENCES legal_entities(entity_id),
  gln varchar(13),
  geom geography(Point,4326),
  provenance_class text NOT NULL,
  source_url text
);
CREATE INDEX IF NOT EXISTS facilities_geom_gix ON facilities USING GIST (geom);

-- Full public adidas network. This is separate from the smaller operational
-- digital twin because most public facilities do not have private BOM/order links.
CREATE TABLE IF NOT EXISTS network_facilities (
  network_facility_id text PRIMARY KEY,
  os_id text,
  name text NOT NULL,
  official_name text,
  country text,
  city text,
  province text,
  address text,
  tiers text,
  product_categories text,
  list_types text,
  parent_organizations text,
  workers_count numeric,
  relationship_count int NOT NULL DEFAULT 1,
  geom geography(Point,4326),
  coordinate_provenance text NOT NULL,
  official_provenance text NOT NULL,
  match_methods text,
  source_url text,
  osh_url text
);
CREATE INDEX IF NOT EXISTS network_facilities_geom_gix
  ON network_facilities USING GIST (geom);
CREATE INDEX IF NOT EXISTS network_facilities_country_idx
  ON network_facilities(country);

CREATE TABLE IF NOT EXISTS network_facility_relationships (
  relationship_id text PRIMARY KEY,
  network_facility_id text REFERENCES network_facilities(network_facility_id),
  list_type text NOT NULL,
  source_row int,
  country text,
  account_name text,
  address text,
  city text,
  province text,
  zip_code text,
  tier text,
  product_categories text,
  workers_count numeric,
  female_workers numeric,
  male_workers numeric,
  migrant_workers numeric,
  parent_organization text,
  trade_union text,
  worker_representation text,
  cba text,
  os_id text,
  match_method text,
  match_score numeric,
  provenance_class text NOT NULL,
  source_url text
);

CREATE TABLE IF NOT EXISTS network_parent_groups (
  parent_id text PRIMARY KEY,
  parent_name text NOT NULL,
  provenance_class text NOT NULL,
  source_url text
);

CREATE TABLE IF NOT EXISTS network_parent_edges (
  network_facility_id text REFERENCES network_facilities(network_facility_id),
  parent_id text REFERENCES network_parent_groups(parent_id),
  relationship_type text NOT NULL,
  provenance_class text NOT NULL,
  source_url text,
  PRIMARY KEY(network_facility_id, parent_id)
);

-- Links the private operational twin to the public network. A public facility
-- can exist without a business link; only linked nodes continue into BOM/orders.
CREATE TABLE IF NOT EXISTS facility_network_links (
  facility_id text REFERENCES facilities(facility_id),
  network_facility_id text REFERENCES network_facilities(network_facility_id),
  match_method text NOT NULL,
  match_confidence numeric NOT NULL CHECK (match_confidence BETWEEN 0 AND 1),
  provenance_class text NOT NULL,
  PRIMARY KEY(facility_id, network_facility_id)
);

CREATE TABLE IF NOT EXISTS products (
  sku text PRIMARY KEY,
  name text NOT NULL,
  category text,
  public_material_basis text,
  standard_unit_revenue_eur numeric,
  standard_unit_margin_eur numeric,
  gtin text,
  hs_code text,
  provenance_class text NOT NULL,
  source_url text
);

CREATE TABLE IF NOT EXISTS materials (
  material_id text PRIMARY KEY,
  name text NOT NULL,
  uom text NOT NULL,
  category text,
  criticality text,
  provenance_class text NOT NULL
);

CREATE TABLE IF NOT EXISTS product_facilities (
  sku text REFERENCES products(sku),
  facility_id text REFERENCES facilities(facility_id),
  role text,
  approved boolean,
  setup_lead_days int,
  provenance_class text NOT NULL,
  PRIMARY KEY(sku, facility_id)
);

CREATE TABLE IF NOT EXISTS bom (
  sku text REFERENCES products(sku),
  material_id text REFERENCES materials(material_id),
  qty_per_unit numeric NOT NULL CHECK (qty_per_unit >= 0),
  provenance_class text NOT NULL,
  PRIMARY KEY(sku, material_id)
);

CREATE TABLE IF NOT EXISTS material_sources (
  material_id text REFERENCES materials(material_id),
  facility_id text REFERENCES facilities(facility_id),
  role text,
  approved boolean,
  lead_time_days int,
  weekly_capacity_units numeric,
  provenance_class text NOT NULL,
  PRIMARY KEY(material_id, facility_id)
);

-- Exact source-of-supply edge. A material source does not automatically feed every SKU
-- that uses the same material. This table links a source to the consuming assembly site/SKU.
CREATE TABLE IF NOT EXISTS material_allocations (
  material_id text REFERENCES materials(material_id),
  source_facility_id text REFERENCES facilities(facility_id),
  destination_facility_id text REFERENCES facilities(facility_id),
  sku text REFERENCES products(sku),
  approved boolean NOT NULL DEFAULT true,
  allocation_share numeric CHECK (allocation_share >= 0 AND allocation_share <= 1),
  provenance_class text NOT NULL,
  PRIMARY KEY(material_id, source_facility_id, destination_facility_id, sku)
);

CREATE TABLE IF NOT EXISTS inventory (
  site_id text,
  item_type text,
  item_id text,
  qty_on_hand numeric NOT NULL,
  qty_reserved numeric NOT NULL DEFAULT 0,
  safety_stock numeric NOT NULL DEFAULT 0,
  updated_at timestamptz,
  provenance_class text NOT NULL,
  PRIMARY KEY(site_id, item_type, item_id)
);

CREATE TABLE IF NOT EXISTS supplier_capacity (
  facility_id text REFERENCES facilities(facility_id),
  sku text REFERENCES products(sku),
  week_start date,
  capacity_units numeric NOT NULL,
  committed_units numeric NOT NULL DEFAULT 0,
  status text,
  evidence_age_hours numeric,
  source text,
  provenance_class text NOT NULL,
  PRIMARY KEY(facility_id, sku, week_start)
);

CREATE TABLE IF NOT EXISTS supplier_capacity_observations (
  observation_id text PRIMARY KEY,
  facility_id text REFERENCES facilities(facility_id),
  sku text REFERENCES products(sku),
  observed_at timestamptz NOT NULL DEFAULT now(),
  valid_until date,
  capacity_units numeric NOT NULL,
  committed_units numeric NOT NULL DEFAULT 0,
  source_channel text,
  raw_message text,
  confirmed boolean NOT NULL DEFAULT false,
  provenance_class text NOT NULL
);

CREATE TABLE IF NOT EXISTS production_orders (
  prod_id text PRIMARY KEY,
  sku text REFERENCES products(sku),
  facility_id text REFERENCES facilities(facility_id),
  qty numeric NOT NULL,
  start_date date,
  due_date date,
  status text,
  provenance_class text NOT NULL
);

CREATE TABLE IF NOT EXISTS fulfilment_commitments (
  commitment_id text PRIMARY KEY,
  customer_or_market text,
  market text,
  sku text REFERENCES products(sku),
  qty numeric NOT NULL,
  due_date date,
  unit_revenue_eur numeric,
  revenue_eur numeric,
  unit_margin_eur numeric,
  gross_margin_eur numeric,
  priority int,
  partial_allowed boolean,
  provenance_class text NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_orders (
  po_id text PRIMARY KEY,
  material_id text REFERENCES materials(material_id),
  supplier_facility_id text REFERENCES facilities(facility_id),
  qty numeric NOT NULL,
  eta timestamptz,
  status text,
  provenance_class text NOT NULL
);

CREATE TABLE IF NOT EXISTS transport_lanes (
  lane_id text PRIMARY KEY,
  origin_facility_id text REFERENCES facilities(facility_id),
  port_unlocode text,
  port_name text,
  destination_market text,
  mode text,
  transit_days int,
  cost_eur_per_unit numeric,
  status text,
  policy_tag text,
  provenance_class text NOT NULL
);

CREATE TABLE IF NOT EXISTS external_events (
  event_id text PRIMARY KEY,
  event_type text NOT NULL,
  mode text NOT NULL,
  source text NOT NULL,
  title text,
  occurred_or_effective_at timestamptz,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  current_as_of date,
  geom geography(Geometry,4326),
  raw_json jsonb,
  provenance_class text NOT NULL,
  source_url text
);
CREATE INDEX IF NOT EXISTS external_events_geom_gix ON external_events USING GIST (geom);

CREATE TABLE IF NOT EXISTS event_exposures (
  event_id text REFERENCES external_events(event_id),
  entity_type text,
  entity_id text,
  exposure_status text,
  evidence_confidence numeric CHECK (evidence_confidence BETWEEN 0 AND 100),
  distance_km numeric,
  evidence jsonb,
  provenance_class text NOT NULL,
  PRIMARY KEY(event_id, entity_type, entity_id)
);

CREATE TABLE IF NOT EXISTS scenarios (
  scenario_id text PRIMARY KEY,
  event_id text REFERENCES external_events(event_id),
  name text NOT NULL,
  mode text NOT NULL,
  as_of date NOT NULL,
  provenance_class text NOT NULL,
  note text
);

CREATE TABLE IF NOT EXISTS scenario_facility_state (
  scenario_id text REFERENCES scenarios(scenario_id),
  facility_id text REFERENCES facilities(facility_id),
  status text NOT NULL CHECK (status IN ('AVAILABLE','DEGRADED','UNAVAILABLE','UNKNOWN')),
  capacity_multiplier numeric NOT NULL DEFAULT 1 CHECK (capacity_multiplier >= 0 AND capacity_multiplier <= 1),
  confirmed boolean NOT NULL DEFAULT false,
  source_type text,
  reason text,
  provenance_class text NOT NULL,
  PRIMARY KEY(scenario_id, facility_id)
);

CREATE TABLE IF NOT EXISTS operational_state_version (
  singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
  version bigint NOT NULL
);
INSERT INTO operational_state_version(singleton, version)
VALUES (true, 1)
ON CONFLICT (singleton) DO NOTHING;
