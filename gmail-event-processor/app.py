# import base64
# from fastapi import FastAPI, Request

# app = FastAPI()

# @app.post("/pubsub/gmail")
# async def pubsub_handler(request: Request):
#     try:
#         print("🔥 PUBSUB TRIGGER RECEIVED")

#         envelope = await request.json()

#         if "message" not in envelope:
#             return {"status": "ignored"}

#         # Decode for completeness (not strictly required)
#         data = envelope["message"].get("data")
#         if data:
#             base64.b64decode(data).decode("utf-8")
#         from gmail_processor import process_new_emails
#         results=process_new_emails()
#         print(results)
#         print("done processing email")
#         return {"status": "ok"}
#     except Exception as e:
#         print("❌ Error processing Pub/Sub message:", e)
#         return {"status": "error-acked"}



import base64
import json
from flask import Flask, request

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from secret_manager import load_gmail_token
from history_store import save_history_id
from gmail_processor import process_new_emails

app = Flask(__name__)

PROJECT_ID = "YOUR_PROJECT_ID"
TOPIC_NAME = "YOUR_TOPIC_NAME"


# -------------------------------------------------
# Gmail API client
# -------------------------------------------------
def get_gmail_service():
    token = load_gmail_token()

    creds = Credentials(
        token=token["token"],
        refresh_token=token["refresh_token"],
        token_uri=token["token_uri"],
        client_id=token["client_id"],
        client_secret=token["client_secret"],
        scopes=token["scopes"],
    )

    return build("gmail", "v1", credentials=creds)


# -------------------------------------------------
# Create / renew Gmail watch
# -------------------------------------------------
def setup_gmail_watch():
    service = get_gmail_service()

    response = service.users().watch(
        userId="me",
        body={
            "topicName": f"projects/{PROJECT_ID}/topics/{TOPIC_NAME}",
            # ⚠️ Leave labelIds OUT while debugging
        },
    ).execute()

    print("📡 Gmail watch created:", response)

    # IMPORTANT: reset historyId after new watch
    save_history_id(int(response["historyId"]))


# -------------------------------------------------
# Pub/Sub PUSH endpoint
# -------------------------------------------------
@app.route("/", methods=["POST"])
def pubsub_handler():
    envelope = request.get_json()

    if not envelope or "message" not in envelope:
        return "Bad Request", 400

    # Decode Gmail push payload
    data = base64.b64decode(
        envelope["message"]["data"]
    ).decode("utf-8")

    payload = json.loads(data)
    print("📨 Gmail push received:", payload)

    # Process new emails using history API
    process_new_emails()

    return "OK", 200


# -------------------------------------------------
# Manual endpoint to (re)create watch (optional)
# -------------------------------------------------
@app.route("/setup-watch", methods=["POST"])
def setup_watch_endpoint():
    setup_gmail_watch()
    return "Watch created", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
