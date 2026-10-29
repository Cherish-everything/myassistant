import sys
import subprocess
import time
import datetime
import pyautogui
import os
from googleapiclient.discovery import build
from google_auth import get_google_services
import json
import base64
import re
from groq import Groq


from dotenv import load_dotenv
load_dotenv()  # reads .env file and loads keys into environment
groq_client = Groq()
EMAIL_STATE_FILE = "email_watch_state.json"
MAX_SEEN_IDS_PER_ACCOUNT = 300  # keeps the state file from growing forever
EMAIL_LOG_FILE = "important_emails.md"

def send_whatsapp_message(contact_name: str, message_content: str) -> str:
    """Automates sending a WhatsApp message to a specific contact using the desktop app."""
    
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", "whatsapp:"], shell=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "whatsapp://"])
    
    time.sleep(3.0)
    
    if sys.platform == "win32":
        pyautogui.hotkey('ctrl', 'f')
    else:
        pyautogui.hotkey('command', 'f')
    time.sleep(1)
    
    pyautogui.write(contact_name)
    time.sleep(1)
    pyautogui.press('down')
    time.sleep(0.5)
    pyautogui.press('enter')
    time.sleep(0.2)
    pyautogui.write(message_content)
    pyautogui.press('enter')
    return f"TRANSMITTING // Desktop App message routed to [{contact_name.upper()}]: '{message_content}'"

# =====================================================================
# HELPER FUNCTIONS & STATE MANAGEMENT
# =====================================================================

def _load_seen_ids(state_file: str) -> dict:
    """Loads the {account: [message_id, ...]} map of processed emails."""
    if not os.path.exists(state_file):
        return {}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_seen_ids(state_file: str, seen: dict) -> None:
    """Saves updated seen message IDs to state file."""
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)

def get_email_body(payload: dict) -> str:
    """Extracts email body"""

    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
            elif 'parts' in part:
                res = get_email_body(part)
                if res:
                    return res
            elif 'body' in payload and 'data' in payload['body']:
                return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
            return ""

