"""
contact_data_purge/modes.py
─────────────────────────────────────────────────────────────────────────────
Mode dispatcher — routes execution to the correct safety level.

Each mode is a self-contained function that accepts the pre-fetched
contact list and a PurgeSession, then handles its own confirmation
flow and batch logic. The dispatcher calls the right one based on MODE.

Modes
─────
  PREVIEW     — identify and export matching contacts. No changes.
  TEST_ONE    — modify 1 contact. Requires confirmation.
  TEST_BATCH  — modify TEST_BATCH_SIZE contacts. Requires confirmation.
  FULL_PURGE  — modify all matching contacts. Requires double confirmation.
  MULTI_BATCH — paginate beyond API limit, one batch per run.
─────────────────────────────────────────────────────────────────────────────
"""

import logging
import time
from typing import List, Dict

from .purge import PurgeSession
from .config import (
    MODE,
    BATCH_SIZE,
    TEST_BATCH_SIZE,
    DELAY_BETWEEN_REQUESTS,
    FILTER_METHOD,
    CURRENT_BATCH_INDEX,
    DATE_RANGES,
    NAME_RANGES,
)

logger = logging.getLogger(__name__)


def _run_batched_purge(
    contacts: List[Dict],
    session: PurgeSession,
) -> bool:
    """
    Shared batching logic for FULL_PURGE and MULTI_BATCH modes.
    Splits contacts into BATCH_SIZE chunks and calls bulk_remove_emails on each.
    """
    total         = len(contacts)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    successful    = 0
    failed        = 0

    for i in range(0, total, BATCH_SIZE):
        batch     = contacts[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1

        if session.bulk_remove_emails(batch, batch_num=batch_num, total_batches=total_batches):
            successful += 1
        else:
            failed += 1

        if i + BATCH_SIZE < total:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    logger.info(f"Batching complete: {successful} successful, {failed} failed.")
    return failed == 0


def run_preview(contacts: List[Dict], session: PurgeSession) -> bool:
    """Show all matching contacts and export to CSV. No data changes."""
    print(f"\n📋 PREVIEW: {len(contacts):,} contacts have email addresses.")
    session.preview(contacts)
    print("\nNo changes made. Change MODE in .env to proceed with deletion.")
    return True


def run_test_one(contacts: List[Dict], session: PurgeSession) -> bool:
    """Modify email data on exactly 1 contact. Safe for initial validation."""
    test = [contacts[0]]
    print(f"\n🧪 TEST_ONE: 1 contact selected for modification.")
    session.preview(test, export=False)

    if input("\nProceed? (type YES): ").strip().upper() == "YES":
        success = session.bulk_remove_emails(test, batch_num=1, total_batches=1)
        if success:
            print("✅ Email data removed from 1 test contact.")
        return success

    print("Cancelled.")
    return True


def run_test_batch(contacts: List[Dict], session: PurgeSession) -> bool:
    """Modify email data on a small batch. Good for validating bulk update behaviour."""
    test = contacts[:TEST_BATCH_SIZE]
    print(f"\n🧪 TEST_BATCH: {len(test)} contacts selected.")
    session.preview(test, export=False)

    if input(f"\nProceed with {len(test)} contacts? (type YES): ").strip().upper() == "YES":
        success = session.bulk_remove_emails(test, batch_num=1, total_batches=1)
        if success:
            print(f"✅ Email data removed from {len(test)} contacts.")
        return success

    print("Cancelled.")
    return True


def run_full_purge(contacts: List[Dict], session: PurgeSession) -> bool:
    """
    Remove email data from all matching contacts.

    Requires explicit double confirmation — this action cannot be undone.
    Processes contacts in BATCH_SIZE chunks with rate-limit delays.
    """
    total = len(contacts)
    print(f"\n⚠️  FULL_PURGE: {total:,} contacts will have email data removed.")
    print("    THIS ACTION CANNOT BE UNDONE.")

    session.preview(contacts[:10], export=False)
    print(f"\n(Showing first 10 of {total:,} contacts.)")

    confirm = input(f"\nAre you ABSOLUTELY SURE? (type YES): ").strip().upper()
    if confirm != "YES":
        print("Cancelled.")
        return True

    return _run_batched_purge(contacts, session)


def run_multi_batch(contacts: List[Dict], session: PurgeSession) -> bool:
    """
    Process one configured batch of contacts.

    Designed for populations that exceed the API's 1,000-record query limit.
    Each run processes a single date or name range batch. Increment
    CURRENT_BATCH_INDEX in .env between runs to step through all batches.
    """
    ranges     = DATE_RANGES if FILTER_METHOD == "DATE_RANGE" else NAME_RANGES
    batch_info = ranges[CURRENT_BATCH_INDEX] if CURRENT_BATCH_INDEX < len(ranges) else None

    if not batch_info:
        logger.error(
            f"Invalid CURRENT_BATCH_INDEX: {CURRENT_BATCH_INDEX}. "
            f"Valid range: 0–{len(ranges) - 1}."
        )
        return False

    print(f"\n📊 MULTI_BATCH: Batch {CURRENT_BATCH_INDEX + 1}/{len(ranges)}")
    print(f"   Range      : {batch_info}")
    print(f"   Filter     : {FILTER_METHOD}")
    print(f"   Contacts   : {len(contacts):,} with email addresses")

    if not contacts:
        print("No contacts with email addresses in this batch.")
        return True

    session.preview(contacts[:10], export=False)

    confirm = input(
        f"\nProceed with batch {CURRENT_BATCH_INDEX + 1}? (type YES): "
    ).strip().upper()

    if confirm != "YES":
        print("Cancelled.")
        return True

    success = _run_batched_purge(contacts, session)

    if success:
        next_idx = CURRENT_BATCH_INDEX + 1
        if next_idx < len(ranges):
            print(f"\n💡 Next batch: set CURRENT_BATCH_INDEX={next_idx} in .env")
        else:
            print("\n✅ All batches complete.")

    return success


# ── Dispatcher ────────────────────────────────────────────────────────────────
MODE_MAP = {
    "PREVIEW":     run_preview,
    "TEST_ONE":    run_test_one,
    "TEST_BATCH":  run_test_batch,
    "FULL_PURGE":  run_full_purge,
    "MULTI_BATCH": run_multi_batch,
}


def dispatch(contacts: List[Dict], session: PurgeSession) -> bool:
    """
    Route execution to the correct mode function based on MODE config.

    Args:
        contacts: Contacts with email data identified.
        session:  Active PurgeSession for bulk updates and audit logging.

    Returns:
        True if the operation completed without errors.
    """
    handler = MODE_MAP.get(MODE.upper())

    if not handler:
        valid = ", ".join(MODE_MAP.keys())
        logger.error(f"Invalid MODE: '{MODE}'. Valid options: {valid}")
        return False

    return handler(contacts, session)
