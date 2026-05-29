from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DB_PATH = ROOT / "support.db"


ORDERS: dict[str, dict[str, Any]] = {
    "1001": {
        "order_id": "1001",
        "customer": "Aarav",
        "status": "shipped",
        "eta": "2 business days",
        "carrier": "BlueDart",
        "tracking": "BD-492018",
        "payment_status": "paid",
        "total": "Rs. 2,499",
        "items": ["Bluetooth headphones", "USB-C cable"],
    },
    "1002": {
        "order_id": "1002",
        "customer": "Meera",
        "status": "processing",
        "eta": "dispatch by tomorrow",
        "carrier": "pending",
        "tracking": "not assigned",
        "payment_status": "paid",
        "total": "Rs. 899",
        "items": ["Laptop sleeve"],
    },
    "1003": {
        "order_id": "1003",
        "customer": "Rohan",
        "status": "delivered",
        "eta": "delivered yesterday",
        "carrier": "Delhivery",
        "tracking": "DL-829410",
        "payment_status": "paid",
        "total": "Rs. 1,299",
        "items": ["Wireless mouse", "Mouse pad"],
    },
}


INTENTS: dict[str, dict[str, Any]] = {
    "greeting": {
        "keywords": {"hi", "hello", "hey", "good", "morning", "evening"},
        "response": "Hello! I can help with orders, refunds, payments, delivery, account access, and support tickets.",
        "suggestions": ["Track order 1001", "Refund policy", "Talk to agent"],
    },
    "shipping": {
        "keywords": {"shipping", "ship", "delivery", "deliver", "courier", "tracking", "track", "where", "late"},
        "response": "Standard delivery takes 3 to 5 business days. Share an order number and I will check the latest status.",
        "suggestions": ["Track order 1001", "Delivery delay", "Create ticket"],
    },
    "refund": {
        "keywords": {"refund", "return", "replace", "exchange", "cancel", "money", "damaged", "broken"},
        "response": "Refunds can be requested within 7 days of delivery. Damaged items are reviewed within 24 hours after proof is shared.",
        "suggestions": ["Create refund ticket", "Return window", "Talk to agent"],
    },
    "payment": {
        "keywords": {"payment", "paid", "card", "upi", "wallet", "invoice", "billing", "failed", "debited"},
        "response": "For failed payments, wait 30 minutes before retrying. If money was debited, reversal usually takes 3 to 5 business days.",
        "suggestions": ["Payment failed", "Need invoice", "Create ticket"],
    },
    "account": {
        "keywords": {"login", "password", "account", "profile", "email", "otp", "signin", "reset"},
        "response": "Password reset is available from the login page. If OTP is delayed, wait a minute and request a new code.",
        "suggestions": ["Reset password", "OTP not received", "Update email"],
    },
    "invoice": {
        "keywords": {"invoice", "bill", "receipt", "gst", "tax"},
        "response": "Invoices are available after payment confirmation. Share your order number and I can check the billing status.",
        "suggestions": ["Need invoice for order 1001", "Payment status", "Talk to agent"],
    },
    "hours": {
        "keywords": {"hours", "timing", "open", "close", "available", "support"},
        "response": "Live support is available from 9 AM to 8 PM, Monday to Saturday. Tickets can be created at any time.",
        "suggestions": ["Create ticket", "Talk to agent", "Email support"],
    },
    "agent": {
        "keywords": {"agent", "human", "person", "executive", "representative", "call", "escalate"},
        "response": "I can create a priority ticket for a human support agent. Share the issue and order number if available.",
        "suggestions": ["Create ticket", "Call back request", "Add order number"],
    },
    "complaint": {
        "keywords": {"complaint", "angry", "bad", "worst", "issue", "problem", "unhappy", "fraud"},
        "response": "I understand this needs careful handling. I can record the complaint and mark it for faster review.",
        "suggestions": ["Create ticket", "Talk to agent", "Track order 1001"],
    },
    "thanks": {
        "keywords": {"thanks", "thank", "okay", "ok", "great", "cool", "done"},
        "response": "You are welcome. I am here if you need anything else.",
        "suggestions": ["Track another order", "Refund policy", "Support hours"],
    },
}


