"""Hermes map API uses real public identities and explicit private graph links."""
from datetime import date
import unittest
from unittest.mock import patch,MagicMock
from dependency.graph.app_views import map_facilities,facility_profile


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


if __name__=="__main__":
    unittest.main()
