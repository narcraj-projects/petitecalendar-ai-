from sqlalchemy import Column, DateTime, Integer, String, Text, Uuid

from app.db.profiles import Base


class EmailJob(Base):
    __tablename__ = "email_jobs"
    __table_args__ = {"schema": "app_private"}
    booking_id = Column(Uuid, primary_key=True)
    revision = Column(Integer, primary_key=True)
    event_type = Column(String(40), nullable=False)
    user_id = Column(Uuid, nullable=False)
    status = Column(String(20), nullable=False)
    attempts = Column(Integer, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    lease_token = Column(Uuid)
    lease_until = Column(DateTime(timezone=True))
    capability_ciphertext = Column(Text)
    payload_ciphertext = Column(Text)
    frozen_at = Column(DateTime(timezone=True))
    provider_id = Column(String(100))
    last_error = Column(String(40))
