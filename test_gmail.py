import os
import base64
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from strands import Agent, tool
from strands.models.litellm import LiteLLMModel

load_dotenv()

model = LiteLLMModel(
    model_id="openrouter/openrouter/free",
    params={
        "max_tokens": 512,
        "api_base": "https://openrouter.ai/api/v1",
        "api_key": os.environ["OPENROUTER_API_KEY"],
    },
)


@tool
def get_recent_emails() -> str:
    """Fetch the last 5 emails from Gmail and return sender, subject, and snippet."""
    creds = Credentials.from_authorized_user_file("token.json")
    service = build("gmail", "v1", credentials=creds)

    results = service.users().messages().list(userId="me", maxResults=5).execute()
    messages = results.get("messages", [])

    emails = []
    for msg in messages:
        detail = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject"]
        ).execute()

        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        emails.append(
            f"From: {headers.get('From', 'unknown')}\n"
            f"Subject: {headers.get('Subject', '(no subject)')}\n"
            f"Snippet: {detail.get('snippet', '')}"
        )

    return "\n\n".join(emails)


agent = Agent(
    model=model,
    system_prompt="You are a helpful assistant that summarizes emails clearly and concisely.",
    tools=[get_recent_emails],
)

if __name__ == "__main__":
    response = agent("Use the get_recent_emails tool to fetch my last 5 emails and give me a brief summary of each.")
    print(response)
