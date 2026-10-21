import unittest

from dependency.db.connection import connect
from dependency.graph.exposure import facilities_within_radius
from dependency.graph.shared_dependencies import backup_independence


class PublicNetworkTests(unittest.TestCase):
    def test_full_public_network_loaded(self):
        with connect() as conn:
            facilities = conn.execute("SELECT COUNT(*) FROM network_facilities").fetchone()[0]
            relationships = conn.execute(
                "SELECT COUNT(*) FROM network_facility_relationships"
            ).fetchone()[0]
            geocoded = conn.execute(
                "SELECT COUNT(*) FROM network_facilities WHERE geom IS NOT NULL"
            ).fetchone()[0]

        self.assertEqual(facilities, 770)
        self.assertEqual(relationships, 836)
        self.assertEqual(geocoded, 770)

    def test_cianjur_full_network_exposure(self):
        within_50 = facilities_within_radius(
            latitude=-6.836,
            longitude=106.997,
            radius_km=50,
        )
        within_150 = facilities_within_radius(
            latitude=-6.836,
            longitude=106.997,
            radius_km=150,
        )
        self.assertEqual(len(within_50), 4)
        self.assertEqual(len(within_150), 20)
        self.assertTrue(all(r["exposure_status"] == "POTENTIALLY_EXPOSED" for r in within_150))

    def test_nominal_backup_has_hidden_shared_sources(self):
        result = backup_independence(
            sku="JI2993",
            primary_facility_id="ADI26-0226",
            backup_facility_id="ADI26-0225",
        )
        self.assertFalse(result["independent"])
        self.assertEqual(result["shared_dependency_count"], 3)
        self.assertEqual(result["decision"], "REJECT_CORRELATED_BACKUP")

    def test_independent_backup_does_not_share_seeded_material_sources(self):
        result = backup_independence(
            sku="JI2993",
            primary_facility_id="ADI26-0226",
            backup_facility_id="ADI26-0240",
        )
        self.assertTrue(result["independent"])
        self.assertEqual(result["shared_dependency_count"], 0)


if __name__ == "__main__":
    unittest.main()
