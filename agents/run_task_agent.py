from tools import (
    create_google_calendar_event, 
    add_google_task, 
    get_active_tasks, 
    complete_google_task,
    get_agenda_for_date
    )

# WORKING!
def run_task_agent(ui_context, tool_name, args):
    """Handles everything related to mission objectives, tasks, and productivity."""

    account_type = args.get("account_type", "personal")  # Default to personal if not specified

    if tool_name == "create_google_calendar_event": #Edit this to use the parser
        return create_google_calendar_event(args, account_type=account_type)
    
    elif tool_name == "add_new_task":
        title = args.get("title")
        notes = args.get("notes", "")
        return add_google_task(title=title, notes=notes)
        
    elif tool_name == "view_active_tasks":
        return get_active_tasks()
        
    elif tool_name == "resolve_completed_task":
        target = args.get("target") # Can be a string index ("1") or phrase ("edit video")
        return complete_google_task(task_title_or_index=target)
    
    elif tool_name == "get_agenda_for_date":
        print(f"[TASK AGENT] Received request to get agenda for date with args: {args}")
        date_query = args.get("date_query", "today")  # Default to today if not specified
        return get_agenda_for_date(date_query=date_query, account_type=account_type)
    
    return f"Task Agent: '{tool_name}' completed."
        