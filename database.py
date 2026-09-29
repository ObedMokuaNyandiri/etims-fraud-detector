"""
Database engine, session factory, and initialization.
Uses standard sync SQLAlchemy with SQLite for the Flask MVP.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///./data/etims.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def init_db():
    """Create all tables if they don't exist."""
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

def get_db():
    """Yield a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
