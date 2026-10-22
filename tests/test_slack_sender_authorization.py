"""Supplier Slack callbacks cannot accept an untrusted channel member."""
import unittest
from unittest.mock import patch, MagicMock
from dependency.services.supplier_outreach import record_slack_reply


class ReplyMapping:
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,query,args):
        if "SELECT request_id" in query:
            return type("Result",(),{"fetchall":lambda self:[("REQ-1",)]})()
        raise AssertionError("Unexpected SQL")

class SenderGuardTests(unittest.TestCase):
    @patch("dependency.services.supplier_outreach.record_confirmation_reply")
    @patch("dependency.services.supplier_outreach.get_confirmation_request")
    @patch("dependency.services.supplier_outreach.connect",return_value=ReplyMapping())
    def test_sender_must_match_authorized_direct_message_user(self,connect,get_request,record):
        get_request.return_value={"address":"U-APPROVED","status":"SENT"}
        bad=record_slack_reply(
            channel_id="D-123",thread_ts="1700000000.00001",
            raw_message="9999 capacity",sender_external_id="U-ATTACKER",
            source_message_id="D-123:1700000001.00001",
        )
        self.assertEqual(bad["reason"],"SENDER_NOT_AUTHORIZED")
        record.assert_not_called()
        record.return_value={"status":"REPLY_RECEIVED","reply_id":"RESP-1"}
        ok=record_slack_reply(
            channel_id="D-123",thread_ts="1700000000.00001",
            raw_message="5000 capacity",sender_external_id="U-APPROVED",
            source_message_id="D-123:1700000001.00002",
        )
        self.assertTrue(ok["matched"])
        record.assert_called_once()

    @patch("dependency.services.supplier_outreach.record_confirmation_reply")
    @patch("dependency.services.supplier_outreach.get_confirmation_request")
    @patch("dependency.services.supplier_outreach.connect",return_value=ReplyMapping())
    def test_channel_reply_requires_explicit_user_allowlist(self,connect,get_request,record):
        get_request.return_value={"address":"C-CHANNEL","status":"SENT"}
        with patch.dict("os.environ",{"SLACK_SUPPLIER_ALLOWED_USER_IDS":"U-CONSENTED"}):
            bad=record_slack_reply(channel_id="C-CHANNEL",thread_ts="123",
                raw_message="5k",sender_external_id="U-RANDOM",source_message_id="m1")
            self.assertEqual(bad["reason"],"SENDER_NOT_AUTHORIZED")
            record.return_value={"status":"REPLY_RECEIVED"}
            good=record_slack_reply(channel_id="C-CHANNEL",thread_ts="123",
                raw_message="5k",sender_external_id="U-CONSENTED",source_message_id="m2")
        self.assertTrue(good["matched"])

    @patch("dependency.services.supplier_outreach.record_confirmation_reply")
    @patch("dependency.services.supplier_outreach.connect",return_value=ReplyMapping())
    def test_unthreaded_cannot_attach_capacity_evidence(self,connect,record):
        value=record_slack_reply(channel_id="C-123",thread_ts=None,
            raw_message="capacity 5000",sender_external_id="U-X",
            source_message_id="C-123:111")
        self.assertEqual(value["reason"],"THREADED_REPLY_REQUIRED")
        record.assert_not_called()

if __name__=="__main__":
    unittest.main()
