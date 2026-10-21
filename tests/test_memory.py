import unittest

from dependency.memory.service import (
    close_incident,
    ensure_incident,
    get_incident_memory,
    record_agent_run,
    record_decision,
    record_evidence,
    save_plan_snapshot,
    similar_incidents,
)
from dependency.services.demo_reset import reset_demo_state


class IncidentMemoryTests(unittest.TestCase):
    EVENT_ID = "IDN-CIANJUR-2022-USGS-us7000ir9t"
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"

    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def test_seed_memory_is_explicitly_simulated_private_and_ranked(self):
        rows = similar_incidents(
            event_type="earthquake",
            event_id=self.EVENT_ID,
            limit=10,
        )
        seeded = next(
            row for row in rows
            if row["incident_id"] == "MEM-CIANJUR-PRIOR-01"
        )
        self.assertEqual(seeded["similarity_score"], 100)
        self.assertEqual(
            seeded["similarity_reason"],
            "SAME_EXTERNAL_EVENT_PRIOR_RUN",
        )
        self.assertEqual(
            seeded["provenance_class"],
            "SIMULATED_PRIVATE",
        )
        self.assertEqual(
            seeded["usage_rule"],
            "HYPOTHESIS_ONLY_RECHECK_CURRENT_STATE",
        )

    def test_operational_memory_lifecycle(self):
        incident = ensure_incident(
            event_id=self.EVENT_ID,
            scenario_id=self.SCENARIO_ID,
            summary="CI memory contract test",
            initial_assessment="Potential exposure only.",
        )
        incident_id = incident["incident_id"]

        record_evidence(
            incident_id=incident_id,
            evidence_type="PUBLIC_EVENT",
            fact={"event_id": self.EVENT_ID, "exposure_status": "POTENTIAL_ONLY"},
            provenance_class="VERIFIED_PUBLIC",
            source_name="USGS",
            confidence=100,
        )

        run = record_agent_run(
            incident_id=incident_id,
            agent_name="Signal Investigator",
            model="test-model",
            output_text="Potential exposure; shutdown not confirmed.",
            tool_trace=[{"tool": "get_event"}],
            state_version=1,
        )
        self.assertTrue(run["run_id"].startswith("ARUN-"))

        plan = save_plan_snapshot(
            incident_id=incident_id,
            state_version=1,
            sku="JI2993",
            plan={
                "plan_id": "TEST-PLAN",
                "decision": "REJECTED",
                "reasons": ["TEST_REASON"],
                "evidence": {"shortage_units": 400},
            },
        )

        decision = record_decision(
            incident_id=incident_id,
            plan_record_id=plan["plan_record_id"],
            action="REJECT_PLAN",
            approved_by="CI_TEST",
            reason="Deterministic guardrail.",
        )
        self.assertTrue(decision["decision_id"].startswith("DEC-"))

        close_incident(
            incident_id=incident_id,
            actual_supplier_delay_days=1,
            actual_shortage_units=400,
            actual_cost_eur=1000,
            customer_impact={"late_units": 400},
            success=False,
            lesson="Recheck stale backup capacity before declaring feasibility.",
        )

        memory = get_incident_memory(incident_id)
        self.assertEqual(memory["incident"]["status"], "CLOSED")
        self.assertEqual(len(memory["evidence"]), 1)
        self.assertEqual(len(memory["plans"]), 1)
        self.assertEqual(len(memory["decisions"]), 1)
        self.assertEqual(len(memory["agent_runs"]), 1)
        self.assertEqual(memory["outcome"]["actual_shortage_units"], 400.0)

        similar = similar_incidents(event_type="earthquake", limit=10)
        self.assertTrue(any(x["incident_id"] == incident_id for x in similar))
        self.assertTrue(
            all(
                x["usage_rule"] == "HYPOTHESIS_ONLY_RECHECK_CURRENT_STATE"
                for x in similar
            )
        )


if __name__ == "__main__":
    unittest.main()
