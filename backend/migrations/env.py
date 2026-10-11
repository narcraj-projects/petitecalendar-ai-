from alembic import context
from app.config import get_settings
from app.db.availability import Availability  # noqa: F401 -- register schedule metadata
from app.db.bookings import Booking  # noqa: F401 -- register booking metadata
from app.db.calendar import CalendarJob  # noqa: F401 -- register integration metadata
from app.db.email import EmailJob  # noqa: F401 -- register email metadata
from app.db.events import EventType  # noqa: F401 -- register event metadata
from app.db.lifecycle import BookingAction, BookingChange  # noqa: F401 -- lifecycle metadata
from app.db.profiles import Base, driver_url
from sqlalchemy import create_engine, pool

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url="postgresql+psycopg://", target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("Set DATABASE_URL in the local .env before migrating.")
    engine = create_engine(
        driver_url(settings.database_url), poolclass=pool.NullPool, hide_parameters=True
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
