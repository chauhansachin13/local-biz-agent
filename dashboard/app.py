"""BizPresence AI — Comprehensive, Zero-Tech-Friendly Streamlit Command Center."""

from __future__ import annotations

import html
import os
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx
import pandas as pd
import streamlit as st

try:
    import plotly.express as px  # type: ignore

    HAS_PLOTLY = True
except ImportError:
    px = None
    HAS_PLOTLY = False

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(
    page_title="BizPresence AI",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    .main {
        background-color: #f8fafc;
    }
    .biz-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        color: #ffffff;
        padding: 1.25rem 1.5rem;
        border-radius: 14px;
        margin-bottom: 1.25rem;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.14);
    }
    .biz-header h1 {
        margin: 0;
        font-size: 1.6rem;
        font-weight: 700;
        color: #ffffff;
    }
    .biz-header p {
        margin: 0.3rem 0 0 0;
        color: #cbd5e1;
        font-size: 0.92rem;
    }
    .metric-card {
        background: #ffffff;
        color: #0f172a;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.04);
    }
    .activity-card {
        background: #ffffff;
        color: #0f172a;
        border-left: 4px solid #3b82f6;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.65rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }
    .badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    .badge-positive { background: #dcfce7; color: #166534; }
    .badge-neutral  { background: #fef9c3; color: #854d0e; }
    .badge-negative { background: #fee2e2; color: #991b1b; }
    .badge-info     { background: #dbeafe; color: #1e40af; }
    .badge-scheduled { background: #ede9fe; color: #5b21b6; }
    .badge-published { background: #dcfce7; color: #166534; }
    .badge-draft     { background: #f1f5f9; color: #475569; }
    .calendar-day {
        background: #ffffff;
        color: #0f172a;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.7rem;
        min-height: 115px;
        margin-bottom: 0.6rem;
    }
    .calendar-day-title {
        font-weight: 700;
        font-size: 0.85rem;
        color: #1e293b;
        margin-bottom: 0.4rem;
        border-bottom: 1px solid #f1f5f9;
        padding-bottom: 0.25rem;
    }
    .suggestion-card {
        background: #ffffff;
        color: #0f172a;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 0.9rem 1rem;
        margin-bottom: 0.75rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# HTTPX API Client Helpers
# ---------------------------------------------------------------------------


def api_request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 25.0,
) -> tuple[bool, Any]:
    """Execute an HTTP request against the FastAPI backend via httpx."""
    url = f"{API_BASE_URL}{path}"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(method, url, json=json_body, params=params)
        if resp.status_code >= 400:
            try:
                err_data = resp.json()
                detail = err_data.get("detail") or resp.text
            except ValueError:
                detail = resp.text
            return False, f"API Error ({resp.status_code}): {detail}"
        return True, resp.json()
    except httpx.ConnectError:
        return (
            False,
            (
                f"Cannot connect to FastAPI backend at `{API_BASE_URL}`. "
                "Ensure the API server is running."
            ),
        )
    except (httpx.HTTPError, ValueError) as exc:
        return False, f"Request failed: {exc}"


def sentiment_badge(sentiment: str | None) -> str:
    label = (sentiment or "neutral").lower()
    cls = {
        "positive": "badge-positive",
        "neutral": "badge-neutral",
        "negative": "badge-negative",
    }.get(label, "badge-info")
    return f'<span class="badge {cls}">{label}</span>'


def status_badge(status_str: str | None) -> str:
    low = (status_str or "info").lower()
    cls = {
        "published": "badge-published",
        "responded": "badge-positive",
        "confirmed": "badge-positive",
        "completed": "badge-info",
        "executed": "badge-positive",
        "approved": "badge-positive",
        "ready": "badge-positive",
        "preparing": "badge-scheduled",
        "new": "badge-info",
        "scheduled": "badge-scheduled",
        "pending": "badge-neutral",
        "draft": "badge-draft",
        "cancelled": "badge-negative",
        "rejected": "badge-negative",
        "verified": "badge-positive",
        "high": "badge-negative",
        "medium": "badge-neutral",
        "low": "badge-info",
    }.get(low, "badge-info")
    return f'<span class="badge {cls}">{low}</span>'


def render_header(business: dict[str, Any], subtitle: str) -> None:
    loc = ", ".join(p for p in (business.get("city"), business.get("state")) if p)
    loc_part = f" • {loc}" if loc else ""
    st.markdown(
        f"""
        <div class="biz-header">
            <h1>🏪 {html.escape(business["name"])}</h1>
            <p>{html.escape(business.get("category", "").title() + loc_part)} — {html.escape(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_agent_trace(
    trace: list[dict[str, Any]], label: str = "🔍 Inspect AI Agent & Tool Steps"
) -> None:
    if not trace:
        return
    with st.expander(label, expanded=False):
        for idx, step in enumerate(trace, start=1):
            st.markdown(
                f"**{idx}. `{step.get('agent', 'Agent')}`** → "
                f"`{step.get('tool', 'action')}` "
                f"({status_badge(step.get('status', 'completed'))}) — {step.get('detail', '')}",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Sidebar: Health, Business Selector, Pending Approvals Badge, Navigation
# ---------------------------------------------------------------------------

if "api_overrides" not in st.session_state:
    st.session_state["api_overrides"] = {}

with st.sidebar:
    st.markdown("## 🤖 BizPresence AI")
    st.caption("Always-On Agentic Team for Local Shops")

    healthy, _health_data = api_request("GET", "/health", timeout=5.0)
    if healthy:
        st.success("API + Autopilot Connected", icon="🟢")
    else:
        st.error("API Disconnected", icon="🔴")

    ok_biz, businesses_data = api_request("GET", "/api/businesses/")
    businesses: list[dict[str, Any]] = (
        businesses_data if ok_biz and isinstance(businesses_data, list) else []
    )

    selected_business: dict[str, Any] | None = None
    pending_approvals_cnt = 0
    if businesses:
        biz_labels = {f"{b['name']} ({b['category'].title()})": b for b in businesses}
        chosen_label = st.selectbox(
            "Select Business",
            options=list(biz_labels.keys()),
            key="selected_business_label",
        )
        selected_business = biz_labels[chosen_label]
        if st.session_state.get("active_biz_id") != selected_business["id"]:
            st.session_state["active_biz_id"] = selected_business["id"]
            for stale_key in (
                "draft_content",
                "draft_best_time",
                "draft_image_prompt",
                "ab_variants",
            ):
                st.session_state.pop(stale_key, None)
        gbp_badge = (
            "Verified ✅" if selected_business.get("google_business_id") else "Not Configured"
        )
        st.caption(f"Google Profile: **{gbp_badge}**")

        ok_ap, ap_list = api_request(
            "GET",
            f"/api/agent/{selected_business['id']}/approvals",
            params={"status": "pending"},
        )
        if ok_ap and isinstance(ap_list, list):
            pending_approvals_cnt = len(ap_list)
            if pending_approvals_cnt > 0:
                st.warning(f"🟡 {pending_approvals_cnt} action(s) awaiting approval")
    else:
        st.warning("No businesses yet — launch one in 60 seconds using the Quick Launch Wizard!")

    st.divider()
    nav_options = [
        "🏠 Home & Health Score",
        "✨ 60-Sec Launch Wizard",
        f"🤖 AI Autopilot & Approvals ({pending_approvals_cnt})"
        if pending_approvals_cnt
        else "🤖 AI Autopilot & Approvals",
        "💬 AI Command Chat",
        "📣 Social & Campaigns",
        "⭐ Reviews",
        "📅 Bookings & Orders",
        "👥 CRM & Competitors",
        "💰 Growth, Coupons & ROI",
        "🌟 Loyalty, NPS & Gift Cards",
        "📧 Email Campaigns",
        "📆 Content Calendar",
        "🌐 Customer Storefront",
        "⚙️ Settings",
    ]
    page = st.radio("Navigation", options=nav_options, index=0)
    st.divider()
    st.caption(f"Backend: `{API_BASE_URL}`")


if selected_business is None and page not in {"✨ 60-Sec Launch Wizard", "⚙️ Settings"}:
    st.title("Welcome to BizPresence AI")
    st.info(
        "No businesses are registered yet. Click **✨ 60-Sec Launch Wizard** in the sidebar "
        "to launch your shop's digital presence in one click!"
    )
    st.stop()


# ---------------------------------------------------------------------------
# PAGE: ✨ 60-Sec Launch Wizard
# ---------------------------------------------------------------------------

if page == "✨ 60-Sec Launch Wizard":
    st.markdown(
        """
        <div class="biz-header">
            <h1>✨ 60-Second Digital Launch Wizard</h1>
            <p>No tech skills needed. Enter your shop basics and our AI agents build your Google Profile, SEO bio, menu/catalog, and starter social posts automatically.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("magic_onboard_form"):
        c1, c2 = st.columns(2)
        m_name = c1.text_input("Shop / Business Name*", placeholder="e.g., Chai Junction")
        m_cat = c2.selectbox(
            "Business Type*",
            ["restaurant", "cafe", "bakery", "salon", "retail", "fitness", "medical", "general"],
        )
        m_city = c1.text_input("City", placeholder="e.g., Pune")
        m_state = c2.text_input("State", placeholder="e.g., Maharashtra")
        m_addr = c1.text_input("Street Address", placeholder="e.g., 24 FC Road")
        m_phone = c2.text_input("Phone / WhatsApp", placeholder="e.g., +91 98765 43210")
        m_email = c1.text_input("Email", placeholder="hello@chaijunction.com")
        m_lang = c2.selectbox(
            "Preferred AI Language",
            ["English", "Hindi", "Hinglish", "Spanish", "French"],
        )
        m_spec = st.text_input(
            "What is your shop famous for?",
            placeholder="e.g., Masala chai, bun maska, and fresh evening snacks",
        )
        auto_posts = st.checkbox(
            "Auto-create 3 starter social media posts (Google, Instagram, Facebook)",
            value=True,
        )

        if st.form_submit_button(
            "🚀 Launch My Digital Presence Now", type="primary", use_container_width=True
        ):
            if not m_name.strip():
                st.warning("Please enter your shop or business name.")
            else:
                with st.spinner("AI agents are building your profile, catalog, and posts..."):
                    ok_m, res_m = api_request(
                        "POST",
                        "/api/agent/magic-onboard",
                        json_body={
                            "name": m_name.strip(),
                            "category": m_cat,
                            "city": m_city.strip(),
                            "state": m_state.strip(),
                            "address": m_addr.strip(),
                            "phone": m_phone.strip(),
                            "email": m_email.strip(),
                            "preferred_language": m_lang,
                            "specialty": m_spec.strip(),
                            "auto_schedule_starter_posts": auto_posts,
                        },
                    )
                if ok_m:
                    st.success(res_m["summary"])
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Health Score", f"{res_m['health_score']}/100")
                    k2.metric("Starter Posts Created", res_m["starter_posts_created"])
                    k3.metric("Catalog Items Seeded", res_m["catalog_items_created"])
                    render_agent_trace(
                        res_m.get("agent_trace", []), "🔍 See What the AI Team Just Built"
                    )
                    st.info(
                        f"Your live customer booking & ordering page is ready at: "
                        f"`{API_BASE_URL}/site/{res_m['business']['id']}`"
                    )
                else:
                    st.error(res_m)


# ---------------------------------------------------------------------------
# PAGE 1: Home & Health Score
# ---------------------------------------------------------------------------

elif page == "🏠 Home & Health Score" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Digital Presence Overview & Health Score")

    ok, overview = api_request("GET", f"/api/businesses/{biz_id}/dashboard")
    ok_hs, health = api_request("GET", f"/api/agent/{biz_id}/health-score")
    ok_br, brief = api_request("GET", f"/api/agent/{biz_id}/daily-brief")
    if not ok:
        st.error(overview)
        st.stop()

    if ok_br:
        st.success(
            f"☀️ **Morning AI Briefing:** {brief['summary']} **Next Priority:** {brief['priority_action']}"
        )

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        hs_val = f"{health['overall_score']}/100 ({health['grade']})" if ok_hs else "—"
        st.metric("Presence Health", hs_val)
    with c2:
        st.metric(
            "Total Reviews",
            overview["total_reviews"],
            delta=f"{overview['pending_reviews']} pending",
            delta_color="inverse" if overview["pending_reviews"] > 0 else "normal",
        )
    with c3:
        st.metric(
            "Average Rating",
            f"{overview['average_rating']:.2f} ★",
            delta=f"GBP: {overview['google_profile_status']}",
        )
    with c4:
        st.metric(
            "Posts This Week",
            overview["posts_this_week"],
            delta=f"{overview['scheduled_posts']} scheduled",
        )
    with c5:
        st.metric(
            "Upcoming Bookings",
            overview["upcoming_bookings"],
            delta=f"{overview['bookings_today']} today",
        )

    if ok_hs:
        with st.expander(
            f"📊 Health Score Breakdown — Top Tip: {health['top_recommendation']}", expanded=True
        ):
            p_cols = st.columns(len(health["pillars"]))
            for col, p in zip(p_cols, health["pillars"], strict=True):
                with col:
                    st.markdown(f"**{p['name']}**")
                    st.progress(p["score"] / p["max_score"])
                    st.caption(f"{p['score']}/{p['max_score']} pts — {p['tip']}")

    st.info(
        f"🌐 **Shareable Customer Booking & Order Link:** "
        f"[{API_BASE_URL}/site/{biz_id}]({API_BASE_URL}/site/{biz_id})"
    )

    left_col, right_col = st.columns([1.35, 1.0])
    with left_col:
        st.subheader("📋 Recent Activity Feed")
        activities = overview.get("recent_activity", [])
        if not activities:
            st.info("No recent activity yet.")
        else:
            for item in activities:
                icon = {"review": "⭐", "social": "📱", "booking": "📅"}.get(item["type"], "🔔")
                ts = item["timestamp"][:16].replace("T", " ")
                st.markdown(
                    f"""
                    <div class="activity-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong>{icon} {item["title"]}</strong>
                            {status_badge(item["status"])}
                        </div>
                        <div style="color:#475569; font-size:0.88rem; margin-top:0.35rem;">
                            {item["detail"]}
                        </div>
                        <div style="color:#94a3b8; font-size:0.75rem; margin-top:0.3rem;">
                            {ts} UTC
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with right_col:
        st.subheader("💡 One-Click AI Priority Fixes")
        ok_sug, sug_data = api_request("GET", f"/api/agent/{biz_id}/suggestions")
        if ok_sug and sug_data.get("suggestions"):
            for sug in sug_data["suggestions"]:
                prio_color = {"high": "#dc2626", "medium": "#d97706", "low": "#2563eb"}.get(
                    sug["priority"], "#475569"
                )
                st.markdown(
                    f"""
                    <div class="suggestion-card">
                        <span style="color:{prio_color}; font-weight:700; font-size:0.75rem; text-transform:uppercase;">
                            ● {html.escape(sug["priority"])} priority • {html.escape(sug["category"])}
                        </span>
                        <div style="font-weight:600; font-size:1rem; margin:0.25rem 0; color:#0f172a;">
                            {html.escape(sug["title"])}
                        </div>
                        <div style="color:#475569; font-size:0.86rem;">
                            {html.escape(sug["description"])}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    f"⚡ Run: {sug['recommended_action']}",
                    key=f"dash_sug_{sug['id']}",
                    use_container_width=True,
                ):
                    ok_run, run_res = api_request(
                        "POST",
                        f"/api/agent/{biz_id}/chat",
                        json_body={
                            "message": sug["prompt_to_run"],
                            "auto_execute": True,
                            "context": st.session_state["api_overrides"],
                        },
                    )
                    if ok_run:
                        st.success(run_res["reply"])
                        render_agent_trace(run_res.get("agent_trace", []))
                    else:
                        st.error(run_res)
        else:
            st.info("No AI suggestions right now.")


# ---------------------------------------------------------------------------
# PAGE 2: AI Autopilot & Approvals (Human-in-the-Loop)
# ---------------------------------------------------------------------------

elif page.startswith("🤖 AI Autopilot & Approvals") and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Human-in-the-Loop Approval Inbox & Autonomous Autopilot")

    tab_inbox, tab_council, tab_rules, tab_logs = st.tabs(
        [
            "📥 Approval Inbox",
            "🧠 Strategy Council & Festivals",
            "⚙️ Autopilot Rules",
            "🛰️ Agent Reasoning Logs",
        ]
    )

    with tab_inbox:
        ap_filter = st.selectbox(
            "Filter Approvals", ["pending", "executed", "rejected", "All"], index=0
        )
        ap_params = {} if ap_filter == "All" else {"status": ap_filter}
        ok_ap, approvals = api_request("GET", f"/api/agent/{biz_id}/approvals", params=ap_params)
        if not ok_ap:
            st.error(approvals)
        elif not approvals:
            st.success("🎉 Approval Inbox is clear! No pending actions waiting for your review.")
        else:
            for item in approvals:
                st.markdown(
                    f"""
                    <div class="metric-card" style="margin-bottom:0.5rem;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong>{html.escape(item["title"])}</strong>
                            <div>
                                {status_badge(item["risk_level"])}
                                {status_badge(item["status"])}
                            </div>
                        </div>
                        <div style="color:#475569; font-size:0.86rem; margin:0.35rem 0;">
                            <strong>Agent:</strong> <code>{html.escape(item["agent_name"])}</code> •
                            <strong>Why:</strong> {html.escape(item["reasoning"])}
                        </div>
                        <div style="color:#64748b; font-size:0.84rem;">
                            <em>Context:</em> {html.escape(item["description"])}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                payload = item.get("payload") or {}
                draft_text = payload.get("response_text") or payload.get("content") or ""
                if item["status"] == "pending":
                    edited = st.text_area(
                        "Edit AI draft before publishing (optional)",
                        value=draft_text,
                        key=f"hitl_edit_{item['id']}",
                        height=90,
                    )
                    b1, b2 = st.columns(2)
                    if b1.button(
                        "✅ Approve & Execute",
                        key=f"hitl_approve_{item['id']}",
                        type="primary",
                        use_container_width=True,
                    ):
                        ok_d, res_d = api_request(
                            "POST",
                            f"/api/agent/{biz_id}/approvals/{item['id']}/decide",
                            json_body={"decision": "approve", "edited_content": edited},
                        )
                        if ok_d:
                            st.success("Approved and executed!")
                            st.rerun()
                        else:
                            st.error(res_d)
                    if b2.button(
                        "✖️ Reject",
                        key=f"hitl_reject_{item['id']}",
                        use_container_width=True,
                    ):
                        ok_d, res_d = api_request(
                            "POST",
                            f"/api/agent/{biz_id}/approvals/{item['id']}/decide",
                            json_body={"decision": "reject"},
                        )
                        if ok_d:
                            st.info("Rejected action.")
                            st.rerun()
                        else:
                            st.error(res_d)
                else:
                    if draft_text:
                        st.caption(f"Content: {draft_text}")
                st.divider()

    with tab_council:
        st.subheader("🧠 Multi-Agent Strategy Council (Debate & Synthesis)")
        st.caption(
            "Convene 3 specialist AI agents (Growth Marketer, Reputation Guardian, Operations Optimizer) "
            "to debate your business metrics and synthesize a prioritized weekly plan."
        )
        if st.button("🤝 Convene Weekly Strategy Council", type="primary"):
            ok_sc, sc = api_request("POST", f"/api/agent/{biz_id}/strategy-council")
            if ok_sc:
                st.session_state[f"council_{biz_id}"] = sc
            else:
                st.error(sc)

        sc_data = st.session_state.get(f"council_{biz_id}")
        if sc_data:
            st.success(sc_data["consensus_summary"])
            m_cols = st.columns(len(sc_data["council_members"]))
            for col, mem in zip(m_cols, sc_data["council_members"], strict=True):
                with col:
                    st.markdown(f"**`{mem['agent']}`**")
                    st.caption(mem["stance"])
                    st.info(mem["proposal"])
            st.markdown("**📋 Prioritized Weekly Action Plan:**")
            for step_item in sc_data["action_plan"]:
                sc_c1, sc_c2 = st.columns([3, 1])
                sc_c1.markdown(
                    f"**Step {step_item['step']}: {step_item['title']}** — {step_item['why']}"
                )
                if sc_c2.button("⚡ Run Step", key=f"council_step_{biz_id}_{step_item['step']}"):
                    ok_run, res_run = api_request(
                        "POST",
                        f"/api/agent/{biz_id}/chat",
                        json_body={"message": step_item["prompt"], "auto_execute": True},
                    )
                    if ok_run:
                        st.success(res_run["reply"])
                    else:
                        st.error(res_run)

        st.divider()
        st.subheader("🎉 Upcoming Festival & Local Event Campaigns")
        ok_f, fests = api_request("GET", f"/api/agent/{biz_id}/festivals")
        if ok_f and isinstance(fests, list):
            for idx_f, fest in enumerate(fests):
                fc1, fc2 = st.columns([3, 1])
                fc1.markdown(
                    f"**{fest['occasion']}** (`{fest['window']}`) — *{fest['offer_idea']}*"
                )
                if fc2.button("Queue Promo", key=f"fest_btn_{biz_id}_{idx_f}"):
                    ok_fc, res_fc = api_request(
                        "POST",
                        f"/api/agent/{biz_id}/campaign",
                        json_body={
                            "occasion": fest["occasion"],
                            "offer_details": fest["offer_idea"],
                            "platforms": ["instagram", "google"],
                            "auto_execute": False,
                        },
                    )
                    if ok_fc:
                        st.success(f"Queued {res_fc['approvals_queued']} drafts in Approval Inbox!")
                    else:
                        st.error(res_fc)

    with tab_rules:
        ok_cfg, cfg = api_request("GET", f"/api/agent/{biz_id}/autopilot")
        if not ok_cfg:
            st.error(cfg)
        else:
            col_form, col_run = st.columns([1.4, 1.0])
            with col_form, st.form("autopilot_rules_form"):
                ap_enabled = st.toggle(
                    "Enable Background Autopilot (runs every 5 mins)",
                    value=cfg["autopilot_enabled"],
                )
                auto_pub = st.toggle(
                    "Auto-publish scheduled posts when due", value=cfg["auto_publish_scheduled"]
                )
                auto_pos = st.toggle(
                    "Auto-reply to positive (4-5★) reviews automatically",
                    value=cfg["auto_reply_positive_reviews"],
                )
                hold_neg = st.toggle(
                    "Safety Guardrail: Hold ≤2★ reviews for Human Approval",
                    value=cfg["require_approval_negative_reviews"],
                )
                lang = st.selectbox(
                    "Preferred AI Language",
                    ["English", "Hindi", "Hinglish", "Spanish", "French"],
                    index=["English", "Hindi", "Hinglish", "Spanish", "French"].index(
                        cfg["preferred_language"]
                    )
                    if cfg["preferred_language"]
                    in ["English", "Hindi", "Hinglish", "Spanish", "French"]
                    else 0,
                )
                voice = st.text_input("Brand Voice", value=cfg["brand_voice"])
                if st.form_submit_button("Save Autopilot Rules", type="primary"):
                    ok_u, res_u = api_request(
                        "PUT",
                        f"/api/agent/{biz_id}/autopilot",
                        json_body={
                            "autopilot_enabled": ap_enabled,
                            "auto_publish_scheduled": auto_pub,
                            "auto_reply_positive_reviews": auto_pos,
                            "require_approval_negative_reviews": hold_neg,
                            "preferred_language": lang,
                            "brand_voice": voice,
                        },
                    )
                    if ok_u:
                        st.success("Autopilot rules saved!")
                    else:
                        st.error(res_u)

            with col_run:
                st.subheader("⚡ Run Autonomous Cycle Now")
                st.caption(
                    "Publishes any due scheduled posts and scans pending reviews to draft "
                    "HITL approvals or auto-reply per your rules."
                )
                if st.button(
                    "🤖 Trigger Autopilot Cycle", type="primary", use_container_width=True
                ):
                    ok_r, res_r = api_request("POST", f"/api/agent/{biz_id}/autopilot/run")
                    if ok_r:
                        st.success(
                            f"Done! Published: {res_r.get('published_posts', 0)} • "
                            f"Auto-replied: {res_r.get('auto_replied_reviews', 0)} • "
                            f"Queued for approval: {res_r.get('queued_approvals', 0)}"
                        )
                        render_agent_trace(res_r.get("trace", []))
                    else:
                        st.error(res_r)

    with tab_logs:
        ok_logs, logs = api_request("GET", f"/api/agent/{biz_id}/logs")
        if not ok_logs:
            st.error(logs)
        elif not logs:
            st.info("No agent execution logs yet. Chat with the AI or trigger Autopilot!")
        else:
            for lg in logs:
                st.markdown(
                    f"**#{lg['id']} [{lg['trigger_source']}]** `{lg['outcome']}` "
                    f"({lg['duration_ms']}ms) — *{lg['goal']}*"
                )
                st.caption(
                    f"Agents: {', '.join(lg['agents_invoked'])} | Tools: {', '.join(lg['tools_called'])}"
                )
                render_agent_trace(lg.get("steps_summary", []), "View step trace")


# ---------------------------------------------------------------------------
# PAGE 3: AI Command Chat (Multi-Turn Memory + LangGraph Trace + Copilot/Autopilot)
# ---------------------------------------------------------------------------

elif page == "💬 AI Command Chat" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "LangGraph Multi-Agent Command Center & WhatsApp Concierge")

    tab_owner_chat, tab_whatsapp = st.tabs(
        ["🧠 Owner Command Chat", "📱 WhatsApp Concierge Simulator"]
    )

    with tab_owner_chat:
        session_id = f"biz_{biz_id}"
        c_top1, c_top2, c_top3 = st.columns([1.2, 1.5, 0.8])
        chat_lang = c_top1.selectbox(
            "Reply Language", ["English", "Hindi", "Hinglish", "Spanish"], index=0
        )
        auto_exec = c_top2.toggle(
            "Autopilot Execution (Off = Copilot queues actions in Approval Inbox)",
            value=True,
        )
        if c_top3.button("🗑️ Clear History", use_container_width=True):
            api_request("DELETE", f"/api/agent/{biz_id}/history", params={"session_id": session_id})
            st.rerun()

        st.caption("One-Click Multi-Agent Prompts:")
        qp1, qp2, qp3, qp4 = st.columns(4)
        quick_prompts = [
            (
                qp1,
                "📊 Full Health Audit",
                "Give me a full analytics summary and check my Google insights",
            ),
            (
                qp2,
                "📸 Post + Bookings",
                "Create an Instagram post about our weekend special and show today's bookings",
            ),
            (qp3, "⭐ Draft Review Replies", "Draft responses for all pending reviews"),
            (qp4, "🛒 Check Active Orders", "Show active online orders and open booking slots"),
        ]
        triggered_prompt: str | None = None
        for col, label, prompt_text in quick_prompts:
            if col.button(label, use_container_width=True):
                triggered_prompt = prompt_text

        ok_hist, history = api_request(
            "GET", f"/api/agent/{biz_id}/history", params={"session_id": session_id}
        )
        messages = history if ok_hist and isinstance(history, list) else []

        if not messages:
            with st.chat_message("assistant"):
                st.markdown(
                    f"Hi! I'm **BizPresence AI** for **{selected_business['name']}**. "
                    "I remember our conversation and coordinate specialized Google Business, Social, "
                    "Review, Booking, Order, and Analytics agents—even for compound multi-step requests!"
                )

        for msg in messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg["role"] == "assistant" and msg.get("agent_trace"):
                    render_agent_trace(msg["agent_trace"])

        user_input = st.chat_input(f"Ask BizPresence AI about {selected_business['name']}...")
        prompt_to_send = triggered_prompt or user_input

        if prompt_to_send:
            with st.chat_message("user"):
                st.markdown(prompt_to_send)

            with st.chat_message("assistant"):
                with st.spinner("Supervisor planning & running specialist agents..."):
                    ok_chat, chat_res = api_request(
                        "POST",
                        f"/api/agent/{biz_id}/chat",
                        json_body={
                            "message": prompt_to_send,
                            "auto_execute": auto_exec,
                            "session_id": session_id,
                            "language": chat_lang,
                            "context": st.session_state["api_overrides"],
                        },
                    )
                if ok_chat:
                    st.markdown(chat_res["reply"])
                    if chat_res.get("queued_approvals"):
                        st.warning(
                            f"🟡 {len(chat_res['queued_approvals'])} action(s) queued in **AI Autopilot & Approvals**."
                        )
                    render_agent_trace(chat_res.get("agent_trace", []))
                else:
                    st.error(chat_res)

    with tab_whatsapp:
        st.caption(
            "Test how your AI handles real WhatsApp messages from local **Customers** "
            "(bookings, pickup orders, hours) or **Owner** commands."
        )
        wc1, wc2, wc3 = st.columns([1, 1.2, 1.2])
        wa_role = wc1.selectbox("Sender Role", ["customer", "owner"])
        wa_name = wc2.text_input(
            "Sender Name", value="Priya Sharma" if wa_role == "customer" else "Owner"
        )
        wa_phone = wc3.text_input("WhatsApp Number", value="+91 98765 43210")

        with st.form("whatsapp_sim_form"):
            wa_msg = st.text_input(
                "WhatsApp Message",
                placeholder="e.g., Book tomorrow at 18:00  OR  Order 2 Margherita Pizza for pickup",
            )
            if st.form_submit_button("📤 Send WhatsApp Message", type="primary"):
                if wa_msg.strip():
                    ok_wa, res_wa = api_request(
                        "POST",
                        f"/api/whatsapp/{biz_id}/message",
                        json_body={
                            "sender_phone": wa_phone.strip(),
                            "sender_name": wa_name.strip(),
                            "sender_role": wa_role,
                            "message": wa_msg.strip(),
                        },
                    )
                    if ok_wa:
                        st.success(f"Handled by `{res_wa['agent_used']}`")
                        st.info(res_wa["reply"])
                    else:
                        st.error(res_wa)

        ok_wlog, wlogs = api_request("GET", f"/api/whatsapp/{biz_id}/messages")
        if ok_wlog and isinstance(wlogs, list) and wlogs:
            st.subheader("💬 Recent WhatsApp Conversation Log")
            for w in wlogs[-10:]:
                prefix = "➡️" if w["direction"] == "inbound" else "🤖"
                st.markdown(
                    f"{prefix} **{w['sender_name']}** (`{w['sender_role']}` • {w.get('agent_used', '')}): "
                    f"{w['message_text']}"
                )


# ---------------------------------------------------------------------------
# PAGE 4: Social Media & Campaigns
# ---------------------------------------------------------------------------

elif page == "📣 Social & Campaigns" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Social Media Studio, Campaigns & Calendar")

    tab_compose, tab_campaign, tab_graphic, tab_calendar, tab_history = st.tabs(
        [
            "✍️ Post Composer",
            "🚀 1-Click Campaign Launcher",
            "🎨 Promo Graphic Studio",
            "🗓️ Content Calendar",
            "📊 Post History",
        ]
    )

    with tab_compose:
        col_form, col_preview = st.columns([1.25, 1.0])
        with col_form:
            platform = st.selectbox(
                "Platform",
                ["instagram", "facebook", "google", "twitter"],
                key="social_platform",
            )
            topic = st.text_input(
                "Topic / Promotion",
                placeholder="e.g., Weekend Pasta Special or Summer Balayage Promo",
                key="social_topic",
            )
            tone = st.selectbox(
                "Tone",
                ["friendly and engaging", "professional", "playful", "luxury & refined"],
                key="social_tone",
            )
            cta = st.text_input(
                "Call to Action (optional)",
                placeholder="e.g., Reserve your table via link in bio!",
                key="social_cta",
            )

            ab1, ab2 = st.columns(2)
            if ab1.button("✨ AI Assist — Generate Copy & Hashtags", use_container_width=True):
                ok_gen, gen_data = api_request(
                    "POST",
                    f"/api/social/{biz_id}/generate-content",
                    json_body={
                        "platform": platform,
                        "topic": topic,
                        "tone": tone,
                        "include_hashtags": True,
                        "call_to_action": cta,
                    },
                )
                if ok_gen:
                    tags_line = " ".join(gen_data.get("hashtags") or [])
                    combined = (
                        f"{gen_data['content']}\n\n{tags_line}".strip()
                        if tags_line
                        else gen_data["content"]
                    )
                    st.session_state["draft_content"] = combined
                    st.session_state["draft_best_time"] = gen_data["best_time_to_post"]
                    st.session_state["draft_image_prompt"] = gen_data["image_prompt"]
                    st.success("Generated AI post copy!")
                else:
                    st.error(gen_data)

            if ab2.button("⚡ Generate A/B Variants", use_container_width=True):
                ok_ab, ab_data = api_request(
                    "POST",
                    f"/api/social/{biz_id}/ab-variants",
                    json_body={
                        "platform": platform,
                        "topic": topic,
                        "tone": tone,
                        "include_hashtags": True,
                        "call_to_action": cta,
                    },
                )
                if ok_ab:
                    st.session_state["ab_variants"] = ab_data
                else:
                    st.error(ab_data)

            if st.session_state.get("ab_variants"):
                ab_d = st.session_state["ab_variants"]
                va, vb = st.columns(2)
                for col_v, key_v in [(va, "variant_a"), (vb, "variant_b")]:
                    var = ab_d[key_v]
                    with col_v:
                        st.markdown(
                            f"**{var['label']}** (Predicted Score: `{var['predicted_engagement_score']}/100`)"
                        )
                        st.caption(var["content"])
                        if st.button("Use This Variant", key=f"pick_{key_v}"):
                            tags = " ".join(var.get("hashtags") or [])
                            st.session_state["draft_content"] = (
                                f"{var['content']}\n\n{tags}".strip()
                            )
                            st.rerun()

            content_text = st.text_area(
                "Post Content",
                value=st.session_state.get("draft_content", ""),
                height=150,
                placeholder="Write your post or click AI Assist above...",
            )
            image_url = st.text_input(
                "Image URL (optional)", placeholder="https://example.com/photo.jpg"
            )

            publish_mode = st.radio(
                "Action",
                ["Publish Now", "Schedule for Later", "Save as Draft"],
                horizontal=True,
            )

            sched_date = date.today() + timedelta(days=1)
            sched_time = time(11, 30)
            if publish_mode == "Schedule for Later":
                sc1, sc2 = st.columns(2)
                sched_date = sc1.date_input("Schedule Date", value=sched_date)
                sched_time = sc2.time_input("Schedule Time", value=sched_time)

            if st.button("🚀 Submit Post", type="primary", use_container_width=True):
                if not content_text.strip():
                    st.warning("Please enter post content before submitting.")
                else:
                    if publish_mode == "Schedule for Later":
                        sched_dt = datetime.combine(sched_date, sched_time)
                        ok_sub, sub_res = api_request(
                            "POST",
                            f"/api/social/{biz_id}/schedule",
                            json_body={
                                "platform": platform,
                                "content": content_text,
                                "image_url": image_url.strip() or None,
                                "scheduled_at": sched_dt.isoformat(),
                            },
                        )
                    else:
                        status_val = "published" if publish_mode == "Publish Now" else "draft"
                        ok_sub, sub_res = api_request(
                            "POST",
                            f"/api/social/{biz_id}/post",
                            json_body={
                                "platform": platform,
                                "content": content_text,
                                "image_url": image_url.strip() or None,
                                "status": status_val,
                            },
                        )
                    if ok_sub:
                        st.success(
                            f"Post #{sub_res['id']} saved with status `{sub_res['status']}`!"
                        )
                    else:
                        st.error(sub_res)

        with col_preview:
            st.subheader("📱 Live Preview")
            st.markdown(
                f"""
                <div class="metric-card">
                    <div style="display:flex; justify-content:space-between; color:#0f172a;">
                        <strong style="color:#0f172a;">{html.escape(selected_business["name"])}</strong>
                        <span class="badge badge-info">{html.escape(platform)}</span>
                    </div>
                    <p style="margin-top:0.8rem; white-space:pre-wrap; color:#1e293b;">
                        {html.escape(content_text) if content_text else "Your post preview will appear here..."}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.session_state.get("draft_best_time"):
                st.info(f"⏰ Recommended time: **{st.session_state['draft_best_time']}**")
            if st.session_state.get("draft_image_prompt"):
                st.caption(f"🎨 Visual prompt: {st.session_state['draft_image_prompt']}")

    with tab_campaign:
        st.subheader("🚀 Launch a Multi-Platform Campaign in One Click")
        with st.form("campaign_form"):
            cc1, cc2 = st.columns(2)
            occ = cc1.text_input(
                "Occasion / Theme*", placeholder="e.g., Diwali Weekend Sale or Summer Happy Hour"
            )
            off = cc2.text_input("Offer Details", placeholder="e.g., 15% off all family combos")
            plats = st.multiselect(
                "Target Channels",
                ["instagram", "facebook", "google", "twitter"],
                default=["instagram", "facebook", "google"],
            )
            auto_sched = st.toggle(
                "Schedule immediately (Off = send to Approval Inbox first)",
                value=False,
            )
            if st.form_submit_button("⚡ Generate Campaign", type="primary"):
                if not occ.strip() or not plats:
                    st.warning("Enter an occasion and choose at least one platform.")
                else:
                    ok_c, res_c = api_request(
                        "POST",
                        f"/api/agent/{biz_id}/campaign",
                        json_body={
                            "occasion": occ.strip(),
                            "offer_details": off.strip(),
                            "platforms": plats,
                            "auto_execute": auto_sched,
                        },
                    )
                    if ok_c:
                        st.success(
                            f"Campaign '{res_c['occasion']}' ready! "
                            f"Scheduled: {res_c['posts_created']} • Queued for Approval: {res_c['approvals_queued']}"
                        )
                        for asset in res_c["assets"]:
                            st.markdown(f"**{asset['platform'].title()}** (`{asset['status']}`):")
                            st.info(asset["content"])
                        render_agent_trace(res_c.get("agent_trace", []))
                    else:
                        st.error(res_c)

    with tab_graphic:
        st.subheader("🎨 Generate Branded 1080×1080 Promo Poster (PNG + QR Code)")
        gc1, gc2 = st.columns([1.2, 1.0])
        with gc1:
            g_head = st.text_input("Promo Headline", value="Weekend Neighborhood Special")
            g_offer = st.text_area(
                "Offer Text",
                value="Enjoy 15% off pickup & table bookings this Friday–Sunday!",
                height=90,
            )
            g_code = st.text_input("Promo Code", value="LOCAL15")
        with gc2:
            try:
                img_resp = httpx.get(
                    f"{API_BASE_URL}/api/social/{biz_id}/promo-card.png",
                    params={"headline": g_head, "offer_text": g_offer, "promo_code": g_code},
                    timeout=10.0,
                )
                if img_resp.status_code == 200:
                    st.image(img_resp.content, caption="Branded Social / WhatsApp Promo Card")
                    st.download_button(
                        "⬇️ Download Promo PNG",
                        data=img_resp.content,
                        file_name=f"promo_{biz_id}.png",
                        mime="image/png",
                        use_container_width=True,
                    )
            except httpx.HTTPError:
                st.info("Start the API server to preview the promo graphic.")

    with tab_calendar:
        cal_days = st.slider("Calendar Window (days)", min_value=7, max_value=30, value=14)
        ok_cal, cal_data = api_request(
            "GET", f"/api/social/{biz_id}/calendar", params={"days": cal_days}
        )
        if not ok_cal:
            st.error(cal_data)
        else:
            st.caption(
                f"Showing {cal_data['total_posts']} post(s) from {cal_data['start_date']} to {cal_data['end_date']}"
            )
            days_list = cal_data.get("days", [])
            for row_start in range(0, len(days_list), 7):
                cols = st.columns(7)
                for idx, day_obj in enumerate(days_list[row_start : row_start + 7]):
                    with cols[idx]:
                        posts_html = ""
                        for p in day_obj["posts"]:
                            snippet = (
                                (p["content"][:42] + "…")
                                if len(p["content"]) > 42
                                else p["content"]
                            )
                            posts_html += (
                                f"<div style='background:#f8fafc; color:#0f172a; border-radius:6px; padding:4px 6px; "
                                f"margin-bottom:4px; font-size:0.75rem;'>"
                                f"<strong>{html.escape(p['platform'].title())}</strong> ({html.escape(p['status'])})<br/>{html.escape(snippet)}</div>"
                            )
                        if not posts_html:
                            posts_html = (
                                "<div style='color:#94a3b8; font-size:0.75rem;'>No posts</div>"
                            )
                        st.markdown(
                            f"""
                            <div class="calendar-day">
                                <div class="calendar-day-title">{day_obj["date"]}</div>
                                {posts_html}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

    with tab_history:
        f1, f2 = st.columns(2)
        plat_filter = f1.selectbox(
            "Filter Platform", ["All", "instagram", "facebook", "google", "twitter"]
        )
        stat_filter = f2.selectbox("Filter Status", ["All", "published", "scheduled", "draft"])
        params: dict[str, Any] = {}
        if plat_filter != "All":
            params["platform"] = plat_filter
        if stat_filter != "All":
            params["status"] = stat_filter

        ok_posts, posts_list = api_request("GET", f"/api/social/{biz_id}/posts", params=params)
        if not ok_posts:
            st.error(posts_list)
        elif not posts_list:
            st.info("No social posts match the current filters.")
        else:
            for p in posts_list:
                st.markdown(
                    f"""
                    <div class="metric-card" style="margin-bottom:0.75rem;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong>{html.escape(p["platform"].title())}</strong>
                            {status_badge(p["status"])}
                        </div>
                        <p style="margin:0.55rem 0; color:#1e293b; white-space:pre-wrap;">{html.escape(p["content"])}</p>
                        <div style="margin-top:0.6rem; color:#475569; font-size:0.82rem;">
                            ❤️ {p.get("engagement_likes", 0)} Likes &nbsp;|&nbsp;
                            💬 {p.get("engagement_comments", 0)} Comments &nbsp;|&nbsp;
                            🔁 {p.get("engagement_shares", 0)} Shares
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# PAGE 5: Reviews
# ---------------------------------------------------------------------------

elif page == "⭐ Reviews" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Customer Reviews & Reputation Management")

    tab_feed, tab_analytics, tab_seo = st.tabs(
        ["💬 Review Feed & AI Replies", "📈 Review Analytics", "🔍 Local SEO & Customer Themes"]
    )

    with tab_feed:
        top_c1, top_c2, top_c3 = st.columns([1, 1, 1.2])
        sent_filter = top_c1.selectbox("Sentiment", ["All", "positive", "neutral", "negative"])
        resp_filter = top_c2.selectbox("Response Status", ["All", "pending", "responded"])
        with top_c3:
            st.write("")
            if st.button(
                "🤖 Auto-Respond to All Pending Reviews",
                type="primary",
                use_container_width=True,
            ):
                ok_auto, auto_res = api_request(
                    "POST",
                    f"/api/reviews/{biz_id}/reviews/auto-respond",
                    json_body={"only_positive": False, "min_rating": 1, "max_count": 25},
                )
                if ok_auto:
                    st.success(
                        f"Auto-responded to {auto_res['processed_count']} pending review(s)!"
                    )
                    st.rerun()
                else:
                    st.error(auto_res)

        rev_params: dict[str, Any] = {}
        if sent_filter != "All":
            rev_params["sentiment"] = sent_filter
        if resp_filter != "All":
            rev_params["response_status"] = resp_filter

        ok_rev, reviews = api_request("GET", f"/api/reviews/{biz_id}/reviews", params=rev_params)
        if not ok_rev:
            st.error(reviews)
        elif not reviews:
            st.info("No reviews match the selected filters.")
        else:
            for rev in reviews:
                stars = "★" * rev["rating"] + "☆" * (5 - rev["rating"])
                st.markdown(
                    f"""
                    <div class="metric-card" style="margin-bottom:0.5rem;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <strong>{html.escape(rev["reviewer_name"])}</strong>
                                <span style="color:#f59e0b; margin-left:0.5rem;">{stars} ({rev["rating"]}/5)</span>
                                <span style="color:#64748b; font-size:0.82rem;"> • {html.escape(rev["platform"].title())}</span>
                            </div>
                            <div>
                                {sentiment_badge(rev.get("sentiment"))}
                                {status_badge(rev["response_status"])}
                            </div>
                        </div>
                        <p style="margin:0.5rem 0; color:#1e293b;">{html.escape(rev.get("review_text") or "")}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if rev["response_status"] == "responded" and rev.get("response_text"):
                    st.caption(f"✅ **Owner Reply:** {rev['response_text']}")
                else:
                    rc1, rc2 = st.columns([3, 1])
                    custom_reply = rc1.text_input(
                        "Reply",
                        key=f"reply_input_{rev['id']}",
                        placeholder="Write a custom reply or click One-Click AI Reply...",
                        label_visibility="collapsed",
                    )
                    with rc2:
                        if st.button(
                            "✨ AI Reply",
                            key=f"ai_reply_btn_{rev['id']}",
                            use_container_width=True,
                        ):
                            ok_r, _r_data = api_request(
                                "POST",
                                f"/api/reviews/{biz_id}/reviews/{rev['id']}/respond",
                                json_body={
                                    "response_text": custom_reply or None,
                                    "use_ai": not bool(custom_reply.strip()),
                                },
                            )
                            if ok_r:
                                st.success("Reply posted!")
                                st.rerun()
                            else:
                                st.error(_r_data)

    with tab_analytics:
        ok_an, an = api_request("GET", f"/api/reviews/{biz_id}/reviews/analytics")
        if not ok_an:
            st.error(an)
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Reviews", an["total_reviews"])
            m2.metric("Average Rating", f"{an['average_rating']:.2f} ★")
            m3.metric("Response Rate", f"{an['response_rate']}%")
            m4.metric("Pending Replies", an["pending_count"])

            ch1, ch2 = st.columns(2)
            with ch1:
                sent_df = pd.DataFrame(
                    [
                        {"Sentiment": k.title(), "Count": v}
                        for k, v in an["sentiment_breakdown"].items()
                    ]
                )
                if HAS_PLOTLY:
                    fig_sent = px.pie(
                        sent_df,
                        names="Sentiment",
                        values="Count",
                        title="Sentiment Breakdown",
                        color="Sentiment",
                        color_discrete_map={
                            "Positive": "#22c55e",
                            "Neutral": "#eab308",
                            "Negative": "#ef4444",
                        },
                    )
                    st.plotly_chart(fig_sent, use_container_width=True)
                else:
                    st.subheader("Sentiment Breakdown")
                    st.bar_chart(sent_df.set_index("Sentiment"))

            with ch2:
                rat_df = pd.DataFrame(
                    [{"Stars": f"{k} ★", "Count": v} for k, v in an["rating_distribution"].items()]
                )
                if HAS_PLOTLY:
                    fig_rat = px.bar(
                        rat_df,
                        x="Stars",
                        y="Count",
                        title="Star Rating Distribution",
                        color_discrete_sequence=["#3b82f6"],
                    )
                    st.plotly_chart(fig_rat, use_container_width=True)
                else:
                    st.subheader("Star Rating Distribution")
                    st.bar_chart(rat_df.set_index("Stars"))

    with tab_seo:
        ok_seo, seo = api_request("GET", f"/api/agent/{biz_id}/seo-audit")
        if not ok_seo:
            st.error(seo)
        else:
            s1, s2 = st.columns(2)
            s1.metric("NAP & Listing Completeness", f"{seo['nap_consistency_score']}%")
            s2.metric("Overall Health Score", f"{seo['health_score']}/100")

            th1, th2 = st.columns(2)
            with th1:
                st.markdown("**👍 Top Praised Customer Themes**")
                for t in seo.get("top_strengths") or []:
                    st.success(f"{t['theme']} ({t['mentions']} mentions)")
                if not seo.get("top_strengths"):
                    st.caption("Collect more positive reviews to surface strength themes.")
            with th2:
                st.markdown("**⚠️ Recurring Improvement Areas**")
                for t in seo.get("improvement_themes") or []:
                    st.warning(f"{t['theme']} ({t['mentions']} mentions)")
                if not seo.get("improvement_themes"):
                    st.caption("No recurring complaint themes detected.")

            st.markdown("**🎯 Target Local SEO Keywords**")
            st.write(", ".join(f"`{kw}`" for kw in seo.get("target_local_keywords", [])))
            st.markdown("**📌 Recommendations**")
            for rec in seo.get("recommendations", []):
                st.info(rec)


# ---------------------------------------------------------------------------
# PAGE 6: Bookings & Online Orders
# ---------------------------------------------------------------------------

elif page == "📅 Bookings & Orders" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Bookings, Availability & Online Customer Orders")

    ok_bk, bookings = api_request("GET", f"/api/bookings/{biz_id}/bookings")
    bookings_list = bookings if ok_bk and isinstance(bookings, list) else []
    ok_ord, orders = api_request("GET", f"/api/orders/{biz_id}/orders")
    orders_list = orders if ok_ord and isinstance(orders, list) else []

    today = date.today()
    today_count = sum(
        1
        for b in bookings_list
        if b["booking_date"] == today.isoformat() and b["status"] != "cancelled"
    )
    confirmed_count = sum(1 for b in bookings_list if b["status"] == "confirmed")
    active_orders = sum(1 for o in orders_list if o["status"] not in {"completed", "cancelled"})

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Bookings Today", today_count)
    b2.metric("Total Confirmed Bookings", confirmed_count)
    b3.metric("Active Online Orders", active_orders)
    with b4:
        st.link_button(
            "📥 Calendar (.ics)",
            f"{API_BASE_URL}/api/bookings/{biz_id}/calendar.ics",
            use_container_width=True,
        )
        st.link_button(
            "📄 Bookings CSV",
            f"{API_BASE_URL}/api/businesses/{biz_id}/export?dataset=bookings",
            use_container_width=True,
        )

    tab_cal, tab_new, tab_avail, tab_orders, tab_waitlist = st.tabs(
        [
            "📅 Bookings Schedule",
            "➕ New Booking",
            "🕒 Check Availability",
            "🛒 Online Orders Queue",
            "⏰ Booking Waitlist",
        ]
    )

    with tab_cal:
        if not ok_bk:
            st.error(bookings)
        elif not bookings_list:
            st.info("No bookings found.")
        else:
            status_filter_bk = st.selectbox(
                "Filter Status", ["All", "confirmed", "pending", "completed", "cancelled"]
            )
            filtered = [
                b
                for b in bookings_list
                if status_filter_bk == "All" or b["status"] == status_filter_bk
            ]
            for b in filtered:
                row_c1, row_c2, row_c3 = st.columns([2.5, 1, 1])
                with row_c1:
                    time_str = str(b["booking_time"])[:5]
                    st.markdown(
                        f"**{b['booking_date']} @ {time_str}** ({b['duration_minutes']}m) — "
                        f"**{b['customer_name']}** • {b['service']}"
                    )
                    if b.get("notes"):
                        st.caption(f"Notes: {b['notes']}")
                with row_c2:
                    st.markdown(status_badge(b["status"]), unsafe_allow_html=True)
                with row_c3:
                    if b["status"] not in {"cancelled", "completed"} and st.button(
                        "Cancel", key=f"cancel_bk_{b['id']}"
                    ):
                        ok_del, del_res = api_request(
                            "DELETE", f"/api/bookings/{biz_id}/bookings/{b['id']}"
                        )
                        if ok_del:
                            st.success("Booking cancelled.")
                            st.rerun()
                        else:
                            st.error(del_res)
                st.divider()

    with tab_new, st.form("new_booking_form"):
        fc1, fc2 = st.columns(2)
        cust_name = fc1.text_input("Customer Name*")
        cust_phone = fc2.text_input("Phone*", placeholder="(512) 555-0199")
        cust_email = fc1.text_input("Email*", placeholder="guest@example.com")
        service_name = fc2.text_input("Service*", placeholder="Dinner Reservation or Haircut")
        bk_date = fc1.date_input("Date", value=today + timedelta(days=1))
        bk_time = fc2.time_input("Start Time", value=time(12, 0))
        duration = st.number_input(
            "Duration (minutes)", min_value=15, max_value=360, value=60, step=15
        )
        notes = st.text_area("Notes", placeholder="Preferences, allergies, special requests...")

        if st.form_submit_button("Create Booking", type="primary"):
            if (
                not cust_name.strip()
                or not cust_email.strip()
                or not cust_phone.strip()
                or not service_name.strip()
            ):
                st.warning("Customer name, email, phone, and service are required.")
            else:
                ok_create, create_res = api_request(
                    "POST",
                    f"/api/bookings/{biz_id}/book",
                    json_body={
                        "customer_name": cust_name.strip(),
                        "customer_email": cust_email.strip(),
                        "customer_phone": cust_phone.strip(),
                        "service": service_name.strip(),
                        "booking_date": bk_date.isoformat(),
                        "booking_time": bk_time.strftime("%H:%M:%S"),
                        "duration_minutes": int(duration),
                        "notes": notes or None,
                    },
                )
                if ok_create:
                    st.success(f"Booking #{create_res['id']} confirmed for {cust_name}!")
                else:
                    st.error(create_res)

    with tab_avail:
        av1, av2 = st.columns(2)
        check_date = av1.date_input("Check Date", value=today)
        check_dur = av2.selectbox("Duration (min)", [30, 45, 60, 90, 120], index=2)
        ok_av, av_data = api_request(
            "GET",
            f"/api/bookings/{biz_id}/availability",
            params={"date": check_date.isoformat(), "duration_minutes": check_dur},
        )
        if not ok_av:
            st.error(av_data)
        elif not av_data["is_open"]:
            st.warning(f"Closed on {av_data['day_of_week'].title()} ({av_data['date']}).")
        else:
            st.info(
                f"Open {av_data['open_time']} – {av_data['close_time']} • "
                f"**{av_data['available_count']}** slot(s) available"
            )
            slot_cols = st.columns(4)
            for idx, slot in enumerate(av_data["slots"]):
                with slot_cols[idx % 4]:
                    if slot["available"]:
                        st.success(f"✅ {slot['start_time']} - {slot['end_time']}")
                    else:
                        st.error(f"⛔ {slot['start_time']} - {slot['end_time']}")

    with tab_orders:
        if not orders_list:
            st.info(
                f"No online orders yet. Share your public storefront link `{API_BASE_URL}/site/{biz_id}` "
                "so customers can order directly!"
            )
        else:
            for o in orders_list:
                items_str = ", ".join(f"{it['quantity']}× {it['name']}" for it in o["items"])
                oc1, oc2, oc3 = st.columns([2.2, 1.0, 1.3])
                with oc1:
                    promo_tag = f" • 🎟️ `{o['promo_code']}`" if o.get("promo_code") else ""
                    st.markdown(
                        f"**Order #{o['id']} — {o['customer_name']}** ({o['customer_phone']}) • "
                        f"**${o['total_amount']:.2f}** (`{o['fulfillment_type']}`){promo_tag}"
                    )
                    st.caption(
                        f"Items: {items_str}" + (f" | Note: {o['notes']}" if o.get("notes") else "")
                    )
                with oc2:
                    st.markdown(status_badge(o["status"]), unsafe_allow_html=True)
                with oc3:
                    next_opts = ["new", "confirmed", "preparing", "ready", "completed", "cancelled"]
                    new_stat = st.selectbox(
                        "Update",
                        next_opts,
                        index=next_opts.index(o["status"]) if o["status"] in next_opts else 0,
                        key=f"ord_stat_{o['id']}",
                        label_visibility="collapsed",
                    )
                    if new_stat != o["status"] and st.button("Save", key=f"ord_save_{o['id']}"):
                        ok_u, res_u = api_request(
                            "PUT",
                            f"/api/orders/{biz_id}/orders/{o['id']}",
                            json_body={"status": new_stat},
                        )
                        if ok_u:
                            st.rerun()
                        else:
                            st.error(res_u)
                st.divider()

    with tab_waitlist:
        st.caption(
            "When any booking above is cancelled, waiting guests for that date are "
            "automatically alerted on WhatsApp."
        )
        ok_wl, wl_rows = api_request("GET", f"/api/growth/{biz_id}/waitlist")
        if ok_wl and isinstance(wl_rows, list) and wl_rows:
            for w in wl_rows:
                wc1, wc2, wc3 = st.columns([2.5, 1.0, 1.4])
                wc1.markdown(
                    f"**{w['customer_name']}** ({w['customer_phone']}) — "
                    f"**{w['preferred_date']} @ {w['preferred_time']}** • {w['service']}"
                )
                wc2.markdown(status_badge(w["status"]), unsafe_allow_html=True)
                with wc3:
                    w_b1, w_b2 = st.columns(2)
                    if w["status"] != "booked" and w_b1.button("Book", key=f"wl_book_{w['id']}"):
                        api_request(
                            "PATCH",
                            f"/api/growth/{biz_id}/waitlist/{w['id']}",
                            json_body={"status": "booked"},
                        )
                        st.rerun()
                    if w_b2.button("Del", key=f"wl_del_{w['id']}"):
                        api_request("DELETE", f"/api/growth/{biz_id}/waitlist/{w['id']}")
                        st.rerun()
        else:
            st.info("Waitlist is currently empty.")

        with st.form("add_waitlist_dash_form"):
            st.markdown("**➕ Add Customer to Waitlist**")
            w1, w2 = st.columns(2)
            wl_name = w1.text_input("Customer Name*")
            wl_phone = w2.text_input("Phone*")
            wl_date = w1.date_input("Preferred Date", value=today + timedelta(days=1))
            wl_time = w2.time_input("Preferred Time", value=time(18, 30))
            wl_svc = st.text_input("Service / Party Size", value="Table Reservation")
            if st.form_submit_button("Add to Waitlist"):
                if wl_name.strip() and wl_phone.strip():
                    ok_wadd, res_wadd = api_request(
                        "POST",
                        f"/api/growth/{biz_id}/waitlist",
                        json_body={
                            "customer_name": wl_name.strip(),
                            "customer_phone": wl_phone.strip(),
                            "preferred_date": wl_date.isoformat(),
                            "preferred_time": wl_time.strftime("%H:%M"),
                            "service": wl_svc.strip() or "Reservation",
                        },
                    )
                    if ok_wadd:
                        st.success("Added to waitlist!")
                        st.rerun()
                    else:
                        st.error(res_wadd)


# ---------------------------------------------------------------------------
# PAGE 7: CRM, Loyalty & Competitor Intelligence
# ---------------------------------------------------------------------------

elif page == "👥 CRM & Competitors" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Customer CRM, Loyalty Retention & Competitor Watch")

    tab_crm, tab_comp = st.tabs(["👥 Customer CRM & Loyalty", "🎯 Competitor Watch"])

    with tab_crm:
        top1, top2, top3 = st.columns([1.4, 1.2, 1.0])
        with top1:
            if st.button(
                "🎁 Draft Loyalty & Retention Offers (HITL)",
                type="primary",
                use_container_width=True,
            ):
                ok_ret, res_ret = api_request("POST", f"/api/crm/{biz_id}/retention-offers")
                if ok_ret:
                    st.success(
                        f"Queued {res_ret['queued_count']} personalized offer(s) in Approval Inbox!"
                    )
                else:
                    st.error(res_ret)
        with top3:
            st.link_button(
                "📄 Export CRM CSV",
                f"{API_BASE_URL}/api/businesses/{biz_id}/export?dataset=customers",
                use_container_width=True,
            )

        ok_cust, customers = api_request("GET", f"/api/crm/{biz_id}/customers")
        if not ok_cust:
            st.error(customers)
        elif not customers:
            st.info("No customers synced yet.")
        else:
            df_cust = pd.DataFrame(
                [
                    {
                        "Name": c["name"],
                        "Segment": c["segment"],
                        "Visits": c["visit_count"],
                        "Total Spent ($)": c["total_spent"],
                        "Loyalty Pts": c["loyalty_points"],
                        "Phone": c.get("phone") or "",
                        "Email": c.get("email") or "",
                    }
                    for c in customers
                ]
            )
            st.dataframe(df_cust, use_container_width=True, hide_index=True)

    with tab_comp:
        ok_cmp, cmp_data = api_request("GET", f"/api/crm/{biz_id}/competitors")
        if ok_cmp:
            st.metric(
                "Your Rating vs Market",
                f"{cmp_data['own_rating']} ★ ({cmp_data['own_review_count']} reviews)",
            )
            for strat in cmp_data.get("recommended_counter_strategies", []):
                st.info(f"💡 **AI Counter-Strategy:** {strat}")
            for comp in cmp_data.get("competitors", []):
                cc1, cc2 = st.columns([3, 1])
                cc1.markdown(
                    f"**{comp['name']}** ({comp['price_tier']}) — ★ {comp['rating']} ({comp['review_count']} reviews) "
                    f"| Advantage: `{comp['rating_advantage']:+.2f}★`"
                )
                cc1.caption(
                    f"Strengths: {comp.get('strengths') or '—'} | Weaknesses: {comp.get('weaknesses') or '—'}"
                )
                if cc2.button("Remove", key=f"del_comp_{comp['id']}"):
                    api_request("DELETE", f"/api/crm/{biz_id}/competitors/{comp['id']}")
                    st.rerun()

        with st.form("add_competitor_form"):
            st.markdown("**➕ Track a Nearby Competitor**")
            cf1, cf2, cf3 = st.columns(3)
            c_name = cf1.text_input("Competitor Name*")
            c_rat = cf2.number_input("Rating", min_value=1.0, max_value=5.0, value=4.1, step=0.1)
            c_rev = cf3.number_input("Reviews Count", min_value=0, value=80, step=10)
            c_str = cf1.text_input("Their Strength", placeholder="Prime corner location")
            c_weak = cf2.text_input("Their Weakness", placeholder="Slow weekend wait times")
            c_tier = cf3.selectbox("Price Tier", ["$", "$$", "$$$"], index=1)
            if st.form_submit_button("Add Competitor"):
                if c_name.strip():
                    ok_add, res_add = api_request(
                        "POST",
                        f"/api/crm/{biz_id}/competitors",
                        json_body={
                            "name": c_name.strip(),
                            "category": selected_business["category"],
                            "rating": float(c_rat),
                            "review_count": int(c_rev),
                            "price_tier": c_tier,
                            "strengths": c_str.strip() or None,
                            "weaknesses": c_weak.strip() or None,
                        },
                    )
                    if ok_add:
                        st.success("Competitor added!")
                        st.rerun()
                    else:
                        st.error(res_add)


# ---------------------------------------------------------------------------
# PAGE 8: Growth, Promo Coupons, Segmented Broadcasts, FAQs & ROI
# ---------------------------------------------------------------------------

elif page == "💰 Growth, Coupons & ROI" and selected_business:
    biz_id = selected_business["id"]
    render_header(
        selected_business,
        "Revenue ROI, Promo Coupons, Segmented Broadcasts, Concierge FAQs & Localization",
    )

    tab_roi, tab_coupons, tab_broadcast, tab_faqs = st.tabs(
        [
            "📈 Revenue & Top Items",
            "🎟️ Promo Coupons & Validator",
            "📣 Broadcasts & Translator",
            "📚 Grounded FAQ Knowledge Base",
        ]
    )

    with tab_roi:
        ok_rev, rev = api_request("GET", f"/api/growth/{biz_id}/revenue-analytics")
        if not ok_rev:
            st.error(rev)
        else:
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Est. Total Revenue", f"${rev['total_estimated_revenue']:.2f}")
            r2.metric(
                "Net Order Revenue",
                f"${rev['net_order_revenue']:.2f}",
                delta=f"-${rev['total_discounts_given']:.2f} promo discounts",
            )
            r3.metric("Avg Order Value", f"${rev['average_order_value']:.2f}")
            r4.metric("Repeat Customer Rate", f"{rev['repeat_customer_rate_pct']}%")

            r5, r6, r7, r8 = st.columns(4)
            r5.metric("Est. Booking Value", f"${rev['estimated_booking_revenue']:.2f}")
            r6.metric("Active Coupons", rev["active_coupons"])
            r7.metric("Coupon Redemptions", rev["total_coupon_redemptions"])
            r8.metric("Waitlist Waiting", rev["waitlist_waiting_count"])

            col_ti, col_bh = st.columns(2)
            with col_ti:
                st.subheader("🏆 Top Ordered Items")
                if rev.get("top_ordered_items"):
                    st.dataframe(
                        pd.DataFrame(rev["top_ordered_items"]),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("No item sales recorded yet.")
            with col_bh:
                st.subheader("🕒 Busiest Booking Hours")
                if rev.get("busiest_booking_hours"):
                    st.dataframe(
                        pd.DataFrame(rev["busiest_booking_hours"]),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("No booking hour distribution yet.")

    with tab_coupons:
        col_cform, col_cval = st.columns([1.2, 1.0])
        with col_cform, st.form("create_coupon_form"):
            st.markdown("**➕ Create Promo Coupon**")
            cp1, cp2 = st.columns(2)
            c_code = cp1.text_input("Code*", placeholder="WEEKEND20")
            c_title = cp2.text_input("Title*", placeholder="20% off weekend pickup")
            c_type = cp1.selectbox("Discount Type", ["percent", "fixed"])
            c_val = cp2.number_input("Value (% or $)*", min_value=1.0, value=15.0, step=1.0)
            c_min = cp1.number_input("Minimum Order ($)", min_value=0.0, value=15.0, step=5.0)
            c_uses = cp2.number_input("Max Uses", min_value=1, value=100, step=10)
            c_exp = st.date_input("Valid Until", value=date.today() + timedelta(days=30))
            if st.form_submit_button("Create Coupon", type="primary"):
                if not c_code.strip() or not c_title.strip():
                    st.warning("Coupon code and title are required.")
                else:
                    ok_cc, res_cc = api_request(
                        "POST",
                        f"/api/growth/{biz_id}/coupons",
                        json_body={
                            "code": c_code.strip(),
                            "title": c_title.strip(),
                            "discount_type": c_type,
                            "discount_value": float(c_val),
                            "min_order_amount": float(c_min),
                            "max_uses": int(c_uses),
                            "valid_until": c_exp.isoformat(),
                        },
                    )
                    if ok_cc:
                        st.success(f"Coupon `{res_cc['code']}` created!")
                        st.rerun()
                    else:
                        st.error(res_cc)

        with col_cval, st.form("validate_coupon_form"):
            st.markdown("**🧮 Test Coupon Discount Simulator**")
            val_code = st.text_input("Promo Code", value="LOCAL15")
            val_sub = st.number_input("Cart Subtotal ($)", min_value=0.0, value=50.0, step=5.0)
            if st.form_submit_button("Calculate Discount"):
                ok_v, res_v = api_request(
                    "POST",
                    f"/api/growth/{biz_id}/coupons/validate",
                    json_body={"code": val_code.strip(), "subtotal": float(val_sub)},
                )
                if ok_v:
                    if res_v["valid"]:
                        st.success(
                            f"{res_v['reason']} → Final Total: **${res_v['final_total']:.2f}**"
                        )
                    else:
                        st.warning(res_v["reason"])
                else:
                    st.error(res_v)

        st.divider()
        st.subheader("Active & Past Promo Codes")
        ok_cp, coupons = api_request("GET", f"/api/growth/{biz_id}/coupons")
        if ok_cp and isinstance(coupons, list) and coupons:
            for cp in coupons:
                c1, c2, c3 = st.columns([2.5, 1.0, 1.2])
                val_txt = (
                    f"{int(cp['discount_value'])}% OFF"
                    if cp["discount_type"] == "percent"
                    else f"${cp['discount_value']:.2f} OFF"
                )
                c1.markdown(
                    f"**`{cp['code']}`** — **{val_txt}** ({cp['title']}) • "
                    f"Used `{cp['uses_count']}/{cp['max_uses']}` • Min `${cp['min_order_amount']:.0f}`"
                )
                c2.markdown(
                    status_badge("published" if cp["is_active"] else "draft"),
                    unsafe_allow_html=True,
                )
                with c3:
                    b_tog, b_del = st.columns(2)
                    label_tog = "Pause" if cp["is_active"] else "Enable"
                    if b_tog.button(label_tog, key=f"cp_tog_{cp['id']}"):
                        api_request(
                            "PATCH",
                            f"/api/growth/{biz_id}/coupons/{cp['id']}",
                            json_body={"is_active": not cp["is_active"]},
                        )
                        st.rerun()
                    if b_del.button("Del", key=f"cp_del_{cp['id']}"):
                        api_request("DELETE", f"/api/growth/{biz_id}/coupons/{cp['id']}")
                        st.rerun()
        else:
            st.info("No promo coupons configured yet.")

    with tab_broadcast:
        bc_col, tr_col = st.columns(2)
        with bc_col, st.form("segmented_broadcast_form"):
            st.subheader("📣 Segmented WhatsApp Broadcast")
            bc_seg = st.selectbox("Target Segment", ["All", "VIP", "Regular", "New"])
            bc_topic = st.text_input(
                "Offer / Announcement*", placeholder="Fresh chef tasting dinner this Friday!"
            )
            bc_promo = st.text_input("Attach Promo Code (optional)", placeholder="LOCAL15")
            bc_auto = st.toggle("Send Immediately (Off = Approval Inbox)", value=False)
            if st.form_submit_button("Launch Broadcast", type="primary"):
                if not bc_topic.strip():
                    st.warning("Enter an announcement message.")
                else:
                    ok_bc, res_bc = api_request(
                        "POST",
                        f"/api/growth/{biz_id}/broadcast",
                        json_body={
                            "segment": bc_seg,
                            "topic": bc_topic.strip(),
                            "promo_code": bc_promo.strip() or None,
                            "auto_execute": bc_auto,
                        },
                    )
                    if ok_bc:
                        st.success(
                            f"Broadcast status: `{res_bc['status']}` • "
                            f"Targeted {res_bc['targeted_customers']} customer(s)."
                        )
                        st.info(res_bc["sample_message"])
                    else:
                        st.error(res_bc)

        with tr_col, st.form("translate_copy_form"):
            st.subheader("🌍 Neighborhood Language Translator")
            tr_lang = st.selectbox("Target Language", ["Hindi", "Hinglish", "Spanish", "French"])
            tr_txt = st.text_area(
                "Copy to Localize*",
                placeholder="Enjoy 15% off weekend pickup with code LOCAL15!",
                height=100,
            )
            if st.form_submit_button("Localize Copy"):
                if tr_txt.strip():
                    ok_tr, res_tr = api_request(
                        "POST",
                        f"/api/growth/{biz_id}/translate",
                        json_body={"text": tr_txt.strip(), "target_language": tr_lang},
                    )
                    if ok_tr:
                        st.success(res_tr["translated_text"])
                        st.caption(res_tr["notes"])
                    else:
                        st.error(res_tr)

    with tab_faqs:
        st.caption(
            "These FAQs ground your WhatsApp Concierge so customers get exact shop-verified answers."
        )
        if st.button("✨ Auto-Suggest & Apply Shop FAQs", type="primary"):
            ok_sug, res_sug = api_request("POST", f"/api/growth/{biz_id}/faqs/suggest?apply=true")
            if ok_sug:
                st.success(f"Applied {len(res_sug['faqs'])} grounded FAQs!")
                st.rerun()
            else:
                st.error(res_sug)

        ok_fq, faqs = api_request("GET", f"/api/growth/{biz_id}/faqs")
        faq_list = faqs if ok_fq and isinstance(faqs, list) else []
        for idx_fq, fq in enumerate(faq_list):
            fc1, fc2 = st.columns([4, 0.8])
            fc1.markdown(f"**Q:** {fq['q']}\n\n**A:** {fq['a']}")
            if fc2.button("Del", key=f"del_faq_{biz_id}_{idx_fq}"):
                updated_faqs = [f for i, f in enumerate(faq_list) if i != idx_fq]
                api_request("PUT", f"/api/growth/{biz_id}/faqs", json_body={"faqs": updated_faqs})
                st.rerun()
            st.divider()

        with st.form("add_faq_form"):
            st.markdown("**➕ Add Custom Concierge FAQ**")
            nq = st.text_input(
                "Question*", placeholder="Do you offer gluten-free dough or parking?"
            )
            na = st.text_area("Answer*", placeholder="Yes, validated parking behind 2nd St.")
            if st.form_submit_button("Save FAQ"):
                if nq.strip() and na.strip():
                    faq_list.append({"q": nq.strip(), "a": na.strip()})
                    ok_sf, _ = api_request(
                        "PUT", f"/api/growth/{biz_id}/faqs", json_body={"faqs": faq_list}
                    )
                    if ok_sf:
                        st.success("FAQ saved to concierge knowledge base!")
                        st.rerun()


# ---------------------------------------------------------------------------
# PAGE 9: Customer Storefront & Catalog
# ---------------------------------------------------------------------------

elif page == "🌟 Loyalty, NPS & Gift Cards" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Loyalty Points, NPS Surveys & Gift Cards")

    tab_loy, tab_nps, tab_gc = st.tabs(["🌟 Loyalty Points", "💬 NPS Surveys", "🎁 Gift Cards"])

    with tab_loy:
        st.subheader("Loyalty Program Analytics")
        ok_la, la = api_request("GET", f"/api/loyalty/{biz_id}/points/analytics")
        if ok_la and la:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Members", la.get("total_members", 0))
            col2.metric("Active Members", la.get("active_members", 0))
            col3.metric("Outstanding Points", f"{la.get('total_outstanding_points', 0):,}")
            col4.metric("Liability ($)", f"${la.get('outstanding_liability_dollars', 0):.2f}")
            tier_data = la.get("tier_breakdown", {})
            if tier_data:
                tier_df = pd.DataFrame(list(tier_data.items()), columns=["Tier", "Count"])
                st.bar_chart(tier_df.set_index("Tier"))
        else:
            st.info("No loyalty data yet. Customers can join via the storefront.")

        st.subheader("🏆 Loyalty Leaderboard")
        ok_lb, lb = api_request("GET", f"/api/loyalty/{biz_id}/points/leaderboard?limit=10")
        if ok_lb and lb and lb.get("leaderboard"):
            lb_df = pd.DataFrame(lb["leaderboard"])
            st.dataframe(
                lb_df[["rank", "customer_name", "tier_label", "points_balance", "lifetime_points"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No loyalty members yet.")

        loy_col1, loy_col2 = st.columns(2)
        with loy_col1:
            st.subheader("Award Points Manually")
            with st.form("earn_pts_form"):
                ep_email = st.text_input("Customer Email *")
                ep_pts = st.number_input("Points to Award", min_value=1, max_value=10000, value=100)
                ep_desc = st.text_input("Description", value="Manual bonus points")
                if st.form_submit_button("Award Points", type="primary"):
                    if ep_email:
                        ok_ep, ep_res = api_request(
                            "POST",
                            f"/api/loyalty/{biz_id}/points/earn",
                            json_body={
                                "customer_email": ep_email,
                                "points": int(ep_pts),
                                "description": ep_desc,
                            },
                        )
                        if ok_ep:
                            st.success(
                                f"Awarded {ep_pts} pts to {ep_email}. New balance: {ep_res.get('new_balance', '?')} | Tier: {ep_res.get('tier_label', '?')}"
                            )
                        else:
                            st.error(ep_res)
                    else:
                        st.warning("Email is required.")

        with loy_col2:
            st.subheader("Redeem Member Points")
            with st.form("redeem_pts_form"):
                rp_email = st.text_input("Member Email *")
                rp_pts = st.number_input(
                    "Points to Redeem", min_value=10, max_value=50000, value=100
                )
                rp_desc = st.text_input("Redemption Note", value="In-store reward discount")
                if st.form_submit_button("Redeem Points"):
                    if rp_email:
                        ok_rp, rp_res = api_request(
                            "POST",
                            f"/api/loyalty/{biz_id}/points/redeem",
                            json_body={
                                "customer_email": rp_email,
                                "points": int(rp_pts),
                                "description": rp_desc,
                            },
                        )
                        if ok_rp:
                            st.success(
                                f"Redeemed {rp_pts} pts (${rp_res.get('dollar_value', 0):.2f} value). Remaining: {rp_res.get('remaining_balance', 0)}"
                            )
                        else:
                            st.error(rp_res)
                    else:
                        st.warning("Email is required.")

    with tab_nps:
        st.subheader("Net Promoter Score Analytics")
        ok_nps, nps = api_request("GET", f"/api/loyalty/{biz_id}/nps/analytics")
        if ok_nps and nps and nps.get("total_responses", 0) > 0:
            col1, col2, col3, col4 = st.columns(4)
            score = nps.get("nps_score")
            col1.metric("NPS Score", f"{score:+.1f}" if score is not None else "N/A")
            col2.metric(
                "Promoters", f"{nps.get('promoters', 0)} ({nps.get('promoter_pct', 0):.1f}%)"
            )
            col3.metric("Passives", nps.get("passives", 0))
            col4.metric(
                "Detractors", f"{nps.get('detractors', 0)} ({nps.get('detractor_pct', 0):.1f}%)"
            )
            st.metric("Avg Score", nps.get("avg_score", 0))
            if nps.get("top_praise_tags"):
                st.write(
                    "**Top Praise Tags:**",
                    ", ".join(f"{t[0]} ({t[1]})" for t in nps["top_praise_tags"]),
                )
            if nps.get("top_complaint_tags"):
                st.write(
                    "**Top Complaint Tags:**",
                    ", ".join(f"{t[0]} ({t[1]})" for t in nps["top_complaint_tags"]),
                )
        else:
            st.info("No NPS responses yet. Customers can submit via the storefront NPS widget.")

        ok_nl, nl_res = api_request("GET", f"/api/loyalty/{biz_id}/nps")
        if ok_nl and nl_res and nl_res.get("surveys"):
            st.subheader("Recent Survey Responses")
            st.dataframe(
                pd.DataFrame(nl_res["surveys"])[
                    ["score", "category", "customer_email", "feedback", "source"]
                ],
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("Submit Test NPS Survey")
        with st.form("nps_test_form"):
            n1, n2 = st.columns(2)
            nps_email = n1.text_input("Customer Email *")
            nps_score = n2.number_input("Score (0–10) *", min_value=0, max_value=10, value=8)
            nps_feedback = st.text_area("Feedback (optional)")
            if st.form_submit_button("Submit NPS", type="primary"):
                if nps_email:
                    ok_ns, ns_res = api_request(
                        "POST",
                        f"/api/loyalty/{biz_id}/nps",
                        json_body={
                            "customer_email": nps_email,
                            "score": int(nps_score),
                            "feedback": nps_feedback or None,
                            "source": "dashboard",
                        },
                    )
                    if ok_ns:
                        st.success(
                            f"Category: **{ns_res.get('category', '?').upper()}** | {ns_res.get('follow_up_suggestion', '')}"
                        )
                    else:
                        st.error(ns_res)
                else:
                    st.warning("Email required.")

    with tab_gc:
        st.subheader("Issued Gift Cards")
        ok_glist, glist_res = api_request("GET", f"/api/loyalty/{biz_id}/gift-cards")
        if ok_glist and glist_res and glist_res.get("gift_cards"):
            st.dataframe(
                pd.DataFrame(glist_res["gift_cards"])[
                    ["code", "initial_amount", "remaining_amount", "recipient_name", "status"]
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No gift cards issued yet.")

        st.subheader("Issue a Digital Gift Card")
        with st.form("gc_issue_form"):
            gc1, gc2 = st.columns(2)
            gc_amount = gc1.number_input(
                "Amount ($) *", min_value=1.0, max_value=10000.0, value=50.0
            )
            gc_expires = gc2.number_input(
                "Expires In (days)", min_value=1, max_value=1825, value=365
            )
            gc3, gc4 = st.columns(2)
            gc_recipient_email = gc3.text_input("Recipient Email")
            gc_recipient_name = gc4.text_input("Recipient Name")
            gc_sender_email = gc3.text_input("Sender Email")
            gc_message = st.text_area("Personal Message", max_chars=1000)
            if st.form_submit_button("Issue Gift Card 🎁", type="primary"):
                ok_gc, gc_res = api_request(
                    "POST",
                    f"/api/loyalty/{biz_id}/gift-cards",
                    json_body={
                        "amount": float(gc_amount),
                        "recipient_email": gc_recipient_email or None,
                        "recipient_name": gc_recipient_name or None,
                        "sender_email": gc_sender_email or None,
                        "message": gc_message or None,
                        "expires_days": int(gc_expires),
                    },
                )
                if ok_gc:
                    st.success(
                        f"✅ Gift Card Issued! Code: **{gc_res.get('code')}** | Amount: ${gc_res.get('amount')} | Expires: {gc_res.get('expires_at', '')[:10]}"
                    )
                else:
                    st.error(gc_res)

        gc_col1, gc_col2 = st.columns(2)
        with gc_col1:
            st.subheader("Look Up Gift Card")
            gc_lookup_code = st.text_input("Gift Card Code", placeholder="XXXX-XXXX-XXXX-XXXX")
            if st.button("Check Balance"):
                if gc_lookup_code:
                    ok_gcl, gcl_res = api_request(
                        "GET", f"/api/loyalty/{biz_id}/gift-cards/{gc_lookup_code.strip().upper()}"
                    )
                    if ok_gcl:
                        st.info(
                            f"Code: **{gcl_res.get('code')}** | Remaining: **${gcl_res.get('remaining_amount')}** | Status: {gcl_res.get('status')}"
                        )
                    else:
                        st.error(gcl_res)
                else:
                    st.warning("Enter a gift card code.")
        with gc_col2:
            st.subheader("Redeem Gift Card")
            with st.form("gc_redeem_form"):
                gcr_code = st.text_input("Code to Redeem *", placeholder="XXXX-XXXX-XXXX-XXXX")
                gcr_amt = st.number_input(
                    "Redeem Amount ($)", min_value=0.5, max_value=10000.0, value=10.0
                )
                if st.form_submit_button("Apply Gift Card"):
                    if gcr_code.strip():
                        ok_gcr, gcr_res = api_request(
                            "POST",
                            f"/api/loyalty/{biz_id}/gift-cards/redeem",
                            json_body={"code": gcr_code.strip().upper(), "amount": float(gcr_amt)},
                        )
                        if ok_gcr:
                            st.success(
                                f"Applied ${gcr_amt:.2f}! Remaining: ${gcr_res.get('remaining_balance', 0):.2f} ({gcr_res.get('status')})"
                            )
                        else:
                            st.error(gcr_res)
                    else:
                        st.warning("Enter a valid gift card code.")


elif page == "📧 Email Campaigns" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Email Campaigns & Newsletter Studio")

    tab_create, tab_analytics = st.tabs(["✍️ Create & Manage Campaigns", "📊 Analytics"])

    with tab_create:
        st.subheader("Existing Campaigns")
        ok_clist, clist = api_request("GET", f"/api/loyalty/{biz_id}/email-campaigns")
        if ok_clist and clist and clist.get("campaigns"):
            st.dataframe(
                pd.DataFrame(clist["campaigns"])[
                    [
                        "id",
                        "name",
                        "campaign_type",
                        "target_segment",
                        "status",
                        "recipient_count",
                        "open_count",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("New Email Campaign")
        with st.form("email_campaign_form"):
            camp_name = st.text_input("Campaign Name *", placeholder="November Newsletter")
            ec1, ec2 = st.columns(2)
            camp_type = ec1.selectbox(
                "Campaign Type", ["newsletter", "promotional", "reengagement", "announcement"]
            )
            camp_segment = ec2.selectbox("Target Segment", ["all", "loyal", "new", "vip"])
            camp_subject = st.text_input("Subject Line (leave blank to auto-generate)")
            camp_body = st.text_area("Email Body HTML (leave blank to auto-generate)", height=150)
            camp_schedule = st.text_input("Schedule (ISO datetime, leave blank to save as draft)")
            submitted = st.form_submit_button("Create Campaign", type="primary")
            if submitted:
                payload = {
                    "name": camp_name,
                    "campaign_type": camp_type,
                    "target_segment": camp_segment,
                    "subject": camp_subject or None,
                    "body_html": camp_body or None,
                    "scheduled_at": camp_schedule or None,
                }
                ok_cc, cc_res = api_request(
                    "POST", f"/api/loyalty/{biz_id}/email-campaigns", json_body=payload
                )
                if ok_cc:
                    st.success(
                        f"✅ Campaign '{cc_res.get('name')}' created (ID #{cc_res.get('id')}) — Status: {cc_res.get('status')}"
                    )
                    st.write("**Subject:**", cc_res.get("subject"))
                    st.markdown(
                        f"[🔗 Open HTML Email Preview]({API_BASE_URL}{cc_res.get('preview_url', '')})"
                    )
                else:
                    st.error(cc_res)

        st.subheader("Send a Campaign")
        camp_id_send = st.number_input("Campaign ID to Send", min_value=1, step=1)
        if st.button("🚀 Send Now", type="primary"):
            ok_cs, cs_res = api_request(
                "POST", f"/api/loyalty/{biz_id}/email-campaigns/{int(camp_id_send)}/send"
            )
            if ok_cs:
                st.success(
                    f"Sent to **{cs_res.get('recipient_count')}** recipients | Opens: {cs_res.get('open_count')} | Clicks: {cs_res.get('click_count')}"
                )
            else:
                st.error(cs_res)

    with tab_analytics:
        st.subheader("Campaign Performance Analytics")
        ok_ca, ca = api_request("GET", f"/api/loyalty/{biz_id}/email-campaigns/analytics")
        if ok_ca and ca:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Campaigns", ca.get("total_campaigns", 0))
            col2.metric("Sent", ca.get("sent_campaigns", 0))
            col3.metric("Avg Open Rate", f"{ca.get('avg_open_rate_pct', 0):.1f}%")
            col4.metric("Avg Click Rate", f"{ca.get('avg_click_rate_pct', 0):.1f}%")
            by_type = ca.get("by_type", {})
            if any(v > 0 for v in by_type.values()):
                type_df = pd.DataFrame(list(by_type.items()), columns=["Type", "Count"])
                type_df = type_df[type_df["Count"] > 0]
                st.bar_chart(type_df.set_index("Type"))
        else:
            st.info("No campaigns sent yet.")


elif page == "📆 Content Calendar" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "AI Content Calendar & Social Planner")

    tab_gen, tab_view = st.tabs(["🤖 Generate Calendar", "📋 View & Promote Calendar"])

    with tab_gen:
        st.subheader("AI-Generate a Multi-Platform Content Calendar")
        with st.form("content_cal_form"):
            cg1, cg2 = st.columns(2)
            cal_days = cg1.number_input("Days Ahead", min_value=1, max_value=90, value=7)
            all_platforms = ["instagram", "facebook", "twitter", "email"]
            cal_platforms = st.multiselect(
                "Platforms", all_platforms, default=["instagram", "facebook"]
            )
            if st.form_submit_button("⚡ Generate Calendar", type="primary"):
                if not cal_platforms:
                    st.warning("Select at least one platform.")
                else:
                    ok_cg, cg_res = api_request(
                        "POST",
                        f"/api/loyalty/{biz_id}/content-calendar/generate",
                        json_body={"days_ahead": int(cal_days), "platforms": cal_platforms},
                    )
                    if ok_cg:
                        st.success(
                            f"Generated **{cg_res.get('calendar_entries', 0)}** content entries across {cal_days} days for {', '.join(cal_platforms)}!"
                        )
                        entries = cg_res.get("entries", [])
                        for entry in entries[:6]:
                            with st.expander(
                                f"#{entry.get('id')} | {entry.get('date')} | {entry.get('platform').upper()} | {entry.get('occasion')} (Confidence: {entry.get('confidence', 0):.0%})"
                            ):
                                st.write(entry.get("preview"))
                                st.write("**Hashtags:**", " ".join(entry.get("hashtags", [])))
                    else:
                        st.error(cg_res)

    with tab_view:
        st.subheader("Saved Content Calendar")
        plat_filter = st.selectbox(
            "Filter by Platform", ["All", "instagram", "facebook", "twitter", "email"]
        )
        plat_param = None if plat_filter == "All" else plat_filter
        url = f"/api/loyalty/{biz_id}/content-calendar"
        if plat_param:
            url += f"?platform={plat_param}"
        ok_cv, cv_res = api_request("GET", url)
        if ok_cv and cv_res and cv_res.get("entries"):
            entries = cv_res["entries"]
            st.caption(f"{cv_res.get('total', 0)} entries found")
            cal_df = pd.DataFrame(
                [
                    {
                        "ID": e.get("id"),
                        "Date": e.get("scheduled_date"),
                        "Platform": e.get("platform"),
                        "Type": e.get("content_type"),
                        "Occasion": e.get("occasion"),
                        "Status": e.get("status"),
                        "Confidence": f"{e.get('ai_confidence_score', 0):.0%}",
                        "Preview": e.get("draft_content", "")[:80] + "...",
                    }
                    for e in entries
                ]
            )
            st.dataframe(cal_df, use_container_width=True, hide_index=True)

            pr_col1, pr_col2 = st.columns([1.2, 1.0])
            promo_entry_id = pr_col1.number_input(
                "Entry ID to Promote to Social Post", min_value=1, step=1
            )
            promo_pub = pr_col2.checkbox("Publish Immediately", value=False)
            if st.button("📣 Promote Entry to Social Queue"):
                ok_pr, pr_res = api_request(
                    "POST",
                    f"/api/loyalty/{biz_id}/content-calendar/{int(promo_entry_id)}/promote",
                    json_body={"auto_publish": promo_pub},
                )
                if ok_pr:
                    st.success(
                        f"Promoted entry #{promo_entry_id} -> SocialPost #{pr_res.get('social_post_id')} ({pr_res.get('social_status')})!"
                    )
                else:
                    st.error(pr_res)
        else:
            st.info("No content calendar entries yet. Use the Generate tab to create them.")


# PAGE 9: Customer Storefront & Catalog
# ---------------------------------------------------------------------------

elif page == "🌐 Customer Storefront" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Public Customer Storefront & Menu / Services Catalog")

    store_url = f"{API_BASE_URL}/site/{biz_id}"
    menu_url = f"{API_BASE_URL}/site/{biz_id}/menu"
    poster_url = f"{API_BASE_URL}/site/{biz_id}/poster"
    qr_url = f"{API_BASE_URL}/site/{biz_id}/qr"
    st.success(
        f"🌐 **Your Live Customer Booking, Order & Review Page:** [{store_url}]({store_url})"
    )
    st.markdown(
        f"📋 **Printable Digital Menu:** [{menu_url}]({menu_url}) &nbsp;|&nbsp; "
        f"🖨️ **Printable Counter QR Poster:** [{poster_url}]({poster_url}) &nbsp;|&nbsp; "
        f"📱 **QR Code (SVG):** [{qr_url}]({qr_url})"
    )
    st.caption(
        "Print the QR poster for your counter or share the storefront link on WhatsApp & Instagram Bio."
    )

    ok_cfg, cfg = api_request("GET", f"/api/agent/{biz_id}/autopilot")
    if ok_cfg:
        st.subheader("🛍️ Menu & Services Shown on Your Public Page")
        items = list(cfg.get("catalog_items") or [])
        for it in items:
            st.markdown(
                f"- **{it.get('name')}** — `${float(it.get('price', 0)):.2f}` ({it.get('description', '')})"
            )

        with st.form("add_catalog_item_form"):
            st.markdown("**➕ Add a New Service or Product**")
            ac1, ac2 = st.columns([2, 1])
            it_name = ac1.text_input(
                "Item / Service Name*", placeholder="e.g., Truffle Pizza or Express Haircut"
            )
            it_price = ac2.number_input("Price ($)", min_value=0.0, value=20.0, step=1.0)
            it_desc = st.text_input(
                "Short Description", placeholder="Freshly prepared / 30-min session"
            )
            if st.form_submit_button("Add to Storefront", type="primary"):
                if not it_name.strip():
                    st.warning("Item name is required.")
                else:
                    items.append(
                        {
                            "name": it_name.strip(),
                            "price": float(it_price),
                            "description": it_desc.strip(),
                        }
                    )
                    ok_u, res_u = api_request(
                        "PUT",
                        f"/api/agent/{biz_id}/autopilot",
                        json_body={"catalog_items": items},
                    )
                    if ok_u:
                        st.success("Added to your public storefront!")
                        st.rerun()
                    else:
                        st.error(res_u)


# ---------------------------------------------------------------------------
# PAGE 8: Settings
# ---------------------------------------------------------------------------

elif page == "⚙️ Settings":
    if selected_business:
        render_header(selected_business, "Business Profile, Google Setup & API Keys")
    else:
        st.title("⚙️ Business Setup & Settings")

    tabs = st.tabs(
        [
            "🏢 Business Profile",
            "📍 Google Business Profile",
            "🔑 API Keys",
            "➕ Register New Business",
        ]
    )

    with tabs[0]:
        if selected_business:
            with st.form("edit_business_form"):
                c1, c2 = st.columns(2)
                name = c1.text_input("Business Name", value=selected_business.get("name", ""))
                category = c2.text_input("Category", value=selected_business.get("category", ""))
                description = st.text_area(
                    "Description", value=selected_business.get("description") or ""
                )
                address = c1.text_input("Address", value=selected_business.get("address") or "")
                city = c2.text_input("City", value=selected_business.get("city") or "")
                state = c1.text_input("State", value=selected_business.get("state") or "")
                zip_code = c2.text_input("ZIP Code", value=selected_business.get("zip_code") or "")
                phone = c1.text_input("Phone", value=selected_business.get("phone") or "")
                email = c2.text_input("Email", value=selected_business.get("email") or "")
                website = st.text_input("Website", value=selected_business.get("website") or "")

                if st.form_submit_button("Save Business Profile", type="primary"):
                    ok_upd, upd_res = api_request(
                        "PUT",
                        f"/api/businesses/{selected_business['id']}",
                        json_body={
                            "name": name,
                            "category": category,
                            "description": description,
                            "address": address,
                            "city": city,
                            "state": state,
                            "zip_code": zip_code,
                            "phone": phone,
                            "email": email,
                            "website": website,
                        },
                    )
                    if ok_upd:
                        st.success("Business profile updated!")
                        st.rerun()
                    else:
                        st.error(upd_res)
        else:
            st.info("Select or register a business first.")

    with tabs[1]:
        if selected_business:
            gbp_id_current = selected_business.get("google_business_id")
            st.write(
                f"Current Status: {status_badge('verified' if gbp_id_current else 'not_configured')}",
                unsafe_allow_html=True,
            )
            st.write(f"Google Business ID: `{gbp_id_current or 'Not linked'}`")

            with st.form("gbp_setup_form"):
                gbp_id = st.text_input(
                    "Google Business / Place ID (leave blank to auto-provision)",
                    value=gbp_id_current or "",
                )
                prim_cat = st.text_input(
                    "Primary Google Category",
                    value=selected_business.get("category", ""),
                )
                service_area = st.text_input(
                    "Service Area",
                    value=", ".join(
                        p
                        for p in (selected_business.get("city"), selected_business.get("state"))
                        if p
                    ),
                )
                attrs_raw = st.text_input(
                    "Attributes (comma-separated)",
                    value="Online booking, Wheelchair accessible, Free Wi-Fi",
                )
                verify_now = st.checkbox("Verify immediately", value=True)
                if st.form_submit_button("Setup Google Business Profile", type="primary"):
                    attrs = [a.strip() for a in attrs_raw.split(",") if a.strip()]
                    ok_gbp, gbp_res = api_request(
                        "POST",
                        f"/api/businesses/{selected_business['id']}/setup-google",
                        json_body={
                            "google_business_id": gbp_id.strip() or None,
                            "primary_category": prim_cat.strip() or None,
                            "attributes": attrs,
                            "service_area": service_area,
                            "verify_now": verify_now,
                        },
                    )
                    if ok_gbp:
                        st.success(
                            f"Google Business Profile status: **{gbp_res['status']}** "
                            f"(Completeness: {gbp_res['completeness_score']}%)"
                        )
                        st.json(gbp_res["checklist"])
                    else:
                        st.error(gbp_res)

    with tabs[2]:
        overrides = st.session_state["api_overrides"]
        with st.form("api_keys_form"):
            st.caption("Session-scoped LLM API keys forwarded to the LangGraph Supervisor.")
            gem_key = st.text_input(
                "Google Gemini API Key (optional)",
                value=overrides.get("gemini_api_key", ""),
                type="password",
            )
            openai_key = st.text_input(
                "OpenAI API Key (optional)",
                value=overrides.get("openai_api_key", ""),
                type="password",
            )
            anth_key = st.text_input(
                "Anthropic API Key (optional)",
                value=overrides.get("anthropic_api_key", ""),
                type="password",
            )
            if st.form_submit_button("Save API Keys", type="primary"):
                st.session_state["api_overrides"] = {
                    "gemini_api_key": gem_key.strip(),
                    "openai_api_key": openai_key.strip(),
                    "anthropic_api_key": anth_key.strip(),
                }
                st.success("API key overrides saved for this session!")

    with tabs[3], st.form("register_business_form"):
        rc1, rc2 = st.columns(2)
        new_name = rc1.text_input("Business Name*")
        new_cat = rc2.selectbox(
            "Category",
            ["restaurant", "salon", "fitness", "retail", "medical", "automotive", "general"],
        )
        new_desc = st.text_area("Description", placeholder="What makes your business unique?")
        new_addr = rc1.text_input("Street Address")
        new_city = rc2.text_input("City")
        new_state = rc1.text_input("State")
        new_phone = rc2.text_input("Phone")
        new_email = rc1.text_input("Email")
        new_web = rc2.text_input("Website")

        if st.form_submit_button("Register Business", type="primary"):
            if not new_name.strip():
                st.warning("Business name is required.")
            else:
                ok_reg, reg_res = api_request(
                    "POST",
                    "/api/businesses/",
                    json_body={
                        "name": new_name.strip(),
                        "category": new_cat,
                        "description": new_desc or None,
                        "address": new_addr or None,
                        "city": new_city or None,
                        "state": new_state or None,
                        "phone": new_phone or None,
                        "email": new_email or None,
                        "website": new_web or None,
                    },
                )
                if ok_reg:
                    st.success(f"Registered **{reg_res['name']}** (ID #{reg_res['id']})!")
                    st.rerun()
                else:
                    st.error(reg_res)
