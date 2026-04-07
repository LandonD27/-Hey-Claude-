"""
Hey Claude — local voice assistant server.
Expose POST /ask for iOS Shortcuts to call.
"""

import json
import re
import uuid
from collections import deque
from typing import Optional

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────

MODEL = "claude-opus-4-6"
MAX_HISTORY = 10          # messages kept per session (pairs = 5 turns)
MAX_TOKENS = 1024

SYSTEM_PROMPT = """You are a hands-free voice assistant on the user's iPhone. \
Keep responses SHORT and conversational (under 3 sentences unless asked for detail). \
If the user asks to send a message, set a reminder, or control their phone, \
return a JSON action field embedded in your reply using this exact format on its \
own line at the end of your response:

ACTION_JSON: {"type": "<type>", "payload": {<payload>}}

Where type is one of: send_message | set_reminder | open_app | search
Payload examples:
  send_message  → {"recipient": "Mom", "message": "On my way!"}
  set_reminder  → {"title": "Call dentist", "time": "tomorrow 9am"}
  open_app      → {"app": "Maps", "query": "coffee near me"}
  search        → {"query": "weather in Tokyo"}

Only include ACTION_JSON when an action is clearly requested. \
Never include it for regular conversation."""

# ── Session store ──────────────────────────────────────────────────────────────

# Maps session_id → deque of {"role": ..., "content": ...}
sessions: dict[str, deque] = {}


def get_session(session_id: str) -> deque:
    if session_id not in sessions:
        sessions[session_id] = deque(maxlen=MAX_HISTORY)
    return sessions[session_id]


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(title="Hey Claude", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic()


# ── Request / Response models ──────────────────────────────────────────────────

class AskRequest(BaseModel):
    message: str
    context: Optional[str] = None   # extra iOS context (e.g. current app, location)
    session_id: Optional[str] = None  # omit to auto-create a new session


class AskResponse(BaseModel):
    response: str
    action: Optional[dict] = None
    session_id: str


# ── Action detection ───────────────────────────────────────────────────────────

ACTION_PATTERN = re.compile(r"ACTION_JSON:\s*(\{.*\})", re.DOTALL)


def extract_action(text: str) -> tuple[str, Optional[dict]]:
    """
    Pull ACTION_JSON out of Claude's reply.
    Returns (clean_text, action_dict | None).
    """
    match = ACTION_PATTERN.search(text)
    if not match:
        return text.strip(), None

    raw = match.group(1)
    clean = ACTION_PATTERN.sub("", text).strip()

    try:
        action = json.loads(raw)
        if "type" not in action or "payload" not in action:
            raise ValueError("missing required keys")
        return clean, action
    except (json.JSONDecodeError, ValueError):
        # Malformed action — return text as-is, drop broken JSON
        return clean, None


# ── Web search tool ────────────────────────────────────────────────────────────

WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
}


# ── Core handler ──────────────────────────────────────────────────────────────

@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    # Resolve / create session
    session_id = req.session_id or str(uuid.uuid4())
    history = get_session(session_id)

    # Build user message — optionally prepend iOS context
    user_content = req.message
    if req.context:
        user_content = f"[Context: {req.context}]\n{req.message}"

    # Append to history
    history.append({"role": "user", "content": user_content})

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[WEB_SEARCH_TOOL],  # type: ignore[list-item]
            messages=list(history),
        )
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {e}")

    # Extract text from response (may contain tool use blocks too)
    raw_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            raw_text += block.text

    clean_text, action = extract_action(raw_text)

    # Save assistant reply to history (text only — keeps history lean)
    history.append({"role": "assistant", "content": clean_text})

    return AskResponse(
        response=clean_text,
        action=action,
        session_id=session_id,
    )


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


# ── Dev entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
