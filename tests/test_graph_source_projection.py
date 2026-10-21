"""Graph overview groups duplicate-looking supply arrows without losing routes."""
import unittest
from unittest.mock import patch
from dependency.graph.dependency_view import product_dependency_graph


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def fetchall(self):
        return self.rows


class FakeConnection:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, params):
        if "FROM products" in sql:
            return FakeCursor([("SKU-X", "Demo shoe", "FOOTWEAR", "SIMULATED_PRIVATE", None)])
        if "FROM bom" in sql:
            return FakeCursor([("M1", "Textile upper", "critical", 2.0, "SIMULATED_PRIVATE")])
        if "FROM product_facilities" in sql:
            return FakeCursor([
                ("FA", "Assembly A", "Indonesia", "T1", "primary_assembly", True, 0, "SIMULATED_PRIVATE"),
                ("FB", "Assembly B", "Indonesia", "T1", "backup_assembly", True, 2, "SIMULATED_PRIVATE"),
            ])
        if "FROM material_allocations" in sql:
            return FakeCursor([
                ("M1","SOURCE","Textile Supplier","Indonesia","T2","FA","Assembly A",0.35,"SIMULATED_PRIVATE"),
                ("M1","SOURCE","Textile Supplier","Indonesia","T2","FB","Assembly B",0.65,"SIMULATED_PRIVATE"),
            ])
        if "FROM fulfilment_commitments" in sql:
            return FakeCursor([])
        raise AssertionError("Unexpected query: " + sql[:120])


class GraphSourceProjectionTests(unittest.TestCase):
    @patch("dependency.graph.dependency_view.connect", side_effect=lambda: FakeConnection())
    def test_two_destination_routes_one_visible_supply_edge(self, _connect):
        graph = product_dependency_graph("SKU-X")
        supply = [e for e in graph["edges"] if e["edge_type"] == "SUPPLIES_MATERIAL"]
        self.assertEqual(len(supply), 1)
        item = supply[0]
        self.assertEqual(item["id"], "source:SOURCE:M1:SKU-X")
        self.assertEqual(item["source"], "facility:SOURCE")
        self.assertEqual(item["target"], "material:M1")
        self.assertEqual(item["allocation_count"], 2)
        self.assertEqual(item["destination_count"], 2)
        self.assertEqual(item["route_label"], "2 routes")
        self.assertEqual(
            {r["destination_facility_id"]: r["allocation_share"]
             for r in item["allocation_paths"]},
            {"FA":0.35,"FB":0.65},
        )
        self.assertEqual(
            len([e for e in graph["edges"] if e["edge_type"] == "MATERIAL_FLOW_TO_ASSEMBLY"]), 2
        )
        self.assertEqual(graph["summary"]["explicit_allocation_count"], 2)
        self.assertEqual(graph["summary"]["supplier_material_overview_edge_count"], 1)
        self.assertEqual(len(graph["edges"]), len({e["id"] for e in graph["edges"]}))

    @patch("dependency.graph.dependency_view.connect", side_effect=lambda: FakeConnection())
    def test_shared_source_analysis_remains_intact(self, _connect):
        graph=product_dependency_graph("SKU-X")
        self.assertEqual(len(graph["shared_upstream_sources"]), 1)
        entry=graph["shared_upstream_sources"][0]
        self.assertEqual(entry["source_facility_id"],"SOURCE")
        self.assertEqual(entry["destination_facility_ids"],["FA","FB"])


if __name__ == "__main__":
    unittest.main()