KNOWLEDGE_BASE: list[dict[str, Any]] = [
    {
        "id": "kb_refund_policy",
        "category": "Refunds",
        "title": "Refund policy",
        "keywords": {"refund", "return", "replace", "exchange", "damaged", "broken"},
        "answer": "Refund or replacement requests are accepted within 7 days of delivery. Damaged products should include a photo and order number for faster approval.",
        "next_steps": ["Keep the package and invoice ready", "Share clear photos for damaged items", "Create a ticket if review is needed"],
    },
    {
        "id": "kb_payment_failed",
        "category": "Payments",
        "title": "Payment failed",
        "keywords": {"payment", "failed", "debited", "upi", "card", "wallet", "charged"},
        "answer": "If payment failed but money was debited, do not retry immediately. Most reversals are completed within 3 to 5 business days.",
        "next_steps": ["Check bank statement after 30 minutes", "Save the transaction ID", "Create a ticket for duplicate charges"],
    },
    {
        "id": "kb_delivery_delay",
        "category": "Delivery",
        "title": "Delivery delay",
        "keywords": {"delivery", "delayed", "late", "courier", "tracking", "not", "arrived"},
        "answer": "Delivery delays can happen because of courier handoff, weather, or address verification. Order tracking gives the fastest status update.",
        "next_steps": ["Share the order number", "Confirm phone and address", "Create a ticket if there is no update for 48 hours"],
    },
    {
        "id": "kb_account_access",
        "category": "Account",
        "title": "Account access",
        "keywords": {"login", "password", "otp", "account", "email", "signin", "reset"},
        "answer": "Use password reset for login issues. OTP delivery can take up to 60 seconds during network congestion.",
        "next_steps": ["Check spam folder for email OTP", "Request a new OTP after 60 seconds", "Create a ticket if the phone number changed"],
    },
    {
        "id": "kb_invoice",
        "category": "Billing",
        "title": "Invoice request",
        "keywords": {"invoice", "bill", "receipt", "gst", "tax", "billing"},
        "answer": "Invoices are generated after payment confirmation and can be reissued with GST details before dispatch.",
        "next_steps": ["Share the order number", "Confirm the billing email", "Add GST details before dispatch"],
    },
]


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "for",
    "i",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "please",
    "the",
    "to",
    "with",
    "you",
    "your",
}

POSITIVE_WORDS = {"good", "great", "thanks", "thank", "helpful", "happy", "solved", "nice"}
NEGATIVE_WORDS = {
    "angry",
    "bad",
    "broken",
    "charged",
    "complaint",
    "damaged",
    "debited",
    "delay",
    "delayed",
    "failed",
    "fraud",
    "issue",
    "late",
    "lost",
    "missing",
    "not",
    "problem",
    "refund",
    "unhappy",
    "worst",
}
URGENT_PATTERNS = (
    "urgent",
    "asap",
    "immediately",
    "right now",
    "escalate",
    "fraud",
    "charged twice",
    "money debited",
    "not delivered",
    "damaged",
    "broken",
)


@dataclass
class ChatResult:
    reply: str
    intent: str
    confidence: float
    suggestions: list[str]
    sentiment: str = "neutral"
    priority: str = "normal"
    next_steps: list[str] | None = None
    answer_type: str = "rule_based"
    sources: list[str] | None = None
    ticket_id: str | None = None
    order: dict[str, Any] | None = None
    handoff_required: bool = False


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tickets)")}
        migrations = {
            "priority": "ALTER TABLE tickets ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'",
            "intent": "ALTER TABLE tickets ADD COLUMN intent TEXT NOT NULL DEFAULT 'unknown'",
            "sentiment": "ALTER TABLE tickets ADD COLUMN sentiment TEXT NOT NULL DEFAULT 'neutral'",
            "order_id": "ALTER TABLE tickets ADD COLUMN order_id TEXT",
            "updated_at": "ALTER TABLE tickets ADD COLUMN updated_at INTEGER",
            "transcript": "ALTER TABLE tickets ADD COLUMN transcript TEXT",
        }
        for column, sql in migrations.items():
            if column not in existing:
                conn.execute(sql)


