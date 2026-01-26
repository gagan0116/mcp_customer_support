import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# If modifying these scopes, delete the file token.json.
# Use a more permissive scope to allow reading, sending, and modifying emails.
SCOPES = ["https://mail.google.com/"]

def main():
    """
    Shows basic usage of the Gmail API.
    Logs in, generates token.json, and prepares for future email operations.
    """
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            print("No valid credentials found. Starting authentication flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        with open("token.json", "w") as token:
            token.write(creds.to_json())
            print("Authentication successful. 'token.json' created with full email access.")

    else:
        print("'token.json' already exists and is valid.")
        # Check if the existing token has the correct scopes
        if all(s in creds.scopes for s in SCOPES):
            print("Existing token has the required permissions. No action needed.")
        else:
            print("Existing token has insufficient permissions.")
            print("Please delete 'token.json' and run this script again to grant new permissions.")


if __name__ == "__main__":
    main()