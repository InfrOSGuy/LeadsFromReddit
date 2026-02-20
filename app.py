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
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from src.config_manager import load_config, save_config
from src.reddit_scraper import RedditScraper
from src.analyzer import analyze_post, build_lead_profiles

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


# ---------------------------------------------------------------------------
# Sidebar — navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🔍 InfrOS Lead Finder")
    st.markdown("*Find cloud practitioners experiencing pain InfrOS can solve.*")
    st.divider()

    page = st.radio(
        "Navigate",
        ["Search & Discover", "Lead Profiles", "Settings"],
        format_func=lambda x: {
            "Search & Discover": "🔎 Search & Discover",
            "Lead Profiles": "📊 Lead Profiles",
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

# ===========================================================================
# PAGE: Search & Discover
# ===========================================================================

if page == "Search & Discover":
    st.title("🔎 Search & Discover")
    st.markdown(
        "Search Reddit for cloud/infrastructure pain points that InfrOS solves.  \n"
        "Results are analysed for role signals, tech-stack, and pain indicators."
    )

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

        if mode == "Use Topics":
            topic_names = [t["name"] for t in cfg["reddit"]["topics"]]
            selected_topics = st.multiselect(
                "Topics to search",
                options=topic_names,
                default=topic_names,
            )
            # Flatten keywords from selected topics
            active_keywords = []
            for topic in cfg["reddit"]["topics"]:
                if topic["name"] in selected_topics:
                    active_keywords.extend(topic["keywords"])
            active_keywords = list(dict.fromkeys(active_keywords))  # deduplicate
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

        progress_bar.empty()
        status_text.empty()
        st.success(
            f"Found **{len(analyzed)} posts** → **{len(lead_profiles)} lead profiles**"
        )

    # ---- Results ----
    analyzed_posts = st.session_state.analyzed_posts
    if analyzed_posts:
        st.divider()
        st.markdown(f"### Results  ({len(analyzed_posts)} posts)")

        # Filter bar
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            filter_type = st.multiselect(
                "Post type",
                ["pain", "solution", "mixed", "discussion"],
                default=["pain", "mixed"],
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


def _render_post_card(post: dict):
    rel = post.get("relevance_score", 0)
    post_type = post.get("post_type", "discussion")
    type_emoji = {"pain": "🔴", "solution": "🟢", "mixed": "🟡", "discussion": "⚪"}.get(
        post_type, "⚪"
    )

    with st.expander(
        f"{type_emoji} [{post.get('subreddit', '')}] {post.get('title', '')[:90]}  "
        f"— relevance: {rel:.0%}",
        expanded=False,
    ):
        col_a, col_b = st.columns([2, 1])

        with col_a:
            if post.get("body"):
                st.markdown(f"*{post['body'][:400].strip()}{'…' if len(post.get('body','')) > 400 else ''}*")

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
        # Summary table
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
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            import json
            st.download_button(
                "⬇️ Export profiles (JSON)",
                data=json.dumps(
                    [
                        {k: v for k, v in p.items() if k != "posts"}
                        for p in profiles
                    ],
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


def _render_profile_card(profile: dict, idx: int):
    role = profile["role"]
    cloud = profile["cloud_platform"]
    count = profile["post_count"]
    pain_count = profile["post_type_counts"].get("pain", 0)

    with st.expander(
        f"**{role}** · {cloud}  —  {count} posts ({pain_count} pain)",
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

            st.markdown("**LinkedIn search query:**")
            st.code(profile.get("linkedin_query", ""), language=None)

        st.link_button(
            "🔗 Search LinkedIn →",
            url=profile.get("linkedin_url", "#"),
            use_container_width=True,
        )


# ===========================================================================
# PAGE: Settings
# ===========================================================================

elif page == "Settings":
    st.title("⚙️ Settings")
    st.markdown("Changes are saved to `config.yaml` and take effect on the next search.")

    cfg = st.session_state.config
    changed = False

    # ---- Tabs ----
    tab_api, tab_subs, tab_keywords, tab_topics, tab_search = st.tabs([
        "🔑 Reddit API",
        "📋 Subreddits",
        "🔤 Keywords",
        "🗂️ Topics",
        "🎛️ Search Params",
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
