from tools import send_whatsapp_message, check_for_new_emails, read_email_log
# WORKING!
def run_comms_agent(ui_context, tool_name, args):
    """Handles all communication-related tasks, such as sending messages via WhatsApp."""
    
    if tool_name == "send_whatsapp_message":
        # Ensure args is a dictionary safely
        if not isinstance(args, dict):
            return "COMMS FAILURE // Arguments must be passed as a dictionary structured object."
            
        # Match the variables with what message.py expects
        recipient = args.get("phone_or_name", "")
        message = args.get("message", "")
        
        if not recipient or not message:
            return f"COMMS FAILURE // Missing fields. Got recipient: '{recipient}', message: '{message}'"
        
        return send_whatsapp_message(recipient, message)

    elif tool_name == "check_for_new_emails":
        return check_for_new_emails()
    
    elif tool_name == "read_email_log":
        return read_email_log()
        
    return f"Comms Agent: Operation '{tool_name}' completed."