# AI Customer Support Chatbot

A complete Python customer-support chatbot project for the programming task.

## What it includes

- Natural-language intent detection for support topics.
- Predefined responses for FAQs such as delivery, refunds, payments, account help, and support hours.
- Generated fallback responses for unknown customer queries.
- API-style endpoints for chat, order lookup, health checks, and ticket creation.
- Simple support ticket storage using SQLite.
- Browser-based chat UI.

## Run

```powershell
python main.py
```

Open:

```text
http://127.0.0.1:8000
```

## Try these messages

```text
Track order 1001
What is your refund policy?
My payment failed
Create ticket: my package arrived damaged
I forgot my password
I want to talk to an agent
```

## API examples

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType "application/json" -Body '{"name":"Guest","message":"Track order 1001"}'
Invoke-RestMethod http://127.0.0.1:8000/api/orders/1001
```
