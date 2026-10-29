import datetime 
from datetime import timezone, timedelta
import dateparser
from typing import Optional, Union
from datetime import datetime as _dt
import os
import json
from googleapiclient.discovery import build
from google_auth import get_google_services
import traceback
from dateutil.relativedelta import relativedelta, SA, MO, TU, WE, TH, FR, SU

#--------------------------------
# HELPER FUNCTIONS
#--------------------------------
GMT_PLUS_8 = timezone(timedelta(hours=8))

WEEKDAYS = {
    'monday': MO, 'tuesday': TU, 'wednesday': WE,
    'thursday': TH, 'friday': FR, 'saturday': SA, 'sunday': SU
}

def get_current_date_gmt8() -> datetime.date:
    return datetime.datetime.now(GMT_PLUS_8).date()

def resolve_date_string(date_input: Union[str, datetime.date]) -> datetime.date:
    """Accurately resolves relative day queries and ISO dates in GMT+8."""
    if isinstance(date_input, datetime.date) and not isinstance(date_input, datetime.datetime):
        return date_input
        
    if not date_input or not isinstance(date_input, str):
        return get_current_date_gmt8()

    clean_input = date_input.strip().lower()
    today_gmt8 = get_current_date_gmt8()

    # 1. Direct Relative Day Keywords
    if clean_input in ["today", "now"]:
        return today_gmt8
    elif clean_input == "tomorrow":
        return today_gmt8 + datetime.timedelta(days=1)
    elif clean_input == "yesterday":
        return today_gmt8 - datetime.timedelta(days=1)

    # 2. Weekday Handling ("this saturday", "next monday", "coming friday")
    for day_name, weekday_obj in WEEKDAYS.items():
        if day_name in clean_input:
            # Resolves to the upcoming target weekday relative to today
            target_dt = today_gmt8 + relativedelta(weekday=weekday_obj(+1))
            return target_dt

    # 3. Fallback to dateparser for explicit dates ("Oct 3", "2026-10-03", "in 3 days")
    now_naive = datetime.datetime.now()
    parsed_dt = dateparser.parse(
        clean_input,
        settings={
            'PREFER_DATES_FROM': 'future',
            'RELATIVE_BASE': now_naive
        }
    )

    if parsed_dt:
        return parsed_dt.date()

    return today_gmt8

def get_calendar_events_for_date(target_date: datetime.date, account_type="personal") -> list:
    """Retrieves calendar events for a date in GMT+8."""
    if isinstance(target_date, str):
        target_date = resolve_date_string(target_date)
    elif isinstance(target_date, datetime.datetime):
        target_date = target_date.date()

    try:
        creds = get_google_services(account_type=account_type)
        print("Credentials loaded successfully")
        
        service = build('calendar', 'v3', credentials=creds)

        date_str = target_date.strftime('%Y-%m-%d')
        start_of_day = f"{date_str}T00:00:00+08:00"
        end_of_day = f"{date_str}T23:59:59+08:00"
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_of_day,
            timeMax=end_of_day,
            timeZone='Asia/Singapore',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        print(f"Targeting: {target_date} | Events Retrieved: {len(events_result.get('items', []))}")
        return events_result.get('items', [])
        
    except Exception as e:
        print(f"[CALENDAR CRASH AT HereC1]: {e}")
        traceback.print_exc()
        return []
    
    return f"A.V.A: I ran into an error fetching your agenda: {str(e)}"

def get_active_tasks(target_date: Optional[datetime.date] = None, account_type="personal") -> list:
    print("HereT1")
    if target_date is None:
        target_date = get_current_date_gmt8()

    creds = get_google_services(account_type=account_type)
    service = build('tasks', 'v1', credentials=creds)
    print("HereT2")
    results = service.tasks().list(
        tasklist='@default',
        maxResults=100,
        showCompleted=False
    ).execute()
    
    all_tasks = results.get('items', [])
    filtered_tasks = []
    target_date_str = target_date.strftime('%Y-%m-%d')
    
    for task in all_tasks:
        due_str = task.get('due')
        if due_str:
            utc_dt = datetime.datetime.fromisoformat(due_str.replace('Z', '+00:00'))
            gmt8_dt = utc_dt.astimezone(GMT_PLUS_8)
            
            # Print each task as it's checked
            print(f"Checking Task: '{task.get('title')}' | Due: {gmt8_dt.strftime('%Y-%m-%d')} | Target: {target_date_str}")
            
            if gmt8_dt.strftime('%Y-%m-%d') == target_date_str:
                filtered_tasks.append(task)

    print(f"Targeting: {target_date_str} | Total Matched Tasks: {len(filtered_tasks)}")
    return filtered_tasks

