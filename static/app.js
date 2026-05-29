const messages = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const nameInput = document.querySelector("#customerName");
const suggestions = document.querySelector("#suggestions");
const lastIntent = document.querySelector("#lastIntent");
const confidence = document.querySelector("#confidence");
const openTickets = document.querySelector("#openTickets");

let ticketCount = 0;

const initialSuggestions = ["Track order 1001", "Refund policy", "Support hours"];

function addMessage(role, text) {
  const bubble = document.createElement("article");
  bubble.className = `message ${role}`;

  const label = document.createElement("strong");
  label.textContent = role === "user" ? "Customer" : "SupportBot";

  const body = document.createElement("div");
  body.textContent = text;

  bubble.append(label, body);
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
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
  lastIntent.textContent = data.intent.replaceAll("_", " ");
  confidence.textContent = `${Math.round(data.confidence * 100)}%`;
  if (data.ticket_id) {
    ticketCount += 1;
    openTickets.textContent = String(ticketCount);
  }
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message) return;

  addMessage("user", message);
  input.value = "";
  renderSuggestions([]);

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
    addMessage("bot", data.reply);
    updateStats(data);
    renderSuggestions(data.suggestions || initialSuggestions);
  } catch (error) {
    addMessage("bot", "I could not reach the support service. Please check that the Python server is running.");
    renderSuggestions(initialSuggestions);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.prompt));
});

addMessage("bot", "Hello! Share your order number or ask about refunds, payments, delivery, account access, or support tickets.");
renderSuggestions(initialSuggestions);
