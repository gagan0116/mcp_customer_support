import base64
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/pubsub/gmail")
async def pubsub_handler(request: Request):
    try:
        envelope = await request.json()

        if "message" not in envelope:
            return {"status": "ignored"}

        # Decode for completeness (not strictly required)
        data = envelope["message"].get("data")
        if data:
            base64.b64decode(data).decode("utf-8")
        from gmail_processor import process_new_emails
        process_new_emails()
        print("done processing email")
        return {"status": "ok"}

    except Exception as e:
        # VERY IMPORTANT: log but ACK
        print("❌ Error processing Pub/Sub message:", e)
        return {"status": "error-acked"}