#--------------------------------
# GET AGENDA FUNCTIONS
#--------------------------------
def get_agenda_for_date(date_query: Optional[str] = "today", account_type="personal") -> dict:
    """
    Retrieves agenda (events and tasks) for any relative or explicit date string.
    Examples: 'today', 'tomorrow', 'next monday', 'in 3 days', '2026-10-05'
    """
    target_date = resolve_date_string(date_query)
    print(f"[TASK AGENT] Resolved date query '{date_query}' to target date: {target_date}")
    try:
        print("Here1")
        events = get_calendar_events_for_date(target_date, account_type=account_type)
        tasks = get_active_tasks(target_date, account_type=account_type)
        print("Here2")
        event_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            time_str = start.split('T')[1][:5] if 'T' in start else "All-Day"
            event_list.append({
                "time": time_str,
                "summary": event.get('summary', 'Untitled Event')
            })
        print("Here3")
        task_list = [task.get('title') for task in tasks]
        
        return {
            "query_parsed_as": target_date.strftime('%A, %B %d, %Y'),
            "calendar_events": event_list,
            "tasks": task_list
        }
    except Exception as e:
        return {"error": f"Failed to load agenda for '{date_query}': {str(e)}"}

#--------------------------------
# MODIFYING FUNCTIONS
#--------------------------------
def create_google_calendar_event(args, account_type: str = "personal") -> str:
    """
    Executes the direct Google Calendar injection payload.
    Expects args dict containing: 'task_description', 'start_time', and 'end_time'.
    """
    try:
        creds = get_google_services(account_type=account_type)
       
        service = build('calendar', 'v3', credentials=creds)
        
        if not isinstance(args, dict):
            return "TASK FAILURE // Invalid argument structural format. Arguments must be a dict."
            
        title = args.get("task_description") or args.get("title") or "A.V.A Scheduled Task"
        start_time = args.get("start_time") 
        end_time = args.get("end_time") or args.get("start_time") + "PT1H"  # Default to 1 hour if end_time not provided
        
        if not start_time or not end_time:
            return "TASK FAILURE // Missing required parameters: 'start_time'"
        
        event_payload = {
            'summary': title,
            'description': 'Generated automatically by A.V.A (Artificial Virtual Assistant)',
            'start': {
                'dateTime': start_time, 
                'timeZone': 'Asia/Singapore'  # Synchronized with your local environment
            },
            'end': {
                'dateTime': end_time, 
                'timeZone': 'Asia/Singapore'
            },
        }
        
        # 4. Fire it to Google's cloud servers
        event = service.events().insert(calendarId='primary', body=event_payload).execute()
        
        return f"SUCCESS // Synced event safely. Link: {event.get('htmlLink')}"
        
    except Exception as err:
        return f"TASK FAILURE // Google API integration execution rejected: {str(err)}"

def add_google_task(title, notes=None):
    """Creates a fresh task item under your primary default task list."""
    try:
        service = build("tasks", "v1", credentials=get_google_services())
        task_data = {"title": title}
        if notes:
            task_data["notes"] = notes
            
        # '@default' targets your main account inbox list natively
        result = service.tasks().insert(tasklist="@default", body=task_data).execute() #
        return f"SUCCESS // Task added: '{result.get('title')}'"
    except Exception as e:
        return f"TASK ERROR // Generation failed: {str(e)}"

def complete_google_task(task_title_or_index):
    """Finds an active task by title matching or string index, then flags it complete."""
    try:
        service = build("tasks", "v1", credentials=get_google_services())
        results = service.tasks().list(tasklist="@default", maxResults=30, showCompleted=False).execute() #
        items = results.get("items", [])
        
        target_task = None
        
        # 1. Attempt to match via an integer index parameter (e.g., "1")
        if task_title_or_index.isdigit():
            idx = int(task_title_or_index) - 1
            if 0 <= idx < len(items):
                target_task = items[idx]
        else:
            # 2. Attempt fuzzy text string parsing alternative
            for item in items:
                if task_title_or_index.lower() in item['title'].lower():
                    target_task = item
                    break
                    
        if not target_task:
            return f"MATCH FAILURE // No active task matches parameter: '{task_title_or_index}'"
            
        # To resolve a task in Google's schema, you patch its status to 'completed'
        target_task['status'] = 'completed' #
        service.tasks().patch(tasklist="@default", task=target_task['id'], body=target_task).execute() #
        
        return f"SUCCESS // Cleared task objective: '{target_task['title']}'"
    except Exception as e:
        return f"TASK ERROR // Completion pipeline blocked: {str(e)}"