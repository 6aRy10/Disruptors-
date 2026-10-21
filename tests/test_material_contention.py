"""Adversarial material contention across unrelated products in a shared source."""
import unittest
from dependency.solver.material_contention import evaluate_material_contention


class SharedMaterialContentionTests(unittest.TestCase):
    def test_shared_source_does_not_hide_double_booked_material(self):
        moves=[
            {"sku":"A","resource_type":"BACKUP_ASSEMBLY","resource_id":"ASSEMBLY-X","units":60},
            {"sku":"B","resource_type":"BACKUP_ASSEMBLY","resource_id":"ASSEMBLY-Y","units":60},
        ]
        bom=[
            ("A","ASSEMBLY-X","MAT-SHARED","SOURCE-X",2,1,100),
            ("B","ASSEMBLY-Y","MAT-SHARED","SOURCE-X",3,1,100),
        ]
        r=evaluate_material_contention(allocations=moves,source_rows=bom)
        self.assertEqual(r["status"],"MODELED_SHARED_MATERIAL_SHORTFALL")
        self.assertEqual(r["shared_source_count"],1)
        self.assertAlmostEqual(r["modeled_capacity_conflicts"][0]["modeled_shortfall_units"],200)
        self.assertFalse(r["execution_materials_verified"])

    def test_distinct_material_sources_do_not_create_false_conflict(self):
        moves=[
            {"sku":"A","resource_type":"BACKUP_ASSEMBLY","resource_id":"FACTORY","units":20},
            {"sku":"B","resource_type":"BACKUP_ASSEMBLY","resource_id":"FACTORY","units":30},
        ]
        rows=[
            ("A","FACTORY","MAT-SHARED","SOURCE-ONE",2,1,100),
            ("B","FACTORY","MAT-SHARED","SOURCE-TWO",2,1,100),
        ]
        r=evaluate_material_contention(allocations=moves,source_rows=rows)
        self.assertEqual(r["status"],"NO_SHARED_UPSTREAM_CONTENTION")
        self.assertEqual(r["shared_source_count"],0)

    def test_only_new_manufacturing_needs_new_materials(self):
        move=[{"sku":"A","resource_type":"FINISHED_INVENTORY",
               "resource_id":"FINISHED_INVENTORY","units":100}]
        r=evaluate_material_contention(allocations=move,source_rows=[])
        self.assertEqual(r["status"],"NO_BACKUP_PRODUCTION")
        self.assertTrue(r["execution_materials_verified"])

    def test_missing_source_link_never_claims_verified(self):
        move=[{"sku":"A","resource_type":"BACKUP_ASSEMBLY",
               "resource_id":"UNKNOWN-FACTORY","units":20}]
        r=evaluate_material_contention(allocations=move,source_rows=[])
        self.assertEqual(r["status"],"SHARED_MATERIAL_EVIDENCE_REQUIRED")
        self.assertFalse(r["execution_materials_verified"])

    def test_identical_source_not_capacity_proof_even_if_modeled_enough(self):
        move=[
            {"sku":"A","resource_type":"BACKUP_ASSEMBLY","resource_id":"FA","units":5},
            {"sku":"B","resource_type":"BACKUP_ASSEMBLY","resource_id":"FB","units":5},
        ]
        rows=[
            ("A","FA","MAT-X","SUP-X",1,1,1000),
            ("B","FB","MAT-X","SUP-X",1,1,1000),
        ]
        r=evaluate_material_contention(allocations=move,source_rows=rows)
        self.assertEqual(r["status"],"SHARED_MATERIAL_EVIDENCE_REQUIRED")
        self.assertFalse(r["execution_materials_verified"])


if __name__=="__main__":
    unittest.main()
