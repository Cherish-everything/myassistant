import os
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OBSIDIAN = os.environ.get("OBSIDIAN_VAULT_PATH")

INBOX_DIR = os.path.join(OBSIDIAN, "INBOX")
VOICE_DIR = os.path.join(OBSIDIAN, "VN")

os.makedirs(INBOX_DIR, exist_ok=True)
os.makedirs(VOICE_DIR, exist_ok=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        print("No messages")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    formatted_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if msg.voice or msg.audio:
        audio = msg.voice or msg.audio
        obj = await audio.get_file()

        audio_filename = f"vn_{timestamp}.ogg"
        audio_path = os.path.join(VOICE_DIR, audio_filename)

        await obj.download_to_drive(audio_path)

        note_content = f"""---
date: {formatted_date}
source: telegram
type: voice_note
tags: [inbox, voice-note]
---

# 🎙️ Voice Note Capture

![[{audio_filename}]]
"""

        # Save note directly inside INBOX_DIR
        note_path = os.path.join(INBOX_DIR, f"VN_{timestamp}.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(note_content)
        
        print(f"Saved voice note to {audio_path} and note to {note_path}")

    elif msg.text:
        note_content = f"""---
date: {formatted_date}
source: telegram
type: text
tags: [inbox, idea]

# 💡 Telegram Quick Capture

{msg.text.strip()}
"""
        note_path = os.path.join(INBOX_DIR, f"Idea_{timestamp}.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(note_content)

        print(f"Saved text note to {note_path}")

def start_telegram_sync():
    """Entry point to run the listener."""
    asyncio.sleep(30)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    print("Telegram Sync is running...")
    app.run_polling()

if __name__ == "__main__":
    start_telegram_sync()