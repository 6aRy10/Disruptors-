import unittest
from pathlib import Path

from dependency.db.connection import connect
from dependency.incidents.triage import triage_event
from dependency.graph.event_impact import trace_business_event_impact
from dependency.graph.exposure import facilities_within_radius, operational_facilities_within_radius
from dependency.solver.candidates import generate_recovery_candidates
from dependency.solver.recovery import plan_sku_recovery


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "dependency"

BANNED_PRODUCTION_LITERALS = (
    "JI2993",
    "JQ6656",
    "SCN-CIANJUR-REPLAY-01",
    "IDN-CIANJUR-2022-USGS-us7000ir9t",
    "ADI26-0240",
    "hwa_capacity",
    "hwa_committed",
)


class DehardcodingTests(unittest.TestCase):
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"
    SCALE_SCENARIO = "TEST-SCALE-GENERALIZATION"
    SCALE_EVENT = "TEST-SCALE-GENERALIZATION-EVENT"
    SCALE_SKU = "DTSKU-00001"

    def setUp(self):
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO external_events(
                  event_id,event_type,mode,source,title,
                  occurred_or_effective_at,current_as_of,raw_json,
                  provenance_class
                ) VALUES (
                  %s,'test_disruption','REPLAY','TEST',
                  'Generic de-hardcoding test event',
                  '2026-10-21T00:00:00Z','2026-10-21','{}'::jsonb,
                  'SIMULATED_PRIVATE'
                )
                ON CONFLICT (event_id) DO NOTHING
                """,
                (self.SCALE_EVENT,),
            )
            conn.execute(
                """
                INSERT INTO scenarios(
                  scenario_id,event_id,name,mode,as_of,provenance_class,note
                ) VALUES (
                  %s,%s,'Generic generated-SKU scenario','REPLAY',
                  '2026-10-21','SIMULATED_PRIVATE',
                  'Test-only scenario proving the solver is not tied to Cianjur.'
                )
                ON CONFLICT (scenario_id) DO NOTHING
                """,
                (self.SCALE_SCENARIO, self.SCALE_EVENT),
            )
            primary = conn.execute(
                """
                SELECT pf.facility_id
                FROM product_facilities pf
                WHERE pf.sku=%s
                  AND pf.role='primary_assembly'
                ORDER BY pf.facility_id
                LIMIT 1
                """,
                (self.SCALE_SKU,),
            ).fetchone()
            if not primary:
                raise AssertionError("Generated scale SKU has no primary facility.")
            self.scale_primary = primary[0]
            conn.execute(
                """
                INSERT INTO scenario_facility_state(
                  scenario_id,facility_id,status,capacity_multiplier,confirmed,
                  source_type,reason,provenance_class
                ) VALUES (
                  %s,%s,'UNAVAILABLE',0,true,'TEST',
                  'Generic primary unavailable for de-hardcoding test.',
                  'SIMULATED_PRIVATE'
                )
                ON CONFLICT (scenario_id,facility_id) DO UPDATE SET
                  status='UNAVAILABLE',
                  capacity_multiplier=0,
                  confirmed=true,
                  source_type='TEST',
                  reason='Generic primary unavailable for de-hardcoding test.',
                  provenance_class='SIMULATED_PRIVATE'
                """,
                (self.SCALE_SCENARIO, self.scale_primary),
            )
            conn.commit()

    def tearDown(self):
        with connect() as conn:
            conn.execute(
                "DELETE FROM fulfilment_commitments WHERE commitment_id='TEST-DYNAMIC-DEMAND'"
            )
            conn.execute(
                "DELETE FROM scenario_facility_state WHERE scenario_id=%s",
                (self.SCALE_SCENARIO,),
            )
            conn.execute(
                "DELETE FROM scenarios WHERE scenario_id=%s",
                (self.SCALE_SCENARIO,),
            )
            conn.execute(
                "DELETE FROM external_events WHERE event_id=%s",
                (self.SCALE_EVENT,),
            )
            conn.commit()

    def test_production_source_contains_no_flagship_ids(self):
        offenders = []
        for path in SRC.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for literal in BANNED_PRODUCTION_LITERALS:
                if literal in text:
                    offenders.append(
                        f"{path.relative_to(ROOT)} contains {literal}"
                    )

        self.assertEqual(
            offenders,
            [],
            "Flagship fixture identifiers leaked into production logic:\n"
            + "\n".join(offenders),
        )

    def test_recovery_candidates_are_discovered_for_second_flagship_sku(self):
        plans = generate_recovery_candidates(
            scenario_id=self.SCENARIO_ID,
            sku="JQ6656",
        )
        backup_ids = {
            p["evidence"]["backup_facility_id"]
            for p in plans
            if p["plan_type"] == "ASSEMBLY_REALLOCATION"
        }
        self.assertTrue(
            {"ADI26-0228", "ADI26-0403", "ADI26-0104"}.issubset(backup_ids)
        )
        self.assertTrue(all("JI2993" not in p["title"] for p in plans))

    def test_event_triage_derives_business_products_and_scenario(self):
        result = triage_event(
            event_id="IDN-CIANJUR-2022-USGS-us7000ir9t",
            radius_km=150,
        )
        skus = {p["sku"] for p in result["impacted_products"]}
        self.assertEqual(result["public_facility_count"], 20)
        self.assertIn("JI2993", skus)
        self.assertIn("JQ6656", skus)
        self.assertEqual(result["scenario_id"], self.SCENARIO_ID)
        self.assertTrue(result["recovery_ready"])

    def _insert_scale_earthquake(self, event_id: str):
        with connect() as conn:
            row = conn.execute(
                """
                SELECT f.facility_id,ST_X(f.geom::geometry),ST_Y(f.geom::geometry)
                FROM facilities f
                JOIN facility_network_links l
                  ON l.facility_id=f.facility_id
                WHERE f.facility_id LIKE 'DTF-A-%'
                  AND EXISTS (
                    SELECT 1
                    FROM product_facilities pf
                    WHERE pf.facility_id=f.facility_id
                      AND pf.sku LIKE 'DTSKU-%'
                  )
                ORDER BY f.facility_id
                LIMIT 1
                """
            ).fetchone()
            self.assertIsNotNone(row)
            facility_id, lon, lat = row
            expected = {
                r[0]
                for r in conn.execute(
                    """
                    SELECT sku
                    FROM product_facilities
                    WHERE facility_id=%s
                      AND sku LIKE 'DTSKU-%'
                    ORDER BY sku
                    """,
                    (facility_id,),
                ).fetchall()
            }
            conn.execute(
                """
                INSERT INTO external_events(
                  event_id,event_type,mode,source,title,
                  occurred_or_effective_at,current_as_of,geom,raw_json,
                  provenance_class
                ) VALUES (
                  %s,'earthquake','REPLAY','TEST',
                  'Arbitrary scale-network earthquake',
                  '2026-10-21T00:00:00Z','2026-10-21',
                  ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                  '{}'::jsonb,'SIMULATED_PRIVATE'
                )
                """,
                (event_id, lon, lat),
            )
            conn.commit()
        return {
            "facility_id": facility_id,
            "longitude": float(lon),
            "latitude": float(lat),
            "expected_skus": expected,
        }

    def _delete_test_event(self, event_id: str):
        with connect() as conn:
            conn.execute(
                "DELETE FROM external_events WHERE event_id=%s",
                (event_id,),
            )
            conn.commit()

    def test_generated_facility_has_products_and_coordinates(self):
        with connect() as conn:
            row = conn.execute(
                """
                SELECT
                  f.facility_id,
                  ST_X(f.geom::geometry),
                  ST_Y(f.geom::geometry),
                  COUNT(pf.sku)
                FROM facilities f
                JOIN product_facilities pf ON pf.facility_id=f.facility_id
                WHERE f.facility_id LIKE 'DTF-A-%'
                  AND pf.sku LIKE 'DTSKU-%'
                GROUP BY f.facility_id,f.geom
                ORDER BY f.facility_id
                LIMIT 1
                """
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertIsNotNone(row[1])
        self.assertIsNotNone(row[2])
        self.assertGreater(int(row[3]), 0)

    def test_generated_facility_has_public_network_link(self):
        with connect() as conn:
            row = conn.execute(
                """
                SELECT
                  f.facility_id,
                  l.network_facility_id,
                  ST_Distance(f.geom,nf.geom)
                FROM facilities f
                JOIN facility_network_links l
                  ON l.facility_id=f.facility_id
                JOIN network_facilities nf
                  ON nf.network_facility_id=l.network_facility_id
                WHERE f.facility_id LIKE 'DTF-A-%'
                  AND EXISTS (
                    SELECT 1
                    FROM product_facilities pf
                    WHERE pf.facility_id=f.facility_id
                      AND pf.sku LIKE 'DTSKU-%'
                  )
                ORDER BY f.facility_id
                LIMIT 1
                """
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertTrue(row[0].startswith("DTF-A-"))
        self.assertIsNotNone(row[1])
        self.assertLess(float(row[2]), 1.0)

    def test_public_radius_query_returns_generated_network_node(self):
        with connect() as conn:
            row = conn.execute(
                """
                SELECT
                  f.facility_id,l.network_facility_id,
                  ST_X(f.geom::geometry),ST_Y(f.geom::geometry)
                FROM facilities f
                JOIN facility_network_links l
                  ON l.facility_id=f.facility_id
                WHERE f.facility_id LIKE 'DTF-A-%'
                  AND EXISTS (
                    SELECT 1
                    FROM product_facilities pf
                    WHERE pf.facility_id=f.facility_id
                      AND pf.sku LIKE 'DTSKU-%'
                  )
                ORDER BY f.facility_id
                LIMIT 1
                """
            ).fetchone()
        self.assertIsNotNone(row)
        facility_id, network_id, lon, lat = row
        public_rows = facilities_within_radius(
            latitude=float(lat),
            longitude=float(lon),
            radius_km=3,
        )
        public_ids = {item["network_facility_id"] for item in public_rows}
        self.assertIn(
            network_id,
            public_ids,
            f"Expected public node {network_id}; nearby nodes={sorted(public_ids)}",
        )

    def test_public_radius_query_preserves_generated_operational_link(self):
        with connect() as conn:
            row = conn.execute(
                """
                SELECT
                  f.facility_id,l.network_facility_id,
                  ST_X(f.geom::geometry),ST_Y(f.geom::geometry)
                FROM facilities f
                JOIN facility_network_links l
                  ON l.facility_id=f.facility_id
                WHERE f.facility_id LIKE 'DTF-A-%'
                  AND EXISTS (
                    SELECT 1
                    FROM product_facilities pf
                    WHERE pf.facility_id=f.facility_id
                      AND pf.sku LIKE 'DTSKU-%'
                  )
                ORDER BY f.facility_id
                LIMIT 1
                """
            ).fetchone()
        self.assertIsNotNone(row)
        facility_id, network_id, lon, lat = row
        public_rows = facilities_within_radius(
            latitude=float(lat),
            longitude=float(lon),
            radius_km=3,
        )
        target = next(
            (
                item
                for item in public_rows
                if item["network_facility_id"] == network_id
            ),
            None,
        )
        self.assertIsNotNone(target)
        self.assertIn(
            facility_id,
            target["operational_facility_ids"],
            (
                f"Expected operational link {facility_id}; got "
                f"{target['operational_facility_ids']}"
            ),
        )

    def test_arbitrary_new_event_finds_generated_facility_geospatially(self):
        event_id = "TEST-ARBITRARY-SCALE-GEO"
        fixture = self._insert_scale_earthquake(event_id)
        try:
            rows = operational_facilities_within_radius(
                latitude=fixture["latitude"],
                longitude=fixture["longitude"],
                radius_km=3,
            )
            ids = {row["facility_id"] for row in rows}
            self.assertIn(fixture["facility_id"], ids)
        finally:
            self._delete_test_event(event_id)

    def test_arbitrary_new_earthquake_reaches_generated_private_graph(self):
        event_id = "TEST-ARBITRARY-SCALE-EARTHQUAKE"
        fixture = self._insert_scale_earthquake(event_id)
        try:
            impact = trace_business_event_impact(
                event_id=event_id,
                radius_km=3,
            )
            impacted = {row["sku"] for row in impact["products"]}
            self.assertTrue(fixture["expected_skus"])
            self.assertTrue(
                fixture["expected_skus"] & impacted,
                (
                    f"Expected at least one of {sorted(fixture['expected_skus'])} "
                    f"from facility {fixture['facility_id']}; got "
                    f"{sorted(impacted)}"
                ),
            )
            self.assertTrue(
                all(
                    sku.startswith("DTSKU-")
                    for sku in fixture["expected_skus"] & impacted
                )
            )
        finally:
            self._delete_test_event(event_id)

    def test_arbitrary_ocean_event_does_not_create_fake_business_impact(self):
        event_id = "TEST-ARBITRARY-OCEAN-EARTHQUAKE"
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO external_events(
                  event_id,event_type,mode,source,title,
                  occurred_or_effective_at,current_as_of,geom,raw_json,
                  provenance_class
                ) VALUES (
                  %s,'earthquake','REPLAY','TEST',
                  'Ocean earthquake with no supply-network intersection',
                  '2026-10-21T00:00:00Z','2026-10-21',
                  ST_SetSRID(ST_MakePoint(-145,0),4326)::geography,
                  '{}'::jsonb,'SIMULATED_PRIVATE'
                )
                """,
                (event_id,),
            )
            conn.commit()

        try:
            result = triage_event(
                event_id=event_id,
                radius_km=25,
            )
            self.assertEqual(result["status"], "NO_NETWORK_EXPOSURE")
            self.assertEqual(result["public_facility_count"], 0)
            self.assertEqual(result["impacted_products"], [])
        finally:
            with connect() as conn:
                conn.execute(
                    "DELETE FROM external_events WHERE event_id=%s",
                    (event_id,),
                )
                conn.commit()

    def test_generated_sku_uses_same_recovery_engine(self):
        plan = plan_sku_recovery(
            scenario_id=self.SCALE_SCENARIO,
            sku=self.SCALE_SKU,
            release_safety_stock=False,
        )
        candidates = generate_recovery_candidates(
            scenario_id=self.SCALE_SCENARIO,
            sku=self.SCALE_SKU,
        )

        self.assertEqual(plan["sku"], self.SCALE_SKU)
        self.assertGreater(plan["demand_units"], 0)
        self.assertNotEqual(plan["demand_units"], 9500)
        self.assertGreater(plan["lost_primary_units"], 0)
        self.assertGreaterEqual(len(plan["backup_candidates"]), 2)
        self.assertTrue(
            any(
                row["plan_type"] == "ASSEMBLY_REALLOCATION"
                for row in candidates
            )
        )

    def test_demand_change_changes_plan_without_code_change(self):
        baseline = plan_sku_recovery(
            scenario_id=self.SCALE_SCENARIO,
            sku=self.SCALE_SKU,
            release_safety_stock=False,
        )

        with connect() as conn:
            product = conn.execute(
                """
                SELECT standard_unit_revenue_eur,standard_unit_margin_eur
                FROM products
                WHERE sku=%s
                """,
                (self.SCALE_SKU,),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO fulfilment_commitments(
                  commitment_id,customer_or_market,market,sku,qty,due_date,
                  unit_revenue_eur,revenue_eur,unit_margin_eur,gross_margin_eur,
                  priority,partial_allowed,provenance_class
                ) VALUES (
                  'TEST-DYNAMIC-DEMAND','Adversarial test customer','Europe',
                  %s,777,'2026-11-01',%s,%s,%s,%s,1,true,
                  'SIMULATED_PRIVATE'
                )
                """,
                (
                    self.SCALE_SKU,
                    product[0],
                    float(product[0]) * 777,
                    product[1],
                    float(product[1]) * 777,
                ),
            )
            conn.commit()

        changed = plan_sku_recovery(
            scenario_id=self.SCALE_SCENARIO,
            sku=self.SCALE_SKU,
            release_safety_stock=False,
        )

        self.assertEqual(
            changed["demand_units"],
            baseline["demand_units"] + 777,
        )

    def test_capacity_change_changes_generated_sku_recovery(self):
        baseline = plan_sku_recovery(
            scenario_id=self.SCALE_SCENARIO,
            sku=self.SCALE_SKU,
            release_safety_stock=False,
        )

        with connect() as conn:
            rows = conn.execute(
                """
                SELECT sc.facility_id,sc.week_start,sc.capacity_units,
                       sc.committed_units
                FROM supplier_capacity sc
                JOIN product_facilities pf
                  ON pf.facility_id=sc.facility_id
                 AND pf.sku=sc.sku
                WHERE sc.sku=%s
                  AND pf.role <> 'primary_assembly'
                ORDER BY sc.facility_id,sc.week_start
                """,
                (self.SCALE_SKU,),
            ).fetchall()
            self.assertGreaterEqual(len(rows), 2)

            for row in rows:
                conn.execute(
                    """
                    UPDATE supplier_capacity
                    SET capacity_units=committed_units + 10
                    WHERE facility_id=%s AND sku=%s AND week_start=%s
                    """,
                    (row[0], self.SCALE_SKU, row[1]),
                )
            conn.commit()

        try:
            constrained = plan_sku_recovery(
                scenario_id=self.SCALE_SCENARIO,
                sku=self.SCALE_SKU,
                release_safety_stock=False,
            )
            self.assertLessEqual(constrained["backup_available_units"], 10.0)
            self.assertGreaterEqual(
                constrained["shortage_units"],
                baseline["shortage_units"],
            )
        finally:
            with connect() as conn:
                for row in rows:
                    conn.execute(
                        """
                        UPDATE supplier_capacity
                        SET capacity_units=%s,committed_units=%s
                        WHERE facility_id=%s AND sku=%s AND week_start=%s
                        """,
                        (
                            row[2],
                            row[3],
                            row[0],
                            self.SCALE_SKU,
                            row[1],
                        ),
                    )
                conn.commit()


if __name__ == "__main__":
    unittest.main()
