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
CREATE INDEX IF NOT EXISTS network_facility_relationships_facility_idx
  ON network_facility_relationships(network_facility_id, list_type);

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
CREATE INDEX IF NOT EXISTS facility_network_links_network_idx
  ON facility_network_links(network_facility_id, facility_id);


CREATE TABLE IF NOT EXISTS operational_contacts (
  contact_id text PRIMARY KEY,
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  name text NOT NULL,
  channel text NOT NULL,
  address text NOT NULL,
  can_confirm_operational_data boolean NOT NULL DEFAULT false,
  provenance_class text NOT NULL
);
CREATE INDEX IF NOT EXISTS operational_contacts_entity_idx
  ON operational_contacts(entity_type, entity_id);

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
CREATE INDEX IF NOT EXISTS product_facilities_facility_idx
  ON product_facilities(facility_id, approved, sku);

CREATE TABLE IF NOT EXISTS bom (
  sku text REFERENCES products(sku),
  material_id text REFERENCES materials(material_id),
  qty_per_unit numeric NOT NULL CHECK (qty_per_unit >= 0),
  provenance_class text NOT NULL,
  PRIMARY KEY(sku, material_id)
);
CREATE INDEX IF NOT EXISTS bom_material_idx
  ON bom(material_id, sku);

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
CREATE INDEX IF NOT EXISTS material_sources_facility_idx
  ON material_sources(facility_id, approved, material_id);

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
CREATE INDEX IF NOT EXISTS material_allocations_source_idx
  ON material_allocations(source_facility_id, approved, sku);
CREATE INDEX IF NOT EXISTS material_allocations_destination_idx
  ON material_allocations(destination_facility_id, sku, approved);
CREATE INDEX IF NOT EXISTS material_allocations_sku_idx
  ON material_allocations(sku, approved, destination_facility_id);

