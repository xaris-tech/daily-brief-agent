# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Daily Brief Agent - Fetches Slack mentions, Gmail, and Calendar to send daily summary.

This agent runs on a cron schedule (default: 8am daily) and sends a personalized
daily brief to the user via Slack.
"""

import datetime
import os
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.tools import FunctionTool
from google.adk.models import Gemini
from google.genai import types

import google.auth

# Set up Google Cloud environment
try:
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
except Exception:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "default-project")

os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

# Environment variables (set these in .env or environment)
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
SLACK_USER_ID = os.environ.get("SLACK_USER_ID", "")  # Your Slack user ID
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")  # OAuth client secret
USER_TIMEZONE = os.environ.get("USER_TIMEZONE", "America/New_York")


def get_slack_mentions() -> str:
    """Fetch all Slack messages where you were mentioned.
    
    Returns a formatted summary of all mentions.
    """
    if not SLACK_BOT_TOKEN:
        return "Error: SLACK_BOT_TOKEN not configured. Please set the SLACK_BOT_TOKEN environment variable."
    
    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
        
        client = WebClient(token=SLACK_BOT_TOKEN)
        
        # Get mentions using conversations.history and search.messages
        # First, try to get recent messages from your DMs and channels
        mentions = []
        
        # Use conversations.list to get all channels
        try:
            response = client.conversations_list(types="public_channel,private_channel,im,mpim")
            channels = response["channels"]
            
            for channel in channels[:20]:  # Limit to first 20 channels
                try:
                    history = client.conversations_history(
                        channel=channel["id"],
                        limit=100,
                        inclusive=True,
                        oldest="0",  # Last 24 hours
                    )
                    
                    for msg in history["messages"]:
                        if msg.get("subtype") == "message":
                            text = msg.get("text", "")
                            # Check if user was mentioned
                            if f"<@{SLACK_USER_ID}>" in text or f"<@{SLACK_USER_ID}|" in text:
                                user_info = client.users_info(user=msg.get("user", ""))
                                user_name = user_info["user"]["real_name"] if user_info["ok"] else msg.get("user", "Unknown")
                                mentions.append({
                                    "user": user_name,
                                    "text": text,
                                    "ts": msg.get("ts"),
                                    "channel": channel["name"] if channel.get("name") else "DM"
                                })
                except SlackApiError:
                    continue
                    
        except SlackApiError as e:
            return f"Slack API Error: {e}"
        
        if not mentions:
            return "No mentions found in the last 24 hours."
        
        # Format the response
        result = "📢 **Your Slack Mentions (Last 24h):**\n\n"
        for m in mentions[:10]:  # Limit to 10
            result += f"• **{m['user']}** in {m['channel']}: {m['text'][:200]}\n"
        
        return result
        
    except ImportError:
        return "Error: slack-sdk not installed. Run: pip install slack-sdk"
    except Exception as e:
        return f"Error fetching Slack mentions: {str(e)}"
    finally:
        pass


def get_gmail() -> str:
    """Fetch recent important emails from Gmail.
    
    Returns a formatted summary of recent emails.
    """
    try:
        from googleapiclient.discovery import build
        from google.auth import credentials
        from oauthlib.oauth2.rfc6749.parameters import TokenError
        
        # Try to get credentials
        try:
            creds, _ = google.auth.default(scopes=[
                "https://www.googleapis.com/auth/gmail.readonly"
            ])
        except TokenError:
            return "Error: No Google credentials found. Please authenticate via 'gcloud auth application-default login'"
        
        service = build("gmail", "v1", credentials=creds)
        
        # Get messages
        results = service.users().messages().list(
            userId="me",
            q="is:unread OR label:important",
            maxResults=10
        ).execute()
        
        messages = results.get("messages", [])
        
        if not messages:
            return "No recent important emails."
        
        # Get message details
        email_summary = "📧 **Recent Important Emails:**\n\n"
        
        for msg in messages[:10]:
            msg_detail = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata"
            ).execute()
            
            headers = msg_detail["payload"]["headers"]
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
            from_addr = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
            
            email_summary += f"• **{subject}**\n  From: {from_addr[:80]}\n"
        
        return email_summary
        
    except ImportError:
        return "Error: google-api-python-client not installed."
    except Exception as e:
        return f"Error fetching Gmail: {str(e)}"
    finally:
        pass


def get_calendar() -> str:
    """Fetch today's calendar events.
    
    Returns a formatted summary of today's meetings.
    """
    try:
        from googleapiclient.discovery import build
        from google.auth import credentials
        from oauthlib.oauth2.rfc6749.parameters import TokenError
        
        # Try to get credentials
        try:
            creds, _ = google.auth.default(scopes=[
                "https://www.googleapis.com/auth/calendar.readonly"
            ])
        except TokenError:
            return "Error: No Google credentials found. Please authenticate via 'gcloud auth application-default login'"
        
        service = build("calendar", "v3", credentials=creds)
        
        # Get today's date range
        tz = ZoneInfo(USER_TIMEZONE)
        now = datetime.datetime.now(tz)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        events = service.events().list(
            calendarId="primary",
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        
        event_list = events.get("items", [])
        
        if not event_list:
            return "📅 **Today's Calendar:** No events scheduled."
        
        # Format events
        calendar_summary = "📅 **Today's Meetings:**\n\n"
        
        for event in event_list:
            start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", "All day"))
            summary = event.get("summary", "Untitled event")
            
            # Parse time
            if "T" in start:
                event_dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
                event_dt = event_dt.astimezone(tz)
                time_str = event_dt.strftime("%-I:%M %p")
            else:
                time_str = "All day"
            
            # Get attendees
            attendees = event.get("attendees", [])
            attendee_names = [a.get("displayName", a.get("email", "").split("@")[0]) for a in attendees if a.get("displayName") or a.get("email")]
            
            calendar_summary += f"• **{time_str}** - {summary}\n"
            if attendee_names:
                calendar_summary += f"  With: {', '.join(attendee_names[:5])}\n"
        
        return calendar_summary
        
    except ImportError:
        return "Error: google-api-python-client not installed."
    except Exception as e:
        return f"Error fetching Calendar: {str(e)}"
    finally:
        pass


def send_to_slack(message: str, channel: str = None) -> str:
    """Send a message to Slack.
    
    Args:
        message: The message to send to Slack.
        channel: The Slack channel or user ID to send to. Defaults to the user's own DM.
    
    Returns: Confirmation message.
    """
    if not SLACK_BOT_TOKEN:
        return "Error: SLACK_BOT_TOKEN not configured."
    
    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
        
        client = WebClient(token=SLACK_BOT_TOKEN)
        
        # Determine channel - use user's ID or passed channel
        target_channel = channel or SLACK_USER_ID
        if not target_channel:
            return "Error: No target channel or SLACK_USER_ID specified."
        
        # Send message
        response = client.chat_postMessage(
            channel=target_channel,
            text=message,
            unfurl_links=False
        )
        
        if response["ok"]:
            return "✅ Message sent to Slack successfully!"
        else:
            return f"❌ Failed to send message: {response}"
            
    except SlackApiError as e:
        return f"❌ Slack API Error: {e}"
    except Exception as e:
        return f"❌ Error sending to Slack: {str(e)}"
    finally:
        pass


def generate_daily_brief() -> str:
    """Generate the daily brief by fetching all data sources.
    
    Combines Slack mentions, Gmail, and Calendar into a daily summary.
    """
    # Get current date/time
    tz = ZoneInfo(USER_TIMEZONE)
    now = datetime.datetime.now(tz)
    date_str = now.strftime("%A, %B %d, %Y")
    
    # Build the brief
    brief = f"🌟 **Your Daily Brief - {date_str}**\n\n"
    
    # Get calendar (most important - shows meetings first)
    brief += get_calendar() + "\n\n"
    
    # Get Slack mentions
    brief += get_slack_mentions() + "\n\n"
    
    # Get Gmail
    brief += get_gmail() + "\n\n"
    
    # Add goals section (the agent will help fill this in)
    brief += "---" + "\n\n"
    brief += "🎯 **Today's Goals:**\n"
    brief += "_Think about what you want to accomplish today._\n"
    
    return brief


def send_daily_brief() -> str:
    """Generate and send the daily brief to Slack.
    
    This is the main function that pulls everything together.
    """
    brief = generate_daily_brief()
    return send_to_slack(brief)


# Wrap functions as ADK tools
get_slack_mentions_tool = FunctionTool(func=get_slack_mentions)
get_gmail_tool = FunctionTool(func=get_gmail)
get_calendar_tool = FunctionTool(func=get_calendar)
send_to_slack_tool = FunctionTool(func=send_to_slack)
generate_daily_brief_tool = FunctionTool(func=generate_daily_brief)
send_daily_brief_tool = FunctionTool(func=send_daily_brief)

# Create the root agent
root_agent = Agent(
    name="daily_brief_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a Daily Brief Agent designed to help the user start their day organized.

You have access to several tools:
- get_slack_mentions: Fetch Slack messages where the user was mentioned
- get_gmail: Fetch recent important emails
- get_calendar: Fetch today's calendar events  
- send_to_slack: Send a message to Slack
- generate_daily_brief: Generate a complete daily brief combining all sources
- send_daily_brief: Generate and send the daily brief to Slack

When the user asks for their "daily brief", "morning update", or "day summary", use generate_daily_brief 
or individually fetch the data and present it in a friendly, organized format.

Always be helpful, concise, and action-oriented. Highlight what's important and what needs attention.""",
    tools=[
        get_slack_mentions_tool,
        get_gmail_tool,
        get_calendar_tool,
        send_to_slack_tool,
        generate_daily_brief_tool,
        send_daily_brief_tool,
    ],
)

# Create the App
app = App(
    root_agent=root_agent,
    name="daily_brief_agent",
)