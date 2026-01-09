import base64
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/pubsub/gmail")
async def pubsub_handler(request: Request):
    envelope = await request.json()

    if "message" not in envelope:
        return {"status": "ignored"}

    # Decode message (optional, but fine)
    base64.b64decode(envelope["message"]["data"]).decode()

  
    from gmail_processor import process_new_emails
    process_new_emails()

    return {"status": "ok"}
