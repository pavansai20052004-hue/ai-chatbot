const messages = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const nameInput = document.querySelector("#customerName");
const sendButton = document.querySelector("#sendButton");
const suggestions = document.querySelector("#suggestions");
const lastIntent = document.querySelector("#lastIntent");
const confidence = document.querySelector("#confidence");
const sentiment = document.querySelector("#sentiment");
const priorityLevel = document.querySelector("#priorityLevel");
const openTickets = document.querySelector("#openTickets");
const totalTickets = document.querySelector("#totalTickets");
const ticketList = document.querySelector("#ticketList");
const knowledgeList = document.querySelector("#knowledgeList");
const answerType = document.querySelector("#answerType");

const initialSuggestions = ["Track order 1001", "Refund policy", "Support hours"];

function formatLabel(value) {
  if (!value) return "Ready";
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function addMessage(role, text, data = {}) {
  const bubble = document.createElement("article");
  bubble.className = `message ${role}`;

  const label = document.createElement("strong");
  label.textContent = role === "user" ? "Customer" : "SupportBot";

  const body = document.createElement("div");
  body.textContent = text;

  bubble.append(label, body);

  if (role === "bot" && data.intent) {
    bubble.appendChild(renderMeta(data));
  }

  if (data.order) {
    bubble.appendChild(renderOrderCard(data.order));
  }

  if (data.next_steps?.length) {
    bubble.appendChild(renderNextSteps(data.next_steps));
  }

  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

function renderMeta(data) {
  const meta = document.createElement("div");
  meta.className = "meta-row";
  [data.intent, data.priority, data.sentiment, data.answer_type].forEach((item) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = formatLabel(item);
    meta.appendChild(chip);
  });
  return meta;
}

function renderOrderCard(order) {
  const card = document.createElement("dl");
  card.className = "order-card";
  const fields = [
    ["Order", order.order_id],
    ["Status", order.status],
    ["ETA", order.eta],
    ["Carrier", order.carrier],
    ["Tracking", order.tracking],
    ["Total", order.total],
  ];

  fields.forEach(([label, value]) => {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = value;
    row.append(dt, dd);
    card.appendChild(row);
  });
  return card;
}

function renderNextSteps(steps) {
  const list = document.createElement("ul");
  list.className = "next-steps";
  steps.forEach((step) => {
    const item = document.createElement("li");
    item.textContent = step;
    list.appendChild(item);
  });
  return list;
}

function addTyping() {
  const node = addMessage("bot", "Thinking...");
  node.classList.add("typing");
  return node;
}

function renderSuggestions(items) {
  suggestions.replaceChildren();
  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item;
    button.addEventListener("click", () => sendMessage(item));
    suggestions.appendChild(button);
  });
}

function updateStats(data) {
  lastIntent.textContent = formatLabel(data.intent);
  confidence.textContent = `${Math.round(data.confidence * 100)}%`;
  sentiment.textContent = formatLabel(data.sentiment);
  priorityLevel.textContent = formatLabel(data.priority);
  answerType.textContent = formatLabel(data.answer_type);
  priorityLevel.dataset.priority = data.priority || "normal";
}

function renderTickets(tickets) {
  ticketList.replaceChildren();
  if (!tickets.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No tickets yet";
    ticketList.appendChild(empty);
    return;
  }

  tickets.forEach((ticket) => {
    const item = document.createElement("article");
    item.className = "ticket-item";

    const top = document.createElement("div");
    const id = document.createElement("strong");
    const priority = document.createElement("span");
    id.textContent = ticket.id;
    priority.textContent = formatLabel(ticket.priority);
    priority.dataset.priority = ticket.priority;
    top.append(id, priority);

    const text = document.createElement("p");
    text.textContent = ticket.message;

    item.append(top, text);
    ticketList.appendChild(item);
  });
}

async function loadAnalytics() {
  const response = await fetch("/api/analytics");
  const data = await response.json();
  openTickets.textContent = data.tickets_open;
  totalTickets.textContent = data.tickets_total;
  renderTickets(data.recent_tickets || []);
}

async function loadKnowledge() {
  const response = await fetch("/api/knowledge");
  const data = await response.json();
  knowledgeList.replaceChildren();
  data.articles.forEach((article) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = article.title;
    button.addEventListener("click", () => sendMessage(article.title));
    knowledgeList.appendChild(button);
  });
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message) return;

  addMessage("user", message);
  input.value = "";
  renderSuggestions([]);
  sendButton.disabled = true;
  const typing = addTyping();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: nameInput.value || "Guest",
        message,
      }),
    });

    const data = await response.json();
    typing.remove();
    addMessage("bot", data.reply, data);
    updateStats(data);
    renderSuggestions(data.suggestions || initialSuggestions);
    await loadAnalytics();
  } catch (error) {
    typing.remove();
    addMessage("bot", "I could not reach the support service. Please check that the Python server is running.");
    renderSuggestions(initialSuggestions);
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.prompt));
});

addMessage("bot", "Hello! Share an order number or ask about refunds, payments, delivery, account access, invoices, or support tickets.");
renderSuggestions(initialSuggestions);
loadAnalytics().catch(() => {});
loadKnowledge().catch(() => {});
