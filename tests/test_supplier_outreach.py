import hashlib
import hmac
import unittest

from dependency.db.connection import connect
from dependency.incidents.triage import triage_event
from dependency.notifications.slack import verify_slack_signature
from dependency.services.demo_reset import reset_demo_state
from dependency.services.supplier_outreach import (
    confirm_supplier_reply,
    create_capacity_confirmation_request,
    dispatch_confirmation_request,
    get_confirmation_request,
    record_confirmation_reply,
)


class SupplierOutreachTests(unittest.TestCase):
    EVENT_ID = "IDN-CIANJUR-2022-USGS-us7000ir9t"
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"

    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def test_reply_is_parsed_but_does_not_change_state_until_confirmation(self):
        triage = triage_event(event_id=self.EVENT_ID, radius_km=150)
        incident_id = triage["incident"]["incident_id"]

        request = create_capacity_confirmation_request(
            facility_id="ADI26-0240",
            sku="JI2993",
            incident_id=incident_id,
            scenario_id=self.SCENARIO_ID,
        )
        self.assertEqual(request["recipient_contact_id"], "CNT-HS")
        self.assertEqual(request["status"], "PENDING_DISPATCH")
        self.assertEqual(request["system_value"]["capacity_units"], 9500.0)

        blocked_send = dispatch_confirmation_request(
            request_id=request["request_id"],
            allow_external=False,
        )
        self.assertFalse(blocked_send["dispatched"])

        reply = record_confirmation_reply(
            request_id=request["request_id"],
            raw_message=(
                "Capacity has declined to 5,500 pairs per week "
                "until 2026-11-04."
            ),
            sender_external_id="U_SUPPLIER",
            source_message_id="SLACK-TEST-001",
        )
        self.assertEqual(reply["status"], "REPLY_RECEIVED")
        self.assertEqual(reply["parsed"]["capacity_units"], 5500)
        self.assertTrue(reply["requires_confirmation"])

        with connect() as conn:
            state_version = conn.execute(
                "SELECT version FROM operational_state_version WHERE singleton=true"
            ).fetchone()[0]
            capacity = conn.execute(
                """
                SELECT capacity_units
                FROM supplier_capacity
                WHERE facility_id='ADI26-0240' AND sku='JI2993'
                ORDER BY week_start DESC
                LIMIT 1
                """
            ).fetchone()[0]

        self.assertEqual(state_version, 1)
        self.assertEqual(float(capacity), 9500.0)

        confirmed = confirm_supplier_reply(
            request_id=request["request_id"],
            reply_id=reply["reply_id"],
            confirmed_by="Planner",
        )
        self.assertEqual(confirmed["status"], "CONFIRMED")
        self.assertEqual(
            confirmed["capacity_update"]["new_capacity_units"],
            5500,
        )
        self.assertEqual(
            confirmed["capacity_update"]["state_version"],
            2,
        )

        stored = get_confirmation_request(request["request_id"])
        self.assertEqual(stored["status"], "CONFIRMED")
        self.assertTrue(stored["replies"][0]["supplier_confirmed"])

    def test_source_message_id_is_idempotent(self):
        request = create_capacity_confirmation_request(
            facility_id="ADI26-0240",
            sku="JI2993",
            scenario_id=self.SCENARIO_ID,
        )
        first = record_confirmation_reply(
            request_id=request["request_id"],
            raw_message="Current capacity is 7000 until 2026-11-04.",
            source_message_id="SLACK-DUPLICATE",
        )
        second = record_confirmation_reply(
            request_id=request["request_id"],
            raw_message="Current capacity is 7000 until 2026-11-04.",
            source_message_id="SLACK-DUPLICATE",
        )
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["reply_id"], second["reply_id"])

    def test_slack_signature_verification(self):
        secret = "test-secret"
        body = b'{"type":"event_callback"}'
        timestamp = "1770000000"
        base = b"v0:" + timestamp.encode() + b":" + body
        digest = hmac.new(
            secret.encode(),
            base,
            hashlib.sha256,
        ).hexdigest()

        self.assertTrue(
            verify_slack_signature(
                raw_body=body,
                timestamp=timestamp,
                signature=f"v0={digest}",
                signing_secret=secret,
                now_epoch=1770000000,
            )
        )
        self.assertFalse(
            verify_slack_signature(
                raw_body=body,
                timestamp=timestamp,
                signature="v0=bad",
                signing_secret=secret,
                now_epoch=1770000000,
            )
        )


if __name__ == "__main__":
    unittest.main()
