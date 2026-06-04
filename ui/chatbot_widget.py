"""
Floating chatbot widget — bottom-right corner chat box powered by
HuggingFace free Inference API (facebook/blenderbot-400M-distill).
"""

from __future__ import annotations

import streamlit.components.v1 as components


_CHATBOT_HTML = """
<div id="ds-chatbot-toggle" onclick="toggleChat()" title="Chat with DividendScope Bot">
  💬
</div>
<div id="ds-chatbot-box">
  <div id="ds-chatbot-header">
    <span>🤖 DividendScope Assistant</span>
    <button onclick="toggleChat()" title="Close">&times;</button>
  </div>
  <div id="ds-chatbot-messages">
    <div class="ds-bot-msg">Hi! I'm your DividendScope assistant. Ask me about dividends, portfolio strategies, or how to use this app.</div>
  </div>
  <div id="ds-chatbot-input-area">
    <input id="ds-chatbot-input" type="text" placeholder="Type a message..." onkeydown="if(event.key==='Enter')sendMessage()" autocomplete="off" />
    <button onclick="sendMessage()" title="Send">➤</button>
  </div>
</div>

<style>
#ds-chatbot-toggle {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #0f766e, #115e59);
  color: white;
  font-size: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(15, 118, 110, 0.35);
  z-index: 99999;
  transition: transform 0.2s, box-shadow 0.2s;
  user-select: none;
}
#ds-chatbot-toggle:hover {
  transform: scale(1.08);
  box-shadow: 0 6px 24px rgba(15, 118, 110, 0.45);
}
#ds-chatbot-box {
  position: fixed;
  bottom: 90px;
  right: 24px;
  width: 360px;
  max-height: 480px;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
  display: none;
  flex-direction: column;
  z-index: 99999;
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
#ds-chatbot-header {
  background: linear-gradient(135deg, #0f766e, #115e59);
  color: white;
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
#ds-chatbot-header button {
  background: none;
  border: none;
  color: white;
  font-size: 20px;
  cursor: pointer;
  line-height: 1;
  padding: 0 4px;
}
#ds-chatbot-messages {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  max-height: 340px;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ds-bot-msg, .ds-user-msg {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.45;
  max-width: 85%;
  word-wrap: break-word;
}
.ds-bot-msg {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #14532d;
  align-self: flex-start;
}
.ds-user-msg {
  background: #e0f2fe;
  border: 1px solid #7dd3fc;
  color: #0c4a6e;
  align-self: flex-end;
}
.ds-typing {
  font-style: italic;
  color: #64748b;
  font-size: 12px;
  align-self: flex-start;
}
#ds-chatbot-input-area {
  display: flex;
  border-top: 1px solid #e2e8f0;
  padding: 10px 12px;
  gap: 8px;
  align-items: center;
}
#ds-chatbot-input {
  flex: 1;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}
#ds-chatbot-input:focus {
  border-color: #0f766e;
}
#ds-chatbot-input-area button {
  background: #0f766e;
  border: none;
  color: white;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}
#ds-chatbot-input-area button:hover {
  background: #115e59;
}
</style>

<script>
const HF_API_URL = "https://api-inference.huggingface.co/models/facebook/blenderbot-400M-distill";
let chatHistory = [];

function toggleChat() {
  const box = document.getElementById('ds-chatbot-box');
  const toggle = document.getElementById('ds-chatbot-toggle');
  if (box.style.display === 'flex') {
    box.style.display = 'none';
    toggle.style.display = 'flex';
  } else {
    box.style.display = 'flex';
    toggle.style.display = 'none';
    document.getElementById('ds-chatbot-input').focus();
  }
}

function appendMessage(text, cls) {
  const msgs = document.getElementById('ds-chatbot-messages');
  const div = document.createElement('div');
  div.className = cls;
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div;
}

async function sendMessage() {
  const input = document.getElementById('ds-chatbot-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  appendMessage(text, 'ds-user-msg');
  chatHistory.push(text);

  const typing = appendMessage('Thinking...', 'ds-typing');

  try {
    const response = await fetch(HF_API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        inputs: {
          past_user_inputs: chatHistory.slice(0, -1).slice(-3),
          generated_responses: [],
          text: text
        }
      })
    });
    typing.remove();

    if (response.ok) {
      const data = await response.json();
      const reply = data.generated_text || "I'm not sure how to answer that. Try asking about dividends or portfolio strategies!";
      appendMessage(reply, 'ds-bot-msg');
    } else if (response.status === 503) {
      appendMessage("Model is loading, please try again in a moment...", 'ds-bot-msg');
    } else {
      appendMessage("Sorry, I couldn't process that. Please try again.", 'ds-bot-msg');
    }
  } catch (e) {
    typing.remove();
    appendMessage("Connection error. Please check your internet and try again.", 'ds-bot-msg');
  }
}
</script>
"""


def render_chatbot_widget() -> None:
    """Inject the floating chatbot widget into the Streamlit page."""
    components.html(_CHATBOT_HTML, height=0, scrolling=False)
