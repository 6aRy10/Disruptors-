"""Evidence agent can draft, but must not change private state or dispatch."""
import unittest
from unittest.mock import patch

from dependency.agents.specs import EVIDENCE_INVESTIGATOR
from dependency.agents.tools import TOOL_SCHEMAS,dispatch_tool
from scripts.run_live_stack import run_cycle


class EvidenceAgentContracts(unittest.TestCase):
    def test_restricted_tools_and_provenance(self):
        allowed=set(EVIDENCE_INVESTIGATOR.tool_names)
        self.assertIn("get_event_investigation_tasks",allowed)
        self.assertIn("prepare_investigation_outreach",allowed)
        for prohibited in ("confirm_supplier_capacity","execute_approved_action",
                           "dispatch_confirmation_request","request_human_approval"):
            self.assertNotIn(prohibited,allowed)
        schema_names={s["name"] for s in TOOL_SCHEMAS}
        self.assertTrue(allowed <= schema_names)

    @patch("dependency.agents.tools.prepare_investigation_outreach")
    def test_draft_tool_dispatches_only_to_safe_review_service(self,draft):
        draft.return_value={"status":"REVIEW_REQUIRED","dispatched":False}
        out=dispatch_tool("prepare_investigation_outreach",{"task_id":"TASK-ANY"})
        self.assertFalse(out["dispatched"])
        draft.assert_called_once_with(task_id="TASK-ANY")

    @patch("scripts.run_live_stack.process_pending_events")
    def test_agent_run_is_opt_in(self,consumer):
        consumer.return_value={"attempted":0,"succeeded":0,"failed":0}
        run_cycle(usgs=False,gdacs=False,agents=False)
        self.assertFalse(consumer.call_args.kwargs["run_agents"])
        run_cycle(usgs=False,gdacs=False,agents=True)
        self.assertTrue(consumer.call_args.kwargs["run_agents"])


if __name__=="__main__":
    unittest.main()
