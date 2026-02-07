import json
import google.generativeai as genai
from secret_manager import load_gemini_api_key

CONFIDENCE_THRESHOLD = 0.75

CLASSIFICATION_PROMPT = """
You are an email classification system.

Classify the email into ONE category:
- RETURN
- REPLACEMENT
- REFUND
- NONE

Rules:
- RETURN: customer wants to return a product
- REPLACEMENT: damaged / defective / wrong item
- REFUND: wants money back
- NONE: unrelated

Extract user_id ONLY if explicitly mentioned.
Give a confidence score between 0 and 1.

Respond ONLY in valid JSON.

Email Subject:
{subject}

Email Body:
{body}
"""

def classify_email(subject, body):
    genai.configure(api_key=load_gemini_api_key())
    model = genai.GenerativeModel("models/gemini-3-flash-preview")

    body = body[:4000]

    response = model.generate_content(
        CLASSIFICATION_PROMPT.format(subject=subject, body=body),
        generation_config={
            "temperature": 0,
            "response_mime_type": "application/json"
        }
    )

    result = json.loads(response.text)
    if isinstance(result, list):
        if not result:
            result = {}
        else:
            result = result[0]
    return {
        "category": result.get("category", "NONE"),
        "user_id": result.get("user_id"),
        "confidence": float(result.get("confidence", 0))
    }
