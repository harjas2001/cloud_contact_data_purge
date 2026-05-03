"""
contact_data_purge/client.py
─────────────────────────────────────────────────────────────────────────────
Authenticated HTTP client for the contact centre platform REST API.

Wraps requests with Bearer token auth, consistent error handling,
and optional SSL verification. All API calls in the pipeline go
through this single client so auth and error behaviour is centralised.
─────────────────────────────────────────────────────────────────────────────
"""

import logging
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


class APIClient:
    """
    Thin authenticated client for a REST API.

    Args:
        base_url:     API base URL (e.g. https://api.mypurecloud.com.au).
        access_token: Bearer token obtained via OAuth2.
        verify_cert:  Whether to verify SSL certificates (default True).
    """

    def __init__(self, base_url: str, access_token: str, verify_cert: bool = True):
        self.base_url     = base_url.rstrip("/")
        self.access_token = access_token
        self.verify_cert  = verify_cert

    @property
    def _headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type":  "application/json",
        }

    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Authenticated GET request.

        Args:
            endpoint: API path (e.g. /api/v2/externalcontacts/contacts).
            params:   Optional query parameters.

        Returns:
            Parsed JSON response dict.
        """
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """
        Authenticated POST request.

        Args:
            endpoint: API path.
            data:     Request body (serialised as JSON).

        Returns:
            Parsed JSON response dict.
        """
        return self._request("POST", endpoint, data=data)

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict:
        url = f"{self.base_url}{endpoint}"

        try:
            if method == "GET":
                response = requests.get(
                    url, headers=self._headers, params=params,
                    verify=self.verify_cert, timeout=30,
                )
            elif method == "POST":
                response = requests.post(
                    url, headers=self._headers, json=data,
                    verify=self.verify_cert, timeout=30,
                )
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {method} {url} — {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise
