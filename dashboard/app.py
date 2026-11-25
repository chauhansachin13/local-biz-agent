"""BizPresence AI — Comprehensive Streamlit Dashboard."""

from __future__ import annotations

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
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        color: #ffffff;
        padding: 1.25rem 1.5rem;
        border-radius: 14px;
        margin-bottom: 1.25rem;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.12);
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
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.04);
    }
    .activity-card {
        background: #ffffff;
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
    timeout: float = 20.0,
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
        "scheduled": "badge-scheduled",
        "pending": "badge-neutral",
        "draft": "badge-draft",
        "cancelled": "badge-negative",
        "verified": "badge-positive",
    }.get(low, "badge-info")
    return f'<span class="badge {cls}">{low}</span>'


def render_header(business: dict[str, Any], subtitle: str) -> None:
    loc = ", ".join(p for p in (business.get("city"), business.get("state")) if p)
    loc_part = f" • {loc}" if loc else ""
    st.markdown(
        f"""
        <div class="biz-header">
            <h1>🏪 {business["name"]}</h1>
            <p>{business.get("category", "").title()}{loc_part} — {subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Sidebar: Health, Business Selector, Navigation
# ---------------------------------------------------------------------------

if "api_overrides" not in st.session_state:
    st.session_state["api_overrides"] = {}

with st.sidebar:
    st.markdown("## 🤖 BizPresence AI")
    st.caption("Local Business Digital Presence Agent")

    healthy, _health_data = api_request("GET", "/health", timeout=5.0)
    if healthy:
        st.success("API Connected", icon="🟢")
    else:
        st.error("API Disconnected", icon="🔴")

    ok_biz, businesses_data = api_request("GET", "/api/businesses/")
    businesses: list[dict[str, Any]] = (
        businesses_data if ok_biz and isinstance(businesses_data, list) else []
    )

    selected_business: dict[str, Any] | None = None
    if businesses:
        biz_labels = {f"{b['name']} ({b['category'].title()})": b for b in businesses}
        chosen_label = st.selectbox(
            "Select Business",
            options=list(biz_labels.keys()),
            key="selected_business_label",
        )
        selected_business = biz_labels[chosen_label]
        gbp_badge = "Verified" if selected_business.get("google_business_id") else "Not Configured"
        st.caption(f"Google Profile: **{gbp_badge}**")
    else:
        st.warning("No businesses found. Register one in Settings or run seed_data.py.")

    st.divider()
    page = st.radio(
        "Navigation",
        options=[
            "Dashboard Overview",
            "Social Media",
            "Reviews",
            "Bookings",
            "AI Assistant",
            "Settings",
        ],
        index=0,
    )
    st.divider()
    st.caption(f"Backend: `{API_BASE_URL}`")


if selected_business is None and page != "Settings":
    st.title("Welcome to BizPresence AI")
    st.info(
        "No businesses are registered yet. Open **Settings** to create your first business "
        "or run `python scripts/seed_data.py` to load sample data."
    )
    st.stop()


# ---------------------------------------------------------------------------
# PAGE 1: Dashboard Overview
# ---------------------------------------------------------------------------

if page == "Dashboard Overview" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Digital Presence Overview")

    ok, overview = api_request("GET", f"/api/businesses/{biz_id}/dashboard")
    if not ok:
        st.error(overview)
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "Total Reviews",
            overview["total_reviews"],
            delta=f"{overview['pending_reviews']} pending reply",
            delta_color="inverse" if overview["pending_reviews"] > 0 else "normal",
        )
    with c2:
        st.metric(
            "Average Rating",
            f"{overview['average_rating']:.2f} ★",
            delta=f"GBP: {overview['google_profile_status']}",
        )
    with c3:
        st.metric(
            "Posts This Week",
            overview["posts_this_week"],
            delta=f"{overview['scheduled_posts']} scheduled",
        )
    with c4:
        st.metric(
            "Upcoming Bookings",
            overview["upcoming_bookings"],
            delta=f"{overview['bookings_today']} today",
        )

    st.markdown("")
    left_col, right_col = st.columns([1.4, 1.0])

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
        st.subheader("💡 AI Priority Suggestions")
        ok_sug, sug_data = api_request("GET", f"/api/agent/{biz_id}/suggestions")
        if ok_sug and sug_data.get("suggestions"):
            for sug in sug_data["suggestions"]:
                prio_color = {
                    "high": "#dc2626",
                    "medium": "#d97706",
                    "low": "#2563eb",
                }.get(sug["priority"], "#475569")
                st.markdown(
                    f"""
                    <div class="suggestion-card">
                        <span style="color:{prio_color}; font-weight:700; font-size:0.75rem; text-transform:uppercase;">
                            ● {sug["priority"]} priority • {sug["category"]}
                        </span>
                        <div style="font-weight:600; font-size:1rem; margin:0.25rem 0;">
                            {sug["title"]}
                        </div>
                        <div style="color:#475569; font-size:0.86rem;">
                            {sug["description"]}
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
                    else:
                        st.error(run_res)
        else:
            st.info("No AI suggestions right now.")


# ---------------------------------------------------------------------------
# PAGE 2: Social Media
# ---------------------------------------------------------------------------

elif page == "Social Media" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Social Media Studio & Content Calendar")

    tab_compose, tab_calendar, tab_history = st.tabs(
        ["✍️ Post Composer", "🗓️ Content Calendar", "📊 Post History & Engagement"]
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

            if st.button("✨ AI Assist — Generate Copy & Hashtags", use_container_width=True):
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

            content_text = st.text_area(
                "Post Content",
                value=st.session_state.get("draft_content", ""),
                height=150,
                placeholder="Write your post or click AI Assist above...",
            )
            image_url = st.text_input(
                "Image URL (optional)",
                placeholder="https://example.com/photo.jpg",
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
                    <div style="display:flex; justify-content:space-between;">
                        <strong>{selected_business["name"]}</strong>
                        <span class="badge badge-info">{platform}</span>
                    </div>
                    <p style="margin-top:0.8rem; white-space:pre-wrap; color:#1e293b;">
                        {content_text or "Your post preview will appear here..."}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.session_state.get("draft_best_time"):
                st.info(f"⏰ Recommended time: **{st.session_state['draft_best_time']}**")
            if st.session_state.get("draft_image_prompt"):
                st.caption(f"🎨 Visual prompt: {st.session_state['draft_image_prompt']}")

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
                                f"<div style='background:#f8fafc; border-radius:6px; padding:4px 6px; "
                                f"margin-bottom:4px; font-size:0.75rem;'>"
                                f"<strong>{p['platform'].title()}</strong> ({p['status']})<br/>{snippet}</div>"
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
                            <strong>{p["platform"].title()}</strong>
                            {status_badge(p["status"])}
                        </div>
                        <p style="margin:0.55rem 0; color:#1e293b; white-space:pre-wrap;">{p["content"]}</p>
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
# PAGE 3: Reviews
# ---------------------------------------------------------------------------

elif page == "Reviews" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Customer Reviews & Reputation Management")

    tab_feed, tab_analytics = st.tabs(["💬 Review Feed & AI Replies", "📈 Review Analytics"])

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
                                <strong>{rev["reviewer_name"]}</strong>
                                <span style="color:#f59e0b; margin-left:0.5rem;">{stars} ({rev["rating"]}/5)</span>
                                <span style="color:#64748b; font-size:0.82rem;"> • {rev["platform"].title()}</span>
                            </div>
                            <div>
                                {sentiment_badge(rev.get("sentiment"))}
                                {status_badge(rev["response_status"])}
                            </div>
                        </div>
                        <p style="margin:0.5rem 0; color:#1e293b;">{rev.get("review_text") or ""}</p>
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


# ---------------------------------------------------------------------------
# PAGE 4: Bookings
# ---------------------------------------------------------------------------

elif page == "Bookings" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "Bookings, Calendar & Availability")

    ok_bk, bookings = api_request("GET", f"/api/bookings/{biz_id}/bookings")
    bookings_list = bookings if ok_bk and isinstance(bookings, list) else []

    today = date.today()
    week_end = today + timedelta(days=7)
    today_count = sum(
        1
        for b in bookings_list
        if b["booking_date"] == today.isoformat() and b["status"] != "cancelled"
    )
    week_count = sum(
        1
        for b in bookings_list
        if today.isoformat() <= b["booking_date"] <= week_end.isoformat()
        and b["status"] != "cancelled"
    )
    confirmed_count = sum(1 for b in bookings_list if b["status"] == "confirmed")

    b1, b2, b3 = st.columns(3)
    b1.metric("Bookings Today", today_count)
    b2.metric("Next 7 Days", week_count)
    b3.metric("Total Confirmed", confirmed_count)

    tab_cal, tab_new, tab_avail = st.tabs(
        ["📅 Bookings Schedule", "➕ New Booking", "🕒 Check Availability"]
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


# ---------------------------------------------------------------------------
# PAGE 5: AI Assistant
# ---------------------------------------------------------------------------

elif page == "AI Assistant" and selected_business:
    biz_id = selected_business["id"]
    render_header(selected_business, "BizPresence AI Orchestrator")

    chat_key = f"chat_history_{biz_id}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = [
            {
                "role": "assistant",
                "content": (
                    f"Hi! I'm **BizPresence AI**, your digital presence assistant for "
                    f"**{selected_business['name']}**. Ask me to create social posts, draft or "
                    "auto-respond to reviews, check bookings, or summarize your performance."
                ),
            }
        ]

    st.caption("Quick Prompts:")
    qp1, qp2, qp3, qp4 = st.columns(4)
    quick_prompts = [
        (qp1, "📊 Performance Summary", "Give me a summary of our performance"),
        (
            qp2,
            "📸 Create Instagram Post",
            "Create and schedule an Instagram post about our weekend special",
        ),
        (qp3, "⭐ Draft Review Replies", "Draft responses for all pending reviews"),
        (qp4, "📅 Today's Bookings", "Show upcoming bookings and today's open slots"),
    ]
    triggered_prompt: str | None = None
    for col, label, prompt_text in quick_prompts:
        if col.button(label, use_container_width=True):
            triggered_prompt = prompt_text

    auto_exec = st.toggle(
        "Allow AI to execute actions automatically (create posts / send replies)",
        value=True,
    )

    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input(f"Ask BizPresence AI about {selected_business['name']}...")
    prompt_to_send = triggered_prompt or user_input

    if prompt_to_send:
        st.session_state[chat_key].append({"role": "user", "content": prompt_to_send})
        with st.chat_message("user"):
            st.markdown(prompt_to_send)

        with st.chat_message("assistant"):
            with st.spinner("BizPresence AI is thinking..."):
                ok_chat, chat_res = api_request(
                    "POST",
                    f"/api/agent/{biz_id}/chat",
                    json_body={
                        "message": prompt_to_send,
                        "auto_execute": auto_exec,
                        "context": st.session_state["api_overrides"],
                    },
                )
            if ok_chat:
                reply_text = chat_res["reply"]
                if chat_res.get("actions_taken"):
                    reply_text += "\n\n**Actions Executed:** " + ", ".join(
                        chat_res["actions_taken"]
                    )
                st.markdown(reply_text)
                st.session_state[chat_key].append({"role": "assistant", "content": reply_text})
            else:
                st.error(chat_res)


# ---------------------------------------------------------------------------
# PAGE 6: Settings
# ---------------------------------------------------------------------------

elif page == "Settings":
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
            st.caption("Session-scoped LLM API keys forwarded to the AI Orchestrator.")
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
