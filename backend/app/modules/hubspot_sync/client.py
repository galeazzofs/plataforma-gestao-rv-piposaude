import time
import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)

HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotClient:
    def __init__(self, token=None):
        self.token = token or current_app.config.get("HUBSPOT_TOKEN")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers["Content-Type"] = "application/json"

    def _request(self, method, path, **kwargs):
        """Make request with rate limit handling and retry."""
        url = f"{HUBSPOT_API_BASE}{path}"
        max_retries = 3

        for attempt in range(max_retries):
            response = self.session.request(method, url, **kwargs)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 10))
                logger.warning(f"Rate limited, retrying after {retry_after}s")
                time.sleep(retry_after)
                continue

            response.raise_for_status()
            return response.json()

        raise Exception(f"Max retries exceeded for {path}")

    def search_tickets(self, filters, properties, limit=100, after=None):
        """Search tickets via CRM search API."""
        body = {
            "filterGroups": [{"filters": filters}],
            "properties": properties,
            "limit": limit,
        }
        if after:
            body["after"] = after
        return self._request("POST", "/crm/v3/objects/tickets/search", json=body)

    def get_associations(self, object_type, object_id, to_type):
        """Get associations for an object."""
        return self._request(
            "GET",
            f"/crm/v4/objects/{object_type}/{object_id}/associations/{to_type}",
        )

    def get_deal(self, deal_id, properties):
        """Get a deal by ID."""
        params = {"properties": ",".join(properties)}
        return self._request("GET", f"/crm/v3/objects/deals/{deal_id}", params=params)

    def get_ticket(self, ticket_id, properties):
        """Get a ticket by ID."""
        params = {"properties": ",".join(properties)}
        return self._request("GET", f"/crm/v3/objects/tickets/{ticket_id}", params=params)
