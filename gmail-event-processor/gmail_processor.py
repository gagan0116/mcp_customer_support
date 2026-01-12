# import base64
# import re
# from typing import Dict, List, Tuple, Optional

# from bs4 import BeautifulSoup
# from googleapiclient.discovery import build
# from google.oauth2.credentials import Credentials

# from secret_manager import load_gmail_token
# from history_store import load_history_id, save_history_id
# from classifier import classify_email, CONFIDENCE_THRESHOLD


# SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# # -------------------------------------------------
# # HTML → TEXT
# # -------------------------------------------------
# def html_to_text(html: str) -> str:
#     return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


# # -------------------------------------------------
# # RECURSIVE MIME PARSER (BODY + ATTACHMENTS)
# # -------------------------------------------------
# def extract_parts(
#     payload: Dict,
#     service,
#     message_id: str,
# ) -> Tuple[str, List[Dict]]:
#     body_text = ""
#     attachments: List[Dict] = []

#     mime_type = payload.get("mimeType", "")
#     body = payload.get("body", {})

#     # ---- TEXT ----
#     if mime_type == "text/plain" and "data" in body:
#         body_text += base64.urlsafe_b64decode(
#             body["data"]
#         ).decode(errors="ignore")

#     elif mime_type == "text/html" and "data" in body:
#         html = base64.urlsafe_b64decode(
#             body["data"]
#         ).decode(errors="ignore")
#         body_text += html_to_text(html)

#     # ---- ATTACHMENT ----
#     filename = payload.get("filename")
#     attachment_id = body.get("attachmentId")

#     if filename and attachment_id:
#         att = (
#             service.users()
#             .messages()
#             .attachments()
#             .get(
#                 userId="me",
#                 messageId=message_id,
#                 id=attachment_id,
#             )
#             .execute()
#         )

#         attachments.append(
#             {
#                 "filename": filename,
#                 "data": base64.urlsafe_b64decode(att["data"]),
#                 "mimeType": mime_type,
#             }
#         )

#     # ---- RECURSE ----
#     for part in payload.get("parts", []):
#         text, files = extract_parts(part, service, message_id)
#         body_text += text
#         attachments.extend(files)

#     return body_text.strip(), attachments


# # -------------------------------------------------
# # USER ID EXTRACTION (EXPLICIT ONLY)
# # -------------------------------------------------
# def extract_user_id(text: str) -> Optional[str]:
#     patterns = [
#         r"user[_\s-]?id[:\s]+([a-zA-Z0-9\-]+)",
#         r"customer[_\s-]?id[:\s]+([a-zA-Z0-9\-]+)",
#         r"account[_\s-]?id[:\s]+([a-zA-Z0-9\-]+)",
#     ]

#     for p in patterns:
#         match = re.search(p, text, re.IGNORECASE)
#         if match:
#             return match.group(1)

#     return None


# # -------------------------------------------------
# # MAIN PROCESSOR
# # -------------------------------------------------
# def process_new_emails():
#     print("📥 Processing new emails")

#     token = load_gmail_token()

#     creds = Credentials(
#         token=token["token"],
#         refresh_token=token["refresh_token"],
#         token_uri=token["token_uri"],
#         client_id=token["client_id"],
#         client_secret=token["client_secret"],
#         scopes=token["scopes"],
#     )

#     service = build("gmail", "v1", credentials=creds)

#     last_history_id = load_history_id()

#     # ---- FIRST RUN ----
#     if not last_history_id:
#         profile = service.users().getProfile(userId="me").execute()
#         save_history_id(int(profile["historyId"]))
#         print("🆕 Initialized historyId")
#         return []

#     history = service.users().history().list(
#         userId="me",
#         startHistoryId=last_history_id,
#         historyTypes=["messageAdded"],
#     ).execute()

#     results = []
#     max_history_id = last_history_id

#     for h in history.get("history", []):
#         max_history_id = max(max_history_id, int(h["id"]))

#         for msg in h.get("messagesAdded", []):
#             msg_id = msg["message"]["id"]

#             email = service.users().messages().get(
#                 userId="me",
#                 id=msg_id,
#                 format="full",
#             ).execute()

#             headers = {
#                 h["name"].lower(): h["value"]
#                 for h in email["payload"]["headers"]
#             }

#             subject = headers.get("subject", "")

#             body, attachments = extract_parts(
#                 email["payload"], service, msg_id
#             )

#             user_id = extract_user_id(body)

#             classification = classify_email(subject, body)

