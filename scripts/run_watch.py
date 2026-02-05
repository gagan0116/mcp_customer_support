from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def rerun_watch_from_token_file():
    creds = Credentials.from_authorized_user_file(
        "token.json",
        SCOPES
    )

    service = build("gmail", "v1", credentials=creds)

    response = service.users().watch(
        userId="me",
        body={
            "labelIds": ["INBOX", "UNREAD"],
            "topicName": "projects/vara-483300/topics/gmail-inbox-topic"
        }
    ).execute()

    print("✅ WATCH RESTARTED")
    print("historyId:", response["historyId"])
    print("expiration:", response["expiration"])

if __name__ == "__main__":
    rerun_watch_from_token_file()
