# SET UP   
import os
import sys
import json
import re
import threading
import asyncio
import edge_tts
import time
import io
from datetime import datetime, timedelta
import psutil
import requests
from tavily import TavilyClient
from helpers import send_to_lcd, listen_for_button, HARDWARE_ENABLED
psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS) # For Windows

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSlot, QObject, QUrl, QThread, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from tools import store_conversation, retrieve_relevant_memory
from agents import route_to_agent
from tools import check_for_new_emails
from tools import start_telegram_sync

# Master switch + poll interval for the autonomous inbox watcher. Set to
# False to disable proactive email announcements entirely.
EMAIL_WATCHER_ENABLED = True
EMAIL_POLL_INTERVAL_SECONDS = 300  # 3 minutes
EMAIL_LOG_FILE = "important_emails.md"

import speech_recognition as sr
import pyautogui
import sounddevice as sd
import numpy as np
from scipy.io import wavfile
from groq import Groq

# =====================================================================
# CORE CONFIGURATION
# =====================================================================

from dotenv import load_dotenv
load_dotenv()  # reads .env file and loads keys into environment
client = Groq()  # Groq auto-reads GROQ_API_KEY from environment — no change needed here

# =====================================================================
# MORNING BRIEFING
# =====================================================================
# EDIT IT TO THE NEWSPAPER FORMAT
def run_local_morning_sync():
    """Runs a deep AI morning briefing summary pipeline via Groq and Tavily."""
    lock_file = ".last_brief_date.txt"
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(lock_file):
        with open(lock_file, "r") as f:
            if f.read().strip() == today_str:
                print("[SYSTEM LOG] Morning brief already delivered for today. Skipping sync.")
                return

    print("[SYSTEM LOG] First boot detected. Initializing AI News Summarization...")
    
    try:
        # 1. Gather raw data vectors from Tavily
        tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
        search_query = "top japanese tech innovation business and technology advancement headlines today" 
        response = tavily.search(query=search_query, search_depth="basic", max_results=5)
        
        # Format raw data for Llama to read
        raw_news_data = ""
        for idx, res in enumerate(response.get("results", []), 1):
            raw_news_data += f"Source {idx}: {res.get('title')}\nURL: {res.get('url')}\nContent: {res.get('content')}\n\n"

        # 2. Initialize your Groq Client (Ensure groq package is imported at top)
        from groq import Groq
        groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        # 3. Use Llama to process the messy data into an absolute masterpiece briefing
        system_prompt = (
            "You are A.V.A, an elite executive intelligence assistant. Your job is to take raw, messy web scraping search "
            "data and compile a beautifully organized, highly informative morning briefing report for your executive director.\n\n"
            "Formatting Rules:\n"
            "1. Start with a clean greeting, preferably using user's name.\n"
            "2. Group insights or number them cleanly.\n"
            "3. DO NOT output code formatting blocks or print raw escape characters like '\\n'. Output clean, natural paragraphs.\n"
            "4. Provide a substantial summary at a glance so the user learns the actual story context without needing to click.\n"
            "5. Include the specific URL link at the end of each news summary segment using clean Telegram Markdown: [Read Article ↗](URL)\n"
            "6. Keep it concise, sharp, and business-focused."
            "7. Remove any irrelevant content or boilerplate"
            "8. Avoid using emojis or casual language. Keep it professional."
        )
        
        ai_generation = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Here is today's raw intelligence payload:\n\n{raw_news_data}"}
            ],
            temperature=0.3
        )
        
        message_payload = ai_generation.choices[0].message.content
        
        # 4. Transmit compiled payload to Telegram
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(telegram_url, json={
            "chat_id": chat_id,
            "text": message_payload,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True # Keeps chat view clean from massive preview bubbles
        })
        
        with open(lock_file, "w") as f:
            f.write(today_str)
            
        print("[SYSTEM LOG] Elite AI intelligence packet dispatched safely.")
        
    except Exception as e:
        print(f"[SYSTEM LOG] Morning briefing pipeline faulted: {str(e)}")

# --- START UP ---
# Spin it up inside a non-blocking background thread right when app.py runs
threading.Thread(target=run_local_morning_sync, daemon=True).start()
threading.Thread(target=start_telegram_sync, daemon=True).start()

# =====================================================================
# ROOT FUNCTIONS
# =====================================================================

