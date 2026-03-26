"""
InfrOS Lead Research Tool
=========================
Finds Reddit discussions where cloud/infrastructure practitioners express pain
points that InfrOS solves, then surfaces LinkedIn search queries so you can
manually approach those professionals.

Run with:
    streamlit run app.py
"""

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from src.config_manager import load_config, save_config
from src.reddit_scraper import RedditScraper
from src.analyzer import analyze_post, build_lead_profiles
from src.session_manager import save_session, load_session, autosave as _disk_autosave
from src.report_generator import generate_report
from src.roadmap_validator import validate_roadmap, generate_roadmap_report

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="InfrOS Lead Finder",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session-state initialisation
# ---------------------------------------------------------------------------

if "config" not in st.session_state:
    st.session_state.config = load_config()
if "raw_posts" not in st.session_state:
    st.session_state.raw_posts = []
if "analyzed_posts" not in st.session_state:
    st.session_state.analyzed_posts = []
if "lead_profiles" not in st.session_state:
    st.session_state.lead_profiles = []
if "_prev_page" not in st.session_state:
    st.session_state._prev_page = None
if "last_autosave_at" not in st.session_state:
    st.session_state.last_autosave_at = None
if "last_manual_save_at" not in st.session_state:
    st.session_state.last_manual_save_at = None
if "_session_metadata" not in st.session_state:
    st.session_state._session_metadata = {}
if "_loaded_session_name" not in st.session_state:
    st.session_state._loaded_session_name = None
if "_generated_report" not in st.session_state:
    st.session_state._generated_report = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mark_manual_save():
    st.session_state.last_manual_save_at = datetime.now()


def _do_autosave():
    _disk_autosave(
        st.session_state.raw_posts,
        st.session_state.analyzed_posts,
        st.session_state.lead_profiles,
    )
    st.session_state.last_autosave_at = datetime.now()


def _session_json() -> str:
    return save_session(
        st.session_state.raw_posts,
        st.session_state.analyzed_posts,
        st.session_state.lead_profiles,
        st.session_state._session_metadata,
    )


def _autosave_label() -> str:
    ts = st.session_state.last_autosave_at
    if ts is None:
        return ""
    delta = int((datetime.now() - ts).total_seconds())
    if delta < 60:
        return "Auto-saved just now"
    return f"Auto-saved {delta // 60} min ago"


# ---------------------------------------------------------------------------
# Sidebar — navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🔍 InfrOS Lead Finder")
    st.markdown("*Find cloud practitioners experiencing pain InfrOS can solve.*")
    st.divider()

    page = st.radio(
        "Navigate",
        ["Search & Discover", "Lead Profiles", "Report", "Roadmap Validator", "Settings"],
        format_func=lambda x: {
            "Search & Discover": "🔎 Search & Discover",
            "Lead Profiles": "📊 Lead Profiles",
            "Report": "📋 Report",
            "Roadmap Validator": "🗺️ Roadmap Validator",
            "Settings": "⚙️ Settings",
        }[x],
    )

    st.divider()
    cfg = st.session_state.config
    using_api = bool(cfg["reddit"]["api"].get("client_id", "").strip())
    st.caption(f"**Reddit:** {'🔑 API (authenticated)' if using_api else '🌐 Public scraping'}")
    if st.session_state.analyzed_posts:
        st.caption(
            f"**Posts found:** {len(st.session_state.analyzed_posts)}  \n"
            f"**Lead profiles:** {len(st.session_state.lead_profiles)}"
        )

    # ---- Session save / load ------------------------------------------------
    st.divider()
    st.markdown("### 💾 Session")

    has_results = bool(st.session_state.analyzed_posts)

    if has_results:
        fname = f"infros_session_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        _sidebar_saved = st.download_button(
            "⬇️ Save session",
            data=_session_json(),
            file_name=fname,
            mime="application/json",
            use_container_width=True,
            help="Download the full session as JSON so you can reload it later.",
        )
        if _sidebar_saved:
            _mark_manual_save()
        label = _autosave_label()
        if label:
            st.caption(label)
        elif st.session_state.last_manual_save_at is None:
            st.caption("⚠️ Not yet saved")
    else:
        st.caption("Run a search to enable session saving.")

    st.markdown("**📂 Load session**")
    uploaded = st.file_uploader(
        "Load session file",
        type=["json"],
        key="session_upload",
        label_visibility="collapsed",
        help="Upload a previously saved InfrOS session JSON file.",
    )
    if uploaded is not None and uploaded.name != st.session_state._loaded_session_name:
        try:
            raw, analyzed, profiles, meta, saved_at = load_session(uploaded.read())
            st.session_state.raw_posts = raw
            st.session_state.analyzed_posts = analyzed
            st.session_state.lead_profiles = profiles
            st.session_state._session_metadata = meta
            st.session_state.last_manual_save_at = datetime.now()
            st.session_state._generated_report = None
            st.session_state._loaded_session_name = uploaded.name
            st.success(f"Session loaded ({saved_at[:10]})", icon="✅")
        except (ValueError, KeyError) as exc:
            st.error(f"Could not load session: {exc}")


