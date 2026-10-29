# google_auth.py
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# The scopes define exactly what A.V.A has permission to read/write
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/gmail.modify',
]

def get_google_services(account_type: str):
    """Authenticates the user and returns valid API credentials."""
    """Returns credentials for either 'personal' or 'business' accounts dynamically."""
    creds_file = f"credentials_{account_type}.json"
    token_file = f"token_{account_type}.json"
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"[AUTH REFRESH FAILED for {account_type}]: {e}. Re-authenticating...")
                creds = None  # Force re-authentication if refresh token was invalidated
        
        if not creds:
            if not os.path.exists(creds_file):
                raise FileNotFoundError(
                    f"Google OAuth client secret file not found: '{creds_file}'."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')

        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    return creds

if __name__ == "__main__":
    # Delete old tokens if forcing a fresh re-auth
    for acc in ["personal", "business"]:
        tf = f"token_{acc}.json"
        if os.path.exists(tf):
            os.remove(tf)

    get_google_services("personal")
    get_google_services("business")
    print("\n[COMPLETE] Both tokens generated with permanent refresh access!")