def tokenize(message: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", message.lower()))
    return {word for word in words if word not in STOP_WORDS}


def extract_order_id(message: str) -> str | None:
    match = re.search(r"(?:order|ord|#)\s*[-:]?\s*(\d{4,})", message.lower())
    if match:
        return match.group(1)

    compact_match = re.search(r"\b(\d{4,})\b", message)
    return compact_match.group(1) if compact_match else None


def detect_sentiment(message: str) -> str:
    tokens = tokenize(message)
    positive = len(tokens & POSITIVE_WORDS)
    negative = len(tokens & NEGATIVE_WORDS)
    lowered = message.lower()

    if "not happy" in lowered or "not satisfied" in lowered:
        negative += 2
    if negative > positive:
        return "negative"
    if positive > negative:
        return "positive"
    return "neutral"


def classify_intent(message: str) -> tuple[str, float]:
    tokens = tokenize(message)
    lowered = message.lower()
    if not tokens:
        return "greeting", 0.35

    if extract_order_id(message) and any(word in tokens for word in {"order", "track", "tracking", "status", "where"}):
        return "order_lookup", 0.98

    best_intent = "unknown"
    best_score = 0.0
    for intent, data in INTENTS.items():
        keywords = data["keywords"]
        matches = tokens & keywords
        if not matches:
            continue
        score = len(matches) / max(len(tokens), 1)
        score += min(len(matches) * 0.16, 0.42)
        if intent in lowered:
            score += 0.2
        if score > best_score:
            best_score = score
            best_intent = intent

    return best_intent, round(min(best_score, 0.98), 2)


def detect_priority(message: str, intent: str, sentiment: str) -> str:
    lowered = message.lower()
    has_urgent_phrase = any(pattern in lowered for pattern in URGENT_PATTERNS)
    if has_urgent_phrase or intent in {"agent", "complaint"} and sentiment == "negative":
        return "high"
    if sentiment == "negative" or intent in {"refund", "payment", "shipping"}:
        return "medium"
    return "normal"


def find_knowledge_answer(message: str) -> tuple[dict[str, Any] | None, float]:
    tokens = tokenize(message)
    best_entry: dict[str, Any] | None = None
    best_score = 0.0
    for entry in KNOWLEDGE_BASE:
        matches = tokens & entry["keywords"]
        if not matches:
            continue
        score = len(matches) / max(len(tokens), 1)
        score += min(len(matches) * 0.18, 0.48)
        if entry["title"].lower() in message.lower():
            score += 0.25
        if score > best_score:
            best_score = score
            best_entry = entry
    return best_entry, round(min(best_score, 0.95), 2)


def order_response(order_id: str, message: str = "") -> ChatResult:
    sentiment = detect_sentiment(message)
    priority = detect_priority(message, "order_lookup", sentiment)
    order = ORDERS.get(order_id)
    if not order:
        return ChatResult(
            reply=f"I could not find order {order_id}. Please check the number or create a ticket so the support team can verify it.",
            intent="order_lookup",
            confidence=0.91,
            suggestions=["Create ticket", "Try order 1001", "Talk to agent"],
            sentiment=sentiment,
            priority="medium",
            next_steps=["Check the order number", "Use the phone or email linked to the order", "Create a ticket for manual verification"],
            answer_type="api_lookup",
            sources=["Order database"],
            handoff_required=True,
        )

    reply = (
        f"Order {order['order_id']} is {order['status']}. "
        f"ETA: {order['eta']}. Carrier: {order['carrier']}. "
        f"Tracking: {order['tracking']}. Payment: {order['payment_status']}."
    )
    return ChatResult(
        reply=reply,
        intent="order_lookup",
        confidence=0.96,
        suggestions=["Refund policy", "Delivery delay", "Talk to agent"],
        sentiment=sentiment,
        priority=priority,
        next_steps=["Save the tracking ID", "Check courier updates after 6 PM", "Create a ticket if the status does not change"],
        answer_type="api_lookup",
        sources=["Order database"],
        order=order,
        handoff_required=priority == "high",
    )


def create_ticket(
    name: str,
    message: str,
    priority: str = "normal",
    intent: str = "unknown",
    sentiment: str = "neutral",
    order_id: str | None = None,
) -> str:
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    now = int(time.time())
    transcript = json.dumps({"customer": name.strip() or "Guest", "message": message.strip()})
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO tickets
                (id, name, message, status, created_at, priority, intent, sentiment, order_id, updated_at, transcript)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                name.strip() or "Guest",
                message.strip(),
                "open",
                now,
                priority,
                intent,
                sentiment,
                order_id,
                now,
                transcript,
            ),
        )
    return ticket_id


