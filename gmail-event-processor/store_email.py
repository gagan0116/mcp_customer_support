import json
import base64
from datetime import datetime, timezone
from typing import Dict, Any

from google.cloud import storage


BUCKET_NAME = "refunds_bucket"


def _serialize_for_json(obj: Any):
    """
    JSON serializer that converts raw bytes to base64.
    """
    if isinstance(obj, (bytes, bytearray)):
        return {
            "__type__": "bytes",
            "encoding": "base64",
            "data": base64.b64encode(obj).decode("ascii"),
        }

    raise TypeError(f"Type {type(obj)} is not JSON serializable")


def _normalize_timestamp(received_at) -> datetime:
    """
    Accepts datetime | ISO string | epoch
    Returns UTC datetime
    """
    if isinstance(received_at, datetime):
        return received_at.astimezone(timezone.utc)

    if isinstance(received_at, str):
        return datetime.fromisoformat(received_at).astimezone(timezone.utc)

    if isinstance(received_at, (int, float)):
        return datetime.fromtimestamp(received_at, tz=timezone.utc)

    # Fallback
    return datetime.now(timezone.utc)


def store_email_result(result: Dict):
    """
    Stores processed email result in Cloud Storage.

    Expects result in this shape:
    {
        "category": str,
        "confidence": float,
        "user_id": str,
        "received_at": datetime | str | epoch,
        "email_body": str,
        "attachments": [ { ..., "data": bytes } ]
    }
    """

    user_id = result.get("user_id")
    received_at = result.get("received_at")

    if not user_id:
        raise ValueError("user_id is required to store email")

    timestamp = _normalize_timestamp(received_at)

    ts = timestamp.strftime("%Y%m%dT%H%M%SZ")
    safe_user = user_id.replace("@", "_at_").replace(".", "_")

    blob_path = f"{safe_user}/{safe_user}_{ts}.json"

    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(blob_path)

    blob.upload_from_string(
        json.dumps(
            result,
            indent=2,
            default=_serialize_for_json,  # ✅ handles raw bytes
        ),
        content_type="application/json",
    )

    print(f"📦 Stored email in gs://{BUCKET_NAME}/{blob_path}")
