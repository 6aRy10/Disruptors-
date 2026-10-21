"""Evidence-gap outreach drafts cannot silently become supplier communication."""
import unittest
from dependency.investigation.outreach import build_evidence_question


class OutreachDraftTests(unittest.TestCase):
    def test_unknown_event_and_facility_generate_a_question_not_damage_claim(self):
        message=build_evidence_question(
            task_type="CONFIRM_FACILITY_STATUS",target_id="FACTORY-UNKNOWN-92",
            required_fact="Confirm operating status and capacity.",
            event_id="DYNAMIC-EVENT-77",event_title="Public hazard near candidate supplier",
            skus=["SKU-DYN-1"],
        )
        self.assertIn("DYNAMIC-EVENT-77",message)
        self.assertIn("FACTORY-UNKNOWN-92",message)
        self.assertIn("SKU-DYN-1",message)
        self.assertIn("does not prove",message)
        self.assertNotIn("your factory is closed",message.lower())

    def test_missing_fact_is_rejected(self):
        with self.assertRaises(ValueError):
            build_evidence_question(
                task_type="CONFIRM_MATERIAL_SUPPLY",target_id="FAC:MAT",
                required_fact=" ",event_id="E",event_title="Event",skus=[],
            )


if __name__=="__main__":
    unittest.main()
