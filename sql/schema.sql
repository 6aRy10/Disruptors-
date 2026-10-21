CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE facilities (
  facility_id text PRIMARY KEY, name text, country text, city text, tier text,
  product_categories text, parent_organization text,
  geom geography(Point,4326), provenance_class text, source_url text
);

CREATE TABLE products (
  sku text PRIMARY KEY, name text, category text, public_material_basis text,
  standard_unit_revenue_eur numeric, standard_unit_margin_eur numeric,
  provenance_class text, source_url text
);

CREATE TABLE product_facilities (
  sku text REFERENCES products, facility_id text REFERENCES facilities,
  role text, approved boolean, setup_lead_days int, provenance_class text,
  PRIMARY KEY(sku,facility_id)
);

CREATE TABLE materials (
  material_id text PRIMARY KEY, name text, uom text, category text, criticality text,
  public_basis text, provenance_class text
);

CREATE TABLE bom (
  sku text REFERENCES products, material_id text REFERENCES materials,
  qty_per_unit numeric, provenance_class text, PRIMARY KEY(sku,material_id)
);

CREATE TABLE material_sources (
  material_id text REFERENCES materials, facility_id text REFERENCES facilities,
  role text, approved boolean, lead_time_days int, weekly_capacity_units numeric,
  provenance_class text, PRIMARY KEY(material_id,facility_id)
);

CREATE TABLE inventory (
  site_id text, item_type text, item_id text, qty_on_hand numeric, qty_reserved numeric,
  safety_stock numeric, updated_at timestamptz, provenance_class text,
  PRIMARY KEY(site_id,item_type,item_id)
);

CREATE TABLE supplier_capacity (
  facility_id text REFERENCES facilities, sku text REFERENCES products, week_start date,
  capacity_units numeric, committed_units numeric, status text,
  evidence_age_hours numeric, source text, provenance_class text,
  PRIMARY KEY(facility_id,sku,week_start)
);

CREATE TABLE production_orders (
  prod_id text PRIMARY KEY, sku text, facility_id text, qty numeric,
  start_date date, due_date date, status text, provenance_class text
);

CREATE TABLE fulfilment_commitments (
  commitment_id text PRIMARY KEY, customer_or_market text, market text, sku text, qty numeric,
  due_date date, unit_revenue_eur numeric, revenue_eur numeric,
  unit_margin_eur numeric, gross_margin_eur numeric, priority int,
  partial_allowed boolean, provenance_class text
);

CREATE TABLE purchase_orders (
  po_id text PRIMARY KEY, material_id text, supplier_facility_id text,
  qty numeric, eta timestamptz, status text, provenance_class text
);

CREATE TABLE transport_lanes (
  lane_id text PRIMARY KEY, origin_facility_id text, port_unlocode text, port_name text,
  destination_market text, mode text, transit_days int,
  cost_eur_per_unit numeric, status text, policy_tag text, provenance_class text
);

CREATE TABLE product_trade_classification (
  sku text PRIMARY KEY, origin_country text, classification_id text,
  reciprocal_tariff_applicable boolean, exception_code text,
  customs_value_eur_equiv_per_unit numeric, provenance_class text, source text
);

CREATE TABLE external_events (
  event_id text PRIMARY KEY, event_type text, mode text,
  source text, title text, occurred_or_effective_at timestamptz,
  ingested_at timestamptz DEFAULT now(), current_as_of date,
  geom geography(Geometry,4326), raw_json jsonb,
  provenance_class text, source_url text
);

CREATE TABLE event_exposures (
  event_id text, entity_type text, entity_id text, exposure_status text,
  evidence_confidence numeric, distance_km numeric, evidence jsonb,
  provenance_class text, PRIMARY KEY(event_id,entity_type,entity_id)
);

CREATE TABLE policy_exposures (
  event_id text, sku text, origin_country text, destination_market text,
  classification_id text, tariff_applicable boolean,
  additional_tariff_rate numeric, incremental_cost numeric,
  provenance_class text, evidence jsonb,
  PRIMARY KEY(event_id,sku,destination_market)
);

CREATE TABLE risk_scores (
  score_id uuid PRIMARY KEY, event_id text, object_type text, object_id text,
  score numeric CHECK(score>=0 AND score<=100), band text,
  drivers jsonb, evidence_confidence numeric,
  state_version bigint, calculated_at timestamptz DEFAULT now()
);

CREATE TABLE risk_thresholds (
  threshold_id text PRIMARY KEY, object_type text, object_id text,
  notify_above numeric, escalate_above numeric,
  score_jump_notify numeric, channel text, owner_role text, enabled boolean
);

CREATE TABLE supplier_contacts (
  contact_id text PRIMARY KEY, entity_id text, channel text, address text,
  can_confirm_operational_data boolean
);

CREATE TABLE supplier_confirmation_requests (
  request_id uuid PRIMARY KEY, facility_id text, sku text, field_requested text,
  system_value jsonb, requested_at timestamptz, status text, contact_id text
);

CREATE TABLE supplier_confirmation_responses (
  response_id uuid PRIMARY KEY, request_id uuid, raw_message text,
  parsed_update jsonb, parser_confidence numeric, supplier_confirmed boolean,
  evidence_message_id text, received_at timestamptz DEFAULT now()
);

CREATE TABLE operational_state_version (
  singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
  version bigint NOT NULL
);

CREATE TABLE incidents (
  incident_id uuid PRIMARY KEY, event_id text, opened_at timestamptz DEFAULT now(),
  status text, summary text, evidence jsonb
);

CREATE TABLE scenarios (
  scenario_id uuid PRIMARY KEY, incident_id uuid, state_version bigint,
  assumptions jsonb, actions jsonb, revenue_protected numeric,
  margin_protected numeric, incremental_cost numeric, units_late numeric,
  feasible boolean, constraint_failures jsonb
);

CREATE TABLE decisions (
  decision_id uuid PRIMARY KEY, incident_id uuid, scenario_id uuid,
  decision text, approved_by text, approved_at timestamptz,
  execution_status text, actual_outcome jsonb
);
