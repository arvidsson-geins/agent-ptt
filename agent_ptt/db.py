"""Database layer — SQLAlchemy + libSQL (Turso-compatible).

Local development:  DATABASE_URL=sqlite:///agent_ptt.db  (default)
Production/Turso:   DATABASE_URL=libsql://your-db.turso.io?authToken=...
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from agent_ptt.models import Base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///agent_ptt.db")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
