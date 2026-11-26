"""Pytest fixtures for BizPresence AI test suite."""

from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, time, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database.db import Base, get_db
from src.main import app
from src.models.booking import Booking, BookingStatus
from src.models.business import Business
from src.models.review import ResponseStatus, Review, Sentiment
from src.models.social_post import PostStatus, SocialPlatform, SocialPost

TEST_DB_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def test_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx AsyncClient wired to the test database."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def sample_business(db_session: AsyncSession) -> Business:
    """Create and persist a sample local business."""
    now = datetime.now(UTC)
    business = Business(
        name="Sunrise Artisan Bakery",
        category="Bakery",
        description="Neighborhood sourdough bakery and specialty coffee shop.",
        address="42 Maple Street",
        city="Austin",
        state="TX",
        zip_code="78701",
        phone="+1-512-555-0199",
        email="hello@sunrisebakery.com",
        website="https://sunrisebakery.example.com",
        operating_hours={"monday": {"open": "07:00", "close": "18:00", "closed": False}},
        created_at=now,
        updated_at=now,
    )
    db_session.add(business)
    await db_session.commit()
    await db_session.refresh(business)
    return business


@pytest_asyncio.fixture(scope="function")
async def sample_review(db_session: AsyncSession, sample_business: Business) -> Review:
    """Create and persist a sample customer review."""
    review = Review(
        business_id=sample_business.id,
        platform="google",
        reviewer_name="Maya Lin",
        rating=5,
        review_text="Best rosemary sourdough in town and super friendly baristas!",
        response_status=ResponseStatus.PENDING,
        sentiment=Sentiment.POSITIVE,
        created_at=datetime.now(UTC),
    )
    db_session.add(review)
    await db_session.commit()
    await db_session.refresh(review)
    return review


@pytest_asyncio.fixture(scope="function")
async def sample_post(db_session: AsyncSession, sample_business: Business) -> SocialPost:
    """Create and persist a sample social media post."""
    post = SocialPost(
        business_id=sample_business.id,
        platform=SocialPlatform.INSTAGRAM,
        content="Fresh croissants out of the oven every morning at 7 AM!",
        status=PostStatus.DRAFT,
        created_at=datetime.now(UTC),
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)
    return post


@pytest_asyncio.fixture(scope="function")
async def sample_booking(db_session: AsyncSession, sample_business: Business) -> Booking:
    """Create and persist a sample booking."""
    tomorrow = date.today() + timedelta(days=1)
    booking = Booking(
        business_id=sample_business.id,
        customer_name="Alex Rivera",
        customer_email="alex.rivera@example.com",
        customer_phone="+1-512-555-0100",
        service="Private Cake Tasting",
        booking_date=tomorrow,
        booking_time=time(14, 0),
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        created_at=datetime.now(UTC),
    )
    db_session.add(booking)
    await db_session.commit()
    await db_session.refresh(booking)
    return booking


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Alias for test_client — provides httpx AsyncClient wired to test database."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_business_id(client: AsyncClient) -> int:
    """Create a test business and return its ID."""
    resp = await client.post(
        "/api/businesses/",
        json={
            "name": "Test Loyalty Bakery",
            "category": "Bakery",
            "city": "Austin",
            "state": "TX",
            "phone": "+15125550199",
            "email": "test@testbiz.com",
        },
    )
    assert resp.status_code in (200, 201), f"Failed to create business: {resp.text}"
    return resp.json()["id"]
