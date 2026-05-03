"""
aws/lambda_handler.py
─────────────────────────────────────────────────────────────────────────────
AWS Lambda entry point for the Cloud Contact Data Purge utility.

Designed to run on a schedule via Amazon EventBridge (CloudWatch Events).
Credentials are loaded from AWS Secrets Manager — no secrets are stored
in environment variables or the function package.

Deployment
──────────
  Runtime  : Python 3.11
  Handler  : aws/lambda_handler.lambda_handler
  Memory   : 256 MB
  Timeout  : 900 seconds (15 minutes — max Lambda runtime)
  Trigger  : EventBridge scheduled rule (e.g. rate(7 days))
  IAM role : Needs secretsmanager:GetSecretValue, logs:CreateLogGroup,
             logs:CreateLogStream, logs:PutLogEvents, s3:PutObject

Environment variables (set in Lambda console — not secrets):
  AWS_SECRET_NAME       — Secrets Manager secret name
  MODE                  — PREVIEW / TEST_BATCH / FULL_PURGE / MULTI_BATCH
  BATCH_SIZE            — max contacts per bulk update request
  PAGE_SIZE             — contacts per paginated GET
  CURRENT_BATCH_INDEX   — which MULTI_BATCH range to process
  FILTER_METHOD         — DATE_RANGE or NAME_RANGE
  S3_BUCKET             — bucket for audit CSV archiving (optional)

The event payload can override any of the above at invocation time:
  {
    "mode": "MULTI_BATCH",
    "batch_index": 2,
    "filter_method": "DATE_RANGE",
    "s3_bucket": "your-audit-bucket"
  }

Deployment steps:
  1. zip -r function.zip . -x "*.env" -x "output/*" -x ".git/*" -x "venv/*"
  2. aws lambda update-function-code --function-name contact-purge \
       --zip-file fileb://function.zip
  3. Set environment variables in Lambda console
  4. Configure EventBridge rule for scheduling
─────────────────────────────────────────────────────────────────────────────
"""

import os
import glob
import json
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _upload_to_s3(local_path: str, s3_bucket: str, s3_key: str) -> None:
    """Archive a local file to S3."""
    boto3.client("s3").upload_file(local_path, s3_bucket, s3_key)
    logger.info(f"Audit file archived → s3://{s3_bucket}/{s3_key}")


def lambda_handler(event: dict, context) -> dict:
    """
    Lambda entry point.

    Accepts runtime overrides via the event payload (see module docstring).
    Returns a summary dict with statusCode and operation result.
    """
    # Allow event payload to override environment config
    mode         = event.get("mode",          os.getenv("MODE",                 "PREVIEW"))
    batch_index  = event.get("batch_index",   int(os.getenv("CURRENT_BATCH_INDEX", 0)))
    filter_method = event.get("filter_method", os.getenv("FILTER_METHOD",       "DATE_RANGE"))
    s3_bucket    = event.get("s3_bucket",     os.getenv("S3_BUCKET"))

    # Inject overrides so the pipeline modules pick them up via config.py
    os.environ["MODE"]                = mode
    os.environ["CURRENT_BATCH_INDEX"] = str(batch_index)
    os.environ["FILTER_METHOD"]       = filter_method
    os.environ["OUTPUT_DIR"]          = "/tmp/purge_output"

    logger.info(
        f"Lambda invoked | mode={mode} | batch_index={batch_index} "
        f"| filter={filter_method}"
    )

    # Import after env vars are set so config.py reads correct values
    from main import run as purge_run
    from contact_data_purge.config import OUTPUT_DIR

    try:
        success = purge_run()

        # Archive most recent audit CSV to S3
        audit_files = sorted(glob.glob(f"{OUTPUT_DIR}/purge_audit_*.csv"))
        audit_file  = audit_files[-1] if audit_files else None

        if s3_bucket and audit_file and os.path.isfile(audit_file):
            s3_key = f"purge-audit/{os.path.basename(audit_file)}"
            _upload_to_s3(audit_file, s3_bucket, s3_key)

        return {
            "statusCode": 200 if success else 500,
            "body": json.dumps({
                "status":      "success" if success else "partial_failure",
                "mode":        mode,
                "batch_index": batch_index,
                "audit_file":  audit_file,
            }),
        }

    except Exception as e:
        logger.error(f"Lambda execution failed: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "message": str(e)}),
        }
