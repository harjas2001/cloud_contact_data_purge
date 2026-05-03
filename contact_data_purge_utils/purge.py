"""
contact_data_purge/purge.py
─────────────────────────────────────────────────────────────────────────────
Bulk field removal, CSV audit trail, and contact preview.

All write-side operations against the contacts API live here.
Each bulk update call is logged to a timestamped session audit CSV
for compliance and post-run review.
─────────────────────────────────────────────────────────────────────────────
"""

import os
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from .client import APIClient
from .config import EXPORT_TO_CSV, OUTPUT_DIR

logger = logging.getLogger(__name__)

BULK_UPDATE_ENDPOINT = "/api/v2/externalcontacts/contacts/bulk/update"


class PurgeSession:
    """
    Manages a single purge session — audit file lifecycle and bulk update calls.

    Args:
        api: Authenticated APIClient instance.
    """

    def __init__(self, api: APIClient):
        self.api       = api
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        self.audit_csv = os.path.join(OUTPUT_DIR, f"purge_audit_{self.timestamp}.csv")

    def bulk_remove_emails(
        self,
        contacts: List[Dict],
        batch_num: int = 1,
        total_batches: int = 1,
    ) -> bool:
        """
        Remove all email address fields from a batch of contacts via bulk update.

        Writes each contact's outcome (SUCCESS / FAILED) to the session audit CSV.

        Args:
            contacts:      Contacts to update (must include `_emails_found`).
            batch_num:     Current batch number (for logging).
            total_batches: Total number of batches in this run (for logging).

        Returns:
            True if the batch succeeded, False otherwise.
        """
        payload = [
            {
                "id":            c["id"],
                "emailAddress":  None,
                "emailAddress2": None,
                "emailAddress3": None,
                "emailAddress4": None,
            }
            for c in contacts
        ]

        logger.info(
            f"Bulk update: batch {batch_num}/{total_batches} "
            f"({len(contacts)} contacts)"
        )

        try:
            response = self.api.post(
                BULK_UPDATE_ENDPOINT,
                data={"contacts": payload},
            )
            updated = response.get("entities", [])
            logger.info(f"Batch {batch_num}: {len(updated)} contacts updated.")

            if EXPORT_TO_CSV:
                self._append_audit(contacts, status="SUCCESS")

            return True

        except Exception as e:
            logger.error(f"Batch {batch_num} failed: {e}")
            if EXPORT_TO_CSV:
                self._append_audit(contacts, status="FAILED")
            return False

    def preview(self, contacts: List[Dict], export: bool = True) -> None:
        """
        Print a formatted preview of contacts with email addresses.
        Optionally exports to a timestamped preview CSV.

        Args:
            contacts: Contacts with `_emails_found` attached.
            export:   Whether to write a preview CSV (respects EXPORT_TO_CSV).
        """
        logger.info(f"\n── Contact Preview ({len(contacts)} contacts) ─────────────")
        for i, c in enumerate(contacts, 1):
            name   = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
            emails = [v for _, v in c.get("_emails_found", [])]
            logger.info(f"  {i:>3}. {name:<30} | {c['id']} | {emails}")

        if export and EXPORT_TO_CSV:
            preview_file = os.path.join(OUTPUT_DIR, f"preview_{self.timestamp}.csv")
            with open(preview_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["contact_id", "first_name", "last_name", "email_addresses"])
                for c in contacts:
                    emails = ", ".join(v for _, v in c.get("_emails_found", []))
                    writer.writerow([c["id"], c.get("firstName", ""), c.get("lastName", ""), emails])
            logger.info(f"Preview exported → {preview_file}")

    def _append_audit(self, contacts: List[Dict], status: str) -> None:
        """
        Append processed contacts to the session audit CSV.

        Creates the file with a header row on first write.
        Subsequent calls append rows without re-writing the header.
        """
        file_exists = os.path.isfile(self.audit_csv)

        with open(self.audit_csv, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(
                    ["contact_id", "name", "emails_removed", "status", "timestamp"]
                )
            for c in contacts:
                name   = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
                emails = ", ".join(v for _, v in c.get("_emails_found", []))
                writer.writerow([c["id"], name, emails, status, datetime.now().isoformat()])
