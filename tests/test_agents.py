import unittest

from dependency.agents.specs import AGENTS
from dependency.agents.tools import TOOL_SCHEMAS


class AgentContractTests(unittest.TestCase):
    def test_every_agent_tool_has_a_schema(self):
        schema_names = {tool["name"] for tool in TOOL_SCHEMAS}
        for spec in AGENTS.values():
            self.assertTrue(set(spec.tool_names).issubset(schema_names))

    def test_tool_schemas_are_strict(self):
        for tool in TOOL_SCHEMAS:
            self.assertTrue(tool["strict"])
            self.assertEqual(tool["parameters"]["type"], "object")
            self.assertFalse(tool["parameters"]["additionalProperties"])

    def test_signal_agent_cannot_run_recovery_solver(self):
        self.assertNotIn("generate_recovery_candidates", AGENTS["signal"].tool_names)
        self.assertNotIn("get_recovery_plan", AGENTS["signal"].tool_names)

    def test_recovery_agent_has_deterministic_planning_tools(self):
        self.assertIn("generate_recovery_candidates", AGENTS["recovery"].tool_names)
        self.assertIn("get_recovery_plan", AGENTS["recovery"].tool_names)
        self.assertIn("get_supplier_capacity", AGENTS["recovery"].tool_names)


if __name__ == "__main__":
    unittest.main()
