"""
Shared pytest fixtures for the test suite.

Provides an in-memory SQLite session usable across all test files,
eliminating the duplicated fixture definitions in test_multiagent_logic.py
and test_agent_audit.py.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base


@pytest.fixture
def db_session():
    """SQLite in-memory session for isolated unit tests.

    Uses StaticPool so the same in-memory database is shared across
    all threads that use this connection, which is required for
    SQLite :memory: databases in multi-threaded test scenarios.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
