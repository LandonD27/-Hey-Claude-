# Hey Claude — Voice Assistant Server

A local FastAPI server that turns "Hey Siri, Hey Claude" into a full Claude-powered voice assistant on your iPhone.

## Stack

- **Backend**: Python + FastAPI
- **AI**: Anthropic Claude (`claude-opus-4-6`) with web search
- **Client**: iOS Shortcuts

---

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API key

```bash
cp .env.example .env
# Edit .env and paste your Anthropic API key
```

### 3. Start the server

```bash
python main.py
# Server runs at http://0.0.0.0:8000
```

Or with uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## API

### `POST /ask`

**Request body:**
```json
{
  "message": "What's the weather in Tokyo?",
  "context": "optional iOS context string",
  "session_id": "optional UUID — omit to start a new session"
}
```

**Response:**
```json
{
  "response": "It's currently 72°F and sunny in Tokyo.",
  "action": null,
  "session_id": "abc123-..."
}
```

When an action is detected:
```json
{
  "response": "Sending your message to Mom now.",
  "action": {
    "type": "send_message",
    "payload": {
      "recipient": "Mom",
      "message": "On my way!"
    }
  },
  "session_id": "abc123-..."
}
```

**Action types:**

| type | payload keys |
|---|---|
| `send_message` | `recipient`, `message` |
| `set_reminder` | `title`, `time` |
| `open_app` | `app`, `query` (optional) |
| `search` | `query` |

### `GET /health`

Returns `{"status": "ok", "model": "claude-opus-4-6"}`.

---

## Conversational Memory

Each session keeps the last **10 messages** in context. Pass the `session_id` returned in every response back in subsequent requests to maintain a conversation. Omit it to start fresh.

---

## Expose to iPhone via ngrok

If your iPhone and server are **not** on the same Wi-Fi network, use ngrok to create a public tunnel:

```bash
# Install ngrok: https://ngrok.com/download
ngrok http 8000
```

Copy the `https://xxxx.ngrok-free.app` URL — use that as your base URL in the Shortcut instead of `http://localhost:8000`.

If they **are** on the same Wi-Fi, find your Mac's local IP:

```bash
ipconfig getifaddr en0   # macOS
# or
hostname -I              # Linux
```

Use `http://192.168.x.x:8000` in the Shortcut.

---

## iOS Shortcut Setup

> **Trigger phrase:** "Hey Siri, Hey Claude"

Build this shortcut in the **Shortcuts** app on your iPhone. Each step is one action block.

### Step-by-step

#### 1 — Dictate the question
- Action: **Dictate Text**
- Language: English (or your preferred language)
- Save output to variable: `UserSpeech`

#### 2 — Store session ID
- Action: **Get Contents of URL** — skip for first run; use a persistent variable (see note below)
- For simplicity, use a **Text** action with a fixed value (e.g., your name) as a stable session ID so memory persists across calls:
  - Action: **Text** → `hey-claude-main-session`
  - Save to variable: `SessionID`

#### 3 — Build the request body
- Action: **Dictionary**
  - Add key `message` → Variable: `UserSpeech`
  - Add key `session_id` → Variable: `SessionID`
  - *(Optional)* Add key `context` → Text: `iPhone` (or any static context)
- Save to variable: `RequestBody`

#### 4 — Call the server
- Action: **Get Contents of URL**
  - URL: `http://YOUR_SERVER_IP:8000/ask`  *(or your ngrok URL)*
  - Method: `POST`
  - Request Body: `JSON`
  - Body: Variable `RequestBody`
- Save output to variable: `RawResponse`

#### 5 — Parse the response
- Action: **Get Dictionary from Input** ← `RawResponse`
- Save to variable: `ResponseDict`

#### 6 — Extract the text reply
- Action: **Get Dictionary Value**
  - Dictionary: `ResponseDict`
  - Key: `response`
- Save to variable: `ClaudeReply`

#### 7 — Speak the reply
- Action: **Speak Text** ← `ClaudeReply`
  - Rate: 0.55 (slightly slower than default — sounds more natural)
  - Wait until done: ON

---

### Action Routing (Optional — Advanced)

Add an **If** block after step 6 to handle structured actions:

```
Get Dictionary Value  Key: "action"  from ResponseDict → ActionBlock

If  ActionBlock  is not  null
│
├─ Get Dictionary Value  Key: "type"  from ActionBlock → ActionType
│
├─ If  ActionType  contains  "send_message"
│   ├─ Get Dictionary Value  Key: "payload"  from ActionBlock → Payload
│   ├─ Get Dictionary Value  Key: "recipient"  from Payload → Recipient
│   ├─ Get Dictionary Value  Key: "message"   from Payload → MsgBody
│   └─ Send Message  Body: MsgBody  Recipients: Recipient
│
├─ If  ActionType  contains  "set_reminder"
│   ├─ Get Dictionary Value  Key: "payload"  from ActionBlock → Payload
│   ├─ Get Dictionary Value  Key: "title"    from Payload → ReminderTitle
│   ├─ Get Dictionary Value  Key: "time"     from Payload → ReminderTime
│   └─ Add New Reminder  Title: ReminderTitle  Due Date: ReminderTime
│
├─ If  ActionType  contains  "open_app"
│   ├─ Get Dictionary Value  Key: "payload"  from ActionBlock → Payload
│   ├─ Get Dictionary Value  Key: "app"      from Payload → AppName
│   └─ Open App  AppName
│
└─ If  ActionType  contains  "search"
    ├─ Get Dictionary Value  Key: "payload"  from ActionBlock → Payload
    ├─ Get Dictionary Value  Key: "query"    from Payload → Query
    └─ Search Web  Query
```

---

### Trigger with Siri

1. Open **Shortcuts** → tap your shortcut → tap the **...** (settings)
2. Toggle **Add to Siri**
3. Record the phrase: **"Hey Claude"**

Now say **"Hey Siri"** → **"Hey Claude"** and the shortcut runs automatically.

---

## Running on a VPS

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in .env
cp .env.example .env

# Run with a process manager (e.g., systemd or screen)
uvicorn main:app --host 0.0.0.0 --port 8000

# Or with gunicorn for production
pip install gunicorn
gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Point your iOS Shortcut at `http://YOUR_VPS_IP:8000` (or set up nginx + SSL for `https://`).

---

## Project Structure

```
.
├── main.py            # FastAPI server
├── requirements.txt
├── .env.example       # Copy to .env and add your key
└── README.md
```
