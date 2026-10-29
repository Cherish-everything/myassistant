# A.V.A. — v1 (legacy)

A.V.A (Artificial Vritual Assistant) is a personal desktop voice assistant. You say her name, she listens, thinks with an LLM, calls tools
(calendar, email, web search, Spotify, WhatsApp, ...), and answers out loud and on screen.

> **Status:** this is the original, prototype V1 version. It works, but every tool is wired by hand in several
> places. The rewrite will replace that with a tool registry, permission grants and a sandboxed script runner.

---

## What she can do

| Area | Tool | What it does |
|---|---|---|
| Calendar and tasks | `get_agenda_for_date` | Events and tasks for "today", "tomorrow", "next monday", `2026-10-05`, ... (GMT+8) |
| | `create_google_calendar_event` | Creates an event; defaults to 1 hour; skips exact duplicates |
| | `add_new_task`, `view_active_tasks`, `resolve_completed_task` | Google Tasks |
| Email | `check_for_new_emails`, `read_email_log` | Scans Gmail (personal and business), classifies important mail, logs it to `important_emails.md` |
| Messaging | `send_whatsapp_message` | Drives the WhatsApp desktop app with keyboard automation |
| Web | `basic_web_search`, `execute_deep_research` | Tavily search; deep research writes a report to `<vault>/research/` |
| | `get_weather_forecast` | wttr.in |
| Media | `play_spotify` | Opens a Spotify search through the `spotify:` URI and presses Enter |
| System | `launch_system_application`, `run_system_maintenance`, `get_visual_context` | Launch apps, open Disk Cleanup, OCR the screen (EasyOCR) |
| Memory | `store_fact` | Saves a fact to an Obsidian note and to ChromaDB |
| Scripts | `execute_python_code` | Runs an LLM-written script in an isolated subprocess (see below) |

Also built in:

- **Wake-word voice input** ("ava" / "eva") with Groq Whisper transcription
- **Spoken replies** with edge-tts (`en-US-EmmaNeural`)
- **Morning briefing** once a day, sent to Telegram (Groq plus Tavily)
- **Inbox watcher** that polls Gmail every 5 minutes and announces important mail
- **Telegram sync** (`start_telegram_sync`)
- **Optional hardware:** an Arduino button and LCD, toggled by `HARDWARE_ENABLED` in `helpers.py`

---

## How it works

```
 voice (sounddevice + SpeechRecognition + Whisper)  ─┐
 hardware button / on-screen input bar               ─┼─►  AICommunicationBridge.get_ai_response()
                                                      │          │
                                                      │          ▼
                                                      │   Groq chat (openai/gpt-oss-20b) + tool schemas
                                                      │          │ tool_calls
                                                      │          ▼
                                                      │   router.route_to_agent()
                                                      │          │
                                                      │          ▼
                                                      │   DOMAIN_MAP -> run_*_agent -> tools/*.py
                                                      │          │ results
                                                      │          ▼
                                                      └─  second Groq pass writes the final reply
                                                                 │
                                         edge-tts voice  ◄───────┴───────►  on-screen UI (/+ LCD)
```

1. **Input.** `VoiceListenerWorker` records audio, transcribes it with Groq `whisper-large-v3` and only reacts
   when a wake word appears. Text can also arrive from the on-screen bar or the hardware button.
2. **Context.** The system prompt gets the active window, date, time and timezone, plus anything relevant
   pulled from memory (`retrieve_relevant_memory`).
3. **Tool calling.** Groq chooses tools from hand-written JSON schemas in `app.py`. Each call goes to
   `route_to_agent`, which looks the name up in `DOMAIN_MAP` and calls the matching specialist agent.
4. **Vagueness check.** Before a search or research tool runs, `analyze_argument_viability` asks an LLM
   whether the query is specific enough, and asks you to clarify if not.
5. **Second pass.** Tool results go back to the model, which writes a short spoken reply. Email checks use a
   special triage prompt.
6. **Output.** The reply is spoken with edge-tts (`QMediaPlayer`), shown in the UI and sent to the LCD.
   The exchange is saved to memory.

### UI

A frameless, transparent-ish PyQt6 window hosting `interface.html` in a `QWebEngineView`. Python and the page talk
over `QWebChannel` (a `backend` object), and replies are pushed back with `runJavaScript`.

### Memory

- **Facts:** `AVA Core Facts.md` in your Obsidian vault is the source of truth. Edit it by hand and the facts
  are re-indexed into ChromaDB on startup.
- **Conversations:** a rolling log in ChromaDB only.
- Retrieval searches both and injects the matches into the prompt.

### Script execution (`execute_python_code`)

`script.py` runs model-written Python in a **separate process** with a timeout and no API keys in its
environment. A script cannot import `os`, `subprocess` or network libraries, cannot call `open()`, and can only
act through an `ava` object:

- `ava.run(tool, **args)`: call an allowlisted, read-only or additive tool
- `ava.ask(prompt)`: ask the LLM
- `ava.read_note(name)` / `ava.append_note(name, text)`: markdown notes inside `<vault>/AVA Scripts/`, append-only

Sending messages, completing tasks, launching apps and reading the screen are deliberately not in the
allowlist. This is a best-effort guard, not an OS-level sandbox.

## Setup

**Requirements:** Python 3.10+, Windows (some tools use Windows-only calls; macOS is partly supported).

```bash
pip install groq tavily-python python-dotenv chromadb dateparser python-dateutil \
            google-api-python-client google-auth-oauthlib \
            PyQt6 PyQt6-WebEngine edge-tts SpeechRecognition sounddevice numpy scipy \
            pyautogui easyocr psutil requests
```

Create a `.env` in the project root:

```
GROQ_API_KEY=...
TAVILY_API_KEY=...
OBSIDIAN_VAULT_PATH=C:\path\to\your\vault   # optional; falls back to ./ava_vault
TELEGRAM_BOT_TOKEN=...                       # morning briefing
TELEGRAM_CHAT_ID=...
```

Google access: put an OAuth client file for each account in the project root as `credentials_personal.json`
and `credentials_business.json`, then run `python google_auth.py` once to sign in. It creates
`token_personal.json` and `token_business.json`. If you add a new scope, delete the tokens and sign in again.

Run:

```bash
python app.py
```

Set `HARDWARE_ENABLED = False` in `helpers.py` if no Arduino is connected.

### Settings in `app.py`

| Name | Default | Meaning |
|---|---|---|
| `EMAIL_WATCHER_ENABLED` | `True` | Turn proactive email announcements on or off |
| `EMAIL_POLL_INTERVAL_SECONDS` | `300` | How often the inbox is checked |
| `voice_profile` | `en-US-EmmaNeural` | edge-tts voice |
| `WAKE_WORDS` | `["ava", "eva"]` | Words that trigger her |

---

## Known limitations (why the rewrite)

- Adding a tool means editing four places: the schema in `app.py`, `DOMAIN_MAP`, a specialist agent, and the
  script allowlist.
- Tools return decorated status strings (`SUCCESS // ...`) instead of structured data, which makes replies
  messy.
- Everything lives in one large `app.py` (UI, voice, LLM loop, scheduling, schemas).
- There is no permission model beyond the script allowlist. Chat has access to every tool.
- The script sandbox is process isolation plus code checks, not a container.
- Scripts can only combine existing tools; they cannot add new abilities.
- `send_whatsapp_message` and `play_spotify` use blind keyboard automation, so keystrokes go to whichever window
  is focused.
- Only one Google Calendar and Tasks account is queried per request (default `personal`).