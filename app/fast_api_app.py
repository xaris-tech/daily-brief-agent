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
Daily Brief Agent - FastAPI app with cron scheduler.

This runs the daily brief generation at 8am every day.
"""

import os
import logging
from datetime import datetime

import google.auth
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback
from app.agent import send_daily_brief, generate_daily_brief

setup_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=True,
)
app.title = "daily-brief-agent"
app.description = "API for interacting with the Agent daily-brief-agent"


# Cron scheduler for daily brief
scheduler = AsyncIOScheduler()


def run_daily_brief():
    """Job function to generate and send daily brief."""
    logger.log("Running daily brief job...", severity="INFO")
    try:
        # Generate and send the brief
        result = send_daily_brief()
        logger.log(f"Daily brief result: {result}", severity="INFO")
    except Exception as e:
        logger.log(f"Error running daily brief: {e}", severity="ERROR")


# Schedule the daily brief at 8am
CRON_HOUR = int(os.environ.get("DAILY_BRIEF_HOUR", "8"))
CRON_MINUTE = int(os.environ.get("DAILY_BRIEF_MINUTE", "0"))

# Add job - run at 8am daily
scheduler.add_job(
    run_daily_brief,
    CronTrigger(hour=CRON_HOUR, minute=CRON_MINUTE),
    id="daily_brief",
    name="Daily Brief",
    replace_existing=True
)

# Also allow manual trigger via API endpoint
@app.post("/trigger-daily-brief")
def trigger_daily_brief() -> dict[str, str]:
    """Manually trigger the daily brief."""
    logger.log("Manually triggered daily brief", severity="INFO")
    try:
        result = send_daily_brief()
        return {"status": "success", "result": result}
    except Exception as e:
        logger.log(f"Error: {e}", severity="ERROR")
        return {"status": "error", "message": str(e)}


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


@app.on_event("startup")
async def start_scheduler():
    """Start the scheduler on startup."""
    if not scheduler.running:
        scheduler.start()
        logger.log("Scheduler started for daily brief at 8am", severity="INFO")


@app.on_event("shutdown")
async def stop_scheduler():
    """Stop the scheduler on shutdown."""
    if scheduler.running:
        scheduler.shutdown()
        logger.log("Scheduler stopped", severity="INFO")


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)