# ---------------------------------------------------------------------------
# Auto-save on page navigation
# ---------------------------------------------------------------------------

_prev = st.session_state._prev_page
if _prev is not None and _prev != page and st.session_state.analyzed_posts:
    _do_autosave()
st.session_state._prev_page = page


# ===========================================================================
# Helpers — card renderers
# ===========================================================================

def _render_profile_card(profile: dict, idx: int):
    role = profile["role"]
    cloud = profile["cloud_platform"]
    count = profile["post_count"]
    pain_count = profile["post_type_counts"].get("pain", 0)

    eval_count = profile.get("post_type_counts", {}).get("evaluation", 0)
    buying_count = profile.get("buying_signal_count", 0)
    competitors = profile.get("competitors_seen", [])
    label_parts = [f"{count} posts", f"{pain_count} pain"]
    if eval_count:
        label_parts.append(f"{eval_count} evaluation")
    if buying_count:
        label_parts.append(f"⚡ {buying_count} buying signals")
    with st.expander(
        f"**{role}** · {cloud}  —  {', '.join(label_parts)}",
        expanded=(idx == 0),
    ):
        col1, col2 = st.columns([3, 2])

        with col1:
            st.markdown("**Pain points observed:**")
            for summary in profile.get("pain_summaries", [])[:6]:
                st.markdown(f"- {summary}")

            if profile.get("sample_titles"):
                st.markdown("**Sample post titles:**")
                for title in profile["sample_titles"]:
                    st.markdown(f"- *{title}*")

        with col2:
            st.markdown("**Tech stack signals:**")
            if profile.get("tech_stack"):
                st.markdown(" ".join(f"`{t}`" for t in profile["tech_stack"]))

            if profile.get("company_sizes"):
                st.markdown("**Company size signals:**")
                st.markdown(", ".join(profile["company_sizes"]))

            if competitors:
                st.markdown("**Competitors mentioned:**")
                st.markdown(" ".join(f"`{c}`" for c in competitors[:4]))

            if profile.get("linkedin_groups"):
                st.markdown("**LinkedIn Groups:**")
                for g in profile["linkedin_groups"][:3]:
                    st.markdown(f"- {g}")

            st.markdown("**LinkedIn search query:**")
            st.code(profile.get("linkedin_query", ""), language=None)

        st.link_button(
            "🔗 Search LinkedIn →",
            url=profile.get("linkedin_url", "#"),
            use_container_width=True,
        )


