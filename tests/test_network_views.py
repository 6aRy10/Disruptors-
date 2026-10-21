import unittest

from dependency.graph.dependency_view import product_dependency_graph
from dependency.graph.network import list_network_facilities, network_stats


class NetworkGraphViewTests(unittest.TestCase):
    def test_public_network_stats_match_loaded_2026_dataset(self):
        stats = network_stats()
        self.assertEqual(stats["network_facilities"], 770)
        self.assertEqual(stats["geocoded_facilities"], 770)
        self.assertEqual(stats["official_list_relationships"], 836)
        self.assertGreater(stats["countries"], 20)

    def test_business_link_filter_returns_operationally_mapped_public_nodes(self):
        rows = list_network_facilities(
            business_linked_only=True,
            limit=1000,
        )
        self.assertTrue(rows)
        self.assertTrue(all(row["business_linked"] for row in rows))
        self.assertTrue(
            any(
                "ADI26-0226" in row["operational_facility_ids"]
                for row in rows
            )
        )

    def test_product_graph_reveals_explicit_shared_upstream_sources(self):
        graph = product_dependency_graph("JI2993")
        self.assertEqual(graph["sku"], "JI2993")
        self.assertGreater(graph["summary"]["node_count"], 10)
        self.assertGreaterEqual(
            graph["summary"]["shared_upstream_source_count"],
            3,
        )

        shared_ids = {
            row["source_facility_id"]
            for row in graph["shared_upstream_sources"]
        }
        self.assertTrue(
            {"ADI26-0751", "ADI26-0754", "ADI26-0758"}.issubset(shared_ids)
        )

        edge_types = {edge["edge_type"] for edge in graph["edges"]}
        self.assertIn("BOM", edge_types)
        self.assertIn("SUPPLIES_MATERIAL", edge_types)
        self.assertIn("MATERIAL_FLOW_TO_ASSEMBLY", edge_types)
        self.assertIn("FULFILLS_COMMITMENT", edge_types)


if __name__ == "__main__":
    unittest.main()
