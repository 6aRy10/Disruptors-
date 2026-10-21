import unittest

from dependency.db.connection import connect


class EnterpriseScaleIndexTests(unittest.TestCase):
    REQUIRED_INDEXES = {
        "facility_network_links_network_idx",
        "network_facility_relationships_facility_idx",
        "product_facilities_facility_idx",
        "bom_material_idx",
        "material_sources_facility_idx",
        "material_allocations_source_idx",
        "material_allocations_destination_idx",
        "material_allocations_sku_idx",
        "inventory_item_idx",
        "supplier_capacity_sku_idx",
        "production_orders_sku_facility_idx",
        "fulfilment_commitments_sku_due_idx",
        "purchase_orders_material_eta_idx",
        "transport_lanes_origin_market_idx",
        "transport_lanes_port_idx",
        "scenario_facility_state_facility_idx",
    }

    def test_large_graph_query_indexes_exist(self):
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname='public'
                """
            ).fetchall()
        names = {row[0] for row in rows}
        missing = sorted(self.REQUIRED_INDEXES - names)
        self.assertEqual(
            missing,
            [],
            "Missing indexes required for the enterprise-scale graph: "
            + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
