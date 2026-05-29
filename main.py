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


ORDERS: dict[str, dict[str, str]] = {
    "1001": {
        "order_id": "1001",
        "customer": "Aarav",
        "status": "shipped",
        "eta": "2 business days",
        "carrier": "BlueDart",
        "tracking": "BD-492018",
    },
    "1002": {
        "order_id": "1002",
        "customer": "Meera",
        "status": "processing",
        "eta": "dispatch by tomorrow",
        "carrier": "pending",
        "tracking": "not assigned",
    },
    "1003": {
        "order_id": "1003",
        "customer": "Rohan",
        "status": "delivered",
        "eta": "delivered yesterday",
        "carrier": "Delhivery",
        "tracking": "DL-829410",
    },
}


INTENTS: dict[str, dict[str, Any]] = {
    "greeting": {
        "keywords": {"hi", "hello", "hey", "good", "morning", "evening"},
        "response": "Hello! I can help with orders, refunds, payments, account access, delivery, or connect you to support.",
        "suggestions": ["Track order 1001", "Refund policy", "Talk to agent"],
    },
    "shipping": {
        "keywords": {"shipping", "ship", "delivery", "deliver", "courier", "tracking", "track", "where"},
        "response": "Standard delivery usually takes 3 to 5 business days. Share an order number and I can check the latest status.",
        "suggestions": ["Track order 1001", "Track order 1002", "Delivery delay"],
    },
    "refund": {
        "keywords": {"refund", "return", "replace", "exchange", "cancel", "money", "damaged"},
        "response": "Refunds can be requested within 7 days of delivery. If the item is damaged, upload a photo and our team will review it within 24 hours.",
        "suggestions": ["Create refund ticket", "Return window", "Talk to agent"],
    },
    "payment": {
        "keywords": {"payment", "paid", "card", "upi", "wallet", "invoice", "billing", "failed"},
        "response": "For failed payments, please wait 30 minutes before retrying. If money was debited, it is normally reversed within 3 to 5 business days.",
        "suggestions": ["Payment failed", "Need invoice", "Talk to agent"],
    },
    "account": {
        "keywords": {"login", "password", "account", "profile", "email", "otp", "signin", "reset"},
        "response": "You can reset your password from the login page. If OTP is delayed, wait a minute and request a new code.",
        "suggestions": ["Reset password", "OTP not received", "Update email"],
    },
    "hours": {
        "keywords": {"hours", "timing", "open", "close", "available", "support"},
        "response": "Live support is available from 9 AM to 8 PM, Monday to Saturday. I can still create a support ticket any time.",
        "suggestions": ["Create ticket", "Talk to agent", "Email support"],
    },
    "agent": {
        "keywords": {"agent", "human", "person", "executive", "representative", "call"},
        "response": "I can create a priority ticket for a human support agent. Please share the issue and your order number if you have one.",
        "suggestions": ["Create ticket", "Call back request", "Add order number"],
    },
    "thanks": {
        "keywords": {"thanks", "thank", "okay", "ok", "great", "cool", "done"},
        "response": "You are welcome. I am here if you need anything else.",
        "suggestions": ["Track another order", "Refund policy", "Support hours"],
    },
}


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
}


@dataclass
class ChatResult:
    reply: str
    intent: str
    confidence: float
    suggestions: list[str]
    ticket_id: str | None = None
    order: dict[str, str] | None = None


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


