"""Seed script inserting sample businesses, reviews, social posts, and bookings via SQLAlchemy."""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Ensure project root is importable when invoked as `python scripts/seed_data.py`
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings  # noqa: E402
from src.database.db import Base, _sync_sqlite_columns  # noqa: E402
from src.models.agent_models import (  # noqa: E402
    AgentApprovalAction,
    AgentRunLog,
    AgentThreadMessage,
    ApprovalStatus,
    BusinessAgentConfig,
    CompetitorBenchmark,
    CustomerProfile,
    FulfillmentType,
    OrderRequest,
    OrderStatus,
    RiskLevel,
    WhatsAppMessage,
)
from src.models.booking import Booking, BookingStatus  # noqa: E402
from src.models.business import Business  # noqa: E402
from src.models.growth_models import (  # noqa: E402
    CouponOffer,
    DiscountType,
    WaitlistEntry,
    WaitlistStatus,
)
from src.models.review import ResponseStatus, Review, Sentiment  # noqa: E402
from src.models.social_post import PostStatus, SocialPlatform, SocialPost  # noqa: E402


def seed_database(reset: bool = True) -> None:
    """Populate the database directly via synchronous SQLAlchemy."""
    sync_url = settings.database_url.replace("+aiosqlite", "")
    connect_args = {"check_same_thread": False} if sync_url.startswith("sqlite") else {}
    engine = create_engine(sync_url, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        _sync_sqlite_columns(conn)

    with Session(engine) as db:
        if reset:
            db.query(WaitlistEntry).delete()
            db.query(CouponOffer).delete()
            db.query(WhatsAppMessage).delete()
            db.query(CompetitorBenchmark).delete()
            db.query(CustomerProfile).delete()
            db.query(AgentRunLog).delete()
            db.query(AgentThreadMessage).delete()
            db.query(AgentApprovalAction).delete()
            db.query(OrderRequest).delete()
            db.query(BusinessAgentConfig).delete()
            db.query(Booking).delete()
            db.query(Review).delete()
            db.query(SocialPost).delete()
            db.query(Business).delete()
            db.commit()
        elif db.query(Business).count() > 0:
            print("Database already populated. Skipping seed (pass reset=True to overwrite).")
            return

        now = datetime.now(UTC)
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
        db.flush()

        # ------------------------------------------------------------------
        # 5. Agent Configs, Sample Online Orders & HITL Approval Item
        # ------------------------------------------------------------------
        configs = [
            BusinessAgentConfig(
                business_id=restaurant.id,
                autopilot_enabled=True,
                auto_publish_scheduled=True,
                auto_reply_positive_reviews=False,
                require_approval_negative_reviews=True,
                preferred_language="English",
                brand_voice="warm Italian hospitality",
                catalog_items=[
                    {
                        "name": "Wood-Fired Margherita Pizza",
                        "price": 18.0,
                        "description": "San Marzano tomatoes, fior di latte & fresh basil",
                    },
                    {
                        "name": "Handmade Truffle Tagliatelle",
                        "price": 24.0,
                        "description": "Fresh pasta with black truffle cream",
                    },
                    {
                        "name": "Classic Tiramisu",
                        "price": 10.0,
                        "description": "Espresso-soaked savoiardi & mascarpone",
                    },
                ],
                faqs=[
                    {
                        "q": "Do you have gluten-free pasta?",
                        "a": "Yes, gluten-free pasta and cauliflower crust are available on request.",
                    },
                    {
                        "q": "Can I book patio tables online?",
                        "a": "Yes, book directly via our online storefront or call us.",
                    },
                ],
            ),
            BusinessAgentConfig(
                business_id=salon.id,
                autopilot_enabled=True,
                auto_publish_scheduled=True,
                auto_reply_positive_reviews=False,
                require_approval_negative_reviews=True,
                preferred_language="English",
                brand_voice="warm, uplifting, and boutique luxury",
                catalog_items=[
                    {
                        "name": "Signature Cut & Blowout",
                        "price": 75.0,
                        "description": "Tailored cut, wash, and styling",
                    },
                    {
                        "name": "Lived-In Balayage Package",
                        "price": 195.0,
                        "description": "Hand-painted dimension + gloss treatment",
                    },
                    {
                        "name": "Botanical Scalp Ritual",
                        "price": 55.0,
                        "description": "45-min organic steam & scalp massage",
                    },
                ],
                faqs=[
                    {
                        "q": "Do you use organic hair color?",
                        "a": "Yes, we specialize in ammonia-free botanical color lines.",
                    },
                ],
            ),
        ]
        db.add_all(configs)

        orders = [
            OrderRequest(
                business_id=restaurant.id,
                customer_name="Daniel Carter",
                customer_phone="(512) 555-3001",
                customer_email="daniel.c@example.com",
                items=[
                    {"name": "Wood-Fired Margherita Pizza", "quantity": 2, "price": 18.0},
                    {"name": "Classic Tiramisu", "quantity": 1, "price": 10.0},
                ],
                subtotal_amount=46.0,
                discount_amount=0.0,
                promo_code=None,
                total_amount=46.0,
                fulfillment_type=FulfillmentType.PICKUP,
                status=OrderStatus.CONFIRMED,
                notes="Extra basil please",
            ),
            OrderRequest(
                business_id=salon.id,
                customer_name="Rachel Kim",
                customer_phone="(206) 555-3002",
                items=[{"name": "Botanical Scalp Ritual", "quantity": 1, "price": 55.0}],
                subtotal_amount=55.0,
                discount_amount=0.0,
                promo_code=None,
                total_amount=55.0,
                fulfillment_type=FulfillmentType.PICKUP,
                status=OrderStatus.NEW,
                notes="Gift voucher pickup",
            ),
        ]
        db.add_all(orders)

        db.add_all(
            [
                CouponOffer(
                    business_id=restaurant.id,
                    code="LOCAL15",
                    title="15% off Weekend Pickup Orders ($15+)",
                    discount_type=DiscountType.PERCENT,
                    discount_value=15.0,
                    min_order_amount=15.0,
                    max_uses=200,
                    uses_count=1,
                    valid_until=today + timedelta(days=30),
                    is_active=True,
                ),
                CouponOffer(
                    business_id=restaurant.id,
                    code="WELCOME10",
                    title="$10 off Family Feast ($40+)",
                    discount_type=DiscountType.FIXED,
                    discount_value=10.0,
                    min_order_amount=40.0,
                    max_uses=100,
                    uses_count=0,
                    valid_until=today + timedelta(days=45),
                    is_active=True,
                ),
                CouponOffer(
                    business_id=salon.id,
                    code="GLOW20",
                    title="20% off Self-Care Packages",
                    discount_type=DiscountType.PERCENT,
                    discount_value=20.0,
                    min_order_amount=30.0,
                    max_uses=100,
                    uses_count=0,
                    valid_until=today + timedelta(days=30),
                    is_active=True,
                ),
                WaitlistEntry(
                    business_id=restaurant.id,
                    customer_name="Elena Rostova",
                    customer_phone="(512) 555-8821",
                    preferred_date=today + timedelta(days=1),
                    preferred_time="19:30",
                    service="Dinner Table (4 Guests)",
                    status=WaitlistStatus.WAITING,
                    notes="Patio preferred",
                ),
            ]
        )

        neg_review = next(r for r in reviews if r.business_id == restaurant.id and r.rating == 2)
        db.flush()
        db.add(
            AgentApprovalAction(
                business_id=restaurant.id,
                action_type="reply_review",
                title=f"Reply to {neg_review.reviewer_name} (2★ Facebook)",
                description=neg_review.review_text or "",
                agent_name="ReviewWatchdogAgent",
                reasoning="2-star review held by HITL guardrail for owner sign-off before posting.",
                risk_level=RiskLevel.HIGH,
                payload={
                    "review_id": neg_review.id,
                    "response_text": (
                        "Hi Marcus, thank you for sharing this feedback, and please accept our sincere "
                        "apologies for the 35-minute wait despite your reservation. We're addressing "
                        "kitchen pacing with our team and would love to invite you back—please email "
                        "hello@bellanapoli-austin.com so we can personally take care of you."
                    ),
                },
                status=ApprovalStatus.PENDING,
            )
        )
        db.add_all(
            [
                CompetitorBenchmark(
                    business_id=restaurant.id,
                    name="Downtown Pasta House",
                    category="restaurant",
                    rating=4.1,
                    review_count=112,
                    price_tier="$$",
                    strengths="Large patio seating",
                    weaknesses="Long Friday night wait times and slow takeaway pickup",
                ),
                CompetitorBenchmark(
                    business_id=salon.id,
                    name="Vogue Cuts Studio",
                    category="salon",
                    rating=4.2,
                    review_count=84,
                    price_tier="$$$",
                    strengths="Central downtown location",
                    weaknesses="Limited Sunday hours and higher balayage pricing",
                ),
                CustomerProfile(
                    business_id=restaurant.id,
                    name="Liam O'Connor",
                    phone="(512) 555-1001",
                    email="liam.oconnor@example.com",
                    visit_count=4,
                    total_spent=165.0,
                    loyalty_points=225,
                    segment="VIP",
                ),
                CustomerProfile(
                    business_id=restaurant.id,
                    name="Ava Chen",
                    phone="(512) 555-1002",
                    email="ava.chen@example.com",
                    visit_count=2,
                    total_spent=88.0,
                    loyalty_points=118,
                    segment="Regular",
                ),
            ]
        )
        db.commit()
        print(
            "Seed complete: inserted 2 businesses, 10 reviews, 5 social posts, 8 bookings, "
            "2 orders, 2 competitors, 2 CRM VIP/Regular customers, and 1 HITL approval draft."
        )


if __name__ == "__main__":
    seed_database(reset=True)
