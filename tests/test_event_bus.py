import unittest

from dependency.events.bus import (
    TOPIC_APPROVAL_REQUESTED,
    TOPIC_BUSINESS_STATE,
    TOPIC_DECISION_CONFIRMED,
    TOPIC_EXTERNAL_EVENTS,
    TOPIC_INCIDENT_DETECTED,
    TOPIC_PLAN_GENERATED,
    TOPIC_PLAN_INVALIDATED,
    TOPIC_SUPPLIER_CAPACITY,
    enqueue,
    pending,
)


class EventBusTests(unittest.TestCase):
    def test_required_topics_are_defined(self):
        self.assertEqual(TOPIC_EXTERNAL_EVENTS, "external.events")
        self.assertEqual(TOPIC_BUSINESS_STATE, "business.state.updated")
        self.assertEqual(TOPIC_SUPPLIER_CAPACITY, "supplier.capacity.updated")
        self.assertEqual(TOPIC_INCIDENT_DETECTED, "incident.detected")
        self.assertEqual(TOPIC_PLAN_GENERATED, "plan.generated")
        self.assertEqual(TOPIC_PLAN_INVALIDATED, "plan.invalidated")
        self.assertEqual(TOPIC_APPROVAL_REQUESTED, "approval.requested")
        self.assertEqual(TOPIC_DECISION_CONFIRMED, "decision.confirmed")

    def test_local_transactional_outbox_retains_event(self):
        outbox_id = enqueue(
            topic="test.event",
            event_key="ci-key",
            payload={"value": 42},
        )
        rows = pending(limit=1000)
        row = next(x for x in rows if x["outbox_id"] == outbox_id)
        self.assertEqual(row["topic"], "test.event")
        self.assertEqual(row["event_key"], "ci-key")
        self.assertEqual(row["payload"]["value"], 42)


if __name__ == "__main__":
    unittest.main()