def tokenize(message: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", message.lower()))
    return {word for word in words if word not in STOP_WORDS}


def extract_order_id(message: str) -> str | None:
    match = re.search(r"(?:order|ord|#)\s*[-:]?\s*(\d{4,})", message.lower())
    if match:
        return match.group(1)

    compact_match = re.search(r"\b(\d{4,})\b", message)
    return compact_match.group(1) if compact_match else None


def classify_intent(message: str) -> tuple[str, float]:
    tokens = tokenize(message)
    if not tokens:
        return "greeting", 0.35

    best_intent = "unknown"
    best_score = 0.0
    for intent, data in INTENTS.items():
        keywords = data["keywords"]
        matches = tokens & keywords
        if not matches:
            continue
        score = len(matches) / max(len(tokens), 1)
        score += min(len(matches) * 0.16, 0.42)
        if score > best_score:
            best_score = score
            best_intent = intent

    return best_intent, round(min(best_score, 0.98), 2)


def order_response(order_id: str) -> ChatResult:
    order = ORDERS.get(order_id)
    if not order:
        return ChatResult(
            reply=f"I could not find order {order_id}. Please check the number or create a ticket so the support team can verify it.",
            intent="order_lookup",
            confidence=0.91,
            suggestions=["Create ticket", "Try order 1001", "Talk to agent"],
        )

    reply = (
        f"Order {order['order_id']} is {order['status']}. "
        f"ETA: {order['eta']}. Carrier: {order['carrier']}. Tracking: {order['tracking']}."
    )
    return ChatResult(
        reply=reply,
        intent="order_lookup",
        confidence=0.96,
        suggestions=["Refund policy", "Delivery delay", "Talk to agent"],
        order=order,
    )


def create_ticket(name: str, message: str) -> str:
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO tickets (id, name, message, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, name.strip() or "Guest", message.strip(), "open", int(time.time())),
        )
    return ticket_id


def fallback_response(message: str) -> ChatResult:
    topic = "customer support"
    tokens = tokenize(message)
    if {"refund", "return", "replace"} & tokens:
        topic = "refunds and returns"
    elif {"payment", "invoice", "billing"} & tokens:
        topic = "payments"
    elif {"delivery", "shipping", "tracking"} & tokens:
        topic = "delivery"
    elif {"login", "account", "password"} & tokens:
        topic = "account access"

    reply = (
        f"I understand this is about {topic}. "
        "Here is the fastest next step: share the order number, account email, or a short description of what happened. "
        "If this needs a human review, I can create a support ticket immediately."
    )
    return ChatResult(
        reply=reply,
        intent="generated_fallback",
        confidence=0.44,
        suggestions=["Create ticket", "Talk to agent", "Support hours"],
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
        )

    order_id = extract_order_id(message)
    if order_id and ({"order", "track", "tracking", "status", "where"} & tokenize(message) or order_id in ORDERS):
        return order_response(order_id)

    lowered = message.lower()
    if "create ticket" in lowered or "raise ticket" in lowered or "complaint" in lowered:
        ticket_id = create_ticket(name, message)
        return ChatResult(
            reply=f"Done. I created ticket {ticket_id}. A support agent will review it and respond as soon as possible.",
            intent="ticket_created",
            confidence=0.93,
            suggestions=["Track order 1001", "Support hours", "Refund policy"],
            ticket_id=ticket_id,
        )

    intent, confidence = classify_intent(message)
    if intent != "unknown" and confidence >= 0.34:
        data = INTENTS[intent]
        return ChatResult(
            reply=data["response"],
            intent=intent,
            confidence=confidence,
            suggestions=list(data["suggestions"]),
        )

    return fallback_response(message)


def result_to_dict(result: ChatResult) -> dict[str, Any]:
    return {
        "reply": result.reply,
        "intent": result.intent,
        "confidence": result.confidence,
        "suggestions": result.suggestions,
        "ticket_id": result.ticket_id,
        "order": result.order,
    }


class ChatbotHandler(BaseHTTPRequestHandler):
    server_version = "SupportChatbot/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_file(STATIC_DIR / "index.html")
            return

        if parsed.path == "/api/health":
            self.send_json({"status": "ok", "service": "ai-customer-support-chatbot"})
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
            if STATIC_DIR.resolve() in file_path.parents or file_path == STATIC_DIR.resolve():
                self.serve_file(file_path)
            else:
                self.send_error(HTTPStatus.FORBIDDEN)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self.read_json()

        if parsed.path == "/api/chat":
            result = handle_chat(payload)
            self.send_json(result_to_dict(result))
            return

        if parsed.path == "/api/tickets":
            message = str(payload.get("message", "")).strip()
            name = str(payload.get("name", "Guest")).strip() or "Guest"
            if not message:
                self.send_json({"error": "message is required"}, HTTPStatus.BAD_REQUEST)
                return
            ticket_id = create_ticket(name, message)
            self.send_json({"ticket_id": ticket_id, "status": "open"}, HTTPStatus.CREATED)
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
