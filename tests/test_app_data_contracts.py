"""Hermes map API uses real public identities and explicit private graph links."""
from datetime import date
import unittest
from unittest.mock import patch,MagicMock
from dependency.graph.app_views import map_facilities,facility_profile,incident_inbox,event_context,map_hazard_reports


class AppDataContracts(unittest.TestCase):
    def test_invalid_latitudes_and_nonfinite_values(self):
        for bounds in [
            {"west":-180,"south":80,"east":180,"north":30},
            {"west":-185,"south":-20,"east":180,"north":40},
            {"west":float("nan"),"south":-85,"east":180,"north":85},
        ]:
            with self.assertRaises(ValueError):
                map_facilities(**bounds)

    @patch("dependency.graph.app_views.connect")
    def test_dateline_bounds_and_public_private_provenance(self,connect):
        conn=MagicMock()
        conn.execute.return_value.fetchall.return_value=[
            ("PUBLIC-1","Real name","Indonesia","City","Tier 1",-6.5,112.0,
             "PUBLIC_DERIVED","VERIFIED_PUBLIC","https://example.invalid",
             ["PRIVATE-A"],1),
        ]
        connect.return_value.__enter__.return_value=conn
        result=map_facilities(west=170,east=-170,south=-20,north=20)
        self.assertEqual(result["total_in_view"],1)
        self.assertEqual(result["facilities"][0]["identity_provenance"],"VERIFIED_PUBLIC")
        self.assertEqual(result["facilities"][0]["operational_link_provenance"],
                         "SIMULATED_PRIVATE")
        self.assertEqual(conn.execute.call_args.args[1][2:4],(170,-170))
        self.assertFalse(result["truncated"])

    @patch("dependency.graph.app_views.connect")
    def test_private_commercial_totals_never_claim_loss(self,connect):
        conn=MagicMock()
        conn.execute.side_effect=[
            MagicMock(fetchone=lambda:(
                "PUBLIC-1","Known site","Indonesia","City","Province","Tier 1",
                "Footwear",-6.5,112.0,"PUBLIC_DERIVED","VERIFIED_PUBLIC",
                "https://example.invalid",None,
            )),
            MagicMock(fetchall=lambda:[(
                "FAC-1","Simulated plant","Indonesia","Tier 1","PUBLIC_LINK",
                0.95,"PUBLIC_DERIVED",
            )]),
            MagicMock(fetchall=lambda:[(
                "SKU-1",["UPSTREAM_MATERIAL"],"Private product","Footwear",
                6000,360000,1,360000,
            )]),
        ]
        connect.return_value.__enter__.return_value=conn
        result=facility_profile(network_facility_id="PUBLIC-1")
        self.assertEqual(result["commercial_exposure_status"],"POTENTIAL_NOT_CONFIRMED_LOSS")
        self.assertEqual(result["connected_products"][0]["relations"],["UPSTREAM_MATERIAL"])
        self.assertEqual(result["total_connected_revenue_eur"],360000)
        self.assertEqual(result["operational_links"][0]["provenance_class"],"PUBLIC_DERIVED")


    @patch("dependency.graph.app_views.connect")
    def test_inbox_prioritizes_real_open_evidence_work(self,connect):
        conn=MagicMock()
        from datetime import UTC,datetime
        now=datetime.now(UTC)
        conn.execute.return_value.fetchall.return_value=[
            ("INC-1","GDACS-1","INVESTIGATING",None,now,"Wildfire",
             "wildfire","LIVE","GDACS",2,1),
        ]
        connect.return_value.__enter__.return_value=conn
        inbox=incident_inbox()
        self.assertEqual(inbox["incidents"][0]["open_evidence_tasks"],2)
        self.assertEqual(inbox["incidents"][0]["product_linked_evidence_tasks"],1)
        self.assertIn("jsonb_array_length(t.connected_skus)>0", conn.execute.call_args.args[0])
        self.assertEqual(inbox["incidents"][0]["mode"],"LIVE")
        self.assertIn("not proof",inbox["truth_rule"])


    @patch("dependency.graph.app_views.connect")
    def test_event_context_preserves_exposure_uncertainty(self,connect):
        conn=MagicMock()
        from datetime import datetime,UTC
        now=datetime.now(UTC)
        conn.execute.side_effect=[
            MagicMock(fetchone=lambda:("GDACS-ANY","wildfire","GDACS","LIVE",
                  "Wildfire",now,"https://example.invalid","VERIFIED_PUBLIC",-7.0,112.0)),
            MagicMock(fetchone=lambda:("INC-ANY","INVESTIGATING",None)),
            MagicMock(fetchall=lambda:[("TASK-ANY","CONFIRM_FACILITY_STATUS",
               "facility","FAC-ANY","Confirm status",["SKU-ANY"])]),
        ]
        connect.return_value.__enter__.return_value=conn
        result=event_context(event_id="GDACS-ANY")
        self.assertEqual(result["event"]["latitude"],-7.0)
        self.assertEqual(result["evidence_tasks"][0]["target_id"],"FAC-ANY")
        self.assertIsNone(result["incident"]["scenario_id"])
        self.assertIn("not confirmed",result["claim_rule"])


    @patch("dependency.graph.app_views.connect")
    def test_report_map_preserves_real_point_and_date(self,connect):
        from datetime import datetime,timezone
        now=datetime.now(timezone.utc)
        db=MagicMock()
        db.execute.return_value.fetchall.return_value=[(
            "GDACS-DYNAMIC","wildfire","GDACS","Forest fires in Indonesia",
            "LIVE",now,"https://example.invalid","VERIFIED_PUBLIC",
            '{"type":"Point","coordinates":[112.0,-7.0]}',112.0,-7.0,
        )]
        connect.return_value.__enter__.return_value=db
        result=map_hazard_reports(days=30)
        self.assertEqual(result["shown"],1)
        self.assertEqual(result["features"][0]["geometry"]["type"],"Point")
        self.assertEqual(result["features"][0]["properties"]["event_id"],"GDACS-DYNAMIC")
        self.assertIn("no invented hazard radius",result["geometry_rule"])

    def test_report_map_rejects_unbounded_queries(self):
        with self.assertRaises(ValueError):
            map_hazard_reports(limit=100000)
        with self.assertRaises(ValueError):
            map_hazard_reports(days=0)


if __name__=="__main__":
    unittest.main()