def get_current_system_context():
    """Gathers real-time data about your workspace."""
    return {
        "active_window": pyautogui.getActiveWindowTitle(),
        "time": datetime.now().strftime("%H:%M")
    }
class VoiceListenerWorker(QThread):
    text_recognized = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.recognizer = sr.Recognizer()
        self.running = True
        self.WAKE_WORDS = ["ava", "eva"]
        self.is_paused = False

        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 300
        self.recognizer.pause_threshold = 0.6

        try:
            default_device_info = sd.query_devices(kind='input')
            self.sample_rate = int(default_device_info['default_samplerate'])
            self.block_size = int(self.sample_rate * 0.5)
            self.device_config = {
                'device': default_device_info['index'],
                'samplerate': self.sample_rate,
                'blocksize': self.block_size,
                'dtype': 'int16',
                'channels': 1
            }
            print(f"[AUDIO INITIALIZER]: sounddevice input found - device {default_device_info['name']} ({default_device_info['index']}) at {self.sample_rate}Hz")
        except Exception as init_err:
            self.sample_rate = 16000
            self.block_size = 8000
            self.device_config = {
                'samplerate': self.sample_rate,
                'blocksize': self.block_size,
                'dtype': 'int16',
                'channels': 1
            }
            print(f"[AUDIO INITIALIZER WARNING]: sounddevice init failed, falling back to defaults: {str(init_err)}")

    def run(self):
        print("\n====================================================")
        print("[AUDIO CORE]: Eco-Mode Audio Pipeline ACTIVE.")
        print("====================================================\n")

        while self.running:
            try:
                with sd.RawInputStream(**self.device_config) as stream:
                    data, overflow = stream.read(self.block_size)
                    if overflow:
                        continue

                    byte_io = io.BytesIO()
                    wavfile.write(byte_io, self.sample_rate, np.frombuffer(data, dtype=np.int16))
                    byte_io.seek(0)
                    byte_io.name = "audio_stream.wav"

                    with sr.AudioFile(byte_io) as source:
                        audio_data = self.recognizer.record(source)
                        try:
                            transcription = client.audio.transcriptions.create(
                                file=byte_io,
                                model="whisper-large-v3",
                                language="en",
                                temperature=0.0
                            )

                            text = transcription.text.lower().strip()

                            if text:
                                print(f"[WHISPER]: '{text}'")
                                matched_wake_word = next((word for word in self.WAKE_WORDS if word in text), None)

                                if matched_wake_word:
                                    clean_prompt = text.replace(matched_wake_word, "").strip().rstrip('.?!,')
                                    self.text_recognized.emit(clean_prompt if clean_prompt else "hello")

                        except Exception:
                            pass

            except Exception as hardware_err:
                print(f"[HARDWARE ERROR]: {str(hardware_err)}")
                time.sleep(3.0)

            # Increased cooldown check so your system core cycles down between phrases
            time.sleep(0.4)

