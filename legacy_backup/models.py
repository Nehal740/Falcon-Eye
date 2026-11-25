
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime
from database import Base


class FirewallEvent(Base):
    __tablename__ = "firewall_events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, index=True)
    agent_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    resource = Column(String)
    decision = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    approval_id = Column(String, unique=True, index=True)
    agent_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    resource = Column(String)
    reason = Column(String)
    status = Column(String, default="PENDING")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )