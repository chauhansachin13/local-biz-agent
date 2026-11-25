"""Pytest fixtures for BizPresence AI test suite."""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Booking, Business, Review, SocialPost


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """Create an isolated in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(scope="function")
def test_client(test_db: Session) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient wired to the isolated test database."""

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def sample_business(test_db: Session) -> Business:
    """Create and persist a sample local business in the test database."""
    business = Business(
        name="Sunrise Artisan Bakery",
        category="Bakery & Cafe",
        description="Neighborhood sourdough bakery and specialty coffee shop.",
        address="42 Maple Street, Austin, TX 78701",
        phone="+1-512-555-0199",
        website="https://sunrisebakery.example.com",
        hours="Mon-Sun 07:00-18:00",
    )
    test_db.add(business)
    test_db.commit()
    test_db.refresh(business)
    return business


@pytest.fixture(scope="function")
def sample_review(test_db: Session, sample_business: Business) -> Review:
    """Create and persist a sample customer review for the sample business."""
    review = Review(
        business_id=sample_business.id,
        author_name="Maya Lin",
        rating=5,
        comment="Best rosemary sourdough in town and super friendly baristas!",
        sentiment="positive",
        sentiment_score=0.95,
        reply_text=None,
    )
    test_db.add(review)
    test_db.commit()
    test_db.refresh(review)
    return review


@pytest.fixture(scope="function")
def sample_post(test_db: Session, sample_business: Business) -> SocialPost:
    """Create and persist a sample social media post for the sample business."""
    post = SocialPost(
        business_id=sample_business.id,
        platform="instagram",
        content="Fresh croissants out of the oven every morning at 7 AM!",
        hashtags="#ArtisanBakery #FreshBaked #ShopLocal",
        status="draft",
    )
    test_db.add(post)
    test_db.commit()
    test_db.refresh(post)
    return post


@pytest.fixture(scope="function")
def sample_booking(test_db: Session, sample_business: Business) -> Booking:
    """Create and persist a sample booking for the sample business."""
    start_time = datetime.now(timezone.utc).replace(
        hour=14, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    booking = Booking(
        business_id=sample_business.id,
        customer_name="Alex Rivera",
        customer_email="alex.rivera@example.com",
        service_name="Private Cake Tasting",
        scheduled_at=start_time,
        duration_minutes=60,
        status="confirmed",
    )
    test_db.add(booking)
    test_db.commit()
    test_db.refresh(booking)
    return booking
