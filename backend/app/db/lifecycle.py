"""Private lifecycle history. The invitee capability never appears in an API response."""

from contextlib import contextmanager

from sqlalchemy import Column, DateTime, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.profiles import Base


class BookingChange(Base):
    __tablename__ = "booking_changes"
    __table_args__ = {"schema": "app_private"}
    id = Column(Uuid, primary_key=True)
    booking_id = Column(Uuid, nullable=False)
    user_id = Column(Uuid, nullable=False)
    booking_revision = Column(Integer, nullable=False)
    candidates = Column(JSONB, nullable=False)
    timezone = Column(String(100), nullable=False)
    capability_ciphertext = Column(Text)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class BookingAction(Base):
    __tablename__ = "booking_actions"
    __table_args__ = {"schema": "app_private"}
    id = Column(Uuid, primary_key=True)
    booking_id = Column(Uuid, nullable=False)
    user_id = Column(Uuid, nullable=False)
    request_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


def lock_booking(c, booking_id):
    # Same transaction advisory lock for mutation and provider delivery. No personal data.
    c.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:id, 8))"), {"id": str(booking_id)}
    )


@contextmanager
def delivery_lock(engine, booking_id):
    with engine.begin() as c:
        lock_booking(c, booking_id)
        yield
