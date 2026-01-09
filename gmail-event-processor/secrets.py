from google.cloud import secretmanager
import json

PROJECT_ID = "YOUR_PROJECT_ID"

def access_secret(secret_name):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(name=name)
    return response.payload.data.decode("utf-8")

def load_gmail_token():
    return json.loads(access_secret("gmail-token"))

def load_gemini_api_key():
    return access_secret("gemini-api-key")