def fallback_response(message: str) -> ChatResult:
    intent, confidence = classify_intent(message)
    sentiment = detect_sentiment(message)
    priority = detect_priority(message, intent, sentiment)
    topic = intent.replace("_", " ") if intent != "unknown" else "customer support"
    reply = (
        f"I understand this is about {topic}. "
        "Share the order number, account email, or a short description of what happened. "
        "If this needs review, I can create a support ticket immediately."
    )
    return ChatResult(
        reply=reply,
        intent="generated_fallback",
        confidence=max(confidence, 0.44),
        suggestions=["Create ticket", "Talk to agent", "Support hours"],
        sentiment=sentiment,
        priority=priority,
        next_steps=["Add the order number if available", "Describe the problem in one sentence", "Create a ticket for agent review"],
        answer_type="generated_template",
        sources=["Support triage rules"],
        handoff_required=priority == "high",
    )


def handle_chat(payload: dict[str, Any]) -> ChatResult:
    message = str(payload.get("message", "")).strip()
    name = str(payload.get("name", "Guest")).strip() or "Guest"

    if not message:
        return ChatResult(
            reply="Please type your question so I can help.",
            intent="empty",
            confidence=1.0,
            suggestions=["Track order 1001", "Refund policy", "Support hours"],
            next_steps=["Type a short question", "Add an order number if available"],
        )

    order_id = extract_order_id(message)
    tokens = tokenize(message)
    lowered = message.lower()
    if order_id and ({"order", "track", "tracking", "status", "where", "invoice"} & tokens or order_id in ORDERS):
        return order_response(order_id, message)

    intent, intent_confidence = classify_intent(message)
    sentiment = detect_sentiment(message)
    priority = detect_priority(message, intent, sentiment)

    ticket_requested = (
        "create ticket" in lowered
        or "raise ticket" in lowered
        or "complaint" in lowered
        or "call back" in lowered
    )
    if ticket_requested:
        ticket_id = create_ticket(name, message, priority, intent, sentiment, order_id)
        return ChatResult(
            reply=f"Done. I created {priority}-priority ticket {ticket_id}. A support agent will review it as soon as possible.",
            intent="ticket_created",
            confidence=0.94,
            suggestions=["Track order 1001", "Support hours", "Refund policy"],
            sentiment=sentiment,
            priority=priority,
            next_steps=["Keep the ticket ID for follow-up", "Add photos or transaction ID if relevant", "Watch for agent response"],
            answer_type="ticket_workflow",
            sources=["Ticket database"],
            ticket_id=ticket_id,
            handoff_required=True,
        )

    kb_entry, kb_confidence = find_knowledge_answer(message)
    if kb_entry and kb_confidence >= 0.44:
        return ChatResult(
            reply=kb_entry["answer"],
            intent=intent if intent != "unknown" else kb_entry["category"].lower(),
            confidence=max(kb_confidence, intent_confidence),
            suggestions=["Create ticket", "Talk to agent", "Track order 1001"],
            sentiment=sentiment,
            priority=priority,
            next_steps=list(kb_entry["next_steps"]),
            answer_type="knowledge_base",
            sources=[kb_entry["title"]],
            handoff_required=priority == "high",
        )

    if intent != "unknown" and intent_confidence >= 0.34:
        data = INTENTS[intent]
        return ChatResult(
            reply=data["response"],
            intent=intent,
            confidence=intent_confidence,
            suggestions=list(data["suggestions"]),
            sentiment=sentiment,
            priority=priority,
            next_steps=["Share order details if available", "Create a ticket for agent review"],
            answer_type="intent_response",
            sources=["Intent library"],
            handoff_required=priority == "high",
        )

    return fallback_response(message)


