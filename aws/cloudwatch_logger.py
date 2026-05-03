"""
aws/cloudwatch_logger.py
─────────────────────────────────────────────────────────────────────────────
Structured CloudWatch logging for the purge utility.

Emits JSON-structured log events to CloudWatch Logs for operational
monitoring, alerting, and long-term audit retention.

Usage:
  from aws.cloudwatch_logger import PurgeLogger
  log = PurgeLogger(job_id="purge-20260504")
  log.info("Contacts fetched", contacts_fetched=1200, page=12)
  log.error("Batch failed", batch=3, error="timeout")

CloudWatch Insights query to monitor purge jobs:
  fields @timestamp, level, message, contacts_processed, batch
  | filter job_id like /purge/
  | sort @timestamp desc
  | limit 50

Configuration (via .env):
  AWS_REGION        — CloudWatch region
  CW_LOG_GROUP      — CloudWatch log group name (created if not exists)
─────────────────────────────────────────────────────────────────────────────
"""

import os
import json
import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PurgeLogger:
    """
    Emits structured JSON logs to both stdout and AWS CloudWatch Logs.
    Falls back gracefully to stdout-only if boto3 or permissions are unavailable.
    """

    def __init__(self, job_id: str = None):
        self.job_id       = job_id or f"purge-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.log_group    = os.getenv("CW_LOG_GROUP", "/conversational-ai/contact-purge")
        self.aws_region   = os.getenv("AWS_REGION",   "ap-southeast-2")
        self.log_stream   = self.job_id
        self._cw_client   = None
        self._sequence_token = None

        self._init_cloudwatch()

    def _init_cloudwatch(self) -> None:
        """Initialise CloudWatch Logs client and ensure log group + stream exist."""
        try:
            import boto3
            self._cw_client = boto3.client("logs", region_name=self.aws_region)

            # Create log group if it doesn't exist
            try:
                self._cw_client.create_log_group(logGroupName=self.log_group)
            except self._cw_client.exceptions.ResourceAlreadyExistsException:
                pass

            # Create log stream for this job
            try:
                self._cw_client.create_log_stream(
                    logGroupName=self.log_group,
                    logStreamName=self.log_stream,
                )
            except self._cw_client.exceptions.ResourceAlreadyExistsException:
                pass

            logger.info(f"CloudWatch logging initialised: {self.log_group}/{self.log_stream}")

        except Exception as e:
            logger.warning(f"CloudWatch unavailable — stdout only. ({e})")
            self._cw_client = None

    def _emit(self, level: str, message: str, **kwargs) -> None:
        """Emit a structured log event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     level,
            "job_id":    self.job_id,
            "message":   message,
            **kwargs,
        }

        # Always log to stdout
        print(json.dumps(event))

        # Send to CloudWatch if available
        if self._cw_client:
            try:
                put_kwargs = {
                    "logGroupName":  self.log_group,
                    "logStreamName": self.log_stream,
                    "logEvents": [{
                        "timestamp": int(time.time() * 1000),
                        "message":   json.dumps(event),
                    }],
                }
                if self._sequence_token:
                    put_kwargs["sequenceToken"] = self._sequence_token

                response = self._cw_client.put_log_events(**put_kwargs)
                self._sequence_token = response.get("nextSequenceToken")

            except Exception as e:
                logger.warning(f"Failed to write to CloudWatch: {e}")

    def info(self, message: str, **kwargs) -> None:
        self._emit("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._emit("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self._emit("ERROR", message, **kwargs)

    def audit(self, message: str, **kwargs) -> None:
        """Emit an AUDIT-level event — used for data modification events."""
        self._emit("AUDIT", message, **kwargs)
