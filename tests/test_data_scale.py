import json
import unittest
from pathlib import Path

from dependency.db.connection import connect
from dependency.incidents.triage import triage_event


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "data" / "generated" / "private_twin"


class EnterpriseDataScaleTests(unittest.TestCase):
    def test_private_twin_has_enterprise_scale(self):
        with connect() as conn:
            counts = {
                "facilities": conn.execute(
                    "SELECT COUNT(*) FROM facilities WHERE facility_id LIKE 'DTF-%'"
                ).fetchone()[0],
                "facility_links": conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM facility_network_links
                    WHERE facility_id LIKE 'DTF-%'
                    """
                ).fetchone()[0],
                "products": conn.execute(
                    "SELECT COUNT(*) FROM products WHERE sku LIKE 'DTSKU-%'"
                ).fetchone()[0],
                "materials": conn.execute(
                    "SELECT COUNT(*) FROM materials WHERE material_id LIKE 'DTMAT-%'"
                ).fetchone()[0],
                "bom": conn.execute(
                    "SELECT COUNT(*) FROM bom WHERE sku LIKE 'DTSKU-%'"
                ).fetchone()[0],
                "product_facilities": conn.execute(
                    "SELECT COUNT(*) FROM product_facilities WHERE sku LIKE 'DTSKU-%'"
                ).fetchone()[0],
                "material_allocations": conn.execute(
                    "SELECT COUNT(*) FROM material_allocations WHERE sku LIKE 'DTSKU-%'"
                ).fetchone()[0],
                "commitments": conn.execute(
                    "SELECT COUNT(*) FROM fulfilment_commitments WHERE sku LIKE 'DTSKU-%'"
                ).fetchone()[0],
                "purchase_orders": conn.execute(
                    "SELECT COUNT(*) FROM purchase_orders WHERE po_id LIKE 'DTPO-%'"
                ).fetchone()[0],
                "production_orders": conn.execute(
                    "SELECT COUNT(*) FROM production_orders WHERE prod_id LIKE 'DTPROD-%'"
                ).fetchone()[0],
                "transport_lanes": conn.execute(
                    "SELECT COUNT(*) FROM transport_lanes WHERE lane_id LIKE 'DTLANE-%'"
                ).fetchone()[0],
            }

        self.assertEqual(counts["facilities"], 240)
        self.assertEqual(counts["facility_links"], counts["facilities"])
        self.assertEqual(counts["products"], 2500)
        self.assertEqual(counts["materials"], 792)
        self.assertEqual(counts["bom"], 28335)
        self.assertEqual(counts["product_facilities"], 7500)
        self.assertEqual(counts["material_allocations"], 170010)
        self.assertEqual(counts["commitments"], 20000)
        self.assertEqual(counts["purchase_orders"], 12500)
        self.assertEqual(counts["production_orders"], 5000)
        self.assertEqual(counts["transport_lanes"], 900)

    def test_generated_csv_manifest_matches_database_scale(self):
        manifest_path = GENERATED / "manifest.json"
        self.assertTrue(manifest_path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["private_data_provenance"], "SIMULATED_PRIVATE")
        self.assertEqual(manifest["public_identity_provenance"], "VERIFIED_PUBLIC")
        self.assertEqual(manifest["counts"]["products"], 2500)
        self.assertEqual(manifest["counts"]["bom"], 28335)
        self.assertEqual(
            manifest["counts"]["material_allocations"],
            170010,
        )
        self.assertGreaterEqual(manifest["total_generated_rows"], 266000)

        for dataset in (
            "products",
            "materials",
            "bom",
            "material_allocations",
            "customer_orders",
            "purchase_orders",
            "supplier_capacity",
        ):
            self.assertTrue((GENERATED / f"{dataset}.csv").exists())

    def test_scale_rows_do_not_pollute_flagship_cianjur_ground_truth(self):
        result = triage_event(
            event_id="IDN-CIANJUR-2022-USGS-us7000ir9t",
            radius_km=150,
        )
        skus = {row["sku"] for row in result["impacted_products"]}

        self.assertEqual(result["public_facility_count"], 20)
        self.assertEqual(skus, {"JI2993", "JQ6656"})
        self.assertEqual(
            result["commercial_totals"]["commitment_units"],
            16000.0,
        )

    def test_scale_operational_relationships_are_simulated_private(self):
        with connect() as conn:
            bad = conn.execute(
                """
                SELECT COUNT(*)
                FROM (
                  SELECT provenance_class
                  FROM product_facilities
                  WHERE sku LIKE 'DTSKU-%'
                  UNION ALL
                  SELECT provenance_class
                  FROM bom
                  WHERE sku LIKE 'DTSKU-%'
                  UNION ALL
                  SELECT provenance_class
                  FROM material_allocations
                  WHERE sku LIKE 'DTSKU-%'
                  UNION ALL
                  SELECT provenance_class
                  FROM fulfilment_commitments
                  WHERE sku LIKE 'DTSKU-%'
                ) x
                WHERE provenance_class <> 'SIMULATED_PRIVATE'
                """
            ).fetchone()[0]

        self.assertEqual(bad, 0)

    def test_scale_facilities_avoid_flagship_countries(self):
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT country
                FROM facilities
                WHERE facility_id LIKE 'DTF-%'
                ORDER BY country
                """
            ).fetchall()
        countries = {row[0] for row in rows}

        self.assertFalse({"Indonesia", "China", "Vietnam"} & countries)


if __name__ == "__main__":
    unittest.main()