def _render_post_card(post: dict):
    rel = post.get("relevance_score", 0)
    post_type = post.get("post_type", "discussion")
    type_emoji = {
        "pain": "🔴", "solution": "🟢", "mixed": "🟡",
        "evaluation": "🔵", "hiring_signal": "🟣", "discussion": "⚪",
    }.get(post_type, "⚪")

    with st.expander(
        f"{type_emoji} [{post.get('subreddit', '')}] {post.get('title', '')[:90]}  "
        f"— relevance: {rel:.0%}",
        expanded=False,
    ):
        col_a, col_b = st.columns([2, 1])

        with col_a:
            if post.get("body"):
                body = post["body"][:400].strip()
                suffix = "…" if len(post.get("body", "")) > 400 else ""
                st.markdown(f"*{body}{suffix}*")

            if post.get("pain_signals"):
                st.markdown("**Pain signals:** " + " · ".join(f"`{s}`" for s in post["pain_signals"]))
            if post.get("solution_signals"):
                st.markdown("**Solution signals:** " + " · ".join(f"`{s}`" for s in post["solution_signals"]))

        with col_b:
            if post.get("roles"):
                st.markdown("**Roles detected:**")
                for r in post["roles"]:
                    st.markdown(f"- {r}")
            if post.get("tech_stack"):
                st.markdown("**Tech stack:**")
                st.markdown(" ".join(f"`{t}`" for t in post["tech_stack"]))
            if post.get("company_size"):
                st.markdown("**Company size:** " + ", ".join(post["company_size"]))

        st.markdown(
            f"👍 {post.get('score', 0)}  💬 {post.get('num_comments', 0)}  "
            f"📅 {post.get('created_date', '')}  "
            f"[View on Reddit ↗]({post.get('url', '')})"
        )


# ===========================================================================
# PAGE: Search & Discover
# ===========================================================================

