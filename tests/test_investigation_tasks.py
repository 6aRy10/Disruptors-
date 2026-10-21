"""Investigation planning must use explicit graph paths and reject invented impact."""
import unittest

from dependency.investigation.tasks import propose_investigation_tasks


class InvestigationTaskTests(unittest.TestCase):
    def test_earthquake_creates_supplier_and_material_evidence_requests(self):
        triage = {
            "event": {"event_type": "earthquake"},
            "impacted_products": [{
                "sku": "DYNAMIC-SKU-1", "gross_margin_eur": 400,
                "reasons": [
                    {"path_type": "ASSEMBLY", "facility_id": "DYNAMIC-FACILITY-A"},
                    {"path_type": "UPSTREAM_MATERIAL", "facility_id": "DYNAMIC-FACILITY-B", "material_id": "DYNAMIC-MAT-X"}
                ],
            }],
        }
        tasks = propose_investigation_tasks(triage)
        self.assertEqual(len(tasks), 3)
        self.assertEqual({t["task_type"] for t in tasks}, {
            "CONFIRM_FACILITY_STATUS", "CONFIRM_MATERIAL_SUPPLY",
        })
        self.assertTrue(all(t["connected_margin_eur"] == 400 for t in tasks))

    def test_port_activity_requires_shipment_evidence_not_factory_closure(self):
        triage = {
            "event": {"event_type": "port_activity_anomaly"},
            "impacted_products": [{"sku": "X", "gross_margin_eur": 120,
                "reasons": [{"lane_id": "LANE-ANY-1"}]}],
        }
        tasks = propose_investigation_tasks(triage)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_type"], "CONFIRM_SHIPMENT_STATUS")
        self.assertEqual(tasks[0]["target_id"], "LANE-ANY-1")

    def test_unknown_public_supplier_never_gets_invented_sku(self):
        triage = {
            "event": {"event_type": "wildfire"},
            "impacted_products": [],
            "public_exposure": [{"network_facility_id": "PUBLIC-ONLY-SITE"}],
        }
        tasks = propose_investigation_tasks(triage)
        self.assertEqual(tasks[0]["connected_skus"], [])
        self.assertEqual(tasks[0]["task_type"], "VERIFY_PUBLIC_SUPPLIER_LINK")

    def test_trade_policy_requires_classification_not_fake_duty(self):
        triage = {"event": {"event_type": "tariff_policy"},
                  "impacted_products": [{"sku": "ANY-SKU", "gross_margin_eur": 98, "reasons": []}]}
        tasks = propose_investigation_tasks(triage)
        self.assertEqual(tasks[0]["task_type"], "VERIFY_TARIFF_APPLICABILITY")
        self.assertIn("HS classification", tasks[0]["required_fact"])

    def test_no_business_path_creates_no_fake_operational_task(self):
        triage = {"event": {"event_type": "earthquake"}, "impacted_products": []}
        self.assertEqual(propose_investigation_tasks(triage), [])


if __name__ == "__main__":
    unittest.main()
