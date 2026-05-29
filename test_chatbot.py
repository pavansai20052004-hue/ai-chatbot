import unittest

from main import handle_chat, init_db


class ChatbotTests(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_order_lookup_returns_order_card_data(self):
        result = handle_chat({"name": "Tester", "message": "Track order 1001"})

        self.assertEqual(result.intent, "order_lookup")
        self.assertEqual(result.order["order_id"], "1001")
        self.assertEqual(result.answer_type, "api_lookup")

    def test_payment_question_uses_knowledge_base(self):
        result = handle_chat({"name": "Tester", "message": "Payment failed and money debited"})

        self.assertEqual(result.intent, "payment")
        self.assertEqual(result.answer_type, "knowledge_base")
        self.assertIn("transaction ID", " ".join(result.next_steps))

    def test_complaint_creates_high_priority_ticket(self):
        result = handle_chat({"name": "Tester", "message": "Complaint: damaged order, create ticket"})

        self.assertEqual(result.intent, "ticket_created")
        self.assertEqual(result.priority, "high")
        self.assertTrue(result.ticket_id.startswith("TKT-"))


if __name__ == "__main__":
    unittest.main()
