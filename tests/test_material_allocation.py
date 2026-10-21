"""Shared-material allocation adversarial cases. No database required."""
import unittest
from dependency.solver.material_allocation import allocate_shared_materials


def allocation(sku, qty, priority=1, kind="BACKUP_ASSEMBLY", facility="F", margin=20):
    return {"sku":sku,"order_id":sku+"-ORDER","resource_id":facility,
            "resource_type":kind,"units":qty,"priority":priority,
            "unit_margin_eur":margin,"transport_cost_eur_per_unit":1}


class MaterialCapacityTests(unittest.TestCase):
    def solve(self, moves, rows, bom):
        return allocate_shared_materials(allocations=moves,source_rows=rows,bom_rows=bom)

    def test_shared_source_is_spent_once_across_products(self):
        result=self.solve(
            [allocation("B",80,2),allocation("A",80,1)],
            [("A","F","M","SOURCE",1,1,100),("B","F","M","SOURCE",1,1,100)],
            [("A","M",1),("B","M",1)])
        self.assertEqual(result["material_feasible_units"],100)
        self.assertEqual(result["material_reduced_units"],60)
        self.assertEqual(result["protected_by_sku_after_materials"],{"A":80,"B":20})
        self.assertFalse(result["execution_materials_verified"])

    def test_every_bom_input_is_limited(self):
        result=self.solve([allocation("A",10)],
            [("A","F","M1","X",2,1,10),("A","F","M2","Y",3,1,30)],
            [("A","M1",2),("A","M2",3)])
        self.assertEqual(result["material_feasible_units"],5)
        self.assertEqual(sum(x["allocated_material_units"] for x in result["modeled_source_usage"]),25)

    def test_missing_material_is_not_free(self):
        result=self.solve([allocation("A",10)],
            [("A","F","M1","X",1,1,20)],
            [("A","M1",1),("A","M2",1)])
        self.assertEqual(result["material_feasible_units"],0)
        self.assertEqual(result["status"],"INCOMPLETE_MATERIAL_ROUTE")

    def test_unknown_capacity_does_not_prove_feasibility(self):
        result=self.solve([allocation("A",8)],
            [("A","F","M","X",1,1,None)], [("A","M",1)])
        self.assertEqual(result["material_feasible_units"],8)
        self.assertEqual(result["status"],"MODELED_CAPACITY_UNKNOWN")
        self.assertFalse(result["execution_materials_verified"])

    def test_existing_inventory_not_double_charged(self):
        result=self.solve([allocation("A",8,kind="FINISHED_INVENTORY"),
                           allocation("B",15)],
            [("B","F","M","X",1,1,5)], [("B","M",1)])
        self.assertEqual(result["material_feasible_units"],13)

    def test_two_suppliers_have_independent_capacity(self):
        result=self.solve([allocation("A",5),allocation("B",5)],
            [("A","F","M","X",1,1,5),("B","F","M","Y",1,1,5)],
            [("A","M",1),("B","M",1)])
        self.assertEqual(result["material_feasible_units"],10)

    def test_duplicate_source_edge_not_charged_twice(self):
        rows=[("A","F","M","X",1,1,5)]*2
        result=self.solve([allocation("A",10)],rows,[("A","M",1)])
        self.assertEqual(result["material_feasible_units"],5)
        self.assertEqual(len(result["modeled_source_usage"]),1)

    def test_unsafe_share_rejected(self):
        with self.assertRaises(ValueError):
            self.solve([allocation("A",3)],[("A","F","M","X",1,1.5,10)],[("A","M",1)])

    def test_margin_breaks_equal_priority_tie(self):
        result=self.solve([allocation("A",8,margin=2),allocation("B",8,margin=40)],
            [("A","F","M","X",1,1,10),("B","F","M","X",1,1,10)],
            [("A","M",1),("B","M",1)])
        self.assertEqual(result["protected_by_sku_after_materials"],{"A":2,"B":8})

    def test_nonbackup_needs_no_new_material(self):
        result=self.solve([allocation("A",12,kind="CURRENT_PRODUCTION")],[],[])
        self.assertEqual(result["material_feasible_units"],12)
        self.assertTrue(result["execution_materials_verified"])


if __name__ == "__main__":
    unittest.main()
