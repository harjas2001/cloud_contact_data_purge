"""
main.py
─────────────────────────────────────────────────────────────────────────────
Entry point for the Cloud Contact Data Purge utility.

Orchestrates the full pipeline:
  1. Load credentials (Secrets Manager → .env fallback)
  2. Authenticate and build API client
  3. Fetch and filter contacts
  4. Identify contacts with target data fields
  5. Dispatch to the configured safety mode

Run locally:
  python main.py

Run on AWS EC2 (credentials from instance role via Secrets Manager):
  AWS_SECRET_NAME=prod/contact-purge/api-credentials python main.py

For Lambda deployment, see aws/lambda_handler.py.
─────────────────────────────────────────────────────────────────────────────
"""

import logging

from contact_data_purge.auth import load_credentials, get_access_token
from contact_data_purge.client import APIClient
from contact_data_purge.contacts import fetch_all_contacts, filter_by_date, find_contacts_with_emails
from contact_data_purge.modes import dispatch, MODE
from contact_data_purge.purge import PurgeSession
from contact_data_purge.config import FILTER_METHOD, CURRENT_BATCH_INDEX, EXPORT_TO_CSV

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run() -> bool:
    """
    Execute the full purge pipeline.

    Returns:
        True if the operation completed without errors.
    """
    try:
        # ── 1. Credentials + auth ─────────────────────────────────────────────
        creds        = load_credentials()
        access_token = get_access_token(
            creds["client_id"],
            creds["client_secret"],
            creds["region"],
            creds.get("verify_cert", True),
        )

        # ── 2. API client ─────────────────────────────────────────────────────
        api = APIClient(
            base_url=f"https://api.{creds['region']}",
            access_token=access_token,
            verify_cert=creds.get("verify_cert", True),
        )

        # ── 3. Fetch contacts ─────────────────────────────────────────────────
        all_contacts     = fetch_all_contacts(api)
        filtered         = filter_by_date(all_contacts)
        contacts_to_purge = find_contacts_with_emails(filtered)

        if not contacts_to_purge:
            logger.info("No contacts with email addresses found. Nothing to do.")
            return True

        # ── 4. Dispatch to mode ───────────────────────────────────────────────
        session = PurgeSession(api)
        return dispatch(contacts_to_purge, session)

    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        return False
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return False


def main():
    print("=" * 60)
    print("  Cloud Contact Data Purge")
    print("=" * 60)
    print(f"  Mode         : {MODE}")
    print(f"  Filter       : {FILTER_METHOD if MODE == 'MULTI_BATCH' else 'N/A'}")
    print(f"  Batch index  : {CURRENT_BATCH_INDEX if MODE == 'MULTI_BATCH' else 'N/A'}")
    print(f"  Audit CSV    : {'enabled' if EXPORT_TO_CSV else 'disabled'}")
    print("=" * 60)

    if input(f"\nContinue in {MODE} mode? (type YES): ").strip().upper() != "YES":
        print("Cancelled.")
        return

    success = run()

    print()
    if success:
        print("✅ Operation completed successfully.")
    else:
        print("❌ Operation completed with errors. Check logs above.")


if __name__ == "__main__":
    main()
