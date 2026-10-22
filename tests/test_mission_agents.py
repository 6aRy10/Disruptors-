"""Mission specialist safety and selection gates. No model API calls."""
import os
import unittest
from unittest.mock import patch

from dependency.assistant.mission_agents import (
    READ_ONLY_TOOLS, SIGNAL, EVIDENCE, IMPACT, CHALLENGER,
    choose_specialists, run_supervised_agents,
)


def baseline(*, sku="SKU-X", scenario="SCN-1", status="BACKUP_CHALLENGED"):
    return {
        "event_id": "EVENT-1", "sku": sku, "scenario_id": scenario,
        "decision_gate": {
            "status": status, "issues": ["CORRELATED_BACKUP"],
            "execution_allowed": False,
        },
    }


class MissionSpecialistTests(unittest.TestCase):
    def test_exact_tool_allowlists_have_no_side_effects(self):
        agents = [SIGNAL, EVIDENCE, IMPACT, CHALLENGER]
        for agent in agents:
            self.assertTrue(set(agent.tool_names) <= READ_ONLY_TOOLS)
            for blocked in (
                "prepare_investigation_outreach",
                "request_supplier_capacity_confirmation",
                "request_human_approval",
                "dispatch_confirmation_request",
                "confirm_supplier_reply",
            ):
                self.assertNotIn(blocked, agent.tool_names)

    def test_selection_depends_on_evidence_not_round_robin(self):
        self.assertEqual(
            [a.name for a in choose_specialists(baseline())],
            ["Signal Investigator", "Impact Investigator", "Recovery Challenger"],
        )
        self.assertEqual(
            [a.name for a in choose_specialists(baseline(scenario=None))],
            ["Signal Investigator", "Impact Investigator", "Evidence Investigator"],
        )
        self.assertEqual(
            [a.name for a in choose_specialists(baseline(sku=None, scenario=None))],
            ["Signal Investigator", "Evidence Investigator"],
        )
        self.assertEqual(
            choose_specialists(baseline(status="INCOMPLETE_TOOL_ERROR")), [],
        )

    @patch("dependency.assistant.mission_agents.run_agent")
    @patch("dependency.assistant.mission_agents.mission_preview")
    def test_opt_in_tool_routing_cannot_authorize_execution(self, preview, run):
        preview.return_value = baseline()
        run.side_effect = lambda **kwargs: {
            "output_text": f"{kwargs['spec'].name} investigated stored facts.",
            "tool_rounds": 1,
            "tool_trace": [{"tool": kwargs["spec"].tool_names[0],
                            "arguments": {"event_id": "EVENT-1"},
                            "result": {"private": "secret-plan"}}],
        }
        with patch.dict(os.environ, {
            "DEPENDENCY_MISSION_MODEL_ENABLED": "1", "OPENAI_API_KEY": "TEST_KEY"
        }):
            value = run_supervised_agents(
                event_id="EVENT-1", question="Check backup feasibility",
                sku="SKU-X", caller_opt_in=True,
            )
        self.assertEqual(value["mode"], "OPT_IN_MODEL_SPECIALISTS")
        self.assertEqual(len(value["agent_runs"]), 3)
        self.assertEqual(value["metrics"]["tool_calls"], 3)
        self.assertEqual(run.call_count, 3)
        self.assertTrue(all(c.kwargs["max_tool_rounds"] == 3
                            for c in run.call_args_list))
        self.assertNotIn("secret-plan", str(value["agent_runs"]))
        self.assertFalse(value["execution_allowed"])
        self.assertIsNone(value["metrics"]["model_cost_usd"])

    @patch("dependency.assistant.mission_agents.run_agent")
    @patch("dependency.assistant.mission_agents.mission_preview")
    def test_model_is_disabled_without_both_server_and_caller_consent(
        self, preview, run
    ):
        with patch.dict(os.environ, {
            "DEPENDENCY_MISSION_MODEL_ENABLED": "0",
            "OPENAI_API_KEY": "TEST_KEY"
        }):
            with self.assertRaises(ValueError):
                run_supervised_agents(
                    event_id="EVENT-1", question="Check recovery",
                    caller_opt_in=True,
                )
        with patch.dict(os.environ, {
            "DEPENDENCY_MISSION_MODEL_ENABLED": "1",
            "OPENAI_API_KEY": "TEST_KEY"
        }):
            with self.assertRaises(ValueError):
                run_supervised_agents(
                    event_id="EVENT-1", question="Check recovery",
                    caller_opt_in=False,
                )
        preview.assert_not_called()
        run.assert_not_called()

    @patch("dependency.assistant.mission_agents.run_agent",
           side_effect=RuntimeError("Sensitive API token 123"))
    @patch("dependency.assistant.mission_agents.mission_preview",
           return_value=baseline())
    def test_agent_error_stops_delegation_and_redacts_private_text(
        self, preview, run
    ):
        with patch.dict(os.environ, {
            "DEPENDENCY_MISSION_MODEL_ENABLED": "1",
            "OPENAI_API_KEY": "TEST_KEY",
        }):
            result = run_supervised_agents(
                event_id="EVENT-1", question="Recovery choices",
                sku="SKU-X", caller_opt_in=True,
            )
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result["agent_runs"][0]["status"], "ERROR")
        self.assertEqual(result["agent_runs"][0]["error_type"], "RuntimeError")
        self.assertNotIn("Sensitive API token", str(result))
        self.assertFalse(result["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
