# AI Customer Support Chatbot

A polished Python customer-support chatbot project with a browser dashboard, ticket workflow, order lookup, and API endpoints.

## Next-level feature

- Intent detection for delivery, refunds, payments, accounts, invoices, complaints, and agent handoff.
- Knowledge-base matching with answer sources and next-step guidance.
- Sentiment and priority detection for support triage.
- Order lookup through mock API-style data.
- Ticket creation with SQLite storage, priority, sentiment, intent, and recent-ticket analytics.
- Dashboard UI with live context, knowledge actions, recent tickets, chat metadata, and order cards.
- Dependency-free Python backend using only the standard library.
- Unit tests for key chatbot behavior.

## Run

```powershell
python main.py
```

Open:

```text
http://127.0.0.1:8000
```

If port 8000 is busy:

```powershell
python main.py 8001
```

## Try these messages

```text
Track order 1001
Payment failed and money debited
My order is damaged, create ticket
Need invoice for order 1002
I forgot my password
I want to talk to an agent
```

## API examples

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/chat -ContentType "application/json" -Body '{"name":"Guest","message":"Track order 1001"}'
Invoke-RestMethod http://127.0.0.1:8001/api/orders/1001
Invoke-RestMethod http://127.0.0.1:8001/api/analytics
Invoke-RestMethod http://127.0.0.1:8001/api/knowledge
```

## Tests

```powershell
python -m unittest
```