if page == "Search & Discover":
    st.title("🔎 Search & Discover")
    st.markdown(
        "Search Reddit for cloud/infrastructure pain points that InfrOS solves.  \n"
        "Results are analysed for role signals, tech-stack, and pain indicators."
    )

    # ---- Unsaved-results warning ----
    if (
        st.session_state.analyzed_posts
        and st.session_state.last_manual_save_at is None
    ):
        n = len(st.session_state.analyzed_posts)
        warn_col, btn_col = st.columns([3, 1])
        with warn_col:
            st.warning(
                f"⚠️ You have **{n} unsaved posts**. "
                "Running a new search will overwrite them. Save your session first."
            )
        with btn_col:
            _warn_saved = st.download_button(
                "💾 Save now",
                data=_session_json(),
                file_name=f"infros_session_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
                use_container_width=True,
            )
            if _warn_saved:
                _mark_manual_save()

    cfg = st.session_state.config
    search_cfg = cfg["reddit"]["search"]

    # ---- Search controls ----
    with st.expander("Search options", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Subreddits to search**")
            all_subs = cfg["reddit"]["subreddits"]
            selected_subs = st.multiselect(
                "Subreddits",
                options=all_subs,
                default=all_subs,
                label_visibility="collapsed",
            )

        with col2:
            st.markdown("**Search mode**")
            mode = st.radio(
                "mode",
                ["Use Topics", "Use Keywords", "Custom"],
                label_visibility="collapsed",
            )

        selected_topics: list[str] = []  # populated below when mode == "Use Topics"

        if mode == "Use Topics":
            topic_names = [t["name"] for t in cfg["reddit"]["topics"]]
            selected_topics = st.multiselect(
                "Topics to search",
                options=topic_names,
                default=topic_names,
            )
            active_keywords = []
            for topic in cfg["reddit"]["topics"]:
                if topic["name"] in selected_topics:
                    active_keywords.extend(topic["keywords"])
            active_keywords = list(dict.fromkeys(active_keywords))
            st.caption(f"Will search {len(active_keywords)} keywords from {len(selected_topics)} topics.")

        elif mode == "Use Keywords":
            all_kws = cfg["reddit"]["keywords"]
            active_keywords = st.multiselect(
                "Keywords",
                options=all_kws,
                default=all_kws[:5],
            )

        else:  # Custom
            raw = st.text_area(
                "Enter keywords (one per line)",
                placeholder="cloud costs too high\nterraform state management\nmulti-cloud pain",
            )
            active_keywords = [k.strip() for k in raw.splitlines() if k.strip()]

        col3, col4, col5 = st.columns(3)
        with col3:
            time_filter = st.selectbox(
                "Time range",
                ["day", "week", "month", "year", "all"],
                index=["day", "week", "month", "year", "all"].index(
                    search_cfg.get("time_filter", "month")
                ),
            )
        with col4:
            sort_by = st.selectbox(
                "Sort by",
                ["relevance", "hot", "top", "new", "comments"],
                index=["relevance", "hot", "top", "new", "comments"].index(
                    search_cfg.get("sort", "relevance")
                ),
            )
        with col5:
            min_score = st.number_input(
                "Min upvotes",
                min_value=0,
                value=int(search_cfg.get("min_score", 3)),
                step=1,
            )

    # ---- Run button ----
    can_run = bool(selected_subs) and bool(active_keywords)
    if not can_run:
        st.warning("Select at least one subreddit and one keyword / topic to search.")

    run_col, _ = st.columns([1, 4])
    with run_col:
        run_clicked = st.button("🚀 Run Search", disabled=not can_run, use_container_width=True)

    if run_clicked:
        progress_bar = st.progress(0, text="Starting…")
        status_text = st.empty()

        def _progress(pct: float, msg: str):
            progress_bar.progress(min(pct, 1.0), text=msg)
            status_text.caption(msg)

        scraper = RedditScraper(cfg)
        with st.spinner("Searching Reddit…"):
            raw_posts = scraper.search_posts(
                keywords=active_keywords,
                subreddits=selected_subs,
                time_filter=time_filter,
                sort=sort_by,
                limit=int(search_cfg.get("max_results", 25)),
                min_score=int(min_score),
                progress_callback=_progress,
            )

        progress_bar.progress(1.0, text="Analysing…")
        analyzed = [analyze_post(p) for p in raw_posts]
        analyzed.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)
        lead_profiles = build_lead_profiles(analyzed)

        st.session_state.raw_posts = raw_posts
        st.session_state.analyzed_posts = analyzed
        st.session_state.lead_profiles = lead_profiles
        st.session_state.last_manual_save_at = None   # new results → unsaved again
        st.session_state._generated_report = None     # invalidate cached report
        st.session_state._session_metadata = {
            # When
            "searched_at": datetime.now().isoformat(),
            # What was searched
            "search_mode": mode,
            "subreddits_searched": selected_subs,
            "keywords_searched": active_keywords,
            "topics_selected": selected_topics,
            # Search parameters
            "time_filter": time_filter,
            "sort": sort_by,
            "min_score": int(min_score),
            "max_results_per_query": int(search_cfg.get("max_results", 25)),
            # Result summary
            "total_posts_found": len(analyzed),
            "total_lead_profiles": len(lead_profiles),
            # API info
            "api_mode": "authenticated" if using_api else "public",
        }

        # Auto-save immediately after search so a browser refresh loses nothing
        _do_autosave()

        progress_bar.empty()
        status_text.empty()
        st.success(
            f"Found **{len(analyzed)} posts** → **{len(lead_profiles)} lead profiles**  \n"
            "Session auto-saved. Use **💾 Save session** in the sidebar to download a copy."
        )

    # ---- Results ----
    analyzed_posts = st.session_state.analyzed_posts
    if analyzed_posts:
        st.divider()
        st.markdown(f"### Results  ({len(analyzed_posts)} posts)")

        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            filter_type = st.multiselect(
                "Post type",
                ["pain", "evaluation", "mixed", "hiring_signal", "solution", "discussion"],
                default=["pain", "evaluation", "mixed"],
            )
        with filter_col2:
            filter_min_rel = st.slider("Min relevance", 0.0, 1.0, 0.25, 0.05)
        with filter_col3:
            filter_sub = st.multiselect(
                "Subreddit",
                sorted({p["subreddit"] for p in analyzed_posts}),
                default=[],
            )

        filtered = [
            p for p in analyzed_posts
            if (not filter_type or p.get("post_type") in filter_type)
            and p.get("relevance_score", 0) >= filter_min_rel
            and (not filter_sub or p.get("subreddit") in filter_sub)
        ]

        st.caption(f"Showing {len(filtered)} of {len(analyzed_posts)} posts")

        for post in filtered:
            _render_post_card(post)

    elif not run_clicked:
        st.info("Configure your search above and click **Run Search** to start.")


# ===========================================================================
# PAGE: Lead Profiles
# ===========================================================================

