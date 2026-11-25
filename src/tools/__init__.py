"""LangChain tool collections and individual `@tool` exports for BizPresence AI."""

from src.tools.analytics_tools import (
    AnalyticsTools,
    aggregate_platform_metrics,
    generate_performance_report,
    identify_trends,
    suggest_data_improvements,
)
from src.tools.booking_tools import (
    BookingTools,
    cancel_booking,
    check_availability,
    create_booking,
    get_daily_bookings,
    reschedule_booking,
    send_booking_confirmation,
)
from src.tools.content_tools import (
    ContentTools,
    create_content_calendar,
    generate_blog_outline,
    generate_post_ideas,
    generate_promotional_offer,
)
from src.tools.google_tools import (
    GoogleBusinessTools,
    get_business_insights,
    handle_business_qa,
    manage_business_photos,
    post_google_update,
    update_business_hours,
    update_business_profile,
)
from src.tools.review_tools import (
    ReviewTools,
    analyze_review_sentiment,
    fetch_facebook_reviews,
    fetch_google_reviews,
    flag_critical_review,
    get_review_trends,
    respond_to_review,
)
from src.tools.social_tools import (
    SocialMediaTools,
    get_optimal_posting_times,
    get_social_metrics,
    post_to_facebook,
    post_to_instagram,
    post_to_twitter,
    schedule_post,
)

__all__ = [
    # Tool bundle classes
    "GoogleBusinessTools",
    "SocialMediaTools",
    "ReviewTools",
    "ContentTools",
    "BookingTools",
    "AnalyticsTools",
    # Google Business tools
    "update_business_profile",
    "post_google_update",
    "get_business_insights",
    "update_business_hours",
    "manage_business_photos",
    "handle_business_qa",
    # Social media tools
    "post_to_facebook",
    "post_to_instagram",
    "post_to_twitter",
    "schedule_post",
    "get_social_metrics",
    "get_optimal_posting_times",
    # Review tools
    "fetch_google_reviews",
    "fetch_facebook_reviews",
    "respond_to_review",
    "analyze_review_sentiment",
    "flag_critical_review",
    "get_review_trends",
    # Content tools
    "generate_post_ideas",
    "create_content_calendar",
    "generate_promotional_offer",
    "generate_blog_outline",
    # Booking tools
    "check_availability",
    "create_booking",
    "cancel_booking",
    "get_daily_bookings",
    "reschedule_booking",
    "send_booking_confirmation",
    # Analytics tools
    "aggregate_platform_metrics",
    "generate_performance_report",
    "identify_trends",
    "suggest_data_improvements",
]
