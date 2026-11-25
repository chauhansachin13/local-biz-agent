"""AI agents package for BizPresence AI."""

from src.agents.booking_agent import BookingAgent
from src.agents.concierge_agent import handle_whatsapp_message
from src.agents.crm_and_competitors import (
    analyze_competitors,
    draft_retention_campaigns,
    sync_customers_from_activity,
)
from src.agents.health_and_growth import (
    compute_health_score,
    get_or_create_agent_config,
    launch_multi_channel_campaign,
    run_magic_onboarding,
)
from src.agents.orchestrator import BizPresenceOrchestrator
from src.agents.react_bridge import run_react_specialist
from src.agents.review_agent import ReviewAgent
from src.agents.scheduler import (
    run_autopilot_cycle_for_business,
    start_autopilot_scheduler,
    stop_autopilot_scheduler,
)
from src.agents.seo_audit import generate_daily_brief, run_seo_and_sentiment_audit
from src.agents.social_agent import SocialMediaAgent
from src.agents.strategy_council import get_upcoming_festivals, run_strategy_council
from src.agents.supervisor import decide_approval_action, run_supervisor_turn

__all__ = [
    "BizPresenceOrchestrator",
    "BookingAgent",
    "ReviewAgent",
    "SocialMediaAgent",
    "analyze_competitors",
    "compute_health_score",
    "decide_approval_action",
    "draft_retention_campaigns",
    "generate_daily_brief",
    "get_or_create_agent_config",
    "get_upcoming_festivals",
    "handle_whatsapp_message",
    "launch_multi_channel_campaign",
    "run_autopilot_cycle_for_business",
    "run_magic_onboarding",
    "run_react_specialist",
    "run_seo_and_sentiment_audit",
    "run_strategy_council",
    "run_supervisor_turn",
    "start_autopilot_scheduler",
    "stop_autopilot_scheduler",
    "sync_customers_from_activity",
]
