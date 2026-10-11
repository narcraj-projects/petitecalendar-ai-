from functools import lru_cache
from uuid import UUID

from sqlalchemy import DateTime, String, Uuid, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.auth import failure
from app.config import get_settings


class Base(DeclarativeBase):
    pass


class HostProfile(Base):
    __tablename__ = "host_profiles"
    __table_args__ = {"schema": "app_private"}

    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80))
    username: Mapped[str] = mapped_column(String(32), unique=True)
    timezone: Mapped[str] = mapped_column(String(100))
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def driver_url(value: str) -> str:
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql+psycopg://"):
        return value
    raise ValueError("Use a PostgreSQL connection string.")


@lru_cache(maxsize=2)
def get_engine(url: str):
    return create_engine(
        driver_url(url),
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )


def profile_dict(row) -> dict | None:
    if row is None:
        return None
    return {key: str(row[key]) for key in ("user_id", "display_name", "username", "timezone")}


class ProfileRepository:
    def __init__(self, url: str):
        self.engine = get_engine(url)

    def _set_actor(self, connection, user_id: UUID):
        connection.execute(text("SET LOCAL ROLE petitecalendar_api"))
        connection.execute(
            text("SELECT set_config('app.user_id', :user_id, true)"),
            {"user_id": str(user_id)},
        )

    def get(self, user_id: UUID) -> dict | None:
        try:
            with self.engine.begin() as connection:
                self._set_actor(connection, user_id)
                row = (
                    connection.execute(
                        select(HostProfile.__table__).where(HostProfile.user_id == user_id)
                    )
                    .mappings()
                    .first()
                )
                return profile_dict(row)
        except SQLAlchemyError:
            raise failure(
                503, "PROFILE_UNAVAILABLE", "Your profile could not be loaded. Try again."
            ) from None

    def save(self, user_id: UUID, values: dict) -> dict:
        try:
            with self.engine.begin() as connection:
                self._set_actor(connection, user_id)
                statement = insert(HostProfile).values(user_id=user_id, **values)
                statement = statement.on_conflict_do_update(
                    index_elements=[HostProfile.user_id],
                    set_={**values, "updated_at": func.now()},
                ).returning(HostProfile.__table__)
                return profile_dict(connection.execute(statement).mappings().one())
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise failure(
                    409, "USERNAME_TAKEN", "That booking username is already taken."
                ) from None
            raise failure(
                503, "PROFILE_UNAVAILABLE", "Your profile could not be saved. Try again."
            ) from None
        except SQLAlchemyError:
            raise failure(
                503, "PROFILE_UNAVAILABLE", "Your profile could not be saved. Try again."
            ) from None


def get_profile_repository() -> ProfileRepository:
    settings = get_settings()
    if not settings.database_url:
        raise failure(503, "PROFILE_UNAVAILABLE", "Host profile storage is not available yet.")
    try:
        return ProfileRepository(settings.database_url)
    except ValueError:
        raise failure(
            503, "PROFILE_UNAVAILABLE", "Host profile storage is not available yet."
        ) from None