def log_email_to_markdown(email_data: dict) -> None:
    """Logs important email content to the markdown file for AVA to read later."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = f"""
    ## [{timestamp}] {email_data['subject']}
    - **Account:** {email_data['account'].upper()}
    - **From:** {email_data['from']}
    - **Message ID:** {email_data['id']}

    ### Content:
    ```text
        {email_data['body'].strip()}```
    """
    with open(EMAIL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def is_known_noise_or_important(sender: str, subject: str) -> tuple[bool, str]:
    """
    Returns (True/False, status)
    If status is 'SKIPPED_UNIMPORTANT', skip Groq (0 tokens).
    If status is 'SKIPPED_IMPORTANT', treat as important directly (0 tokens).
    If status is 'NEED_AI', pass to Groq.
    """
    sender_lower = sender.lower()
    subject_lower = subject.lower()

    # 1. Immediate skips (Newsletters / Automated / No-reply / Alerts)
    noise_keywords = [
        "noreply", "no-reply", "digest", "newsletter", "marketing", 
        "substack", "medium.com", "buymeacoffee", "zeerk", "cambly", 
        "wfp.sharethemeal", "jimmymaths", "icanstudy", "googleplay"
    ]
    if any(k in sender_lower for k in noise_keywords):
        return False, "SKIPPED_UNIMPORTANT"

    # 2. Immediate matches (Obvious inquiries or personal outreach)
    important_keywords = ["inquiry", "commission", "quote", "invoice", "urgent", "proposal", "contract"]
    if any(k in subject_lower for k in important_keywords):
        return True, "SKIPPED_IMPORTANT"

    return False, "NEED_AI"


def is_email_important(sender: str, subject: str, snippet: str) -> bool:
    """
    Ultra-lean classifier using minimal tokens.
    """
    # Check local rules first (0 tokens spent)
    is_imp, status = is_known_noise_or_important(sender, subject)
    if status != "NEED_AI":
        print(f"    [LOCAL RULE]: Classified as {status}")
        return is_imp

    # Ultra-compact prompt (~50 tokens total input instead of 300+)
    prompt = f"From: {sender[:40]}\nSubj: {subject[:60]}\nSnippet: {snippet[:80]}\n\nIs this a client inquiry, personal email, or urgent matter? Answer TRUE or FALSE."

    try:
        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": "Respond strictly with TRUE or FALSE."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=3  # Minimal token expenditure
        )
        raw_text = completion.choices[0].message.content or ""
        print(f"    [GROQ API CALL]: Raw output = '{raw_text.strip()}'")
        
        return "TRUE" in raw_text.strip().upper()

    except Exception as e:
        print(f"[EMAIL WATCHER] Groq error: {str(e)}")
        return True  # Fallback to avoid missing emails if API fails

def read_email_log() -> str:
    """Reads the .md file"""
    if not os.path.exists(EMAIL_LOG_FILE):
        return "No important emails logged yet."
    with open(EMAIL_LOG_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()
    
# =====================================================================
# GMAIL INBOX OPERATIONS & WATCHER
# =====================================================================

def check_for_new_emails(state_file: str = EMAIL_STATE_FILE) -> list:
    print("EMAIL CHECK RUNNING")
    with open(EMAIL_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("# Latest Important Emails\n\n")

    accounts = ["personal", "business"]
    seen = _load_seen_ids(state_file)
    alerts = []

    for acc in accounts:
        acc_seen = set(seen.get(acc, []))

        try:
            creds = get_google_services(account_type=acc)
            service = build('gmail', 'v1', credentials=creds)

            # Query without is:unread temporarily to test fetching
            query = "newer_than:7d -category:promotions -category:social"
            
            results = service.users().messages().list(
                userId='me', 
                q=query, 
                labelIds=['INBOX'],
                maxResults=10
            ).execute()
            
            messages = results.get('messages', [])
            print(f"[{acc.upper()}] Raw messages found from query: {len(messages)}")

            fresh_ids = [m['id'] for m in messages if m['id'] not in acc_seen]
            print(f"[{acc.upper()}] Unseen fresh message IDs: {len(fresh_ids)}")

            for msg_id in fresh_ids:
                meta = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
                headers = meta.get('payload', {}).get('headers', [])

                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
                snippet = meta.get('snippet', '')
                
                print(f"--> FETCHED: '{subject}' from '{sender}'")
                
                is_imp = is_email_important(sender, subject, snippet)
                print(f"--> GROQ VERDICT: {is_imp}")

                if is_imp:
                    full_body = get_email_body(meta.get('payload', {})) or snippet

                    email_payload = {
                        "account": acc,
                        "id": msg_id,
                        "from": sender,
                        "subject": subject,
                        "snippet": snippet,
                        "body": full_body
                    }

                    log_email_to_markdown(email_payload)
                    print("LOG SUCCESSFUL")

                    alerts.append({
                        **email_payload,
                        "prompt_action": (
                            f"New important email from {sender} regarding '{subject}'. "
                            f"Content logged to {EMAIL_LOG_FILE}. "
                            f"Notify the user and ask if they would like a summary or brief reading."
                        )
                    })

            acc_seen.update(m['id'] for m in messages)
            seen[acc] = list(acc_seen)[-MAX_SEEN_IDS_PER_ACCOUNT:]

        except Exception as e:
            print(f"[EMAIL WATCHER] {acc} check failed: {str(e)}")
            continue

    _save_seen_ids(state_file, seen)
    return alerts

#WORK ON THIS LATER
def reply_to_email(account: str, message_id: str, reply_body: str) -> str:
    """
    Replies directly to a specific email message using the specified account ('personal' or 'business').
    """
    try:
        from email.mime.text import MIMEText
        import base64

        creds = get_google_services(account_type=account)
        service = build('gmail', 'v1', credentials=creds)

        # Retrieve original email metadata for thread matching
        orig_msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        headers = orig_msg.get('payload', {}).get('headers', [])
        
        orig_from = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
        orig_subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
        thread_id = orig_msg.get('threadId')

        # Format Subject Line
        reply_subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"

        # Construct MIME Message
        mime_msg = MIMEText(reply_body)
        mime_msg['to'] = orig_from
        mime_msg['subject'] = reply_subject
        
        raw_string = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()

        send_payload = {
            'raw': raw_string,
            'threadId': thread_id
        }

        sent_msg = service.users().messages().send(userId='me', body=send_payload).execute()
        return f"SUCCESS // Reply transmitted via [{account.upper()}] to {orig_from} (Message ID: {sent_msg.get('id')})."

    except Exception as e:
        return f"REPLY FAILURE // Could not send email reply: {str(e)}"
