"""No synthetic cyclone shutdowns; real DB numbers drive Think charts."""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime,timezone
from dependency.notifications.cyclone_alerts import build_cyclone_message, notify_pending_cyclones
from dependency.assistant.grounded_analytics import grounded_think

class CycloneAlertsTest(unittest.TestCase):
    def test_message_explains_unknowns_and_quantifies_modeled_exposure(self):
        event={"event_id":"GDACS-TC-123","title":"Typhoon reported near coast",
               "occurred_at":"2026-10-22T10:00Z","source":"GDACS",
               "source_url":"https://www.gdacs.org/"}
        impact={"products":[{"sku":"SKU-1"}],
                "facilities":[{"facility_id":"FAC-1","name":"Factory A"}],
                "totals":{"commitment_units":350,"revenue_eur":72000}}
        message=build_cyclone_message(event,impact)
        self.assertIn("GDACS-TC-123",message["text"])
        self.assertIn("350",message["text"])
        self.assertIn("72,000",message["text"])
        self.assertIn("not a confirmed factory closure",message["text"])
        self.assertIn("available capacity",message["text"])
        self.assertNotIn("factory shut down",message["text"].lower())

    @patch("dependency.notifications.cyclone_alerts.pending_cyclone_events")
    @patch("dependency.notifications.cyclone_alerts.send_webhook")
    def test_no_webhook_outbound_by_default(self,send,pending):
        with patch.dict("os.environ",{"DEPENDENCY_ALLOW_EXTERNAL_MESSAGES":"0"}):
            result=notify_pending_cyclones()
        self.assertEqual(result["status"],"DISABLED")
        pending.assert_not_called()
        send.assert_not_called()

class GroundedThinkTest(unittest.TestCase):
    @patch("dependency.assistant.grounded_analytics.product_dependency_graph")
    @patch("dependency.assistant.grounded_analytics.answer_expeditor")
    def test_sku_charts_aggregate_stored_orders_and_exact_routes(self,answer,graph):
        answer.return_value={"answer":"Stored commitments.", "sources":[],
                             "mode":"DETERMINISTIC_READ_ONLY","sku":"ABC"}
        graph.return_value={
            "summary":{"material_count":2,"commitment_count":3},
            "nodes":[
                {"node_type":"CUSTOMER_COMMITMENT","commitment_id":"C1",
                 "label":"EU", "market":"EU","qty":50,"due_date":"2026-11-04"},
                {"node_type":"CUSTOMER_COMMITMENT","commitment_id":"C2",
                 "label":"EU2","market":"EU","qty":75,"due_date":"2026-11-08"},
                {"node_type":"CUSTOMER_COMMITMENT","commitment_id":"C3",
                 "label":"US","market":"US","qty":100,"due_date":"2026-11-09"},
            ],
            "allocation_routes":[{
                "source_facility_name":"S1","material_name":"M1",
                "destination_facility_name":"F1","material_id":"M1",
                "source_facility_id":"S1","destination_facility_id":"F1",
                "allocation_share":0.8,
            }]
        }
        result=grounded_think(question="Which orders are at risk?",sku="ABC")
        self.assertEqual(result["visualization_count"],2)
        markets=result["visualizations"][0]["data"]
        self.assertEqual({x["label"]:x["value"] for x in markets},{"EU":125,"US":100})
        self.assertEqual(result["visualizations"][1]["data"][0]["destination"],"F1")
        self.assertIn("NOT",result["visualizations"][0]["limitation"])
        self.assertEqual(result["mode"],"DETERMINISTIC_READ_ONLY")

    @patch("dependency.assistant.grounded_analytics.trace_business_event_impact")
    @patch("dependency.assistant.grounded_analytics.event_context")
    @patch("dependency.assistant.grounded_analytics.answer_expeditor")
    def test_event_chart_never_labels_connected_revenue_as_loss(self,answer,event,impact):
        answer.return_value={"answer":"Public cyclone report","sources":[],"mode":"DETERMINISTIC_READ_ONLY"}
        event.return_value={"event":{"event_id":"CY-1","title":"Cyclone",
            "source":"GDACS","occurred_at":"2026-10-22","provenance_class":"VERIFIED_PUBLIC"},
            "evidence_tasks":[{"task_id":"T1","required_fact":"Capacity?"}]}
        impact.return_value={"totals":{"products_impacted":1,"commitment_units":25,
                           "revenue_eur":1600},
                           "products":[{"sku":"SK-1","commitment_units":25}]}
        value=grounded_think(question="What happened?",event_id="CY-1")
        self.assertEqual(value["visualizations"][0]["data"][0]["value"],25)
        self.assertEqual(value["visualizations"][0]["limitation"],
                         "Model-connected demand, NOT confirmed lost production.")
        self.assertEqual(value["metrics"][0]["value"],1)
        self.assertEqual(value["evidence"][1]["id"],"T1")

if __name__=="__main__":
    unittest.main()