elif page == "Lead Profiles":
    st.title("📊 Lead Profiles")
    st.markdown(
        "Aggregated prospect personas built from the search results.  \n"
        "Use the LinkedIn search queries to find matching professionals manually."
    )

    profiles = st.session_state.lead_profiles

    if not profiles:
        st.info("No lead profiles yet — run a search first.")
    else:
        import pandas as pd

        table_data = [
            {
                "Role": p["role"],
                "Cloud": p["cloud_platform"],
                "Tech Stack": ", ".join(p["tech_stack"][:4]),
                "Company Size": ", ".join(p["company_sizes"]) or "—",
                "Posts": p["post_count"],
                "Pain Posts": p["post_type_counts"].get("pain", 0),
            }
            for p in profiles
        ]
        st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

        st.divider()

        for i, profile in enumerate(profiles):
            _render_profile_card(profile, i)

        # Export
        st.divider()
        import json as _json

        col_exp1, col_exp2, col_exp3 = st.columns(3)
        with col_exp1:
            st.download_button(
                "⬇️ Export profiles (JSON)",
                data=_json.dumps(
                    [{k: v for k, v in p.items() if k != "posts"} for p in profiles],
                    indent=2,
                ),
                file_name="infros_lead_profiles.json",
                mime="application/json",
            )
        with col_exp2:
            csv_rows = "\n".join(
                f'"{p["role"]}","{p["cloud_platform"]}","{p["linkedin_query"]}","{p["linkedin_url"]}"'
                for p in profiles
            )
            csv_data = f'"Role","Cloud","LinkedIn Query","LinkedIn URL"\n{csv_rows}'
            st.download_button(
                "⬇️ Export LinkedIn queries (CSV)",
                data=csv_data,
                file_name="infros_linkedin_queries.csv",
                mime="text/csv",
            )
        with col_exp3:
            _profiles_saved = st.download_button(
                "💾 Save full session (JSON)",
                data=_session_json(),
                file_name=f"infros_session_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
                help="Download the full session including all posts and profiles.",
            )
            if _profiles_saved:
                _mark_manual_save()


# ===========================================================================
# PAGE: Report
# ===========================================================================

elif page == "Report":
    st.title("📋 Report & Insights")
    st.markdown(
        "An actionable summary of your search results with persona-specific "
        "outreach recommendations."
    )

    analyzed_posts = st.session_state.analyzed_posts
    lead_profiles = st.session_state.lead_profiles

    if not analyzed_posts:
        st.info("No data yet — run a search first.")
    else:
        # Generate (or use cached) report
        regen_col, dl_col, _ = st.columns([1, 1, 3])
        with regen_col:
            if st.button("🔄 Regenerate report", help="Rebuild the report from current results"):
                st.session_state._generated_report = None

        if st.session_state._generated_report is None:
            with st.spinner("Generating report…"):
                st.session_state._generated_report = generate_report(
                    analyzed_posts,
                    lead_profiles,
                    st.session_state._session_metadata,
                )

        report_md = st.session_state._generated_report

        with dl_col:
            st.download_button(
                "⬇️ Download report (.md)",
                data=report_md,
                file_name=f"infros_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                mime="text/markdown",
            )

        st.divider()
        st.markdown(report_md)


# ===========================================================================
# PAGE: Roadmap Validator
# ===========================================================================

