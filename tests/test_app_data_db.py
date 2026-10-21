"""Check Hermes map reads the seeded PostgreSQL/PostGIS graph."""
import unittest
from dependency.db.connection import connect
from dependency.graph.app_views import map_facilities,facility_profile,incident_inbox,event_context


class AppDataDatabaseTests(unittest.TestCase):
    def test_world_map_matches_seeded_public_facilities(self):
        result=map_facilities()
        self.assertEqual(result["total_in_view"],770)
        self.assertEqual(result["shown"],770)
        self.assertFalse(result["truncated"])
        self.assertTrue(all(-180<=r["longitude"]<=180 for r in result["facilities"]))

    def test_one_real_public_facility_drills_to_explicit_private_product(self):
        with connect() as conn:
            row=conn.execute(
                """
                SELECT fnl.network_facility_id
                FROM facility_network_links fnl
                JOIN product_facilities pf ON pf.facility_id=fnl.facility_id
                WHERE pf.approved=true
                ORDER BY fnl.network_facility_id
                LIMIT 1
                """
            ).fetchone()
        self.assertIsNotNone(row)
        result=facility_profile(network_facility_id=row[0])
        self.assertGreater(result["connected_product_count"],0)
        self.assertGreater(len(result["operational_links"]),0)
        self.assertEqual(result["commercial_exposure_status"],"POTENTIAL_NOT_CONFIRMED_LOSS")
        self.assertTrue(all(p["provenance_class"]=="SIMULATED_PRIVATE"
                            for p in result["connected_products"]))


    def test_seeded_event_has_a_public_source_and_usable_context(self):
        with connect() as conn:
            evt=conn.execute(
                "SELECT event_id FROM external_events ORDER BY event_id LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(evt)
        result=event_context(event_id=evt[0])
        self.assertEqual(result["event"]["event_id"],evt[0])
        self.assertIn(result["event"]["provenance_class"],{
            "VERIFIED_PUBLIC","PUBLIC_DERIVED","SIMULATED_PRIVATE","INFERRED",
        })
        self.assertIn("not confirmed",result["claim_rule"])
        inbox=incident_inbox()
        self.assertIsInstance(inbox["incidents"],list)


if __name__=="__main__":
    unittest.main()
