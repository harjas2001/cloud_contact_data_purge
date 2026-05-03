"""
contact_data_purge/auth.py
─────────────────────────────────────────────────────────────────────────────
Credential loading and OAuth2 authentication.

Production: credentials are pulled from AWS Secrets Manager.
Local dev:  credentials fall back to .env variables.

The Secrets Manager secret should be a JSON object:
  {
    "client_id":     "...",
    "client_secret": "...",
    "region":        "mypurecloud.com.au",
    "verify_cert":   true
  }
─────────────────────────────────────────────────────────────────────────────
"""

import os
import json
import logging
from typing import Dict

import requests

from .config import AWS_REGION, AWS_SECRET_NAME

logger = logging.getLogger(__name__)


def load_credentials_from_secrets_manager(secret_name: str, aws_region: str) -> Dict:
    """Pull API credentials from AWS Secrets Manager."""
    try:
        import boto3
        client = boto3.client("secretsmanager", region_name=aws_region)
        secret = client.get_secret_value(SecretId=secret_name)
        logger.info(f"Credentials loaded from Secrets Manager: {secret_name}")
        return json.loads(secret["SecretString"])
    except Exception as e:
        logger.warning(f"Secrets Manager unavailable: {e}. Falling back to .env.")
        return {}


def load_credentials() -> Dict:
    """
    Load credentials from Secrets Manager (production) or .env (local).
    Returns dict with keys: client_id, client_secret, region, verify_cert.
    """
    if AWS_SECRET_NAME:
        creds = load_credentials_from_secrets_manager(AWS_SECRET_NAME, AWS_REGION)
        if creds:
            return creds

    logger.info("Loading credentials from .env (local development mode).")
    return {
        "client_id":     os.getenv("CLIENT_ID"),
        "client_secret": os.getenv("CLIENT_SECRET"),
        "region":        os.getenv("REGION"),
        "verify_cert":   os.getenv("VERIFY_CERT", "true").lower() == "true",
    }


def get_access_token(client_id: str, client_secret: str, region: str, verify_cert: bool) -> str:
    """
    Obtain an OAuth2 client credentials access token.

    Args:
        client_id:     OAuth client ID.
        client_secret: OAuth client secret.
        region:        Platform API region (e.g. mypurecloud.com.au).
        verify_cert:   Whether to verify SSL certificates.

    Returns:
        Access token string.

    Raises:
        requests.exceptions.RequestException on auth failure.
    """
    token_url = f"https://login.{region}/oauth/token"
    data = {
        "grant_type": "client_credentials",
        "scope": "external-contacts:contact:view external-contacts:contact:edit",
    }

    try:
        response = requests.post(
            token_url,
            data=data,
            auth=(client_id, client_secret),
            timeout=30,
            verify=verify_cert,
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        logger.info("Authentication successful.")
        return token
    except requests.exceptions.RequestException as e:
        logger.error(f"Authentication failed: {e}")
        raise