elif page == "Roadmap Validator":
    st.title("🗺️ Roadmap Validator")
    st.markdown(
        "Cross-references your planned features against the Reddit pain data to answer: "
        "**which features have real demand, which have buying-intent signals, "
        "what pain exists that's not on your roadmap, and what has no signal at all.**"
    )

    analyzed_posts = st.session_state.analyzed_posts
    cfg = st.session_state.config

    if not analyzed_posts:
        st.info("Run a search first — the validator needs Reddit pain data to work with.")
    else:
        roadmap_items = cfg.get("roadmap", {}).get("features", [])
        if not roadmap_items:
            st.warning("No roadmap features configured. Add them in **Settings → Roadmap**.")
        else:
            st.caption(
                f"Validating {len(roadmap_items)} features against "
                f"{len(analyzed_posts)} analyzed posts."
            )

            if st.button("▶️ Run Validation", use_container_width=False):
                st.session_state["_roadmap_validation"] = validate_roadmap(
                    roadmap_items, analyzed_posts
                )

            validation = st.session_state.get("_roadmap_validation")

            if validation is None:
                st.info("Click **Run Validation** to start.")
            else:
                features = validation["features"]
                white_space = validation["white_space"]
                dead_weight = validation["dead_weight"]
                total = validation["total_relevant_posts"]

                # ---- Summary metrics ----------------------------------------
                active_features = [f for f in features if f["matched_posts"] > 0]
                hot_features = [f for f in active_features if f["buyer_readiness"] >= 0.3]

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Features validated", len(features))
                m2.metric("Features with signal", len(active_features))
                m3.metric("⚡ With buying intent", len(hot_features))
                m4.metric("White space gaps", len(white_space))

                st.divider()

                # ---- Priority table -----------------------------------------
                st.markdown("### Feature Priority Ranking")
                st.caption(
                    "Ranked by: demand (40%) + buyer readiness (40%) + pain intensity (20%). "
                    "⚡ = ≥30% of matching posts have buying signals."
                )

                import pandas as pd

                table_rows = []
                for f in features:
                    flag = "⚡" if f["buyer_readiness"] >= 0.3 else ""
                    table_rows.append({
                        "Rank": f["priority_rank"],
                        "Feature": f"{flag} {f['name']}".strip(),
                        "Posts": f["matched_posts"],
                        "Demand": f"{f['demand_score']:.0%}",
                        "Buyer Ready": f"{f['buyer_readiness']:.0%}",
                        "Pain Intensity": f"{f['pain_intensity']:.0%}",
                        "Score": f"{f['priority_score']:.0%}",
                    })
                st.dataframe(
                    pd.DataFrame(table_rows),
                    use_container_width=True,
                    hide_index=True,
                )

                st.divider()

                # ---- Feature detail cards -----------------------------------
                st.markdown("### Feature Details")
                for f in features:
                    if f["matched_posts"] == 0:
                        continue
                    buyer_flag = " ⚡" if f["buyer_readiness"] >= 0.3 else ""
                    with st.expander(
                        f"#{f['priority_rank']} — **{f['name']}**{buyer_flag} "
                        f"— {f['matched_posts']} posts · {f['priority_score']:.0%} score",
                        expanded=(f["priority_rank"] == 1),
                    ):
                        c1, c2 = st.columns([2, 1])
                        with c1:
                            st.markdown(f"*{f['description']}*")
                            if f.get("representative_quotes"):
                                st.markdown("**What people are saying:**")
                                for q in f["representative_quotes"]:
                                    st.markdown(f'- *"{q}"*')
                            if f.get("buyer_quotes"):
                                st.markdown("**Active buyers (renewal / budget / RFP):**")
                                for q in f["buyer_quotes"]:
                                    st.markdown(f'- *"{q}"*')
                        with c2:
                            st.metric("Demand", f"{f['demand_score']:.0%}")
                            st.metric("Buyer readiness", f"{f['buyer_readiness']:.0%}")
                            st.metric("Evaluating tools", f"{f['eval_fraction']:.0%}")
                            if f.get("competitors_in_context"):
                                st.markdown("**Competitors seen:**")
                                st.markdown(
                                    " ".join(f"`{c}`" for c in f["competitors_in_context"])
                                )

                # ---- White space --------------------------------------------
                if white_space:
                    st.divider()
                    st.markdown("### 🔍 White Space — Unaddressed Pain Themes")
                    st.caption(
                        "High-frequency pain signals in the Reddit data **not covered by any "
                        "feature on your current roadmap**. Potential new feature opportunities."
                    )
                    for ws in white_space:
                        buyer_flag = " ⚡" if ws["buyer_readiness"] >= 0.25 else ""
                        with st.expander(
                            f'*"{ws["pain_theme"]}"*{buyer_flag} — '
                            f'{ws["frequency"]} posts · {ws["buyer_readiness"]:.0%} buyer readiness',
                        ):
                            if ws.get("sample_posts"):
                                st.markdown("**Sample posts:**")
                                for sp in ws["sample_posts"]:
                                    st.markdown(f'- *"{sp}"*')
                            if ws.get("competitors_seen"):
                                st.markdown(
                                    "**Competitors seen alongside this pain:** "
                                    + ", ".join(f"`{c}`" for c in ws["competitors_seen"])
                                )

                # ---- Dead weight -------------------------------------------
                if dead_weight:
                    st.divider()
                    st.markdown("### ⚠️ Dead Weight — Features With No Signal")
                    st.caption(
                        "These features had zero matching posts. Reconsider priority or "
                        "check that keywords match how users actually describe the problem."
                    )
                    for name in dead_weight:
                        st.markdown(f"- {name}")

                # ---- Download report ----------------------------------------
                st.divider()
                report_md = generate_roadmap_report(
                    validation, st.session_state._session_metadata
                )
                st.download_button(
                    "⬇️ Download Roadmap Validation Report (.md)",
                    data=report_md,
                    file_name=f"infros_roadmap_validation_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                    mime="text/markdown",
                )


