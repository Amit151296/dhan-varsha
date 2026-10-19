from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.routers.screener import _find_fresh_cached_job


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_user(db):
    user = models.User(full_name="Test User", email="test@example.com", hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_job(db, user, *, sector_key="IT", status="success", hours_ago=1):
    job = models.ScreenerFetchJob(
        user_id=user.id,
        sector_key=sector_key,
        sector_label="IT",
        status=status,
        row_count=1,
        completed_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_finds_recent_successful_job_for_same_sector(db_session):
    user = _make_user(db_session)
    job = _make_job(db_session, user, hours_ago=2)

    found = _find_fresh_cached_job(db_session, user, "IT")

    assert found is not None
    assert found.id == job.id


def test_ignores_jobs_older_than_the_cache_window(db_session):
    user = _make_user(db_session)
    _make_job(db_session, user, hours_ago=48)

    assert _find_fresh_cached_job(db_session, user, "IT") is None


def test_ignores_failed_jobs(db_session):
    user = _make_user(db_session)
    _make_job(db_session, user, status="failed", hours_ago=1)

    assert _find_fresh_cached_job(db_session, user, "IT") is None


def test_ignores_a_different_sector(db_session):
    user = _make_user(db_session)
    _make_job(db_session, user, sector_key="Bank", hours_ago=1)

    assert _find_fresh_cached_job(db_session, user, "IT") is None


def test_returns_the_most_recent_match(db_session):
    user = _make_user(db_session)
    _make_job(db_session, user, hours_ago=5)
    newest = _make_job(db_session, user, hours_ago=1)

    found = _find_fresh_cached_job(db_session, user, "IT")

    assert found.id == newest.id
