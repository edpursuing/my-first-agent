# my-first-agent

A personal morning briefing agent that reads Gmail, Google Calendar, and Slack, then synthesizes everything into a structured daily digest. Built with [Strands Agents](https://strandsagents.com/) and served via OpenRouter.

## What it does

On each run the agent calls three tools in parallel, then produces a five-section briefing:

| Section | Source |
|---|---|
| **URGENT** | Emails or Slack messages needing same-day response |
| **UPCOMING EVENTS** | Google Calendar events in the next 24 hours |
| **SLACK HIGHLIGHTS** | Recent messages across active channels |
| **OTHER EMAILS** | Informational / low-priority inbox items |
| **SUGGESTED ACTIONS** | Concrete next steps synthesized across all sources |

## Architecture

```
agent.py
├── check_gmail       → Gmail API (read-only), last 12h of unread mail
├── check_calendar    → Google Calendar API (read-only), next 24h of events
└── check_slack       → Slack SDK, last 12h across up to 5 active channels

Model: OpenRouter (LiteLLM) — swap model_id in run() to use any provider
Framework: Strands Agents
Auth: Google OAuth 2.0 (token auto-refreshes); Slack Bot Token via env
```

## Setup

### 1. Clone and install

```bash
git clone https://github.com/edpursuing/my-first-agent
cd my-first-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file in the project root:

```
OPENROUTER_API_KEY=your_openrouter_key
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
```

The Slack bot needs these OAuth scopes: `channels:history`, `channels:read`, `groups:history`, `groups:read`.

### 3. Google OAuth

Download a `credentials.json` (OAuth 2.0 Desktop client) from [Google Cloud Console](https://console.cloud.google.com/) with Gmail and Calendar APIs enabled. Place it in the project root, then run:

```bash
python auth_google.py
```

This opens a browser for consent and writes `token.json`. The token auto-refreshes on subsequent runs — you only need to do this once.

### 4. Run

```bash
python agent.py
```

## Current capabilities

- Reads up to 20 unread emails from the last 12 hours (configurable via `hours_back`)
- Reads calendar events for the next 24 hours (configurable via `hours_ahead`)
- Reads the last 5 messages across up to 5 of the most recently active Slack channels (both configurable)
- All three tools are `@tool`-decorated and callable independently — easy to extend or rewire

## Limitations / known gaps

- **Read-only** — cannot reply to emails, create calendar events, or send Slack messages
- **Single-user** — Google auth is tied to one OAuth token; no multi-tenant support
- **No memory** — each run is stateless; the agent has no awareness of prior briefings
- **Model dependency** — currently uses OpenRouter's free tier; output quality varies by which model is routed
- Slack channel selection is heuristic (last-read timestamp), not semantic

## Integration surface

The three tool functions (`check_gmail`, `check_calendar`, `check_slack`) are self-contained and return plain strings. They can be imported and registered into any Strands agent or called directly. The `run()` function in `agent.py` is a thin wrapper and can be replaced with a scheduler, webhook trigger, or REST endpoint as needed.
