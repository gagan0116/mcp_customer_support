import base64
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from secrets import load_gmail_token
from history_store import load_history_id, save_history_id
from classifier import classify_email, CONFIDENCE_THRESHOLD

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def html_to_text(html):
    return BeautifulSoup(html, "html.parser").get_text()

def extract_body(payload):
    for part in payload.get("parts", []):
        if part["mimeType"] == "text/plain" and "data" in part["body"]:
            return base64.urlsafe_b64decode(part["body"]["data"]).decode()

        if part["mimeType"] == "text/html" and "data" in part["body"]:
            html = base64.urlsafe_b64decode(part["body"]["data"]).decode()
            return html_to_text(html)

    return ""

def process_new_emails():
    token = load_gmail_token()

    creds = Credentials(
        token=token.get("token"),
        refresh_token=token.get("refresh_token"),
        token_uri=token["token_uri"],
        client_id=token["client_id"],
        client_secret=token["client_secret"],
        scopes=token["scopes"],
    )

    service = build("gmail", "v1", credentials=creds)

    last_history_id = load_history_id()
    if not last_history_id:
        return

    history = service.users().history().list(
        userId="me",
        startHistoryId=last_history_id,
        historyTypes=["messageAdded"]
    ).execute()

    for h in history.get("history", []):
        for msg in h.get("messagesAdded", []):
            msg_id = msg["message"]["id"]

            email = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()

            headers = {h["name"]: h["value"] for h in email["payload"]["headers"]}
            subject = headers.get("Subject", "")
            body = extract_body(email["payload"])

            classification = classify_email(subject, body)

            if (
                classification["category"] == "RETURN"
                and classification["confidence"] >= CONFIDENCE_THRESHOLD
            ):
                print("✅ HIGH CONFIDENCE RETURN:", classification)

            save_history_id(int(h["id"]))
