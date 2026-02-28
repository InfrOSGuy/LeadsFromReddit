"""
Report generator — produces an actionable Markdown report from analyzed posts
and lead profiles, with specific outreach recommendations per persona.
"""

from collections import Counter
from datetime import datetime


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(
    analyzed_posts: list[dict],
    lead_profiles: list[dict],
    metadata: dict | None = None,
) -> str:
    """
    Build an actionable Markdown report from session data.

    Returns a Markdown string ready for display or download.
    """
    if not analyzed_posts:
        return "No data to report yet — run a search first."

    lines: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    meta = metadata or {}

    # ---- Header ---------------------------------------------------------------
    searched_at = meta.get("searched_at", "")[:10] or now[:10]
    subs_searched = meta.get("subreddits", [])
    kws_searched = meta.get("keywords", [])

    lines += [
        "# InfrOS Lead Research Report",
        f"*Generated {now}*",
        "",
    ]
    if subs_searched:
        lines.append(
            f"**Search scope:** {len(subs_searched)} subreddits · "
            f"{len(kws_searched)} keywords · date {searched_at}"
        )
        lines.append("")

    # ---- Aggregate metrics ----------------------------------------------------
    total = len(analyzed_posts)
    pain_posts = [p for p in analyzed_posts if p.get("post_type") == "pain"]
    mixed_posts = [p for p in analyzed_posts if p.get("post_type") == "mixed"]
    solution_posts = [p for p in analyzed_posts if p.get("post_type") == "solution"]
    high_rel = [p for p in analyzed_posts if p.get("relevance_score", 0) >= 0.6]

    dates = sorted(p["created_date"] for p in analyzed_posts if p.get("created_date"))
    date_range = f"{dates[0]} – {dates[-1]}" if dates else "—"

    avg_score = sum(p.get("relevance_score", 0) for p in analyzed_posts) / total

    sub_counter = Counter(p.get("subreddit", "") for p in analyzed_posts)
    top_subs = sub_counter.most_common(5)

    all_pain_signals: list[str] = []
    for p in analyzed_posts:
        all_pain_signals.extend(p.get("pain_signals", []))
    pain_counter = Counter(all_pain_signals)
    top_pains = pain_counter.most_common(8)

    all_tech: list[str] = []
    for p in analyzed_posts:
        all_tech.extend(p.get("tech_stack", []))
    tech_counter = Counter(all_tech)
    top_tech = tech_counter.most_common(8)

    # ---- Executive Summary ----------------------------------------------------
    lines += [
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Posts analysed | {total} |",
        f"| Date range | {date_range} |",
        f"| Pain posts | {len(pain_posts)} ({len(pain_posts)/total:.0%}) |",
        f"| Mixed (pain + solution signals) | {len(mixed_posts)} ({len(mixed_posts)/total:.0%}) |",
        f"| Solution posts | {len(solution_posts)} ({len(solution_posts)/total:.0%}) |",
        f"| High-relevance posts (≥60%) | {len(high_rel)} |",
        f"| Lead profiles identified | {len(lead_profiles)} |",
        f"| Avg relevance score | {avg_score:.0%} |",
        "",
    ]

    if top_subs:
        lines.append("**Most active subreddits:**")
        for sub, cnt in top_subs:
            pct = cnt / total
            lines.append(f"- **r/{sub}** — {cnt} posts ({pct:.0%})")
        lines.append("")

    # ---- Pain Signal Breakdown ------------------------------------------------
    if top_pains:
        lines += [
            "## Top Pain Signals",
            "",
            "These phrases appear most often across posts — use them verbatim in "
            "outreach to show you speak their language.",
            "",
        ]
        for signal, cnt in top_pains:
            lines.append(f'- **"{signal}"** — {cnt} mentions')
        lines.append("")

    # ---- Technology Landscape -------------------------------------------------
    if top_tech:
        lines += [
            "## Technology Landscape",
            "",
            "| Technology | Mentions | % of posts |",
            "|-----------|---------|-----------|",
        ]
        for tech, cnt in top_tech:
            lines.append(f"| {tech} | {cnt} | {cnt/total:.0%} |")
        lines.append("")

    # ---- Hot Posts (quick-win signals) ----------------------------------------
    scored = sorted(
        (p for p in analyzed_posts if p.get("post_type") in {"pain", "mixed"}),
        key=lambda p: p.get("relevance_score", 0) * (1 + min(p.get("score", 0) / 100, 1)),
        reverse=True,
    )[:5]

    if scored:
        lines += [
            "## Highest-Signal Posts",
            "",
            "Posts combining high relevance with strong community engagement — "
            "the clearest indicators of widespread pain.",
            "",
        ]
        for p in scored:
            rel = p.get("relevance_score", 0)
            lines += [
                f"### {p.get('title', '')[:100]}",
                f"*r/{p.get('subreddit', '')} · "
                f"👍 {p.get('score', 0)} · "
                f"relevance {rel:.0%} · "
                f"{p.get('created_date', '')}*",
                "",
            ]
            if p.get("pain_signals"):
                lines.append(
                    "**Pain signals:** " + " · ".join(f"`{s}`" for s in p["pain_signals"][:4])
                )
            if p.get("tech_stack"):
                lines.append(
                    "**Tech:** " + " · ".join(f"`{t}`" for t in p["tech_stack"])
                )
            lines += [
                f"[View on Reddit →]({p.get('url', '')})",
                "",
            ]

    # ---- Prospect Personas & Outreach Guide -----------------------------------
    lines += [
        "## Prospect Personas & Outreach Guide",
        "",
        "Each persona is derived from clustered post signals. "
        "The outreach angle is tailored to the observed pain themes.",
        "",
    ]

    for i, profile in enumerate(lead_profiles, 1):
        role = profile.get("role", "Unknown")
        cloud = profile.get("cloud_platform", "Multi-Cloud")
        count = profile.get("post_count", 0)
        pain_count = profile.get("post_type_counts", {}).get("pain", 0)
        mixed_count = profile.get("post_type_counts", {}).get("mixed", 0)
        tech = profile.get("tech_stack", [])
        sizes = ", ".join(profile.get("company_sizes", [])) or "all sizes"
        industries = profile.get("industries", [])
        pain_summaries = profile.get("pain_summaries", [])[:6]
        sample_titles = profile.get("sample_titles", [])[:3]
        linkedin_query = profile.get("linkedin_query", "")
        linkedin_url = profile.get("linkedin_url", "")
        query_variants = profile.get("linkedin_query_variants", [])
        account_url = profile.get("account_url", "")
        seniority_filter = profile.get("seniority_filter", [])
        job_function = profile.get("job_function", "")
        headcount_ranges = profile.get("headcount_ranges", [])

        angle = _suggest_outreach_angle(role, cloud, pain_summaries, tech)
        talking_points = _talking_points(role, cloud, pain_summaries, tech)
        spotlight_recs = _spotlight_recommendations(role, profile.get("company_sizes", []), pain_summaries)
        inmail_subject, inmail_body = _inmail_template(role, cloud, pain_summaries, tech)

        lines += [
            f"### {i}. {role} — {cloud}",
            "",
            f"| Signal | Value |",
            f"|--------|-------|",
            f"| Posts | {count} ({pain_count} pain, {mixed_count} mixed) |",
            f"| Tech stack | {', '.join(tech[:6]) or '—'} |",
            f"| Company sizes | {sizes} |",
        ]
        if industries:
            lines.append(f"| Industries detected | {', '.join(industries[:3])} |")
        lines.append("")

        if pain_summaries:
            lines.append("**Observed pain themes:**")
            for ps in pain_summaries:
                lines.append(f"- {ps}")
            lines.append("")

        if sample_titles:
            lines.append("**Example post titles (verbatim):**")
            for t in sample_titles:
                lines.append(f"- *{t}*")
            lines.append("")

        lines += [
            f"**Outreach angle:** {angle}",
            "",
        ]

        if talking_points:
            lines.append("**Suggested talking points:**")
            for tp in talking_points:
                lines.append(f"- {tp}")
            lines.append("")

        # ---- Sales Navigator: Lead Search ----------------------------------------
        lines += [
            "#### LinkedIn — Lead Search (People)",
            "",
            f"**Primary search:** `{linkedin_query}`",
            f"[Open in Sales Navigator →]({linkedin_url})",
            "",
        ]

        # Filter panel
        lines += [
            "**Sales Navigator filters to apply manually:**",
            "",
            "| Filter | Values |",
            "|--------|--------|",
        ]
        if seniority_filter:
            lines.append(f"| Seniority level | {', '.join(seniority_filter)} |")
        if job_function:
            lines.append(f"| Job function | {job_function} |")
        if headcount_ranges:
            lines.append(f"| Company headcount | {', '.join(headcount_ranges)} |")
        if industries:
            lines.append(f"| Industry | {' / '.join(industries[:2])} |")
        lines.append("")

        # Spotlight filters
        if spotlight_recs:
            lines.append("**Spotlight filters to layer on** *(narrows to warm, high-intent leads)*:")
            for rec in spotlight_recs:
                lines.append(f"- {rec}")
            lines.append("")

        # Alternative search variants
        if query_variants:
            lines.append(
                "**Alternative title searches** *(run separately to reach different title buckets)*:"
            )
            for q, url in query_variants:
                lines.append(f"- `{q}` — [Search →]({url})")
            lines.append("")

        # ---- Sales Navigator: Account Search -------------------------------------
        if account_url:
            lines += [
                "#### LinkedIn — Account Search (Companies)",
                "",
                "Find the right companies first, then look for decision-makers within them:",
                f"[Search matching companies →]({account_url})",
                "",
                "Account filters to apply: headcount ranges above · Engineering headcount growing · "
                "Funding event in last 12 months",
                "",
            ]

        # ---- InMail template -----------------------------------------------------
        lines += [
            "#### InMail Template",
            "",
            f"**Subject:** {inmail_subject}",
            "",
            "**Body:**",
            "",
        ]
        for line in inmail_body.split("\n"):
            lines.append(f"> {line}" if line else ">")
        lines += [
            "",
            "---",
            "",
        ]

    # ---- Recommended Actions --------------------------------------------------
    lines += [
        "## Recommended Actions",
        "",
    ]

    # Best keywords by avg post score (engagement proxy)
    kw_scores: dict[str, list[int]] = {}
    for p in analyzed_posts:
        kw = p.get("matched_keyword", "")
        if kw:
            kw_scores.setdefault(kw, []).append(p.get("score", 0))
    kw_avg = {kw: sum(s) / len(s) for kw, s in kw_scores.items() if s}
    top_kws = sorted(kw_avg.items(), key=lambda x: x[1], reverse=True)[:6]

    if top_kws:
        lines += [
            "### Keywords generating the most engagement",
            "",
            "Run follow-up searches on these first — they surface posts with more upvotes "
            "and therefore wider community resonance.",
            "",
        ]
        for kw, avg in top_kws:
            lines.append(f'- **"{kw}"** — avg {avg:.0f} upvotes per post')
        lines.append("")

    # Best subreddits by avg relevance
    sub_rel: dict[str, list[float]] = {}
    for p in analyzed_posts:
        sub = p.get("subreddit", "")
        if sub:
            sub_rel.setdefault(sub, []).append(p.get("relevance_score", 0))
    sub_avg_rel = {s: sum(r) / len(r) for s, r in sub_rel.items() if r}
    top_rel_subs = sorted(sub_avg_rel.items(), key=lambda x: x[1], reverse=True)[:5]

    if top_rel_subs:
        lines += [
            "### Highest-quality subreddits (by avg relevance score)",
            "",
        ]
        for sub, avg_rel in top_rel_subs:
            lines.append(f"- **r/{sub}** — avg relevance {avg_rel:.0%}")
        lines.append("")

    # Quick-start persona actions
    if lead_profiles:
        lines += [
            "### Immediate next steps by persona",
            "",
        ]
        for profile in lead_profiles[:3]:
            role = profile.get("role", "")
            cloud = profile.get("cloud_platform", "")
            seniority = ", ".join(profile.get("seniority_filter", []))
            function = profile.get("job_function", "")
            headcount = ", ".join(profile.get("headcount_ranges", []))
            angle = _suggest_outreach_angle(
                role, cloud,
                profile.get("pain_summaries", []),
                profile.get("tech_stack", []),
            )
            lines += [
                f"**{role} ({cloud})**",
                f"1. [Open Sales Navigator search →]({profile.get('linkedin_url', '')})",
                f"2. Apply filters: Seniority = {seniority or '—'} · Function = {function or '—'}"
                + (f" · Headcount = {headcount}" if headcount else ""),
                f"3. Layer spotlight: *Changed jobs (90 days)* + *Posted recently*",
                f"4. Outreach angle: {angle}",
                "",
            ]

    lines += [
        "---",
        "*Report generated by InfrOS Lead Finder*",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _inmail_template(
    role: str,
    cloud: str,
    pain_summaries: list[str],
    tech: list[str],
) -> tuple[str, str]:
    """Return (subject_line, body) sized for Sales Navigator InMail limits.

    Subject ≤ 200 chars, body ≤ 1,900 chars.
    Placeholders in [brackets] must be filled in before sending.
    """
    pain_text = " ".join(pain_summaries).lower()

    if any(w in pain_text for w in ("cost", "bill", "spend", "expensive")):
        subject = f"Cloud cost question — {cloud} teams"
        opening = (
            f"A lot of {cloud} teams I speak with are dealing with the same thing right now: "
            "cloud bills that are hard to predict and even harder to justify to leadership."
        )
    elif any(w in pain_text for w in ("terraform", "state", "drift", "iac")):
        subject = "Terraform drift question"
        opening = (
            "Noticed a pattern across infra teams lately — Terraform state management and config "
            "drift are eating up a disproportionate amount of engineer time."
        )
    elif any(w in pain_text for w in ("manual", "automat", "slow", "toil")):
        subject = "Reducing manual infra work"
        opening = (
            "One thing I keep hearing from platform teams is that manual deployment and ops tasks "
            "are still the biggest time sink, even at companies that are otherwise well-automated."
        )
    elif "kubernetes" in [t.lower() for t in tech] or "k8s" in pain_text:
        subject = "K8s ops without the 2 AM pages"
        opening = (
            "Kubernetes cluster management seems to be the thing keeping most platform engineers "
            "up at night — especially around scaling and on-call load."
        )
    elif "FinOps" in role or "Cloud Economics" in role:
        subject = "Cloud cost chargeback question"
        opening = (
            "FinOps practitioners I talk to consistently name the same bottleneck: getting teams "
            "to actually own their cloud spend without a manual chargeback process."
        )
    elif any(r in role for r in ("CTO", "VP", "Manager")):
        subject = "Infrastructure velocity question"
        opening = (
            "One theme I keep seeing in engineering-heavy orgs: infra toil is quietly becoming "
            "the bottleneck on shipping speed."
        )
    else:
        subject = f"Infrastructure question for {role}s"
        opening = (
            "I've been speaking with a lot of infra and platform teams lately, and operational "
            "toil keeps coming up as the thing slowing them down the most."
        )

    cloud_line = (
        f" We work specifically with {cloud} teams, so the context is usually pretty relevant."
        if cloud and cloud != "Multi-Cloud"
        else ""
    )

    body = (
        f"Hi [First Name],\n\n"
        f"{opening}{cloud_line}\n\n"
        f"InfrOS helps teams like yours [one-sentence value prop — e.g. 'cut cloud spend by "
        f"20–35% without changing your architecture' or 'eliminate Terraform drift before it "
        f"becomes an incident'].\n\n"
        f"Worth a 15-minute call to see if it's relevant?\n\n"
        f"[Your name]"
    )
    return subject, body


def _spotlight_recommendations(
    role: str,
    company_sizes: list[str],
    pain_summaries: list[str],
) -> list[str]:
    """Return prioritised Sales Navigator Spotlight/Account alert filters to layer on."""
    recs: list[str] = []
    pain_text = " ".join(pain_summaries).lower()

    if any(r in role for r in ("Manager", "CTO", "VP", "Director", "Architect")):
        recs.append(
            "**Changed jobs in last 90 days** — new leaders actively evaluate tooling and have "
            "mandate to change things; reply rates are 2–3× higher on this segment"
        )

    recs.append(
        "**Posted on LinkedIn in last 30 days** — filters to people who are active on the "
        "platform right now; dramatically increases the chance of a reply"
    )

    if "Enterprise" in company_sizes:
        recs.append(
            "**Account filter → Senior leadership change (last 3 months)** — a new exec is a "
            "new budget holder still defining their vendor stack"
        )

    if any(s in company_sizes for s in ("Startup", "Scale-up / Mid-size")):
        recs.append(
            "**Account filter → Funding event in last 12 months** — fresh capital means infra "
            "investment is on the roadmap; creates a natural buying window"
        )

    recs.append(
        "**Account filter → Engineering headcount growing** — scaling eng teams hit infra pain "
        "first; best leading indicator of near-term need"
    )

    if any(w in pain_text for w in ("cost", "bill", "spend", "finops")):
        recs.append(
            "**Account filter → Actively hiring FinOps / Cloud Cost roles** — if they're "
            "recruiting for this, the pain is real and already budgeted"
        )

    return recs[:4]


def _suggest_outreach_angle(
    role: str,
    cloud: str,
    pain_summaries: list[str],
    tech: list[str],
) -> str:
    """Return a one-sentence outreach angle based on observed signals."""
    pain_text = " ".join(pain_summaries).lower()
    tech_lower = [t.lower() for t in tech]

    if any(w in pain_text for w in ("cost", "bill", "spend", "expensive", "waste")):
        angle = (
            "Lead with cloud cost visibility — they're experiencing bill shock or runaway spend. "
            "Open with: 'I noticed a lot of teams in your space are struggling with unexpected cloud bills…'"
        )
    elif any(w in pain_text for w in ("terraform", "state", "drift", "iac", "infrastructure as code")):
        angle = (
            "Lead with IaC reliability and drift prevention — they're wrestling with "
            "Terraform complexity. Open with: 'How much time does your team spend on Terraform state issues?'"
        )
    elif any(w in pain_text for w in ("scale", "slow", "manual", "automat")):
        angle = (
            "Lead with automation ROI — they're drowning in manual ops. "
            "Open with: 'What would your team do with 20% fewer manual deployment tasks?'"
        )
    elif any(w in pain_text for w in ("migrat")):
        angle = (
            "Lead with safe, fast cloud migration — they need guardrails mid-journey. "
            "Open with: 'Are you finding migration timelines slipping as complexity grows?'"
        )
    elif "kubernetes" in tech_lower or "k8s" in pain_text:
        angle = (
            "Lead with Kubernetes operational simplicity — they're fighting cluster complexity. "
            "Open with: 'How many hours per week does your team spend on Kubernetes firefighting?'"
        )
    elif "FinOps" in role:
        angle = (
            "Lead with cost chargeback and visibility dashboards — FinOps practitioners need "
            "hard numbers to justify optimisation projects."
        )
    elif any(r in role for r in ("CTO", "VP", "Manager")):
        angle = (
            "Lead with business outcomes: faster delivery, lower cloud bill, reduced toil. "
            "Skip technical details — focus on team velocity and cost savings."
        )
    elif "Architect" in role:
        angle = (
            "Lead with infrastructure standardisation and multi-cloud portability. "
            "Architects care about long-term maintainability and avoiding lock-in."
        )
    else:
        angle = (
            "Lead with reducing operational toil and improving deployment reliability. "
            "Ask about their biggest infrastructure bottleneck."
        )

    if cloud == "AWS":
        angle += " Mention native AWS integrations (IAM, CloudWatch, EKS)."
    elif cloud == "Azure":
        angle += " Mention AKS and Azure DevOps integrations."
    elif cloud == "GCP":
        angle += " Mention GKE and BigQuery-native tooling."

    return angle


def _talking_points(
    role: str,
    cloud: str,
    pain_summaries: list[str],
    tech: list[str],
) -> list[str]:
    """Return 3–4 specific talking points for this persona."""
    pain_text = " ".join(pain_summaries).lower()
    points: list[str] = []

    if any(w in pain_text for w in ("cost", "bill", "spend")):
        points.append(
            "Show a cost-savings calculation: 'Teams like yours typically reduce cloud spend by 20–35% in 90 days.'"
        )
    if any(w in pain_text for w in ("terraform", "state", "drift")):
        points.append(
            "Terraform state locking and drift detection: 'Prevent config drift before it becomes an incident.'"
        )
    if any(w in pain_text for w in ("manual", "automat", "slow")):
        points.append(
            "Quantify the toil tax: 'How many engineer-hours per sprint go to manual infra tasks?'"
        )
    if "Kubernetes" in tech:
        points.append(
            "Kubernetes cluster health: 'Self-healing policies that run before your on-call gets paged.'"
        )
    if any(r in role for r in ("Manager", "CTO", "VP")):
        points.append(
            "Board-level framing: 'Infrastructure reliability directly maps to customer uptime and NPS.'"
        )
    if not points:
        points.append(
            "Ask a discovery question: 'What's the biggest thing slowing your infrastructure team down right now?'"
        )

    return points[:4]
