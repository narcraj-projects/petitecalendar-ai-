"""Resend boundary. Only fixed error categories escape; never log provider payloads."""

import httpx


class EmailError(Exception):
    def __init__(self, code="provider_unavailable", permanent=False, ambiguous=False):
        self.code, self.permanent, self.ambiguous = code, permanent, ambiguous
        super().__init__(code)


class ResendEmail:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=httpx.Timeout(12, connect=5))

    def close(self):
        self.client.close()

    def send(self, payload, key):
        if not self.settings.email_configured:
            raise EmailError("configuration_required", permanent=True)
        try:
            response = self.client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={
                    "Authorization": "Bearer " + self.settings.resend_api_key,
                    "Idempotency-Key": key,
                },
            )
        except httpx.HTTPError:
            raise EmailError(ambiguous=True) from None
        if response.status_code in (401, 403):
            raise EmailError("sender_configuration", permanent=True)
        if response.status_code in (400, 422):
            raise EmailError("invalid_email", permanent=True)
        if response.status_code == 409:
            raise EmailError("idempotency_conflict", ambiguous=True)
        if response.status_code == 429:
            raise EmailError("rate_limited")
        if response.status_code != 200:
            raise EmailError(ambiguous=True)
        try:
            id = response.json()["id"]
            if not isinstance(id, str) or not 1 <= len(id) <= 100:
                raise ValueError()
            return id
        except (ValueError, KeyError, TypeError):
            raise EmailError(ambiguous=True) from None
