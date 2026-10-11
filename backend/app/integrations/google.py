"""Google OAuth and Calendar boundary. No raw provider errors leave this adapter."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet, InvalidToken
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2 import OAuth2Error

from app.domain.availability import Interval

SCOPES = (
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
    "https://www.googleapis.com/auth/calendar.events",
)
API = "https://www.googleapis.com/calendar/v3"


def calendar_event_id(booking_id, revision):
    return "pc" + hashlib.sha256(f"{booking_id}:{revision}".encode()).hexdigest()


class CalendarError(Exception):
    def __init__(self, code="provider_unavailable"):
        self.code = code
        super().__init__(code)


class TokenVault:
    def __init__(self, key):
        try:
            self.fernet = Fernet(key.encode())
        except (ValueError, TypeError):
            raise CalendarError("configuration_required") from None

    def seal(self, actor, value):
        return self.fernet.encrypt(
            json.dumps({"actor": str(actor), "value": value}).encode()
        ).decode()

    def open(self, actor, ciphertext):
        try:
            value = json.loads(self.fernet.decrypt(ciphertext.encode()))
            if value["actor"] != str(actor):
                raise ValueError()
            return value["value"]
        except (InvalidToken, ValueError, KeyError, TypeError, AttributeError):
            raise CalendarError("reconnect_required") from None


@dataclass(frozen=True)
class CalendarItem:
    id: str
    name: str
    writable: bool
    meet_supported: bool
    primary: bool = False


class GoogleCalendar:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=httpx.Timeout(12, connect=5))

    def close(self):
        self.client.close()

    def _json(self, response):
        try:
            return response.json()
        except ValueError:
            raise CalendarError() from None

    def _flow(self, state=None, verifier=None):
        return Flow.from_client_config(
            {
                "web": {
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.settings.google_callback_url],
                }
            },
            scopes=SCOPES,
            state=state,
            redirect_uri=self.settings.google_callback_url,
            code_verifier=verifier,
            autogenerate_code_verifier=verifier is None,
        )

    def authorization(self, state):
        flow = self._flow(state=state)
        url, _ = flow.authorization_url(
            access_type="offline", prompt="consent", include_granted_scopes="true"
        )
        return url, flow.code_verifier

    def exchange(self, code, state, verifier):
        try:
            flow = self._flow(state=state, verifier=verifier)
            try:
                token = flow.fetch_token(code=code, timeout=12)
            except Warning as changed_scope:
                # OAuthlib rejects any scope difference, including previously granted extras.
                # Accept a validated token only when every required Calendar scope remains.
                token = getattr(changed_scope, "token", None)
                if not isinstance(token, dict):
                    raise CalendarError("authorization_failed") from None
            granted = token.get("scope", SCOPES)
            if isinstance(granted, str):
                granted = granted.split()
            if (
                not isinstance(granted, (list, tuple))
                or not set(SCOPES).issubset(set(granted))
                or not token.get("refresh_token")
                or not token.get("access_token")
            ):
                raise CalendarError("consent_incomplete")
            return token["refresh_token"]
        except CalendarError:
            raise
        except OAuth2Error as error:
            codes = {
                "invalid_client": "client_configuration",
                "invalid_grant": "consent_expired",
                "redirect_uri_mismatch": "client_configuration",
            }
            raise CalendarError(codes.get(error.error, "authorization_failed")) from None
        except Exception:
            raise CalendarError("authorization_failed") from None

    def access_token(self, refresh_token):
        try:
            r = self.client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                },
            )
            if r.status_code in (400, 401):
                raise CalendarError("reconnect_required")
            if r.status_code != 200:
                raise CalendarError()
            token = self._json(r).get("access_token")
            if not token:
                raise CalendarError()
            return token
        except (httpx.HTTPError, ValueError):
            raise CalendarError() from None

    def _request(self, method, path, token, **kwargs):
        try:
            extra_headers = kwargs.pop("headers", {})
            r = self.client.request(
                method,
                API + path,
                headers={"Authorization": "Bearer " + token, **extra_headers},
                **kwargs,
            )
            if r.status_code == 401:
                raise CalendarError("reconnect_required")
            return r
        except httpx.HTTPError:
            raise CalendarError() from None

    def calendars(self, token):
        result = []
        page = None
        for _ in range(20):
            r = self._request(
                "GET",
                "/users/me/calendarList",
                token,
                params={"maxResults": 250, **({"pageToken": page} if page else {})},
            )
            if r.status_code != 200:
                raise CalendarError()
            body = self._json(r)
            for row in body.get("items", []):
                result.append(
                    CalendarItem(
                        row["id"],
                        row.get("summaryOverride", row.get("summary", "Calendar")),
                        row.get("accessRole") in ("owner", "writer"),
                        "hangoutsMeet"
                        in row.get("conferenceProperties", {}).get(
                            "allowedConferenceSolutionTypes", []
                        ),
                        row.get("primary", False),
                    )
                )
            page = body.get("nextPageToken")
            if not page:
                return result
        raise CalendarError("calendar_limit")

    def free_busy(self, token, ids, start, end):
        if not ids or len(ids) > 20:
            raise CalendarError("selection_required")
        r = self._request(
            "POST",
            "/freeBusy",
            token,
            json={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "timeZone": "UTC",
                "items": [{"id": i} for i in ids],
            },
        )
        if r.status_code != 200:
            raise CalendarError()
        try:
            calendars = self._json(r)["calendars"]
            result = []
            for id in ids:
                value = calendars[id]
                if value.get("errors") or "busy" not in value:
                    raise CalendarError("calendar_unavailable")
                for busy in value["busy"]:
                    a = datetime.fromisoformat(busy["start"])
                    b = datetime.fromisoformat(busy["end"])
                    if a.tzinfo is None or b.tzinfo is None or a >= b:
                        raise ValueError()
                    result.append(Interval(a.astimezone(UTC), b.astimezone(UTC)))
            return tuple(result)
        except (KeyError, ValueError, TypeError):
            raise CalendarError("calendar_unavailable") from None

    def get_event(self, token, calendar_id, event_id):
        r = self._request(
            "GET", f"/calendars/{quote(calendar_id, safe='')}/events/{event_id}", token
        )
        if r.status_code in (404, 410):
            return None
        if r.status_code != 200:
            raise CalendarError()
        return self._json(r)

    def ensure_event(self, token, calendar_id, booking, create_meet):
        event_id = calendar_event_id(booking["id"], booking["revision"])
        existing = self.get_event(token, calendar_id, event_id)
        if existing is None:
            snapshot = booking["snapshot"]
            body = {
                "id": event_id,
                "summary": snapshot["title"],
                "location": snapshot["location"],
                "start": {
                    "dateTime": booking["start_at"].isoformat(),
                    "timeZone": snapshot["host_timezone"],
                },
                "end": {
                    "dateTime": booking["end_at"].isoformat(),
                    "timeZone": snapshot["host_timezone"],
                },
                "description": "Booked with PetCalendar AI. Guest: " + booking["invitee_name"],
                "extendedProperties": {
                    "private": {
                        "petitecalendarBooking": str(booking["id"]),
                        "petitecalendarRevision": str(booking["revision"]),
                    }
                },
                "visibility": "private",
                "guestsCanModify": False,
                "reminders": {"useDefault": False},
            }
            if create_meet:
                body["conferenceData"] = {
                    "createRequest": {
                        "requestId": event_id,
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                }
            r = self._request(
                "POST",
                f"/calendars/{quote(calendar_id, safe='')}/events",
                token,
                params={"conferenceDataVersion": 1, "sendUpdates": "none"},
                json=body,
            )
            if r.status_code == 409:
                existing = self.get_event(token, calendar_id, event_id)
            elif r.status_code in (200, 201):
                existing = self._json(r)
            else:
                raise CalendarError()
        if not existing or existing.get("status") == "cancelled":
            raise CalendarError("event_changed")
        props = existing.get("extendedProperties", {}).get("private", {})
        if props.get("petitecalendarBooking") != str(booking["id"]) or props.get(
            "petitecalendarRevision"
        ) != str(booking["revision"]):
            raise CalendarError("event_changed")
        try:
            event_start = datetime.fromisoformat(existing["start"]["dateTime"])
            event_end = datetime.fromisoformat(existing["end"]["dateTime"])
            if event_start != booking["start_at"] or event_end != booking["end_at"]:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise CalendarError("event_changed") from None
        if create_meet:
            conference = existing.get("conferenceData", {})
            status = conference.get("createRequest", {}).get("status", {}).get("statusCode")
            if status == "failure":
                raise CalendarError("meet_failed")
            link = existing.get("hangoutLink") or next(
                (
                    p.get("uri")
                    for p in conference.get("entryPoints", [])
                    if p.get("entryPointType") == "video"
                ),
                None,
            )
            if not link:
                raise CalendarError("meet_pending")
            parsed = urlparse(link)
            if parsed.scheme != "https" or parsed.hostname != "meet.google.com":
                raise CalendarError("meet_failed")
        else:
            link = None
        return {"event_id": event_id, "meet_url": link}

    def delete_owned_event(self, token, calendar_id, booking_id, revision):
        event_id = calendar_event_id(booking_id, revision)
        event = self.get_event(token, calendar_id, event_id)
        if not event or event.get("status") == "cancelled":
            return
        props = event.get("extendedProperties", {}).get("private", {})
        if props.get("petitecalendarBooking") != str(booking_id) or props.get(
            "petitecalendarRevision"
        ) != str(revision):
            raise CalendarError("event_changed")
        r = self._request(
            "DELETE",
            f"/calendars/{quote(calendar_id, safe='')}/events/{event_id}",
            token,
            params={"sendUpdates": "none"},
            headers={"If-Match": event["etag"]} if event.get("etag") else {},
        )
        if r.status_code == 412:
            raise CalendarError("event_changed")
        if r.status_code not in (204, 404, 410):
            raise CalendarError()

    def busy_without_booking(self, token, calendar_id, start, end, booking_id, excluded):
        """Never subtract merged free/busy: preserve every overlapping unrelated event."""
        result, page = [], None
        for _ in range(20):
            r = self._request(
                "GET",
                f"/calendars/{quote(calendar_id, safe='')}/events",
                token,
                params={
                    "timeMin": start.isoformat(),
                    "timeMax": end.isoformat(),
                    "singleEvents": "true",
                    "showDeleted": "false",
                    "maxResults": 2500,
                    "fields": "timeZone,nextPageToken,"
                    "items(id,status,transparency,start,end,extendedProperties)",
                    **({"pageToken": page} if page else {}),
                },
            )
            if r.status_code != 200:
                raise CalendarError()
            try:
                data = self._json(r)
                for event in data.get("items", []):
                    if (
                        event.get("status") == "cancelled"
                        or event.get("transparency") == "transparent"
                    ):
                        continue
                    props = event.get("extendedProperties", {}).get("private", {})
                    revision = excluded.get(event.get("id"))
                    if (
                        revision is not None
                        and props.get("petitecalendarBooking") == str(booking_id)
                        and props.get("petitecalendarRevision") == str(revision)
                    ):
                        continue

                    def boundary(value):
                        if "dateTime" in value:
                            instant = datetime.fromisoformat(value["dateTime"])
                            if instant.tzinfo is None:
                                raise ValueError()
                            return instant.astimezone(UTC)
                        return (
                            datetime.fromisoformat(value["date"])
                            .replace(tzinfo=ZoneInfo(data["timeZone"]))
                            .astimezone(UTC)
                        )

                    a, b = boundary(event["start"]), boundary(event["end"])
                    if a >= b:
                        raise ValueError()
                    result.append(Interval(a, b))
                page = data.get("nextPageToken")
                if not page:
                    return tuple(result)
            except (ValueError, KeyError, TypeError):
                raise CalendarError("calendar_unavailable") from None
        raise CalendarError("calendar_limit")

    def revoke(self, refresh_token):
        try:
            r = self.client.post(
                "https://oauth2.googleapis.com/revoke", data={"token": refresh_token}
            )
            return r.status_code in (200, 400)
        except httpx.HTTPError:
            return False