# ===========================================================================
# PAGE: Settings
# ===========================================================================

elif page == "Settings":
    st.title("⚙️ Settings")
    st.markdown("Changes are saved to `config.yaml` and take effect on the next search.")

    cfg = st.session_state.config

    tab_api, tab_subs, tab_keywords, tab_topics, tab_search, tab_roadmap = st.tabs([
        "🔑 Reddit API",
        "📋 Subreddits",
        "🔤 Keywords",
        "🗂️ Topics",
        "🎛️ Search Params",
        "🗺️ Roadmap",
    ])

    # ---- Reddit API ----
    with tab_api:
        st.markdown(
            "### Reddit API Credentials\n"
            "Optional — using your own API credentials increases the rate limit from "
            "~30 to 100 requests/min and is more reliable for large searches.  \n\n"
            "**How to get credentials:**\n"
            "1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)\n"
            "2. Create a new **script** app\n"
            "3. Copy the client ID (under the app name) and secret below"
        )
        st.info(
            "Credentials are stored only in `config.yaml` on your local machine. "
            "Never commit this file to a public repository."
        )

        api = cfg["reddit"]["api"]

        new_client_id = st.text_input("Client ID", value=api.get("client_id", ""), type="password")
        new_secret = st.text_input("Client Secret", value=api.get("client_secret", ""), type="password")
        new_username = st.text_input("Reddit Username (optional)", value=api.get("username", ""))
        new_password = st.text_input("Reddit Password (optional)", value=api.get("password", ""), type="password")
        new_ua = st.text_input(
            "User Agent",
            value=api.get("user_agent", "InfrOS Lead Research Tool v1.0"),
            help="Identify your bot. Reddit asks that user agents be descriptive.",
        )

        if st.button("Save API settings"):
            cfg["reddit"]["api"].update({
                "client_id": new_client_id,
                "client_secret": new_secret,
                "username": new_username,
                "password": new_password,
                "user_agent": new_ua,
            })
            save_config(cfg)
            st.session_state.config = cfg
            st.success("API settings saved.")

    # ---- Subreddits ----
    with tab_subs:
        st.markdown(
            "### Subreddits\n"
            "Add or remove subreddits to search. One subreddit name per line."
        )
        current_subs = cfg["reddit"]["subreddits"]
        new_subs_text = st.text_area(
            "Subreddits (one per line)",
            value="\n".join(current_subs),
            height=300,
        )
        if st.button("Save subreddits"):
            new_list = [s.strip().lstrip("r/") for s in new_subs_text.splitlines() if s.strip()]
            cfg["reddit"]["subreddits"] = new_list
            save_config(cfg)
            st.session_state.config = cfg
            st.success(f"Saved {len(new_list)} subreddits.")

        st.markdown("**Suggested subreddits for InfrOS:**")
        suggestions = [
            "devops", "aws", "azure", "googlecloud", "terraform", "kubernetes",
            "sysadmin", "cloudcomputing", "FinOps", "devops_beginner", "docker",
            "k8s", "ExperiencedDevs", "cscareerquestions", "itcareerquestions",
            "aws_certifications",
        ]
        st.code("\n".join(suggestions), language=None)

    # ---- Keywords ----
    with tab_keywords:
        st.markdown(
            "### General Keywords\n"
            "Used when you choose **Use Keywords** in the Search page. One per line."
        )
        current_kws = cfg["reddit"]["keywords"]
        new_kws_text = st.text_area(
            "Keywords (one per line)",
            value="\n".join(current_kws),
            height=300,
        )
        if st.button("Save keywords"):
            new_list = [k.strip() for k in new_kws_text.splitlines() if k.strip()]
            cfg["reddit"]["keywords"] = new_list
            save_config(cfg)
            st.session_state.config = cfg
            st.success(f"Saved {len(new_list)} keywords.")

        st.markdown("**Suggested keywords for InfrOS:**")
        suggestions_kw = [
            "cloud costs too high", "terraform complexity", "cloud migration pain",
            "infrastructure automation", "multi-cloud challenges", "cloud architecture help",
            "IaC best practices", "cloud deployment slow", "Terraform state management",
            "AWS bill shock", "cloud waste", "rightsizing instances", "FinOps",
            "infrastructure as code", "cloud vendor lock-in", "cloud optimization",
        ]
        st.code("\n".join(suggestions_kw), language=None)

    # ---- Topics ----
    with tab_topics:
        st.markdown(
            "### Topics\n"
            "Topics are named keyword groups for focused searches. "
            "Edit the YAML below and save."
        )
        import yaml

        topics_yaml = yaml.dump(
            cfg["reddit"]["topics"],
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        new_topics_yaml = st.text_area(
            "Topics (YAML)",
            value=topics_yaml,
            height=450,
        )
        if st.button("Save topics"):
            try:
                new_topics = yaml.safe_load(new_topics_yaml)
                if isinstance(new_topics, list):
                    cfg["reddit"]["topics"] = new_topics
                    save_config(cfg)
                    st.session_state.config = cfg
                    st.success(f"Saved {len(new_topics)} topics.")
                else:
                    st.error("YAML must be a list of topic objects.")
            except yaml.YAMLError as e:
                st.error(f"YAML parse error: {e}")

    # ---- Search Params ----
    with tab_search:
        st.markdown("### Search Parameters")
        s = cfg["reddit"]["search"]

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            new_time = st.selectbox(
                "Default time filter",
                ["hour", "day", "week", "month", "year", "all"],
                index=["hour", "day", "week", "month", "year", "all"].index(
                    s.get("time_filter", "month")
                ),
                help="How far back Reddit results should go by default.",
            )
            new_sort = st.selectbox(
                "Default sort",
                ["relevance", "hot", "top", "new", "comments"],
                index=["relevance", "hot", "top", "new", "comments"].index(
                    s.get("sort", "relevance")
                ),
            )
        with col_s2:
            new_max = st.number_input(
                "Max results per subreddit/keyword",
                min_value=5,
                max_value=100,
                value=int(s.get("max_results", 25)),
                step=5,
                help="Reddit returns up to 25 posts per public API call. "
                     "Values above 25 trigger multiple pages (slower).",
            )
            new_min_score = st.number_input(
                "Minimum upvotes",
                min_value=0,
                value=int(s.get("min_score", 3)),
                step=1,
            )

        if st.button("Save search params"):
            cfg["reddit"]["search"].update({
                "time_filter": new_time,
                "sort": new_sort,
                "max_results": new_max,
                "min_score": new_min_score,
            })
            save_config(cfg)
            st.session_state.config = cfg
            st.success("Search parameters saved.")

    # ---- Roadmap ----
    with tab_roadmap:
        st.markdown(
            "### Product Roadmap Features\n"
            "Define the features you're planning to build. The **Roadmap Validator** page "
            "will cross-reference these against Reddit pain data to measure real demand.\n\n"
            "Edit the YAML below — each item needs `name`, `description`, and `keywords` "
            "(the keywords that someone in pain about this feature would use)."
        )
        import yaml

        roadmap_yaml = yaml.dump(
            cfg.get("roadmap", {}).get("features", []),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        new_roadmap_yaml = st.text_area(
            "Roadmap features (YAML)",
            value=roadmap_yaml,
            height=500,
        )
        if st.button("Save roadmap"):
            try:
                new_features = yaml.safe_load(new_roadmap_yaml)
                if isinstance(new_features, list):
                    if "roadmap" not in cfg:
                        cfg["roadmap"] = {}
                    cfg["roadmap"]["features"] = new_features
                    save_config(cfg)
                    st.session_state.config = cfg
                    # Invalidate cached validation when roadmap changes
                    st.session_state.pop("_roadmap_validation", None)
                    st.success(f"Saved {len(new_features)} roadmap features.")
                else:
                    st.error("YAML must be a list of feature objects.")
            except yaml.YAMLError as e:
                st.error(f"YAML parse error: {e}")
