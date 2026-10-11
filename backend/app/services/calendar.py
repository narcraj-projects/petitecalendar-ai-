import secrets
from dataclasses import asdict, dataclass
from datetime import datetime
from urllib.parse import urlparse

from app.auth import failure
from app.config import get_settings
from app.db.bookings import digest
from app.db.calendar import connection_stamp, connection_view, get_calendar_repository
from app.integrations.google import CalendarError, GoogleCalendar, TokenVault


@dataclass(frozen=True)
class ExternalAvailability:
    stamp: tuple | None
    busy: tuple = ()


class CalendarService:
    def __init__(self, repository=None, provider=None, settings=None):
        self.settings = settings or get_settings()
        self.repository = repository or get_calendar_repository()
        self.provider = provider or GoogleCalendar(self.settings)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.provider.close()

    def _vault(self):
        return TokenVault(self.settings.token_encryption_key)

    def _configured(self):
        parsed = urlparse(self.settings.app_base_url)
        if not self.settings.google_configured or (
            parsed.scheme != "https" and parsed.hostname not in ("127.0.0.1", "localhost")
        ):
            raise failure(
                503,
                "CALENDAR_CONFIGURATION_REQUIRED",
                "Google Calendar needs server configuration.",
            )

    def _access(self, row):
        try:
            token = self._vault().open(row["user_id"], row["token_ciphertext"])
            return self.provider.access_token(token)
        except CalendarError as e:
            if e.code == "reconnect_required":
                self.repository.mark_reconnect(row["user_id"], row["generation"])
            raise

    def status(self, actor):
        row = self.repository.read(actor)
        calendars = []
        if row and row["status"] == "connected":
            try:
                calendars = [asdict(i) for i in self.provider.calendars(self._access(row))]
            except CalendarError as e:
                raise failure(
                    503,
                    "CALENDAR_UNAVAILABLE",
                    "Google Calendar could not be checked. Reconnect or retry.",
                ) from e
        return {
            "configured": self.settings.google_configured,
            "connection": connection_view(row),
            "calendars": calendars,
        }

    def start(self, actor):
        self._configured()
        state = secrets.token_urlsafe(32)
        binding = secrets.token_urlsafe(32)
        try:
            url, verifier = self.provider.authorization(state)
            self.repository.start_state(
                actor, digest(state), digest(binding), self._vault().seal(actor, verifier)
            )
            return url, binding
        except CalendarError:
            raise failure(
                503, "CALENDAR_UNAVAILABLE", "Google Calendar consent could not start."
            ) from None

    def callback(self, state, binding, code):
        self._configured()
        stored = self.repository.consume_state(digest(state), digest(binding))
        if not stored:
            raise CalendarError("invalid_state")
        if not code:
            return "denied"
        actor = stored["user_id"]
        verifier = self._vault().open(actor, stored["verifier_ciphertext"])
        refresh = self.provider.exchange(code, state, verifier)
        try:
            calendars = self.provider.calendars(self.provider.access_token(refresh))
        except CalendarError:
            raise CalendarError("calendar_access_failed") from None
        primary = next((i for i in calendars if i.primary), None)
        if not primary:
            raise CalendarError("calendar_unavailable")
        self.repository.connect(actor, primary.id, self._vault().seal(actor, refresh), calendars)
        return "connected"

    def save(self, actor, body):
        row = self.repository.read(actor)
        if not row or row["status"] != "connected":
            raise failure(
                409, "RECONNECT_REQUIRED", "Connect Google Calendar before selecting calendars."
            )
        try:
            ids = {i.id: i for i in self.provider.calendars(self._access(row))}
        except CalendarError:
            raise failure(
                503, "CALENDAR_UNAVAILABLE", "Google calendars could not be checked. Try again."
            ) from None
        chosen = set(body.blocking_ids)
        if (
            not chosen.issubset(ids)
            or body.destination_id not in ids
            or not ids[body.destination_id].writable
        ):
            raise failure(
                422, "INVALID_CALENDARS", "Choose accessible calendars and a writable destination."
            )
        if body.create_meet and not ids[body.destination_id].meet_supported:
            raise failure(
                422,
                "MEET_UNSUPPORTED",
                "This calendar does not support Meet. Choose another or disable Meet.",
            )
        # Always block the destination too, preventing conflicts with non-app events there.
        blocking = sorted(chosen | {body.destination_id})
        if len(blocking) > 20:
            raise failure(
                422,
                "INVALID_CALENDARS",
                "Choose at most 20 blocking calendars including the destination.",
            )
        self.repository.preferences(
            actor, body.revision, row["generation"], blocking, body.destination_id, body.create_meet
        )
        return {"connection": connection_view(self.repository.read(actor))}

    def disconnect(self, actor, revision):
        row = self.repository.disconnect(actor, revision)
        revoked = False
        if row["token_ciphertext"]:
            try:
                revoked = self.provider.revoke(self._vault().open(actor, row["token_ciphertext"]))
            except CalendarError:
                pass
        return {
            "connection": connection_view(self.repository.read(actor)),
            "google_revoked": revoked,
        }

    def busy(self, actor, start: datetime, end: datetime):
        row = self.repository.read(actor)
        stamp = connection_stamp(row)
        if not row or row["status"] == "disconnected":
            return ExternalAvailability(stamp)
        if row["status"] != "connected" or not row["destination_id"] or not row["blocking_ids"]:
            raise failure(
                503,
                "CALENDAR_NOT_READY",
                "The host’s calendar connection needs attention. Try later.",
            )
        try:
            busy = self.provider.free_busy(self._access(row), row["blocking_ids"], start, end)
        except CalendarError:
            raise failure(
                503,
                "CALENDAR_UNAVAILABLE",
                "The host’s calendar could not be checked. Try again later.",
            ) from None
        return ExternalAvailability(stamp, busy)

    def busy_excluding(self, actor, start, end, booking_id, jobs):
        row = self.repository.read(actor)
        if not row or row["status"] == "disconnected":
            return ExternalAvailability(connection_stamp(row))
        if row["status"] != "connected" or not row["destination_id"] or not row["blocking_ids"]:
            raise failure(
                503, "CALENDAR_NOT_READY", "The host's calendar needs attention. Try later."
            )
        excluded = {}
        for job in jobs:
            if job["generation"] == row["generation"]:
                excluded.setdefault(job["destination_id"], {})[job["event_id"]] = job["revision"]
        try:
            token = self._access(row)
            normal = [id for id in row["blocking_ids"] if id not in excluded]
            busy = self.provider.free_busy(token, normal, start, end) if normal else ()
            for id in row["blocking_ids"]:
                if id in excluded:
                    busy += self.provider.busy_without_booking(
                        token, id, start, end, booking_id, excluded[id]
                    )
            return ExternalAvailability(connection_stamp(row), busy)
        except CalendarError:
            raise failure(
                503,
                "CALENDAR_UNAVAILABLE",
                "The host's calendar could not be checked. Try again later.",
            ) from None


def get_calendar_service():
    with CalendarService() as service:
        yield service
