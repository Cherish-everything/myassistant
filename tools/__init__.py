from .web import basic_web_search, get_weather_forecast, execute_deep_research
from .tasks import create_google_calendar_event, add_google_task, complete_google_task, get_agenda_for_date, get_active_tasks
from .message import send_whatsapp_message, check_for_new_emails, read_email_log
from .media import play_spotify
from .system import run_system_maintenance, get_visual_context, launch_system_application
from .ava_memory import store_conversation, store_fact, clear_conversation_memory, list_all_facts, retrieve_relevant_memory
from telegram_sync import start_telegram_sync