class AICommunicationBridge(QObject):
    # New signal added to update the UI text asynchronously without crashes
    ai_response_ready = pyqtSignal(str)

    def __init__(self, player, audio_output):
        super().__init__()
        self.player = player
        self.audio_output = audio_output
        self.voice_profile = "en-US-EmmaNeural"
        self.start_email_watcher()

        # Short-term conversational memory: the last few user/assistant turns
        # in THIS session, sent with every request so A.V.A. remembers what
        # was just said. Separate from the long-term vector memory
        # (retrieve_relevant_memory), which is for facts/history across
        # sessions, not immediate back-and-forth context.
        self.conversation_history = []
        self.MAX_HISTORY_TURNS = 10  # keeps last 10 user+assistant exchanges (~20 messages)

    def _record_turn(self, user_prompt: str, ai_text: str):
        """
        Appends a full conversational turn to short-term memory.
        Preserves context for follow-up answers (e.g. User says 'yes' to a prompt).
        """
        self.conversation_history.append({"role": "user", "content": user_prompt})
        self.conversation_history.append({"role": "assistant", "content": ai_text})
        
        # Keep the last 10 back-and-forth turns (20 messages)
        max_messages = self.MAX_HISTORY_TURNS * 2
        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

    WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    MONTHS = ["january", "february", "march", "april", "may", "june", "july",
              "august", "september", "october", "november", "december"]

    def _timeframe_label(self, timeframe: str) -> str:
        """Human-readable phrase for a timeframe value, for use in spoken/UI summaries."""
        if timeframe == "today":
            return "today"
        if timeframe == "tomorrow":
            return "tomorrow"
        if timeframe == "week":
            return "this week"
        if timeframe == "all":
            return "on record"
        try:
            d = datetime.strptime(timeframe, "%Y-%m-%d").date()
            return f"on {d.strftime('%A, %b %-d')}" if os.name != "nt" else f"on {d.strftime('%A, %b %d').replace(' 0', ' ')}"
        except (ValueError, TypeError):
            return "for that timeframe"

    def generate_and_speak(self, text_to_speak):
        def run_async():
            async def generate():
                try:
                    # 1. Use a single static filename instead of a timestamp string
                    filename = "ava_speech_core.mp3"
                    full_path = os.path.abspath(filename)
                    
                    # 2. Safely stop the player to release any active file locks before overwriting
                    self.player.stop()
                    self.player.setSource(QUrl())
                    
                    # Small buffer to let the OS drop the file write handle
                    time.sleep(0.05) 
                    
                    # 3. Generate the fresh audio directly over the old file
                    communicate = edge_tts.Communicate(text_to_speak, self.voice_profile)
                    await communicate.save(full_path)
                    
                    # 4. Load and play instantly (No dynamic signals needed!)
                    self.player.setSource(QUrl.fromLocalFile(full_path))
                    self.player.play()

                except Exception as e:
                    print(f"A.V.A SYSTEM ERROR // Audio Engine pipeline fail: {e}")
                    
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(generate())
            loop.close()
            
        threading.Thread(target=run_async, daemon=True).start()

    def _delete_file_safely(self, file_path):
        """Attempts to cleanly delete the file, trying a few times if OS locks are lifting slowly."""
        for _ in range(5):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                break # Success, break out of retry loop
            except PermissionError:
                # Give the OS player engine an extra 100ms to fully drop its read handle
                time.sleep(0.1)
            except Exception:
                break

    def start_email_watcher(self):
        """Spawns a background loop that polls both inboxes for new mail and
        proactively announces anything the triage filter judges important -
        the same filter used by the check_critical_inbox_triage tool, just
        running on a timer instead of waiting for you to ask."""
        if not EMAIL_WATCHER_ENABLED:
            print("[System] Email watcher disabled (EMAIL_WATCHER_ENABLED = False).")
            return

        def watch_loop():
            print(f"[System] Email watcher active - polling every {EMAIL_POLL_INTERVAL_SECONDS}s.")
            while True:
                time.sleep(EMAIL_POLL_INTERVAL_SECONDS)
                try:
                    raw_new_mail = check_for_new_emails()
                    print("CHECKING DONE")
                    if not raw_new_mail:
                        print("[EMAIL WATCHER] No new mail since last check.")
                        continue  # nothing new this cycle

                    triage_prompt = f"""You are A.V.A's Inbox Triage Matrix. Analyze the raw email data below - these are messages that have arrived since the last check, across both accounts.
Extract and summarize ONLY critical, high-importance operational updates that require immediate attention:
- Payments (Invoices, Stripe receipts, balance transfers, financial alerts)
- Client Communications (Design briefs, visual identity feedback, Clastr Agency revisions)
- High-stakes Opportunities (Scholarships especially MEXT and MOE, major academic updates)

CRITICAL RULES:
1. Ignore all general system logs, newsletters, promotions, and normal conversational noise. This includes any bank statements unless marked as urgent or important.
2. If a message matches, summarize it in a single concise sentence, and always state who it's from (do NOT INCLUDE THE EMAIL ADDRESS) and the subject line, and note which inbox it hit (Personal vs. Business).
3. Maintain your signature A.V.A tone: calm, hyper-efficient, and minimal.
4. If absolutely nothing is critical or matches the guidelines, reply with something like: "All clear on the horizon"
5. Say EXACTLY "X new email(s) since last check" at the top of your response, where X is the number of new messages. And replace 'email' with emails if there's more than 1 new message.
6. Ask me if I want a summary and give it when I say yes. 

New mail since last check:
{raw_new_mail}"""

                    response = client.chat.completions.create(
                        model="openai/gpt-oss-20b",
                        messages=[{"role": "system", "content": triage_prompt}],
                        temperature=0.4  # lower temp keeps the triage filter strict
                    )
                    verdict = (response.choices[0].message.content or "").strip()

                    # Only interrupt you if something actually matters - silence otherwise
                    if verdict and "All clear on the horizon" not in verdict:
                        self.ai_response_ready.emit(verdict)
                        self.generate_and_speak(verdict)
                        lcd_output(verdict)
                        # Do NOT call self._record_turn here if you don't want it treated 
                        # as the immediate preceding conversational turn for user follow-ups.
                        store_conversation("[AUTO EMAIL SCAN]", verdict)

                except Exception as e:
                    print(f"[EMAIL WATCHER] Cycle failed: {str(e)}")

        threading.Thread(target=watch_loop, daemon=True).start()

    

    @pyqtSlot(str)
    def get_ai_response(self, user_prompt):
        """Asynchronously routes the prompt to an isolated processing thread to protect the UI thread."""
        threading.Thread(target=self._threaded_api_handler, args=(user_prompt,), daemon=True).start()

    def _threaded_api_handler(self, user_prompt):
        """Executes the base LLM tool routing and hands off execution immediately to router.py."""
        try:
            self.current_user_prompt = user_prompt

            # Keep your groq_tools definition block right here 
            # (or move it to a config file to save space)
            groq_tools = [
                # Inside your groq_tools array in app.py:
                {
                    "type": "function",
                    "function": {
                        "name": "basic_web_search",
                        "description": "Execute a live Google search query to retrieve current web information, news, or answers.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The exact search string or question to look up."
                                }
                            },
                            "required": ["query"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "play_spotify",
                        "description": "Opens the desktop Spotify application, searches for a specific track, song, or artist, and automatically starts playing it.",
                        "parameters": {
                            "type": "object", 
                            "properties": {
                                "song_or_artist": {
                                    "type": "string",
                                    "description": "The exact name of the song, track, album, or artist the user wants to listen to."
                                }
                            }, 
                            "required": ["song_or_artist"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "launch_system_application",
                        "description": "Launches a local desktop application or system software on the user's laptop based on a spoken or written command.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "app_name": {
                                    "type": "string",
                                    "description": "The clean lowercase name or system alias of the application to execute (e.g., 'spotify', 'vscode', 'notion', 'chrome', 'figma')."
                                },
                            },
                            "required": ["app_name"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "send_whatsapp_message",
                        "description": "Call this to drop a text packet behind the scenes on WhatsApp.",
                        "parameters": {
                            "type": "object",
                            "properties": {"phone_or_name": {"type": "string"}, "message": {"type": "string"}},
                            "required": ["phone_or_name", "message"]
                        },
                    },
                },
                {
                "type": "function",
                "function": {
                    "name": "get_visual_context",
                    "description": "Executes when the user explicitly requests to look, see, review, or inspect elements, text, or layouts on their monitor screen.",
                    "parameters": {
                    "type": "object",
                    "properties": {
                        "user_request": {
                        "type": "string",
                        "description": "The specific question or instruction regarding the screen state."
                        },
                        "target_element": {
                        "type": "string",
                        "description": "The area or interface object specified by the user (e.g., 'screen', 'terminal', 'window')."
                        }
                    },
                    "required": ["user_request", "target_element"]
                    }
                }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather_forecast",
                        "description": "Retrieves weather forecast metrics for a specified geographic location.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "The city name or destination (e.g., 'Singapore')."
                                },
                                "days": {
                                    "type": "integer",
                                    "description": "CRITICAL: Must be a raw integer number ONLY (e.g. 1 or 3). Do NOT wrap this value in quotation marks or string blocks."
                                }
                            },
                            "required": ["location", "days"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "run_system_maintenance",
                        "description": "Call this when the user requests maintenance chores, laptop cleaning, optimization, clearing cache files, or freeing up disk space. It safely opens the native system utility window.",
                        "parameters": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "store_fact",
                        "description": "Call this when the user explicitly tells A.V.A. to remember something, note a preference, or store a personal fact for future reference.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "fact_text": {
                                    "type": "string",
                                    "description": "The exact fact or preference to store (e.g. 'User prefers Python over JavaScript')."
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Category tag: 'preference', 'schedule', 'personal', 'technical', or 'general'."
                                }
                            },
                            "required": ["fact_text"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "add_new_task",
                        "description": "Call this when the user requests to create, remind, or add a task/to-do item straight to their primary Google Tasks inbox.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "The clear title or core objective action item of the task (e.g., 'Draft client pitch proposal script')."
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Optional extra sub-details, descriptive criteria, or specifications for the task."
                                }
                            },
                            "required": ["title"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "create_google_calendar_event",
                        "description": "Call this when the user requests to create a calendar event.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "The clear title or core objective action item of the calendar event (e.g., 'Team meeting')."
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Optional extra sub-details, descriptive criteria, or specifications for the calendar event."
                                },
                                "start_time": {
                                    "type": "string",
                                    "description": "The start time of the calendar event."
                                },
                                "end_time": {
                                    "type": "string",
                                    "description": "The end time of the calendar event."
                                },
                                "account_type": {
                                    "type": "string",
                                    "enum": ["personal", "business"],
                                    "description": "The target Google account profile. Pass 'business' if the user mentions work, business, or company tasks/calendar. Defaults to 'personal'."
                                }
                            }
                        }
                            },
                            "required": ["title", "start_time"]
                },
                {
                    "type": "function",
                    "function": {
                        "name": "view_active_tasks",
                        "description": "Call this when the user asks what tasks they have pending, wants to see their to-do list, or wants an active operational task breakdown from Google Tasks.",
                        "parameters": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "resolve_completed_task",
                        "description": "Call this when the user explicitly mentions finishing, completing, or clearing a task off their plate. Targets specific task indices or keyword references.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "target": {
                                    "type": "string",
                                    "description": "The targeted value to find and finish. Can be the list number position index as a string (e.g., '1', '3') or a partial text phrase (e.g., 'edit video')."
                                }
                            },
                            "required": ["target"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "execute_deep_research",
                        "description": "Call this for multi-layer market research, brand briefs, or deep background lookups. Automatically fuses Tavily web intelligence with a localized file search.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string", 
                                    "description": "The target analytical research query phrase for the live web lookups."
                                },
                                "scan_keyword": {
                                    "type": "string",
                                    "description": "An optional single-word keyword parsed from the user's speech to cross-reference their local laptop notes (e.g., if user says 'check my Clastr documents', keyword is 'clastr')."
                                },
                                "suggested_filename": {
                                    "type": "string",
                                    "description": "A clean markdown filename to save the eventual report as (e.g., 'competitor_brief.md')."
                                }
                            },
                            "required": ["query", "suggested_filename"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "check_for_new_emails",
                        "description": "Reads the user's important unread Gmail messages and returns summaries of recent unread priority emails.",
                        "parameters": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "read_email_log",
                        "description": "If the last assistant message was 'Would you like me to read the email?' or something along that line, call this tool when users respond yes, sure, okay, etc.",
                        "parameters": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_agenda_for_date",
                        "description": "Retrieves the user's schedule, events, and tasks for a specific or relative date (e.g. 'today', 'tomorrow', 'next monday', 'in 3 days'). Also retrieves if users asks if they are free or busy on a specific date. Returns a concise summary of the day's agenda.",
                        "parameters": {
                        "type": "object",
                        "properties": {
                            "date_query": {
                            "type": "string",
                            "description": "The target date string mentioned by the user, like 'next monday', 'tomorrow', 'this Friday', or 'today'."
                            },
                            "account_type": {
                            "type": "string",
                            "enum": ["personal", "business"],
                            "description": "The target Google account profile ('personal' or 'business'). Defaults to 'personal'."
                            }
                        },
                        "required": []
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "execute_python_code",
                        "description": (
                        "Write a Python script for custom multi-step tasks. No open(), os, or network. "
                        "Available: ava.run(tool_name, **args) -> str (call any allowed tool), "
                        "ava.ask(prompt) -> str (LLM for summarising/classifying text), "
                        "ava.read_note(name) / ava.append_note(name, text) (markdown notes, append-only). "
                        "Standard imports: json, re, datetime, math, collections. Use print() for results."
                        ),
                        "parameters": {"type": "object",
                                    "properties": {"script": {"type": "string"}},
                                    "required": ["script"]}
                    }
                }
            ] 
            # Need to add get calendar event for date

            context = get_current_system_context()
            memory_context = retrieve_relevant_memory(user_prompt)
            

            system_message = f"""You are A.V.A. — a calm, hyper-efficient personal AI operator and a sharp, but warm and highly capable coworker. Be precise and minimal but at the same time be engagin and warm.
 
[STRICT PROTOCOL - EXECUTIVE ONLY]
1. Your response must consist ONLY of the final, user-facing sentence. 
2. ABSOLUTELY FORBIDDEN to output internal evaluation steps, character counts, tone analysis, or verification logs (e.g., do NOT output "Length: 94 chars", "Fits constraints", or "Final Polish").
3. Keep the output clean, raw, and highly concise—strictly under 300 characters total. No markdown headers, bold text, or bullet points.
4. Treat tool output as raw system status logs. Read it silently, confirm it worked, and output your own brief, one-line update.
5. NEVER invent, assume, or guess tasks, meetings, or schedule details that are not explicitly present in tool output or the context below. The "recent_logs" field is a truncated preview only, NOT the full task list - if the user asks about their tasks/schedule, rely on the retrieve_active_objectives tool result, not this preview. If there is no real data for something, say so plainly instead of fabricating an answer.

[CONVERSATION CONTINUITY PROTOCOL]
- Always look at the immediate preceding assistant message in the conversation history except when I ask for my new emails or events. In that case, you may ignore the last assistant message and provide a fresh summary of the inbox or calendar events.
- If the last assistant message asked a question or proposed an action (e.g., "Would you like me to read your emails?"), and the user responds with agreement ("yes", "sure", "go ahead", "do it", "read them"), IMMEDIATELY invoke the appropriate tool/function to fulfill that action.

[AGENDA PROTOCOL]
- Ignore events labeled as "Breakfast", "Lunch", or "Dinner" unless the user explicitly asks about them or if they are labelled specifically. E.g., "Lunch with John" is relevant, but "Lunch" is not.
- If tasks overlap with calendar events E.g "Meeting" is on calendar AND on task, only mention the calendar event in your summary. Do not mention the task if it is already on the calendar.

Current workspace context: {context}
{memory_context}

Refer to this file for the content of each email to read outloud: 
{EMAIL_LOG_FILE}
"""

            testing = False
            self.current_user_prompt = user_prompt

            # First LLM pass to determine if a tool is needed
            response = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": system_message},
                    *self.conversation_history,
                    {"role": "user", "content": user_prompt}
                ],
                tools=groq_tools,
                tool_choice="auto",
                temperature=0.2
            )

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # ==========================================
            # PATH A: MODEL TOKENS CALLING A FUNCTION (AGENT ROUTER)
            # ==========================================
            if tool_calls:
                # 1. Build a localized conversation stack
                messages_history = [
                    {"role": "system", "content": system_message},
                    *self.conversation_history,
                    {"role": "user", "content": user_prompt},
                    response_message  # Critical: Contains the assistant's intent to call the tool
                ]
                
                valid_tool_executed = False
                all_raw_data = [] # Track execution outputs for testing mode
                triage_intercept = False # Tracks if we need to run the specialized email triage prompt

                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    
                    # Visual context safety check
                    if func_name == "get_visual_context":
                        trigger_words = ["look", "see", "read", "screen", "inspect", "code", "error", "scan"]
                        if not any(word in user_prompt.lower() for word in trigger_words):
                            continue # Skip this tool call loop step completely
                        
                    # 2. Run your application function
                    raw_tool_data = route_to_agent(self, func_name, func_args)
                    valid_tool_executed = True
                    all_raw_data.append(str(raw_tool_data))
                    
                    # Flag if this is our custom email triage tool
                    if func_name == "check_critical_inbox_triage":
                        triage_intercept = True

                    # 3. Append the execution payload directly as a tool-role block
                    messages_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": str(raw_tool_data)
                    })

                # --- PIPELINE SPLIT: TEST MODE VS PRODUCTION PASS 2 ---
                
                # We skip normal testing mode if we are specifically running our email triage tool
                if testing and not triage_intercept:
                    # If testing, aggregate data (or handle empty strings if no valid tools ran)
                    test_output = "\n".join(all_raw_data) if valid_tool_executed else "No valid tools executed."
                    self.generate_and_speak(test_output)
                    self.ai_response_ready.emit(test_output)
                    store_conversation(user_prompt, test_output)
                    self._record_turn(user_prompt, test_output)
                    return

                # 4. Trigger Pass 2 ONLY if a valid function was safely executed (Production / Triage)
                if valid_tool_executed:
                    try:
                        # JARVIS INTERCEPT: If the email triage tool was called, swap out the history
                        # with a specialized directive to grade your inbox context.
                        if triage_intercept:
                            triage_prompt = f"""You are A.V.A's Inbox Triage Matrix. Analyze the raw multi-account email data dump provided in the tool output.
                            Extract and summarize ONLY critical, high-importance operational updates that require immediate attention:
                            - Payments (Invoices, Stripe receipts, balance transfers, financial alerts)
                            - Client Communications (Design briefs, visual identity feedback, Clastr Agency revisions)
                            - High-stakes Opportunities (Scholarships, major academic updates)

                            CRITICAL RULES:
                            1. Ignore all general system logs, newsletters, promotions, and normal conversational noise.
                            2. If a message matches, summarize it in a single concise sentence and note which inbox it hit (Personal vs. Business).
                            3. Maintain your signature A.V.A tone: calm, hyper-efficient, and minimal.
                            4. If absolutely nothing is critical or matches the guidelines, reply with EXACTLY: "All clear on the horizon, boss."
                            
                            Here is the user's inquiry: "{user_prompt}" """
                            
                            # Rebuild history with the unique triage instruction
                            messages_history = [
                                {"role": "system", "content": triage_prompt},
                                {"role": "user", "content": user_prompt},
                                response_message,
                                # Include the raw harvested email string package
                                {"role": "tool", "tool_call_id": tool_calls[0].id, "name": "check_critical_inbox_triage", "content": "\n".join(all_raw_data)}
                            ]

                        second_pass = client.chat.completions.create(
                            model="openai/gpt-oss-20b",
                            messages=messages_history,
                            temperature=1.0 # High temp to encourage a more conversational, human-like response
                        )
                        final_text = second_pass.choices[0].message.content or ""
                        
                    except Exception as api_err:
                        final_text = f"SYSTEM LAYER // Second-pass context negotiation failed: {str(api_err)}"
                else:
                    final_text = "I flagged a mismatch in my operational pipeline. Request canceled."

                # 5. Output pipeline delivery
                self.generate_and_speak(final_text)
                self.ai_response_ready.emit(final_text)
                store_conversation(user_prompt, final_text)
                self._record_turn(user_prompt, final_text)
                lcd_output(final_text)
                return

            # ==========================================
            # PATH B: STANDARD CHAT ROUTING / NO TOOLS
            # ==========================================
            if response_message.content:
                ai_text = response_message.content
                store_conversation(user_prompt, ai_text)
                self._record_turn(user_prompt, ai_text)
                self.generate_and_speak(ai_text)
                self.ai_response_ready.emit(ai_text)
                lcd_output(ai_text)
            else:
                msg = "SYSTEM LAYER // Diagnostic balance stable."
                self.ai_response_ready.emit(msg)
                lcd_output(msg) # Send the final text to the LCD display
                    
        except Exception as e:
            err_text = str(e)
            # Catching the XML fallback injection string pattern
            raw_match = re.search(r"<function=([a-zA-Z_][a-zA-Z0-9_]*)(?:>)?(.*?)</function>", err_text, re.DOTALL)
            
            if raw_match:
                func_name = raw_match.group(1)
                raw_args_text = raw_match.group(2).strip()
                if not raw_args_text or raw_args_text == "{":
                    func_args = {}
                else:
                    try:
                        func_args = json.loads(raw_args_text)
                    except json.JSONDecodeError:
                        func_args = {}

                # 1. Run the function in the background (e.g. play the song)
                raw_tool_data = route_to_agent(self, func_name, func_args)

                # 2. Re-build the localized chat timeline manual structure for fallback
                messages_history = [
                    {"role": "system", "content": system_message},
                    *self.conversation_history,
                    {"role": "user", "content": user_prompt},
                    # Fake the assistant's request so the history sequence remains structurally valid
                    {"role": "assistant", "content": None, "tool_calls": [
                        {
                            "id": "call_fallback_id",
                            "type": "function",
                            "function": {"name": func_name, "arguments": json.dumps(func_args)}
                        }
                    ]}
                ]
                
                # 3. Append the execution data status back into the chain
                messages_history.append({
                    "role": "tool",
                    "tool_call_id": "call_fallback_id",
                    "name": func_name,
                    "content": str(raw_tool_data)
                })

                # 4. Fire Pass 2 to let Jarvis formulate a dynamic response based on execution success
                try:
                    second_pass = client.chat.completions.create(
                        model="openai/gpt-oss-20b",
                        messages=messages_history,
                        temperature=1.0  # High temp to encourage a more conversational, human-like response
                    )
                    final_text = second_pass.choices[0].message.content or ""
                except Exception as inner_err:
                    final_text = f"SYSTEM LAYER // Conversational re-route crashed: {str(inner_err)}"

                # 5. Output pipeline delivery
                store_conversation(user_prompt, final_text)
                self._record_turn(user_prompt, final_text)
                self.generate_and_speak(final_text)
                self.ai_response_ready.emit(final_text)
                lcd_output(final_text) # Send the final text to the LCD display
                return

            # Real system layer breakages
            err_msg = f"CORE TRANSMISSION FAILURE // {err_text}"
            self.ai_response_ready.emit(err_msg)
            lcd_output(err_msg)

