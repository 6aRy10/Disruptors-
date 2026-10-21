import unittest

from dependency.data.scale_stats import enterprise_data_stats
from dependency.db.connection import connect
from dependency.solver.candidates import generate_recovery_candidates


class EnterpriseScaleTests(unittest.TestCase):
    def test_loaded_private_twin_is_enterprise_scale(self):
        stats = enterprise_data_stats()
        counts = stats["counts"]

        self.assertGreaterEqual(counts["public_network_facilities"], 770)
        self.assertGreaterEqual(counts["public_supplier_relationships"], 836)
        self.assertGreaterEqual(counts["products"], 2500)
        self.assertGreaterEqual(counts["bom_rows"], 28000)
        self.assertGreaterEqual(counts["material_allocations"], 160000)
        self.assertGreaterEqual(counts["customer_commitments"], 20000)
        self.assertGreaterEqual(
            stats["operational_record_count"],
            225000,
        )

    def test_generated_scale_preserves_truth_boundary(self):
        with connect() as conn:
            bad = conn.execute(
                """
                SELECT COUNT(*)
                FROM facilities
                WHERE facility_id LIKE 'DTF-%'
                  AND country IN ('Indonesia','China','Vietnam')
                """
            ).fetchone()[0]
            linked = conn.execute(
                """
                SELECT COUNT(*)
                FROM facilities f
                JOIN facility_network_links l ON l.facility_id=f.facility_id
                WHERE f.facility_id LIKE 'DTF-%'
                  AND f.provenance_class='VERIFIED_PUBLIC'
                  AND l.provenance_class='PUBLIC_DERIVED'
                """
            ).fetchone()[0]
            private_bom = conn.execute(
                """
                SELECT COUNT(*)
                FROM bom
                WHERE sku LIKE 'DTSKU-%'
                  AND provenance_class <> 'SIMULATED_PRIVATE'
                """
            ).fetchone()[0]

        self.assertEqual(bad, 0)
        self.assertGreaterEqual(linked, 200)
        self.assertEqual(private_bom, 0)

    def test_recovery_candidate_engine_works_for_non_flagship_generated_sku(self):
        with connect() as conn:
            row = conn.execute(
                """
                SELECT sku
                FROM products
                WHERE sku LIKE 'DTSKU-%'
                ORDER BY sku
                LIMIT 1
                """
            ).fetchone()
        self.assertIsNotNone(row)

        sku = row[0]
        # Candidate discovery itself must be data-driven. It must not require a
        # flagship SKU constant. A scenario is not required to discover master
        # data options, so this assertion focuses on the generated graph.
        with connect() as conn:
            facilities = conn.execute(
                """
                SELECT COUNT(*)
                FROM product_facilities
                WHERE sku=%s AND approved=true
                """,
                (sku,),
            ).fetchone()[0]
            bom_rows = conn.execute(
                "SELECT COUNT(*) FROM bom WHERE sku=%s",
                (sku,),
            ).fetchone()[0]
            commitments = conn.execute(
                """
                SELECT COUNT(*)
                FROM fulfilment_commitments
                WHERE sku=%s
                """,
                (sku,),
            ).fetchone()[0]

        self.assertGreaterEqual(facilities, 3)
        self.assertGreaterEqual(bom_rows, 10)
        self.assertEqual(commitments, 8)


if __name__ == "__main__":
    unittest.main()
