from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Uuid,
    delete,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.exc import SQLAlchemyError

from app.auth import failure
from app.config import get_settings
from app.db.profiles import Base, HostProfile, ProfileRepository


class GoogleConnection(Base):
    __tablename__ = "google_connections"
    __table_args__ = {"schema": "app_private"}
    user_id = Column(Uuid, primary_key=True)
    generation = Column(Uuid, nullable=False)
    revision = Column(Integer, nullable=False)
    account_id = Column(String(1024), nullable=False)
    token_ciphertext = Column(Text)
    status = Column(String(30), nullable=False)
    blocking_ids = Column(JSONB, nullable=False)
    destination_id = Column(String(1024))
    create_meet = Column(Boolean, nullable=False)
    connected_at = Column(DateTime(timezone=True), nullable=False)


class OAuthState(Base):
    __tablename__ = "google_oauth_states"
    __table_args__ = {"schema": "app_private"}
    state_hash = Column(String(64), primary_key=True)
    user_id = Column(Uuid, nullable=False)
    binding_hash = Column(String(64), nullable=False)
    verifier_ciphertext = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class CalendarJob(Base):
    __tablename__ = "calendar_jobs"
    __table_args__ = {"schema": "app_private"}
    booking_id = Column(Uuid, primary_key=True)
    revision = Column(Integer, primary_key=True)
    operation = Column(String(20), nullable=False)
    user_id = Column(Uuid, nullable=False)
    generation = Column(Uuid, nullable=False)
    destination_id = Column(String(1024), nullable=False)
    create_meet = Column(Boolean, nullable=False)
    status = Column(String(20), nullable=False)
    attempts = Column(Integer, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    lease_token = Column(Uuid)
    lease_until = Column(DateTime(timezone=True))
    last_error = Column(String(40))
    event_id = Column(String(100))
    meet_url = Column(String(2048))
    updated_at = Column(DateTime(timezone=True), nullable=False)


def connection_stamp(row):
    return (row["generation"], row["revision"], row["status"]) if row else None


def connection_view(row):
    if not row:
        return {
            "status": "not_connected",
            "revision": 0,
            "blocking_ids": [],
            "destination_id": None,
            "create_meet": True,
        }
    return {
        k: row[k] for k in ("status", "revision", "blocking_ids", "destination_id", "create_meet")
    }


class CalendarRepository(ProfileRepository):
    def _service(self, c, host):
        c.execute(text("SET LOCAL ROLE petitecalendar_calendar"))
        c.execute(text("SELECT set_config('app.calendar_host',:host,true)"), {"host": str(host)})

    def _lock(self, c, actor):
        self._set_actor(c, actor)
        profile = c.execute(
            select(HostProfile.user_id).where(HostProfile.user_id == actor).with_for_update()
        ).first()
        if not profile:
            raise failure(409, "PROFILE_REQUIRED", "Complete your host profile first.")

    def read(self, actor):
        try:
            with self.engine.begin() as c:
                self._service(c, actor)
                row = (
                    c.execute(
                        select(GoogleConnection.__table__).where(GoogleConnection.user_id == actor)
                    )
                    .mappings()
                    .first()
                )
                return dict(row) if row else None
        except SQLAlchemyError:
            raise failure(
                503, "CALENDAR_UNAVAILABLE", "Calendar connection could not be loaded."
            ) from None

    def start_state(self, actor, state_hash, binding_hash, verifier):
        try:
            with self.engine.begin() as c:
                self._lock(c, actor)
                c.execute(delete(OAuthState).where(OAuthState.user_id == actor))
                c.execute(
                    OAuthState.__table__.insert().values(
                        user_id=actor,
                        state_hash=state_hash,
                        binding_hash=binding_hash,
                        verifier_ciphertext=verifier,
                        expires_at=datetime.now(UTC) + timedelta(minutes=10),
                    )
                )
        except SQLAlchemyError:
            raise failure(
                503, "CALENDAR_UNAVAILABLE", "Calendar consent could not start."
            ) from None

    def consume_state(self, state_hash, binding_hash):
        try:
            with self.engine.begin() as c:
                c.execute(text("SET LOCAL ROLE petitecalendar_calendar"))
                c.execute(
                    text(
                        "SELECT set_config('app.oauth_state',:state,true),"
                        "set_config('app.oauth_binding',:binding,true)"
                    ),
                    {"state": state_hash, "binding": binding_hash},
                )
                row = (
                    c.execute(
                        delete(OAuthState)
                        .where(
                            OAuthState.state_hash == state_hash,
                            OAuthState.binding_hash == binding_hash,
                            OAuthState.expires_at > func.now(),
                        )
                        .returning(OAuthState.__table__)
                    )
                    .mappings()
                    .first()
                )
                return dict(row) if row else None
        except SQLAlchemyError:
            raise failure(
                503, "CALENDAR_UNAVAILABLE", "Calendar consent could not be verified."
            ) from None

    def connect(self, actor, account_id, ciphertext, calendars):
        try:
            with self.engine.begin() as c:
                self._lock(c, actor)
                old = (
                    c.execute(
                        select(GoogleConnection.__table__).where(GoogleConnection.user_id == actor)
                    )
                    .mappings()
                    .first()
                )
                same = old is not None and old["account_id"] == account_id
                ids = {item.id: item for item in calendars}
                destination = old["destination_id"] if same else None
                create_meet = old["create_meet"] if same else True
                if (
                    destination not in ids
                    or not ids[destination].writable
                    or (create_meet and not ids[destination].meet_supported)
                ):
                    destination = None
                values = {
                    "generation": old["generation"] if same else uuid4(),
                    "revision": old["revision"] + 1 if old else 1,
                    "account_id": account_id,
                    "token_ciphertext": ciphertext,
                    "status": "connected",
                    "blocking_ids": [i for i in old["blocking_ids"] if i in ids] if same else [],
                    "destination_id": destination,
                    "create_meet": create_meet,
                    "connected_at": datetime.now(UTC),
                }
                stmt = insert(GoogleConnection).values(user_id=actor, **values)
                c.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[GoogleConnection.user_id], set_=values
                    )
                )
        except SQLAlchemyError:
            raise failure(
                503, "CALENDAR_UNAVAILABLE", "Calendar connection could not be saved."
            ) from None

    def preferences(self, actor, revision, generation, blocking_ids, destination, create_meet):
        try:
            with self.engine.begin() as c:
                self._lock(c, actor)
                row = (
                    c.execute(
                        select(GoogleConnection.__table__).where(GoogleConnection.user_id == actor)
                    )
                    .mappings()
                    .first()
                )
                if (
                    not row
                    or row["revision"] != revision
                    or row["generation"] != generation
                    or row["status"] != "connected"
                ):
                    raise failure(
                        409,
                        "STALE_CONNECTION",
                        "Calendar connection changed. Reload before saving.",
                    )
                c.execute(
                    update(GoogleConnection)
                    .where(GoogleConnection.user_id == actor)
                    .values(
                        blocking_ids=blocking_ids,
                        destination_id=destination,
                        create_meet=create_meet,
                        revision=revision + 1,
                    )
                )
        except SQLAlchemyError:
            raise failure(
                503, "CALENDAR_UNAVAILABLE", "Calendar settings could not be saved."
            ) from None

    def mark_reconnect(self, actor, generation):
        try:
            with self.engine.begin() as c:
                self._service(c, actor)
                c.execute(
                    update(GoogleConnection)
                    .where(
                        GoogleConnection.user_id == actor,
                        GoogleConnection.generation == generation,
                        GoogleConnection.status == "connected",
                    )
                    .values(status="reconnect_required")
                )
        except SQLAlchemyError:
            raise failure(
                503, "CALENDAR_UNAVAILABLE", "Calendar connection could not be verified."
            ) from None

    def disconnect(self, actor, revision):
        try:
            with self.engine.begin() as c:
                self._lock(c, actor)
                row = (
                    c.execute(
                        select(GoogleConnection.__table__).where(GoogleConnection.user_id == actor)
                    )
                    .mappings()
                    .first()
                )
                if not row or row["revision"] != revision:
                    raise failure(
                        409,
                        "STALE_CONNECTION",
                        "Calendar connection changed. Reload before disconnecting.",
                    )
                c.execute(
                    update(GoogleConnection)
                    .where(GoogleConnection.user_id == actor)
                    .values(
                        token_ciphertext=None,
                        status="disconnected",
                        blocking_ids=[],
                        destination_id=None,
                        revision=revision + 1,
                    )
                )
                c.execute(delete(OAuthState).where(OAuthState.user_id == actor))
                return dict(row)
        except SQLAlchemyError:
            raise failure(
                503, "CALENDAR_UNAVAILABLE", "Calendar could not be disconnected."
            ) from None

    def retry(self, actor, booking_id):
        try:
            with self.engine.begin() as c:
                self._lock(c, actor)
                job = (
                    c.execute(
                        select(CalendarJob.__table__)
                        .where(CalendarJob.user_id == actor, CalendarJob.booking_id == booking_id)
                        .order_by(CalendarJob.revision.desc())
                        .limit(1)
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if not job:
                    raise failure(
                        404, "DELIVERY_NOT_FOUND", "This calendar delivery is not available."
                    )
                connection = (
                    c.execute(
                        select(GoogleConnection.__table__).where(GoogleConnection.user_id == actor)
                    )
                    .mappings()
                    .first()
                )
                if (
                    not connection
                    or connection["generation"] != job["generation"]
                    or connection["status"] != "connected"
                ):
                    raise failure(
                        409,
                        "RECONNECT_REQUIRED",
                        "Reconnect the original Google account before retrying.",
                    )
                if job["status"] in ("synced", "working"):
                    raise failure(
                        409,
                        "DELIVERY_IN_PROGRESS",
                        "Delivery is complete or already being processed.",
                    )
                c.execute(
                    update(CalendarJob)
                    .where(
                        CalendarJob.booking_id == booking_id,
                        CalendarJob.revision == job["revision"],
                    )
                    .values(
                        status="queued",
                        attempts=0,
                        due_at=func.now(),
                        lease_token=None,
                        lease_until=None,
                        last_error=None,
                        updated_at=func.now(),
                    )
                )
        except SQLAlchemyError:
            raise failure(
                503, "CALENDAR_UNAVAILABLE", "Calendar delivery could not be retried."
            ) from None


def get_calendar_repository():
    try:
        return CalendarRepository(get_settings().database_url)
    except ValueError:
        raise failure(503, "CALENDAR_UNAVAILABLE", "Calendar storage is not available.") from None