@send_to_lcd
def lcd_output(text: str) -> str:
    return text

class WebAssistantApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(500, 500)
        
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        layout = QVBoxLayout(); layout.setContentsMargins(0, 0, 0, 0)
        self.browser_view = QWebEngineView()
        self.browser_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        
        self.comms_channel = QWebChannel()
        self.bridge_instance = AICommunicationBridge(self.media_player, self.audio_output)
        
        # Connect the asynchronous thread signal back to the HTML layout display helper
        self.bridge_instance.ai_response_ready.connect(self.display_ai_response_in_ui)
        
        self.comms_channel.registerObject("backend", self.bridge_instance)
        self.browser_view.page().setWebChannel(self.comms_channel)
        
        self.browser_view.setUrl(QUrl.fromLocalFile(os.path.abspath("interface.html")))
        layout.addWidget(self.browser_view); self.setLayout(layout)

        # Fire continuous microphone background threads
        self.voice_thread = VoiceListenerWorker()
        self.voice_thread.text_recognized.connect(self.route_voice_command)
        self.voice_thread.start()

        # Fire the hardware button listener now that bridge_instance exists.
        # On trigger, this feeds "Hi" straight into the real AI pipeline
        # (get_ai_response), which already handles: Groq call, tool routing,
        # TTS, emitting back to the on-screen UI, and writing to the LCD.
        # Flip HARDWARE_ENABLED in helpers.py to False to skip this entirely
        # when you're not connected to the Arduino.
        if HARDWARE_ENABLED:
            self.button_thread = threading.Thread(
                target=listen_for_button,
                args=(self.handle_button_press,),
                kwargs={"prompt": "Hey what do I have for today?"},
                daemon=True
            )
            self.button_thread.start()
        else:
            print("[System] Hardware button disabled - skipping button thread.")

    def handle_button_press(self, prompt_text):
        """Runs the moment the physical button is pressed."""
        print("\n[Hardware Event] Button pressed! Alerting A.V.A...")
        lcd_output("A.V.A is thinking...")  # Immediate feedback on the LCD
        self.bridge_instance.get_ai_response(prompt_text)  # Routes to screen + LCD via existing pipeline

    def route_voice_command(self, transcript_text):
        js_injection = f"""
        if (typeof runAICommand === 'function') {{
            runAICommand("{transcript_text}");
        }} else if (document.getElementById('inputBar')) {{
            document.getElementById('inputBar').value = "{transcript_text}";
            var e = new KeyboardEvent('keydown', {{ 'key': 'Enter' }});
            document.getElementById('inputBar').dispatchEvent(e);
        }}
        """
        self.browser_view.page().runJavaScript(js_injection)

    def display_ai_response_in_ui(self, response_text):
        """Safely injects the completed AI text string directly back into your front-end layout."""
        safe_response = response_text.replace('"', '\\"').replace('\n', '\\n')
        
        js_injection = f"""
        var target = document.getElementById('output-readout');
        if (target) {{
            target.innerText = "{safe_response}";
        }} else if (typeof displayResponse === 'function') {{
            displayResponse("{safe_response}");
        }}
        """
        self.browser_view.page().runJavaScript(js_injection)

        def closeEvent(self, event):
            self.voice_thread.running = False; self.voice_thread.wait(); event.accept()

if __name__ == "__main__":
    # Disable heavy 3D rendering elements if you're only showing text/flat UI
    os.environ["QT_WEBENGINE_DISABLE_GPU"] = "1" 
    
    app = QApplication(sys.argv)
    window = WebAssistantApp()
    window.show()
    sys.exit(app.exec())