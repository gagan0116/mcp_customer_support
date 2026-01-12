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
from fastapi import FastAPI, Request, Response


app = FastAPI()

@app.post("/pubsub/gmail")
async def pubsub_handler(request: Request):
    envelope = await request.json()

    if "message" not in envelope:
        return Response(status_code=204)

    try:
        payload = json.loads(
            base64.b64decode(envelope["message"]["data"]).decode("utf-8")
        )

        notification_history_id = payload["historyId"]
        from gmail_processor import process_new_emails

        results =process_new_emails(notification_history_id)
        print(results)
        return Response(status_code=200)  # ACK only on success

    except Exception as e:
        print("❌ Pub/Sub processing failed:", e)
        return Response(status_code=500)  # FORCE RETRY
