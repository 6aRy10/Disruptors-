"""A dated facility-wide confirmation really changes the database solver input."""
from datetime import timedelta
import unittest

from dependency.db.connection import connect
from dependency.services.demo_reset import reset_demo_state
from dependency.services.facility_capacity import (
    confirm_facility_capacity,confirmed_capacity_for_scenario,
)


class FacilityCapacityDatabaseTests(unittest.TestCase):
    SCENARIO="SCN-CIANJUR-REPLAY-01"

    def setUp(self):
        reset_demo_state()
        with connect() as conn:
            facility=conn.execute(
                """
                SELECT pf.facility_id
                FROM product_facilities pf
                GROUP BY pf.facility_id
                ORDER BY COUNT(DISTINCT pf.sku),pf.facility_id
                LIMIT 1
                """
            ).fetchone()
            day=conn.execute(
                "SELECT as_of FROM scenarios WHERE scenario_id=%s",
                (self.SCENARIO,),
            ).fetchone()
        self.facility=facility[0]
        self.as_of=day[0]
        self.start=self.as_of-timedelta(days=1)
        self.end=self.as_of+timedelta(days=5)

    def tearDown(self):
        with connect() as conn:
            conn.execute(
                "DELETE FROM confirmed_facility_capacity WHERE facility_id=%s AND week_start=%s",
                (self.facility,self.start),
            )
            conn.commit()
        reset_demo_state()

    def confirm(self,units):
        return confirm_facility_capacity(
            facility_id=self.facility,week_start=self.start,
            valid_until=self.end,capacity_units=units,committed_units=10,
            evidence_source="SIMULATED_PRIVATE_TEST_OPERATOR",
            evidence_reference="TEST-FACILITY-CAP-1",
            confirmed_by="CI actor",
        )

    def test_confirmed_cap_persists_and_revisions_bump_state_once(self):
        before=confirmed_capacity_for_scenario(
            scenario_id=self.SCENARIO,facility_ids=[self.facility],
        )
        self.assertNotIn(self.facility,before)
        first=self.confirm(40)
        self.assertEqual(first["status"],"UPDATED")
        self.assertEqual(first["available_capacity_units"],30)
        row=confirmed_capacity_for_scenario(
            scenario_id=self.SCENARIO,facility_ids=[self.facility],
        )
        self.assertEqual(row[self.facility]["available_units"],30)
        repeated=self.confirm(40)
        self.assertEqual(repeated["status"],"UNCHANGED")
        self.assertEqual(repeated["state_version"],first["state_version"])
        changed=self.confirm(25)
        self.assertEqual(changed["state_version"],first["state_version"]+1)
        self.assertEqual(
            confirmed_capacity_for_scenario(
                scenario_id=self.SCENARIO,facility_ids=[self.facility],
            )[self.facility]["available_units"],15,
        )

    def test_invalid_commitment_cannot_overbook_factory(self):
        with self.assertRaises(ValueError):
            confirm_facility_capacity(
                facility_id=self.facility,week_start=self.start,
                valid_until=self.end,capacity_units=15,committed_units=30,
                evidence_source="Test",evidence_reference="X",confirmed_by="Tester",
            )


if __name__=="__main__":
    unittest.main()
