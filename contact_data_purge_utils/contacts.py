"""
contact_data_purge/contacts.py
─────────────────────────────────────────────────────────────────────────────
Contact retrieval, pagination, date filtering, and email identification.

Handles all read-side operations against the external contacts API,
including the MULTI_BATCH pagination strategy for bypassing the
platform's 1,000-record query limit.
─────────────────────────────────────────────────────────────────────────────
"""

import logging
import time
from datetime import datetime
from typing import List, Dict, Optional

import requests

from .client import APIClient
from .config import (
    PAGE_SIZE,
    DELAY_BETWEEN_REQUESTS,
    MODE,
    FILTER_METHOD,
    CURRENT_BATCH_INDEX,
    FILTER_START_DATE,
    FILTER_END_DATE,
    DATE_RANGES,
    NAME_RANGES,
)

logger = logging.getLogger(__name__)

CONTACTS_ENDPOINT = "/api/v2/externalcontacts/contacts"
PAGE_SAFETY_LIMIT = 100  # Max pages per run (~10,000 contacts)


def get_filter_params() -> Dict:
    """
    Build API query params for MULTI_BATCH mode.

    Returns query filter based on FILTER_METHOD and CURRENT_BATCH_INDEX.
    Raises ValueError for invalid configuration.
    """
    if FILTER_METHOD == "DATE_RANGE":
        if CURRENT_BATCH_INDEX >= len(DATE_RANGES):
            raise ValueError(
                f"CURRENT_BATCH_INDEX {CURRENT_BATCH_INDEX} is out of range. "
                f"DATE_RANGES has {len(DATE_RANGES)} entries (0–{len(DATE_RANGES) - 1})."
            )
        r = DATE_RANGES[CURRENT_BATCH_INDEX]
        logger.info(f"Date range batch {CURRENT_BATCH_INDEX + 1}: {r['start']} → {r['end']}")
        return {"q": f"modifyDate:[{r['start']} TO {r['end']}]"}

    elif FILTER_METHOD == "NAME_RANGE":
        if CURRENT_BATCH_INDEX >= len(NAME_RANGES):
            raise ValueError(
                f"CURRENT_BATCH_INDEX {CURRENT_BATCH_INDEX} is out of range. "
                f"NAME_RANGES has {len(NAME_RANGES)} entries (0–{len(NAME_RANGES) - 1})."
            )
        r = NAME_RANGES[CURRENT_BATCH_INDEX]
        logger.info(f"Name range batch {CURRENT_BATCH_INDEX + 1}: {r['start']}–{r['end']}")
        return {"q": f"lastName:[{r['start']} TO {r['end']}]"}

    raise ValueError(
        f"Unknown FILTER_METHOD: '{FILTER_METHOD}'. Valid options: DATE_RANGE, NAME_RANGE."
    )


def fetch_all_contacts(api: APIClient) -> List[Dict]:
    """
    Retrieve all external contacts with full pagination.

    In MULTI_BATCH mode, applies date or name range filtering via the API
    query parameter to paginate beyond the platform's 1,000-record limit.
    Each run processes one configured batch (CURRENT_BATCH_INDEX).

    Safety limit: PAGE_SAFETY_LIMIT pages per run.

    Args:
        api: Authenticated APIClient instance.

    Returns:
        List of contact dicts from the API.
    """
    all_contacts = []
    page_number  = 1
    base_params  = {
        "pageSize": PAGE_SIZE,
        "expand":   ["externalOrganization"],
    }

    if MODE == "MULTI_BATCH":
        base_params.update(get_filter_params())
    else:
        logger.info("No range filter — retrieving up to the API record limit.")

    logger.info("Fetching external contacts...")

    while True:
        params = {**base_params, "pageNumber": page_number}

        try:
            response   = api.get(CONTACTS_ENDPOINT, params=params)
            contacts   = response.get("entities", [])
            page_count = response.get("pageCount", 0)
            total_hits = response.get("totalHits", 0)

            logger.info(
                f"Page {page_number}: {len(contacts)} contacts "
                f"(total hits: {total_hits}, pages: {page_count})"
            )

            if not contacts:
                logger.info("No contacts returned — pagination complete.")
                break

            all_contacts.extend(contacts)

            if len(contacts) < PAGE_SIZE:
                logger.info("Last page detected (partial page).")
                break

            if page_count > 0 and page_number >= page_count:
                logger.info(f"Reached final page: {page_number}/{page_count}.")
                break

            if page_number >= PAGE_SAFETY_LIMIT:
                logger.warning(
                    f"Safety limit reached: {PAGE_SAFETY_LIMIT} pages. "
                    "Use MULTI_BATCH mode for larger populations."
                )
                break

            page_number += 1
            time.sleep(DELAY_BETWEEN_REQUESTS)

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                msg = e.response.json().get("message", "")
                if "cannot exceed 1000" in msg:
                    logger.error(
                        f"API record limit hit at page {page_number}. "
                        "Switch to MULTI_BATCH mode to paginate beyond 1,000 records."
                    )
                    break
            logger.error(f"HTTP error on page {page_number}: {e}")
            break

        except Exception as e:
            logger.error(f"Unexpected error on page {page_number}: {e}")
            break

    logger.info(f"Total contacts retrieved: {len(all_contacts):,}")
    return all_contacts


def filter_by_date(contacts: List[Dict]) -> List[Dict]:
    """
    Optional client-side date filter using FILTER_START_DATE and FILTER_END_DATE.

    Supplements the API-level query filter for platforms where the query
    parameter does not guarantee exact date boundary enforcement.

    Args:
        contacts: Raw contact list from the API.

    Returns:
        Contacts whose modifyDate falls within the configured date range.
    """
    start_dt = datetime.fromisoformat(FILTER_START_DATE)
    end_dt   = datetime.fromisoformat(FILTER_END_DATE)
    filtered = []

    for contact in contacts:
        raw_date = contact.get("modifyDate") or contact.get("dateModified")
        if not raw_date:
            continue
        try:
            modify_dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            if start_dt <= modify_dt.replace(tzinfo=None) <= end_dt:
                filtered.append(contact)
        except Exception as e:
            logger.warning(f"Could not parse date for contact {contact.get('id')}: {e}")

    logger.info(f"Date filter: {len(filtered):,} of {len(contacts):,} contacts in range.")
    return filtered


def find_contacts_with_emails(contacts: List[Dict]) -> List[Dict]:
    """
    Identify contacts that have at least one email address field populated.

    Checks emailAddress, emailAddress2, emailAddress3, and emailAddress4.
    Attaches a `_emails_found` list to each matched contact for use
    in preview and audit output.

    Args:
        contacts: Contact list (optionally date-filtered).

    Returns:
        Contacts with at least one email, each with `_emails_found` attached.
    """
    result = []

    for contact in contacts:
        emails = []
        for key in ("emailAddress", "emailAddress2", "emailAddress3", "emailAddress4"):
            if contact.get(key):
                emails.append((key, contact[key]))

        if emails:
            contact["_emails_found"] = emails
            result.append(contact)

    logger.info(f"Contacts with email addresses: {len(result):,}")
    return result