def ticket_rows(limit: int = 5) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, name, message, status, created_at, priority, intent, sentiment, order_id
            FROM tickets
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def analytics_payload() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        open_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'").fetchone()[0]
        high_priority = conn.execute("SELECT COUNT(*) FROM tickets WHERE priority = 'high'").fetchone()[0]
        by_intent = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT intent, COUNT(*) FROM tickets GROUP BY intent ORDER BY COUNT(*) DESC"
            ).fetchall()
        }

    return {
        "tickets_total": total,
        "tickets_open": open_count,
        "high_priority": high_priority,
        "by_intent": by_intent,
        "recent_tickets": ticket_rows(5),
    }


def knowledge_payload() -> dict[str, Any]:
    return {
        "articles": [
            {
                "id": entry["id"],
                "category": entry["category"],
                "title": entry["title"],
                "answer": entry["answer"],
            }
            for entry in KNOWLEDGE_BASE
        ]
    }


def result_to_dict(result: ChatResult) -> dict[str, Any]:
    return {
        "reply": result.reply,
        "intent": result.intent,
        "confidence": result.confidence,
        "suggestions": result.suggestions,
        "sentiment": result.sentiment,
        "priority": result.priority,
        "next_steps": result.next_steps or [],
        "answer_type": result.answer_type,
        "sources": result.sources or [],
        "ticket_id": result.ticket_id,
        "order": result.order,
        "handoff_required": result.handoff_required,
    }


class ChatbotHandler(BaseHTTPRequestHandler):
    server_version = "SupportChatbot/2.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_file(STATIC_DIR / "index.html")
            return

        if parsed.path == "/api/health":
            self.send_json({"status": "ok", "service": "ai-customer-support-chatbot", "version": "2.0"})
            return

        if parsed.path == "/api/analytics":
            self.send_json(analytics_payload())
            return

        if parsed.path == "/api/knowledge":
            self.send_json(knowledge_payload())
            return

        if parsed.path == "/api/tickets":
            init_db()
            self.send_json({"tickets": ticket_rows(20)})
            return

        order_match = re.fullmatch(r"/api/orders/(\d+)", parsed.path)
        if order_match:
            order_id = order_match.group(1)
            order = ORDERS.get(order_id)
            if order:
                self.send_json(order)
            else:
                self.send_json({"error": "Order not found"}, HTTPStatus.NOT_FOUND)
            return

        if parsed.path.startswith("/static/"):
            relative = unquote(parsed.path.replace("/static/", "", 1))
            file_path = (STATIC_DIR / relative).resolve()
            static_root = STATIC_DIR.resolve()
            if static_root in file_path.parents or file_path == static_root:
                self.serve_file(file_path)
            else:
                self.send_error(HTTPStatus.FORBIDDEN)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self.read_json()

        if parsed.path == "/api/chat":
            init_db()
            result = handle_chat(payload)
            self.send_json(result_to_dict(result))
            return

        if parsed.path == "/api/tickets":
            init_db()
            message = str(payload.get("message", "")).strip()
            name = str(payload.get("name", "Guest")).strip() or "Guest"
            if not message:
                self.send_json({"error": "message is required"}, HTTPStatus.BAD_REQUEST)
                return
            intent, _ = classify_intent(message)
            sentiment = detect_sentiment(message)
            priority = detect_priority(message, intent, sentiment)
            ticket_id = create_ticket(name, message, priority, intent, sentiment, extract_order_id(message))
            self.send_json({"ticket_id": ticket_id, "status": "open", "priority": priority}, HTTPStatus.CREATED)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), format % args))


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    init_db()
    server = ThreadingHTTPServer((host, port), ChatbotHandler)
    print(f"AI customer support chatbot running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    selected_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run(port=selected_port)
