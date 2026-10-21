import unittest
from datetime import date

from dependency.solver.component_feasibility import evaluate_component_feasibility


class ComponentFeasibilityTests(unittest.TestCase):
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"
    SKU = "JI2993"

    def _by_material(self, result):
        return {row["material_id"]: row for row in result["materials"]}

    def test_inbound_po_counts_only_for_an_explicit_allocated_source(self):
        result = evaluate_component_feasibility(
            scenario_id=self.SCENARIO_ID,
            sku=self.SKU,
            destination_facility_id="ADI26-0226",
            production_units=1000,
            need_by=date(2026, 10, 29),
        )
        by_material = self._by_material(result)

        textile = by_material["MAT-TEXTILE-UPPER"]
        self.assertEqual(textile["eligible_inbound_po_qty"], 6000.0)
        self.assertEqual(textile["status"], "CONFIRMED_COVERED")

        midsole = by_material["MAT-LIGHTSTRIKE-MIDSOLE"]
        self.assertEqual(midsole["eligible_inbound_po_qty"], 0.0)
        self.assertTrue(midsole["purchase_orders"])
        self.assertFalse(
            midsole["purchase_orders"][0]["eligible_explicit_source"]
        )
        self.assertEqual(midsole["status"], "SOURCE_PATH_NOT_MODELED")

    def test_source_lead_time_can_make_a_critical_material_too_late(self):
        result = evaluate_component_feasibility(
            scenario_id=self.SCENARIO_ID,
            sku=self.SKU,
            destination_facility_id="ADI26-0226",
            production_units=1000,
            need_by=date(2026, 10, 24),
        )
        by_material = self._by_material(result)
        outsole = by_material["MAT-RUBBER-OUTSOLE"]

        self.assertEqual(outsole["required_qty"], 1000.0)
        self.assertEqual(outsole["provisional_supply_qty"], 0.0)
        self.assertEqual(outsole["status"], "PROVISIONAL_SHORTAGE")
        self.assertEqual(result["decision"], "INFEASIBLE")
        self.assertIn(
            "MAT-RUBBER-OUTSOLE",
            result["critical_shortage_material_ids"],
        )

    def test_missing_private_source_path_is_unknown_not_fake_shortage(self):
        result = evaluate_component_feasibility(
            scenario_id=self.SCENARIO_ID,
            sku=self.SKU,
            destination_facility_id="ADI26-0240",
            production_units=1000,
            need_by=date(2026, 10, 29),
        )
        self.assertEqual(result["decision"], "INSUFFICIENT_DATA")
        self.assertIn(
            "MAT-LIGHTSTRIKE-MIDSOLE",
            result["critical_unmodeled_material_ids"],
        )
        self.assertIn(
            "MAT-RUBBER-OUTSOLE",
            result["critical_unmodeled_material_ids"],
        )
        self.assertEqual(result["critical_shortage_material_ids"], [])


if __name__ == "__main__":
    unittest.main()