CREATE TABLE IF NOT EXISTS substitutions (
  material_id text REFERENCES materials(material_id),
  substitute_material_id text REFERENCES materials(material_id),
  approved boolean NOT NULL DEFAULT false,
  max_ratio numeric CHECK (max_ratio >= 0 AND max_ratio <= 1),
  engineering_status text,
  provenance_class text NOT NULL,
  PRIMARY KEY(material_id, substitute_material_id)
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
CREATE INDEX IF NOT EXISTS inventory_item_idx
  ON inventory(item_type, item_id, site_id);

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
CREATE INDEX IF NOT EXISTS supplier_capacity_sku_idx
  ON supplier_capacity(sku, facility_id, week_start DESC);

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
CREATE INDEX IF NOT EXISTS production_orders_sku_facility_idx
  ON production_orders(sku, facility_id, status, due_date);

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
CREATE INDEX IF NOT EXISTS fulfilment_commitments_sku_due_idx
  ON fulfilment_commitments(sku, priority, due_date, commitment_id);

CREATE TABLE IF NOT EXISTS purchase_orders (
  po_id text PRIMARY KEY,
  material_id text REFERENCES materials(material_id),
  supplier_facility_id text REFERENCES facilities(facility_id),
  qty numeric NOT NULL,
  eta timestamptz,
  status text,
  provenance_class text NOT NULL
);
CREATE INDEX IF NOT EXISTS purchase_orders_material_eta_idx
  ON purchase_orders(material_id, status, eta, supplier_facility_id);

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
CREATE INDEX IF NOT EXISTS transport_lanes_origin_market_idx
  ON transport_lanes(origin_facility_id, destination_market, status);
CREATE INDEX IF NOT EXISTS transport_lanes_port_idx
  ON transport_lanes(port_unlocode, status);

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
CREATE INDEX IF NOT EXISTS scenario_facility_state_facility_idx
  ON scenario_facility_state(facility_id, scenario_id, status);


CREATE TABLE IF NOT EXISTS event_outbox (
  outbox_id text PRIMARY KEY,
  topic text NOT NULL,
  event_key text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  attempts int NOT NULL DEFAULT 0,
  last_error text
);
CREATE INDEX IF NOT EXISTS event_outbox_pending_idx
  ON event_outbox(created_at)
  WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS event_consumptions (
  consumer_name text NOT NULL,
  outbox_id text NOT NULL REFERENCES event_outbox(outbox_id) ON DELETE CASCADE,
  status text NOT NULL,
  processed_at timestamptz NOT NULL DEFAULT now(),
  result_json jsonb,
  error_text text,
  PRIMARY KEY(consumer_name, outbox_id)
);
CREATE INDEX IF NOT EXISTS event_consumptions_status_idx
  ON event_consumptions(consumer_name, status, processed_at);

CREATE TABLE IF NOT EXISTS incidents (
  incident_id text PRIMARY KEY,
  event_id text REFERENCES external_events(event_id),
  scenario_id text REFERENCES scenarios(scenario_id),
  event_type text,
  status text NOT NULL,
  summary text,
  initial_assessment text,
  detected_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  provenance_class text NOT NULL
);

-- Live evidence gaps become durable tasks, never assumed operational damage.
CREATE TABLE IF NOT EXISTS incident_investigation_tasks (
  task_id text PRIMARY KEY,
  incident_id text NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
  task_key text NOT NULL,
  task_type text NOT NULL CHECK (task_type IN (
    'CONFIRM_FACILITY_STATUS',
    'CONFIRM_MATERIAL_SUPPLY',
    'CONFIRM_SHIPMENT_STATUS',
    'VERIFY_TARIFF_APPLICABILITY',
    'VERIFY_PUBLIC_SUPPLIER_LINK'
  )),
  target_type text NOT NULL,
  target_id text NOT NULL,
  required_fact text NOT NULL,
  connected_skus jsonb NOT NULL DEFAULT '[]'::jsonb,
  connected_margin_eur numeric NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'OPEN'
    CHECK (status IN ('OPEN','RESOLVED','CANCELLED')),
  provenance_class text NOT NULL DEFAULT 'INFERRED'
    CHECK (provenance_class = 'INFERRED'),
  resolution_json jsonb,
  resolved_at timestamptz,
  resolved_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(incident_id, task_key)
);
CREATE INDEX IF NOT EXISTS investigation_tasks_status_idx
  ON incident_investigation_tasks(status, created_at DESC);
CREATE INDEX IF NOT EXISTS investigation_tasks_incident_idx
  ON incident_investigation_tasks(incident_id, status);

CREATE TABLE IF NOT EXISTS supplier_confirmation_requests (
  request_id text PRIMARY KEY,
  incident_id text REFERENCES incidents(incident_id) ON DELETE SET NULL,
  scenario_id text REFERENCES scenarios(scenario_id) ON DELETE SET NULL,
  facility_id text NOT NULL REFERENCES facilities(facility_id),
  sku text NOT NULL REFERENCES products(sku),
  field_requested text NOT NULL,
  system_value_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  recipient_contact_id text REFERENCES operational_contacts(contact_id),
  message_text text NOT NULL,
  status text NOT NULL CHECK (
    status IN (
      'DRAFT','PENDING_DISPATCH','SENT','REPLY_RECEIVED',
      'PARSE_FAILED','CONFIRMED','REJECTED','FAILED'
    )
  ),
  external_channel_id text,
  external_thread_ts text,
  requested_at timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz,
  replied_at timestamptz,
  confirmed_at timestamptz,
  last_error text,
  provenance_class text NOT NULL
);
CREATE INDEX IF NOT EXISTS supplier_confirmation_requests_status_idx
  ON supplier_confirmation_requests(status, requested_at);
CREATE INDEX IF NOT EXISTS supplier_confirmation_requests_thread_idx
  ON supplier_confirmation_requests(external_channel_id, external_thread_ts);

CREATE TABLE IF NOT EXISTS supplier_confirmation_replies (
  reply_id text PRIMARY KEY,
  request_id text NOT NULL REFERENCES supplier_confirmation_requests(request_id)
    ON DELETE CASCADE,
  sender_external_id text,
  source_message_id text,
  raw_message text NOT NULL,
  parsed_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  parse_ok boolean NOT NULL DEFAULT false,
  supplier_confirmed boolean NOT NULL DEFAULT false,
  received_at timestamptz NOT NULL DEFAULT now(),
  applied_at timestamptz,
  UNIQUE(source_message_id)
);
CREATE INDEX IF NOT EXISTS supplier_confirmation_replies_request_idx
  ON supplier_confirmation_replies(request_id, received_at);

CREATE TABLE IF NOT EXISTS incident_evidence (
  evidence_id text PRIMARY KEY,
  incident_id text REFERENCES incidents(incident_id) ON DELETE CASCADE,
  evidence_type text NOT NULL,
  source_name text,
  source_url text,
  fact_json jsonb NOT NULL,
  confidence numeric CHECK (confidence BETWEEN 0 AND 100),
  observed_at timestamptz NOT NULL DEFAULT now(),
  provenance_class text NOT NULL
);

CREATE TABLE IF NOT EXISTS incident_plan_history (
  plan_record_id text PRIMARY KEY,
  incident_id text REFERENCES incidents(incident_id) ON DELETE CASCADE,
  state_version bigint NOT NULL,
  sku text,
  plan_id text,
  decision text NOT NULL,
  reasons jsonb,
  metrics jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approval_requests (
  request_id text PRIMARY KEY,
  incident_id text NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
  scenario_id text REFERENCES scenarios(scenario_id),
  plan_record_id text REFERENCES incident_plan_history(plan_record_id),
  sku text,
  action_type text NOT NULL,
  action_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  reason text NOT NULL,
  requested_by text NOT NULL,
  status text NOT NULL CHECK (status IN ('PENDING','APPROVED','REJECTED','CANCELLED')),
  requested_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz,
  decided_by text,
  decision_reason text
);
CREATE INDEX IF NOT EXISTS approval_requests_status_idx
  ON approval_requests(status, requested_at);
CREATE INDEX IF NOT EXISTS approval_requests_incident_idx
  ON approval_requests(incident_id, requested_at);

CREATE TABLE IF NOT EXISTS action_executions (
  execution_id text PRIMARY KEY,
  approval_request_id text NOT NULL UNIQUE
    REFERENCES approval_requests(request_id) ON DELETE CASCADE,
  incident_id text NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
  action_type text NOT NULL,
  action_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','FAILED')),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  executed_by text NOT NULL,
  result_json jsonb,
  error_text text
);
CREATE INDEX IF NOT EXISTS action_executions_incident_idx
  ON action_executions(incident_id, started_at);

CREATE TABLE IF NOT EXISTS incident_decisions (
  decision_id text PRIMARY KEY,
  incident_id text REFERENCES incidents(incident_id) ON DELETE CASCADE,
  plan_record_id text REFERENCES incident_plan_history(plan_record_id),
  action text NOT NULL,
  approved_by text,
  reason text,
  made_at timestamptz NOT NULL DEFAULT now(),
  outcome_json jsonb
);

CREATE TABLE IF NOT EXISTS incident_outcomes (
  incident_id text PRIMARY KEY REFERENCES incidents(incident_id) ON DELETE CASCADE,
  actual_supplier_delay_days numeric,
  actual_shortage_units numeric,
  actual_cost_eur numeric,
  customer_impact_json jsonb,
  success boolean,
  lesson text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_runs (
  run_id text PRIMARY KEY,
  incident_id text REFERENCES incidents(incident_id) ON DELETE CASCADE,
  agent_name text NOT NULL,
  model text,
  output_text text,
  tool_trace jsonb,
  state_version bigint,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS incidents_event_idx ON incidents(event_id);
CREATE INDEX IF NOT EXISTS incidents_event_type_idx ON incidents(event_type);
CREATE INDEX IF NOT EXISTS agent_runs_incident_idx ON agent_runs(incident_id);

CREATE TABLE IF NOT EXISTS operational_state_version (
  singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
  version bigint NOT NULL
);
INSERT INTO operational_state_version(singleton, version)
VALUES (true, 1)
ON CONFLICT (singleton) DO NOTHING;
