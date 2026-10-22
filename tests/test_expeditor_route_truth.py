"""Route-safe expeditor: a shared material is not a free supplier-to-factory lane."""
import unittest
from unittest.mock import patch
from dependency.assistant.expeditor import answer_expeditor

def graph():
    return {
        "sku":"SKU-X",
        "summary":{"material_count":1,"assembly_facility_count":2,"commitment_count":1},
        "nodes":[
            {"id":"facility:SUPPLIER-A","node_type":"UPSTREAM_FACILITY",
             "label":"Textile Source A","facility_id":"SUPPLIER-A"},
            {"id":"facility:SUPPLIER-B","node_type":"UPSTREAM_FACILITY",
             "label":"Textile Source B","facility_id":"SUPPLIER-B"},
            {"id":"material:M","node_type":"MATERIAL","label":"Textile M",
             "material_id":"M"},
            {"id":"facility:FACTORY-A","node_type":"ASSEMBLY_FACILITY","label":"Assembly A",
             "facility_id":"FACTORY-A"},
            {"id":"facility:FACTORY-B","node_type":"ASSEMBLY_FACILITY","label":"Assembly B",
             "facility_id":"FACTORY-B"},
            {"id":"product:SKU-X","node_type":"PRODUCT","label":"Product X"},
            {"id":"commitment:ORDER-1","node_type":"CUSTOMER_COMMITMENT","label":"EU Order",
             "commitment_id":"ORDER-1","qty":100},
        ],
        "edges":[
            {"id":"E1","source":"facility:SUPPLIER-A","target":"material:M"},
            {"id":"E2","source":"facility:SUPPLIER-B","target":"material:M"},
            {"id":"E3","source":"material:M","target":"facility:FACTORY-A"},
            {"id":"E4","source":"material:M","target":"facility:FACTORY-B"},
            {"id":"E5","source":"facility:FACTORY-A","target":"product:SKU-X"},
            {"id":"E6","source":"facility:FACTORY-B","target":"product:SKU-X"},
            {"id":"E7","source":"product:SKU-X","target":"commitment:ORDER-1"},
        ],
        "shared_upstream_sources":[],
        "allocation_routes":[
            {"source_facility_id":"SUPPLIER-A","source_facility_name":"Textile Source A",
             "material_id":"M","material_name":"Textile M",
             "destination_facility_id":"FACTORY-A","destination_facility_name":"Assembly A",
             "allocation_share":1.0,"sku":"SKU-X"},
            {"source_facility_id":"SUPPLIER-B","source_facility_name":"Textile Source B",
             "material_id":"M","material_name":"Textile M",
             "destination_facility_id":"FACTORY-B","destination_facility_name":"Assembly B",
             "allocation_share":1.0,"sku":"SKU-X"},
        ],
    }


class SupplierRouteTruthTests(unittest.TestCase):
    @patch("dependency.assistant.expeditor.product_dependency_graph", side_effect=lambda sku: graph())
    @patch.dict("os.environ", {"DEPENDENCY_EXPEDITOR_MODEL":"0"})
    def test_shared_material_does_not_invent_cross_factory_route(self, _graph):
        response = answer_expeditor(
            question="Which customer orders depend on this supplier?",
            sku="SKU-X", object_id="facility:SUPPLIER-A")
        answer=response["answer"]
        self.assertIn("Textile Source A -> Textile M -> Assembly A",answer)
        self.assertNotIn("Textile Source A -> Textile M -> Assembly B",answer)
        self.assertIn("NOT assigned to this supplier or destination",answer)
        self.assertIn("ORDER-1",answer)
        self.assertIn("do not establish which supplier actually supplies each customer order",answer)
        self.assertTrue(response["read_only"])

    @patch("dependency.assistant.expeditor.product_dependency_graph", side_effect=lambda sku: graph())
    @patch.dict("os.environ", {"DEPENDENCY_EXPEDITOR_MODEL":"0"})
    def test_material_lists_real_distinct_destinations(self, _graph):
        response = answer_expeditor(question="Which factories need this material?",
            sku="SKU-X", object_id="material:M")
        answer=response["answer"]
        self.assertIn("Textile Source A -> Textile M -> Assembly A",answer)
        self.assertIn("Textile Source B -> Textile M -> Assembly B",answer)
        self.assertNotIn("Textile Source B -> Textile M -> Assembly A",answer)


if __name__=="__main__":
    unittest.main()
