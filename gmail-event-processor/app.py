import base64
import json
from fastapi import FastAPI, Request

from gmail_processor import process_new_emails

app = FastAPI()

@app.post("/pubsub/gmail")
async def pubsub_handler(request: Request):
    envelope = await request.json()

    if "message" not in envelope:
        return {"status": "ignored"}

    # Decode message (not strictly needed, but good practice)
    base64.b64decode(envelope["message"]["data"]).decode()

    process_new_emails()

    return {"status": "ok"}
