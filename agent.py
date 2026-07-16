import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from strands import Agent, tool
from strands.models.litellm import LiteLLMModel

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

SYSTEM_PROMPT = """You are a morning briefing assistant. When asked for a briefing, you MUST:

1. Call check_gmail to fetch recent emails
2. Call check_calendar to fetch upcoming events
3. Call check_slack to fetch recent Slack messages

Then synthesize everything into a briefing using exactly these five sections in this order:

URGENT
- Any emails or messages that require immediate attention or a same-day response

UPCOMING EVENTS
- All calendar events from the calendar tool, with time, location, and attendees

SLACK HIGHLIGHTS
- Key messages and conversations worth knowing about from each channel

OTHER EMAILS
- Remaining emails that are informational or low priority

SUGGESTED ACTIONS
- Concrete next steps the user should take based on everything above

Be concise. Use bullet points. Do not skip any section."""


def get_google_credentials() -> Credentials:
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())

    return creds


@tool
def check_gmail(hours_back: int = 12) -> str:
    """Fetch unread emails from Gmail from the last N hours.

    Args:
        hours_back: How many hours back to look for unread emails.

    Returns:
        A formatted string with sender, subject, date, and snippet for each email.
    """
    creds = get_google_credentials()
    service = build("gmail", "v1", credentials=creds)

    after_ts = int((datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp())
    query = f"is:unread after:{after_ts}"

    results = service.users().messages().list(userId="me", q=query, maxResults=20).execute()
    messages = results.get("messages", [])

    if not messages:
        return f"No unread emails in the last {hours_back} hours."

    emails = []
    for msg in messages:
        detail = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()

        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        snippet = detail.get("snippet", "")[:200]
        emails.append(
            f"From: {headers.get('From', 'unknown')}\n"
            f"Subject: {headers.get('Subject', '(no subject)')}\n"
            f"Date: {headers.get('Date', 'unknown')}\n"
            f"Snippet: {snippet}"
        )

    return f"Unread emails (last {hours_back}h):\n\n" + "\n\n".join(emails)


@tool
def check_calendar(hours_ahead: int = 24) -> str:
    """Fetch upcoming Google Calendar events for the next N hours.

    Args:
        hours_ahead: How many hours ahead to look for events.

    Returns:
        A formatted string with title, start, end, location, and attendees per event.
    """
    creds = get_google_credentials()
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(hours=hours_ahead)).isoformat()

    results = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = results.get("items", [])

    if not events:
        return f"No calendar events in the next {hours_ahead} hours."

    output = []
    for event in events:
        start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "")
        end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date", "")
        location = event.get("location", "No location")
        attendees = [a.get("email", "") for a in event.get("attendees", [])]
        attendees_str = ", ".join(attendees) if attendees else "No attendees"

        output.append(
            f"Event: {event.get('summary', '(no title)')}\n"
            f"Start: {start}\n"
            f"End: {end}\n"
            f"Location: {location}\n"
            f"Attendees: {attendees_str}"
        )

    return f"Upcoming events (next {hours_ahead}h):\n\n" + "\n\n".join(output)


@tool
def check_slack(hours_back: int = 12, max_channels: int = 5) -> str:
    """Fetch recent messages from the most active Slack channels.

    Args:
        hours_back: How many hours back to look for messages.
        max_channels: Maximum number of channels to check.

    Returns:
        A formatted string with channel names and recent messages.
    """
    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    oldest = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp()

    try:
        response = client.conversations_list(types="public_channel,private_channel", limit=200)
        channels = response.get("channels", [])
    except SlackApiError as e:
        return f"Slack error listing channels: {e.response['error']}"

    # find channels with recent activity
    active = []
    for ch in channels:
        last_read = float(ch.get("last_read", "0") or "0")
        if last_read >= oldest:
            active.append(ch)

    # fall back to any joined channels if none have recent activity timestamps
    if not active:
        active = [ch for ch in channels if ch.get("is_member")]

    active = active[:max_channels]

    if not active:
        return "No accessible Slack channels found."

    output = []
    for ch in active:
        ch_name = ch.get("name", ch["id"])
        try:
            history = client.conversations_history(
                channel=ch["id"],
                oldest=str(oldest),
                limit=5,
            )
            msgs = history.get("messages", [])
            if not msgs:
                continue

            lines = [f"#{ch_name}:"]
            for m in msgs:
                user = m.get("user", m.get("username", "unknown"))
                text = m.get("text", "").replace("\n", " ")[:200]
                lines.append(f"  [{user}]: {text}")
            output.append("\n".join(lines))
        except SlackApiError as e:
            output.append(f"#{ch_name}: error – {e.response['error']}")

    if not output:
        return f"No Slack messages in the last {hours_back} hours."

    return f"Slack messages (last {hours_back}h):\n\n" + "\n\n".join(output)


def run():
    model = LiteLLMModel(
        model_id="openrouter/openrouter/free",
        params={
            "max_tokens": 4096,
            "api_base": "https://openrouter.ai/api/v1",
            "api_key": os.environ["OPENROUTER_API_KEY"],
        },
    )

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[check_gmail, check_calendar, check_slack],
    )

    response = agent("What did I miss? Give me my morning briefing.")
    print(response)


if __name__ == "__main__":
    run()
