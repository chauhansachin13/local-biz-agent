"""Seed script inserting sample businesses, reviews, social posts, and bookings via SQLAlchemy."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Ensure project root is importable when invoked as `python scripts/seed_data.py`
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings  # noqa: E402
from src.database.db import Base  # noqa: E402
from src.models.booking import Booking, BookingStatus  # noqa: E402
from src.models.business import Business  # noqa: E402
from src.models.review import ResponseStatus, Review, Sentiment  # noqa: E402
from src.models.social_post import PostStatus, SocialPlatform, SocialPost  # noqa: E402


def seed_database(reset: bool = True) -> None:
    """Populate the database directly via synchronous SQLAlchemy."""
    sync_url = settings.database_url.replace("+aiosqlite", "")
    connect_args = {"check_same_thread": False} if sync_url.startswith("sqlite") else {}
    engine = create_engine(sync_url, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        if reset:
            db.query(Booking).delete()
            db.query(Review).delete()
            db.query(SocialPost).delete()
            db.query(Business).delete()
            db.commit()
        elif db.query(Business).count() > 0:
            print("Database already populated. Skipping seed (pass reset=True to overwrite).")
            return

        now = datetime.now(timezone.utc)
        today = date.today()

        # ------------------------------------------------------------------
        # 1. Sample Businesses (2: Restaurant & Salon)
        # ------------------------------------------------------------------
        restaurant = Business(
            name="Bella Napoli Trattoria",
            category="restaurant",
            description=(
                "Authentic wood-fired Neapolitan pizza, handmade pasta, and curated Italian wines "
                "served in a warm neighborhood dining room."
            ),
            address="412 Elmwood Ave",
            city="Austin",
            state="TX",
            zip_code="78704",
            phone="(512) 555-0148",
            email="hello@bellanapoli-austin.com",
            website="https://bellanapoli-austin.com",
            google_business_id="ChIJ_BellaNapoli_Austin_001",
            operating_hours={
                "monday": {"open": "11:30", "close": "21:30", "closed": False},
                "tuesday": {"open": "11:30", "close": "21:30", "closed": False},
                "wednesday": {"open": "11:30", "close": "22:00", "closed": False},
                "thursday": {"open": "11:30", "close": "22:00", "closed": False},
                "friday": {"open": "11:30", "close": "23:00", "closed": False},
                "saturday": {"open": "11:00", "close": "23:00", "closed": False},
                "sunday": {"open": "11:00", "close": "21:00", "closed": False},
            },
        )

        salon = Business(
            name="Lumina Hair & Spa",
            category="salon",
            description=(
                "Boutique hair studio and organic day spa specializing in lived-in balayage, "
                "precision cuts, and botanical scalp rituals."
            ),
            address="1280 Market St, Suite 2B",
            city="Seattle",
            state="WA",
            zip_code="98101",
            phone="(206) 555-0192",
            email="care@luminahairspa.com",
            website="https://luminahairspa.com",
            google_business_id=None,
            operating_hours={
                "monday": {"open": "09:00", "close": "18:00", "closed": True},
                "tuesday": {"open": "09:30", "close": "19:00", "closed": False},
                "wednesday": {"open": "09:30", "close": "19:00", "closed": False},
                "thursday": {"open": "09:30", "close": "20:00", "closed": False},
                "friday": {"open": "09:00", "close": "19:00", "closed": False},
                "saturday": {"open": "09:00", "close": "17:00", "closed": False},
                "sunday": {"open": "10:00", "close": "16:00", "closed": False},
            },
        )

        db.add_all([restaurant, salon])
        db.flush()

        # ------------------------------------------------------------------
        # 2. Sample Reviews (10 total: mix of positive, neutral, negative)
        # ------------------------------------------------------------------
        reviews = [
            Review(
                business_id=restaurant.id,
                platform="google",
                reviewer_name="Elena Rodriguez",
                rating=5,
                review_text="Best wood-fired Margherita pizza in Austin! Our server Marco was super attentive and the tiramisu was unforgettable.",
                sentiment=Sentiment.POSITIVE,
                response_text="Grazie mille, Elena! We are thrilled you loved the Margherita pizza and tiramisu!",
                response_status=ResponseStatus.RESPONDED,
                responded_at=now - timedelta(days=3),
                created_at=now - timedelta(days=4),
            ),
            Review(
                business_id=restaurant.id,
                platform="facebook",
                reviewer_name="Marcus Vance",
                rating=2,
                review_text="We had a 7:30 reservation but still waited 35 minutes for a table. Pasta tasted good once it arrived, though lukewarm.",
                sentiment=Sentiment.NEGATIVE,
                response_status=ResponseStatus.PENDING,
                created_at=now - timedelta(days=1),
            ),
            Review(
                business_id=restaurant.id,
                platform="google",
                reviewer_name="Priya Nair",
                rating=5,
                review_text="Cozy ambiance, great wine list, and fresh handmade truffle pasta. Perfect anniversary spot!",
                sentiment=Sentiment.POSITIVE,
                response_status=ResponseStatus.PENDING,
                created_at=now - timedelta(days=2),
            ),
            Review(
                business_id=restaurant.id,
                platform="google",
                reviewer_name="Derek Lin",
                rating=3,
                review_text="Food is solid and portions are fair, though noise levels on Friday night made conversation tricky.",
                sentiment=Sentiment.NEUTRAL,
                response_status=ResponseStatus.PENDING,
                created_at=now - timedelta(days=5),
            ),
            Review(
                business_id=restaurant.id,
                platform="facebook",
                reviewer_name="Hannah Brooks",
                rating=4,
                review_text="Delicious carbonara and friendly staff. Slightly pricey for lunch, but worth it for the quality.",
                sentiment=Sentiment.POSITIVE,
                response_text="Thank you for dining with us, Hannah! Glad you enjoyed the carbonara.",
                response_status=ResponseStatus.RESPONDED,
                responded_at=now - timedelta(days=6),
                created_at=now - timedelta(days=7),
            ),
            Review(
                business_id=salon.id,
                platform="google",
                reviewer_name="Chloe Bennett",
                rating=5,
                review_text="Maya nailed my balayage! The salon feels so relaxing and clean, and my hair looks healthier than ever.",
                sentiment=Sentiment.POSITIVE,
                response_text="Thank you so much, Chloe! Maya loved working with you—enjoy your gorgeous new color!",
                response_status=ResponseStatus.RESPONDED,
                responded_at=now - timedelta(days=2),
                created_at=now - timedelta(days=3),
            ),
            Review(
                business_id=salon.id,
                platform="google",
                reviewer_name="Jordan Kim",
                rating=1,
                review_text="Appointment started 25 minutes late and the front desk seemed disorganized. Haircut felt rushed.",
                sentiment=Sentiment.NEGATIVE,
                response_status=ResponseStatus.PENDING,
                created_at=now - timedelta(hours=18),
            ),
            Review(
                business_id=salon.id,
                platform="google",
                reviewer_name="Sofia Morales",
                rating=5,
                review_text="The botanical scalp ritual was pure bliss! Professional staff and wonderful atmosphere.",
                sentiment=Sentiment.POSITIVE,
                response_status=ResponseStatus.PENDING,
                created_at=now - timedelta(days=1),
            ),
            Review(
                business_id=salon.id,
                platform="facebook",
                reviewer_name="Taylor Reed",
                rating=3,
                review_text="Nice blowout, friendly stylist, just a little expensive compared to nearby studios.",
                sentiment=Sentiment.NEUTRAL,
                response_status=ResponseStatus.PENDING,
                created_at=now - timedelta(days=4),
            ),
            Review(
                business_id=salon.id,
                platform="google",
                reviewer_name="Nadia Patel",
                rating=5,
                review_text="Best haircut I have had in Seattle! Booking was effortless and the team listened carefully.",
                sentiment=Sentiment.POSITIVE,
                response_status=ResponseStatus.PENDING,
                created_at=now - timedelta(days=6),
            ),
        ]
        db.add_all(reviews)

        # ------------------------------------------------------------------
        # 3. Sample Social Posts (5 total)
        # ------------------------------------------------------------------
        posts = [
            SocialPost(
                business_id=restaurant.id,
                platform=SocialPlatform.INSTAGRAM,
                content="Fresh from our 900°F oak-fired oven: San Marzano tomatoes, fior di latte mozzarella, and sweet basil. Come grab a slice tonight! #BellaNapoli #AustinEats",
                status=PostStatus.PUBLISHED,
                published_at=now - timedelta(days=2),
                engagement_likes=148,
                engagement_shares=14,
                engagement_comments=19,
                created_at=now - timedelta(days=2),
            ),
            SocialPost(
                business_id=restaurant.id,
                platform=SocialPlatform.FACEBOOK,
                content="Date night done right! Pair our handmade truffle tagliatelle with a glass of Chianti Classico on our patio this Friday.",
                status=PostStatus.SCHEDULED,
                scheduled_at=now + timedelta(days=2),
                created_at=now - timedelta(days=1),
            ),
            SocialPost(
                business_id=restaurant.id,
                platform=SocialPlatform.GOOGLE,
                content="This weekend only: Enjoy our Chef's 3-Course Tasting Menu featuring seasonal burrata and house-made tiramisu. Reserve your table today!",
                status=PostStatus.PUBLISHED,
                published_at=now - timedelta(days=4),
                engagement_likes=32,
                engagement_shares=6,
                engagement_comments=4,
                created_at=now - timedelta(days=4),
            ),
            SocialPost(
                business_id=salon.id,
                platform=SocialPlatform.INSTAGRAM,
                content="Soft, sun-kissed dimension that grows out seamlessly for months. Book your Lived-In Balayage consultation at Lumina Hair & Spa! #SeattleSalon #Balayage",
                status=PostStatus.PUBLISHED,
                published_at=now - timedelta(days=1),
                engagement_likes=214,
                engagement_shares=21,
                engagement_comments=27,
                created_at=now - timedelta(days=1),
            ),
            SocialPost(
                business_id=salon.id,
                platform=SocialPlatform.TWITTER,
                content="Reset your week with our 45-minute Botanical Scalp Ritual—organic essential oils, steam therapy, and tension-melting massage. #SeattleSpa",
                status=PostStatus.SCHEDULED,
                scheduled_at=now + timedelta(days=3),
                created_at=now,
            ),
        ]
        db.add_all(posts)

        # ------------------------------------------------------------------
        # 4. Sample Bookings (8 total)
        # ------------------------------------------------------------------
        bookings = [
            Booking(
                business_id=restaurant.id,
                customer_name="Liam O'Connor",
                customer_email="liam.oconnor@example.com",
                customer_phone="(512) 555-1001",
                service="Dinner Table Reservation (4 Guests)",
                booking_date=today,
                booking_time=time(18, 30),
                duration_minutes=90,
                status=BookingStatus.CONFIRMED,
                notes="Corner booth requested",
            ),
            Booking(
                business_id=restaurant.id,
                customer_name="Ava Chen",
                customer_email="ava.chen@example.com",
                customer_phone="(512) 555-1002",
                service="Chef's Tasting Menu (2 Guests)",
                booking_date=today,
                booking_time=time(19, 30),
                duration_minutes=120,
                status=BookingStatus.CONFIRMED,
                notes="Anniversary dinner",
            ),
            Booking(
                business_id=restaurant.id,
                customer_name="Noah Martinez",
                customer_email="noah.m@example.com",
                customer_phone="(512) 555-1003",
                service="Lunch Table Reservation (3 Guests)",
                booking_date=today + timedelta(days=1),
                booking_time=time(12, 30),
                duration_minutes=60,
                status=BookingStatus.PENDING,
                notes="One gluten-free guest",
            ),
            Booking(
                business_id=restaurant.id,
                customer_name="Sophia Alvarez",
                customer_email="sophia.a@example.com",
                customer_phone="(512) 555-1004",
                service="Patio Dining (6 Guests)",
                booking_date=today + timedelta(days=2),
                booking_time=time(19, 0),
                duration_minutes=90,
                status=BookingStatus.CONFIRMED,
                notes="Birthday celebration",
            ),
            Booking(
                business_id=salon.id,
                customer_name="Emma Watson",
                customer_email="emma.w@example.com",
                customer_phone="(206) 555-2001",
                service="Signature Cut & Blowout",
                booking_date=today,
                booking_time=time(11, 0),
                duration_minutes=60,
                status=BookingStatus.CONFIRMED,
                notes="Prefer Maya",
            ),
            Booking(
                business_id=salon.id,
                customer_name="Olivia Park",
                customer_email="olivia.p@example.com",
                customer_phone="(206) 555-2002",
                service="Lived-In Balayage",
                booking_date=today + timedelta(days=1),
                booking_time=time(13, 0),
                duration_minutes=150,
                status=BookingStatus.CONFIRMED,
                notes="Warm honey tones",
            ),
            Booking(
                business_id=salon.id,
                customer_name="Grace Miller",
                customer_email="grace.m@example.com",
                customer_phone="(206) 555-2003",
                service="Botanical Scalp Ritual",
                booking_date=today + timedelta(days=2),
                booking_time=time(15, 0),
                duration_minutes=45,
                status=BookingStatus.PENDING,
                notes="",
            ),
            Booking(
                business_id=salon.id,
                customer_name="Zoe Jenkins",
                customer_email="zoe.j@example.com",
                customer_phone="(206) 555-2004",
                service="Keratin Smoothing",
                booking_date=today - timedelta(days=1),
                booking_time=time(10, 0),
                duration_minutes=120,
                status=BookingStatus.COMPLETED,
                notes="Follow-up in 12 weeks",
            ),
        ]
        db.add_all(bookings)
        db.commit()
        print("Seed complete: inserted 2 businesses, 10 reviews, 5 social posts, and 8 bookings.")


if __name__ == "__main__":
    seed_database(reset=True)
