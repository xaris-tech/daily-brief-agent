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
Daily Brief Agent - Fetches Slack mentions, Gmail, and Calendar to send daily summary via email.

This agent runs on a cron schedule (default: 8am daily) and sends a personalized
daily brief to the user via email.
"""

import datetime
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
USER_EMAIL = os.environ.get("USER_EMAIL", "")  # Your email to send the brief to
USER_TIMEZONE = os.environ.get("USER_TIMEZONE", "America/New_York")


def get_slack_mentions() -> str:
    """Fetch Slack messages with mentions/urgents.
    
    Returns a formatted summary of important mentions.
    """
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        return "Slack: Not configured (add SLACK_BOT_TOKEN to enable)."
    
    try:
        from slack_sdk import WebClient
        client = WebClient(token=token)
        
        mentions = []
        response = client.conversations_list(types="public_channel,private_channel,im,mpim")
        channels = response["channels"]
        
        for channel in channels[:20]:
            try:
                history = client.conversations_history(
                    channel=channel["id"],
                    limit=100,
                )
                
                for msg in history["messages"]:
                    if msg.get("type") == "message":
                        text = msg.get("text", "")
                        if "@here" in text or "@channel" in text or "urgent" in text.lower():
                            user_info = client.users_info(user=msg.get("user", ""))
                            user_name = user_info["user"]["real_name"] if user_info["ok"] else "Unknown"
                            mentions.append({
                                "user": user_name,
                                "text": text[:200],
                                "channel": channel.get("name", "DM")
                            })
            except Exception:
                continue
                
        if not mentions:
            return "No urgent mentions in the last 24 hours."
        
        result = "**Slack Mentions:**\n\n"
        for m in mentions[:5]:
            result += f"- {m['user']} in {m['channel']}: {m['text']}\n"
        
        return result
        
    except Exception as e:
        return f"Slack: {str(e)}"
        mentions = []
        response = client.conversations_list(types="public_channel,private_channel,im,mpim")
        channels = response["channels"]
        
        for channel in channels[:20]:
            try:
                history = client.conversations_history(
                    channel=channel["id"],
                    limit=100,
                )
                
                for msg in history["messages"]:
                    if msg.get("type") == "message":
                        text = msg.get("text", "")
                        # Check for mentions (basic check)
                        if "@here" in text or "@channel" in text or "urgent" in text.lower():
                            user_info = client.users_info(user=msg.get("user", ""))
                            user_name = user_info["user"]["real_name"] if user_info["ok"] else "Unknown"
                            mentions.append({
                                "user": user_name,
                                "text": text[:200],
                                "channel": channel.get("name", "DM")
                            })
            except Exception:
                continue
                
        if not mentions:
            return "No urgent mentions in the last 24 hours."
        
        result = "**Slack Mentions:**\n\n"
        for m in mentions[:5]:
            result += f"- {m['user']} in {m['channel']}: {m['text']}\n"
        
        return result
        
    except Exception as e:
        return f"Slack: {str(e)}"


def get_gmail() -> str:
    """Fetch recent important emails from Gmail.
    
    Returns a formatted summary of recent emails.
    """
    try:
        from googleapiclient.discovery import build
        from google.auth import credentials
        
        creds, _ = google.auth.default(scopes=[
            "https://www.googleapis.com/auth/gmail.readonly"
        ])
        
        service = build("gmail", "v1", credentials=creds)
        
        results = service.users().messages().list(
            userId="me",
            q="is:unread OR label:important",
            maxResults=10
        ).execute()
        
        messages = results.get("messages", [])
        
        if not messages:
            return "No recent important emails."
        
        email_summary = "**Recent Important Emails:**\n\n"
        
        for msg in messages[:5]:
            msg_detail = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata"
            ).execute()
            
            headers = msg_detail["payload"]["headers"]
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
            from_addr = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
            
            email_summary += f"- {subject[:60]}... | From: {from_addr[:40]}\n"
        
        return email_summary
        
    except Exception as e:
        return f"Gmail: {str(e)}"


def get_calendar() -> str:
    """Fetch today's calendar events.
    
    Returns a formatted summary of today's meetings.
    """
    try:
        from googleapiclient.discovery import build
        from google.auth import credentials
        
        creds, _ = google.auth.default(scopes=[
            "https://www.googleapis.com/auth/calendar.readonly"
        ])
        
        service = build("calendar", "v3", credentials=creds)
        
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
            return "**Today's Calendar:** No events scheduled."
        
        calendar_summary = "**Today's Meetings:**\n\n"
        
        for event in event_list[:10]:
            start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", "All day"))
            summary = event.get("summary", "Untitled")
            
            if "T" in start:
                event_dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
                event_dt = event_dt.astimezone(tz)
                time_str = event_dt.strftime("%-I:%M %p")
            else:
                time_str = "All day"
            
            attendees = event.get("attendees", [])
            attendee_names = [a.get("displayName", a.get("email", "").split("@")[0]) for a in attendees if a.get("displayName") or a.get("email")][:3]
            
            calendar_summary += f"- {time_str} | {summary[:40]}"
            if attendee_names:
                calendar_summary += f" (with {', '.join(attendee_names)})"
            calendar_summary += "\n"
        
        return calendar_summary
        
    except Exception as e:
        return f"Calendar: {str(e)}"


def send_email(subject: str, body: str) -> str:
    """Send an email via Gmail API.
    
    Args:
        subject: Email subject line
        body: Email body content
    
    Returns: Confirmation message.
    """
    if not USER_EMAIL:
        return "Error: USER_EMAIL not set in .env"
    
    try:
        from googleapiclient.discovery import build
        from google.auth import credentials
        
        creds, _ = google.auth.default(scopes=[
            "https://www.googleapis.com/auth/gmail.send"
        ])
        
        service = build("gmail", "v1", credentials=creds)
        
        # Create email message
        message = MIMEMultipart()
        message["To"] = USER_EMAIL
        message["Subject"] = subject
        
        # Attach plain text body
        message.attach(MIMEText(body, "plain"))
        
        # Encode and send
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        send_result = service.users().messages().send(
            userId="me",
            body={"raw": encoded_message}
        ).execute()
        
        return f"Email sent to {USER_EMAIL}"
        
    except Exception as e:
        return f"Error sending email: {str(e)}"


def generate_daily_brief() -> str:
    """Generate the daily brief by fetching all data sources.
    
    Combines Calendar, Slack, and Gmail into a daily summary.
    """
    tz = ZoneInfo(USER_TIMEZONE)
    now = datetime.datetime.now(tz)
    date_str = now.strftime("%A, %B %d, %Y")
    
    brief = f"Your Daily Brief - {date_str}\n"
    brief += "=" * 30 + "\n\n"
    
    # Calendar (most important)
    brief += get_calendar() + "\n\n"
    
    # Slack mentions
    brief += get_slack_mentions() + "\n\n"
    
    # Gmail
    brief += get_gmail() + "\n\n"
    
    brief += "-" * 30 + "\n\n"
    brief += "Today's Goals:\n"
    brief += "_What do you want to accomplish today?_\n"
    
    return brief


def send_daily_brief() -> str:
    """Generate and send the daily brief via email.
    
    This is the main function that pulls everything together.
    """
    tz = ZoneInfo(USER_TIMEZONE)
    now = datetime.datetime.now(tz)
    date_str = now.strftime("%B %d, %Y")
    
    brief = generate_daily_brief()
    subject = f"Daily Brief - {date_str}"
    
    return send_email(subject, brief)


# Wrap functions as ADK tools
get_slack_mentions_tool = FunctionTool(func=get_slack_mentions)
get_gmail_tool = FunctionTool(func=get_gmail)
get_calendar_tool = FunctionTool(func=get_calendar)
send_email_tool = FunctionTool(func=send_email)
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
- get_calendar: Fetch today's calendar events  
- get_gmail: Fetch recent important emails
- get_slack_mentions: Fetch important Slack messages
- send_email: Send an email via Gmail
- generate_daily_brief: Generate a complete daily brief
- send_daily_brief: Generate and email the daily brief

When the user asks for their "daily brief", "morning update", or "day summary", use generate_daily_brief 
or send_daily_brief to email it to them.

Always be helpful, concise, and action-oriented. Highlight meetings and important items.""",
    tools=[
        get_calendar_tool,
        get_gmail_tool,
        get_slack_mentions_tool,
        send_email_tool,
        generate_daily_brief_tool,
        send_daily_brief_tool,
    ],
)

# Create the App
app = App(
    root_agent=root_agent,
    name="daily_brief_agent",
)