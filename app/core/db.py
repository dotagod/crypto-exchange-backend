from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Persistent database for users, wallets, etc.
PERSISTENT_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/crypto_exchange")

# Persistent engine for user data
persistent_engine = create_engine(
    PERSISTENT_DATABASE_URL,
    pool_pre_ping=True,
)

# Session factory
PersistentSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=persistent_engine)

Base = declarative_base()


def get_persistent_db():
    """Get database session for persistent data (users, wallets)."""
    db = PersistentSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():   
    """Default database session (persistent)."""
    db = PersistentSessionLocal()
    try:
        yield db
    finally:
        db.close()


# For backward compatibility
engine = persistent_engine
SessionLocal = PersistentSessionLocal 