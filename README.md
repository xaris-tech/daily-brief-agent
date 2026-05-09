# daily-brief-agent

AI Agent that fetches Slack mentions, Gmail, and Calendar to send you a daily morning summary.

Generated with `agents-cli` version `0.1.1`

## Project Structure

```
daily-brief-agent/
├── app/         # Core agent code
│   ├── agent.py               # Main agent logic with tools
│   ├── fast_api_app.py       # FastAPI app with cron scheduler
│   └── app_utils/             # App utilities and helpers
├── tests/                     # Unit, integration, and eval tests
├── .env.example              # Environment variables template
├── GEMINI.md                  # AI-assisted development guide
└── pyproject.toml             # Project dependencies
```

## Features

- **Slack mentions** - Fetch messages where you're @mentioned
- **Gmail** - Get recent important emails
- **Calendar** - See today's meetings
- **Daily brief** - Generate a combined summary
- **Cron scheduling** - Runs automatically at 8am daily (configurable)

## Setup

1. **Install dependencies:**
```bash
cd daily-brief-agent
uv sync
```

2. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. **Get Slack credentials:**
   - Create a Slack app at https://api.slack.com/apps
   - Add Bot Token Scopes: `channels:history`, `chat:write`, `channels:read`
   - Copy Bot User OAuth Token to `SLACK_BOT_TOKEN`
   - Get your Slack User ID (click your name in Slack → Copy member ID)

4. **Authenticate Google:**
```bash
gcloud auth application-default login
```

5. **Test locally:**
```bash
uv run python -c "from app.agent import send_daily_brief; print(send_daily_brief())"
```

## Running

### Option 1: Cron job (runs at 8am daily)
```bash
uv run python -m app.fast_api_app
```

### Option 2: On-demand via API
```bash
uv run python -m app.fast_api_app
# Then call: curl -X POST http://localhost:8000/trigger-daily-brief
```

### Option 3: Manual run
```bash
uv run python -c "from app.agent import send_daily_brief; print(send_daily_brief())"
```

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `SLACK_BOT_TOKEN` | Slack Bot OAuth Token | Yes |
| `SLACK_SIGNING_SECRET` | Slack Signing Secret | Yes |
| `SLACK_USER_ID` | Your Slack User ID | Yes |
| `USER_TIMEZONE` | Your timezone | No (default: America/New_York) |
| `DAILY_BRIEF_HOUR` | Hour to run (0-23) | No (default: 8) |
| `DAILY_BRIEF_MINUTE` | Minute to run (0-59) | No (default: 0) |

## Slack App Setup

1. Go to https://api.slack.com/apps
2. Create new app → From scratch
3. Add Bot Token Scopes:
   - `channels:history`
   - `channels:read`
   - `chat:write`
   - `groups:history`
   - `im:history`
   - `mpim:history`
   - `users:read`
4. Install to workspace
5. Copy the Bot User OAuth Token

## Development

```bash
# Run the agent
agents-cli run "What's my daily brief?"

# Or launch the playground
agents-cli playground
```

## Deployment

```bash
gcloud config set project <your-project-id>
agents-cli deploy
```