#             if (
#                 classification["category"] == "RETURN"
#                 and classification["confidence"] >= CONFIDENCE_THRESHOLD
#             ):
#                 print("✅ High confidence RETURN detected")

#             results.append(
#                 {
#                     "category": classification["category"],
#                     "confidence": classification["confidence"],
#                     "user_id": user_id,
#                     "email_body": body,
#                     "attachments": attachments,  # RAW BYTES INCLUDED
#                 }
#             )

#     save_history_id(max_history_id)
#     return results


import base64
import re
from typing import Dict, List, Tuple, Optional

from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from secret_manager import load_gmail_token
from history_store import load_history_id, save_history_id
from classifier import classify_email, CONFIDENCE_THRESHOLD


# -------------------------------------------------
# HTML → TEXT
# -------------------------------------------------
def html_to_text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(
        separator=" ", strip=True
    )


# -------------------------------------------------
# RECURSIVE MIME PARSER
# -------------------------------------------------
def extract_parts(
    payload: Dict,
    service,
    message_id: str,
) -> Tuple[str, List[Dict]]:
    body_text = ""
    attachments: List[Dict] = []

    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})

    if mime_type == "text/plain" and "data" in body:
        body_text += base64.urlsafe_b64decode(
            body["data"]
        ).decode(errors="ignore")

    elif mime_type == "text/html" and "data" in body:
        html = base64.urlsafe_b64decode(
            body["data"]
        ).decode(errors="ignore")
        body_text += html_to_text(html)

    filename = payload.get("filename")
    attachment_id = body.get("attachmentId")

    if filename and attachment_id:
        att = (
            service.users()
            .messages()
            .attachments()
            .get(
                userId="me",
                messageId=message_id,
                id=attachment_id,
            )
            .execute()
        )

        attachments.append(
            {
                "filename": filename,
                "data": base64.urlsafe_b64decode(att["data"]),
                "mimeType": mime_type,
            }
        )

    for part in payload.get("parts", []):
        text, files = extract_parts(part, service, message_id)
        body_text += text
        attachments.extend(files)

    return body_text.strip(), attachments


# -------------------------------------------------
# USER ID EXTRACTION
# -------------------------------------------------
def extract_user_id(text: str) -> Optional[str]:
    patterns = [
        r"user[_\s-]?id[:\s]+([a-zA-Z0-9\-]+)",
        r"customer[_\s-]?id[:\s]+([a-zA-Z0-9\-]+)",
        r"account[_\s-]?id[:\s]+([a-zA-Z0-9\-]+)",
    ]

    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


# -------------------------------------------------
# MAIN PROCESSOR
# -------------------------------------------------
def process_new_emails():
    print("📥 Processing new emails")

    token = load_gmail_token()

    creds = Credentials(
        token=token["token"],
        refresh_token=token["refresh_token"],
        token_uri=token["token_uri"],
        client_id=token["client_id"],
        client_secret=token["client_secret"],
        scopes=token["scopes"],
    )

    service = build("gmail", "v1", credentials=creds)

    last_history_id = load_history_id()

    if not last_history_id:
        profile = service.users().getProfile(
            userId="me"
        ).execute()
        save_history_id(int(profile["historyId"]))
        print("🆕 Initialized historyId")
        return []

    history = service.users().history().list(
        userId="me",
        startHistoryId=last_history_id,
        historyTypes=["messageAdded"],
    ).execute()

    results = []
    max_history_id = last_history_id

    for h in history.get("history", []):
        max_history_id = max(
            max_history_id, int(h["id"])
        )

        for msg in h.get("messagesAdded", []):
            msg_id = msg["message"]["id"]

            email = service.users().messages().get(
                userId="me",
                id=msg_id,
                format="full",
            ).execute()

            headers = {
                h["name"].lower(): h["value"]
                for h in email["payload"]["headers"]
            }

            subject = headers.get("subject", "")
            body, attachments = extract_parts(
                email["payload"], service, msg_id
            )

            user_id = extract_user_id(body)
            classification = classify_email(subject, body)

            if (
                classification["category"] == "RETURN"
                and classification["confidence"]
                >= CONFIDENCE_THRESHOLD
            ):
                print("✅ High confidence RETURN detected")

            results.append(
                {
                    "category": classification["category"],
                    "confidence": classification["confidence"],
                    "user_id": user_id,
                    "email_body": body,
                    "attachments": attachments,
                }
            )

    save_history_id(max_history_id)
    return results
