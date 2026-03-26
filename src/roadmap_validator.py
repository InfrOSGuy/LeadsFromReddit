"""
Roadmap Validator — cross-references a product roadmap against Reddit pain signals.

Answers three questions:
  1. Which planned features have real, measurable demand? (priority rank)
  2. Which pain themes exist that aren't on the roadmap? (white space / opportunity)
  3. Which planned features have no signal? (dead weight — reconsider priority)

Each feature result includes:
  - matched_posts: how many relevant posts express this pain
  - demand_score: matched / total_relevant_posts (0–1)
  - buyer_readiness: posts with buying signals / matched (0–1)
    — these are people who are actively evaluating, have budget, have a renewal due
  - pain_intensity: avg relevance_score of matching posts (0–1)
  - competitors_in_context: which competitor tools appear alongside this pain
  - representative_quotes: top post titles from matching posts
  - priority_score: weighted composite of demand + buyer readiness + pain intensity
"""

import re
from collections import Counter
from datetime import datetime


# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------

def validate_roadmap(
    roadmap_items: list[dict],
    analyzed_posts: list[dict],
) -> dict:
    """
    Cross-reference roadmap items against analyzed Reddit posts.

    Parameters
    ----------
    roadmap_items : list of {"name": str, "description": str, "keywords": list[str]}
    analyzed_posts : list of dicts from analyzer.analyze_post()

    Returns
    -------
    dict with keys: total_relevant_posts, features, white_space, dead_weight
    """
    relevant_posts = [p for p in analyzed_posts if p.get("relevance_score", 0) >= 0.25]
    total_relevant = len(relevant_posts) or 1

    # ---- Score each roadmap item ------------------------------------------------
    feature_results: list[dict] = []

    for item in roadmap_items:
        keywords = [k.lower().strip() for k in item.get("keywords", []) if k.strip()]
        name = item.get("name", "Unnamed feature")
        description = item.get("description", "")

        if not keywords:
            feature_results.append(_zero_result(name, description))
            continue

        # Build a single pattern — keyword OR keyword OR …
        pattern = "|".join(re.escape(k) for k in keywords)

        matched = [
            p for p in relevant_posts
            if re.search(pattern, f"{p.get('title','')} {p.get('body','')}".lower())
        ]

        if not matched:
            feature_results.append(_zero_result(name, description))
            continue

        buyer_posts = [p for p in matched if p.get("buying_signals")]
        eval_posts = [p for p in matched if p.get("evaluation_signals")]
        buyer_readiness = len(buyer_posts) / len(matched)
        eval_fraction = len(eval_posts) / len(matched)
        pain_intensity = sum(p.get("relevance_score", 0) for p in matched) / len(matched)

        # Competitors mentioned in posts about this feature
        comp_counter: Counter = Counter()
        for p in matched:
            for c in p.get("competitors_mentioned", []):
                comp_counter[c] += 1

        # Top quotes by relevance
        top = sorted(matched, key=lambda p: p.get("relevance_score", 0), reverse=True)
        quotes = [p["title"] for p in top[:3]]

        # Buying signal posts — verbatim titles for the report
        buyer_quotes = [p["title"] for p in buyer_posts[:2]]

        # priority_score: demand (40%) + buyer readiness (40%) + pain intensity (20%)
        demand_score = len(matched) / total_relevant
        priority_score = demand_score * 0.4 + buyer_readiness * 0.4 + pain_intensity * 0.2

        feature_results.append({
            "name": name,
            "description": description,
            "matched_posts": len(matched),
            "demand_score": round(demand_score, 3),
            "buyer_readiness": round(buyer_readiness, 3),
            "eval_fraction": round(eval_fraction, 3),
            "pain_intensity": round(pain_intensity, 3),
            "competitors_in_context": [c for c, _ in comp_counter.most_common(4)],
            "representative_quotes": quotes,
            "buyer_quotes": buyer_quotes,
            "priority_score": round(priority_score, 3),
        })

    # Sort by priority and add rank
    feature_results.sort(key=lambda f: f["priority_score"], reverse=True)
    for rank, f in enumerate(feature_results, 1):
        f["priority_rank"] = rank

    # ---- Dead weight: 0 matched posts ------------------------------------------
    dead_weight = [f["name"] for f in feature_results if f["matched_posts"] == 0]

    # ---- White space: pain signals not covered by any feature keyword ----------
    all_feature_keywords: set[str] = set()
    for item in roadmap_items:
        for kw in item.get("keywords", []):
            # Add the keyword and each word in it
            all_feature_keywords.add(kw.lower().strip())
            all_feature_keywords.update(kw.lower().split())

    # Count pain signals across all relevant posts
    pain_counter: Counter = Counter()
    for p in relevant_posts:
        for sig in p.get("pain_signals", []):
            pain_counter[sig.lower()] += 1

    white_space: list[dict] = []
    for signal, freq in pain_counter.most_common(25):
        # Skip if any word in the signal matches a feature keyword
        signal_words = set(re.sub(r"[^a-z0-9 ]", "", signal).split())
        if signal_words & all_feature_keywords:
            continue

        # Find posts containing this signal
        ws_posts = [
            p for p in relevant_posts
            if signal in f"{p.get('title','')} {p.get('body','')}".lower()
        ]
        if not ws_posts:
            continue

        ws_buyer_readiness = (
            sum(1 for p in ws_posts if p.get("buying_signals")) / len(ws_posts)
        )
        ws_avg_relevance = sum(p.get("relevance_score", 0) for p in ws_posts) / len(ws_posts)

        # Competitor tools seen alongside this unaddressed pain
        ws_competitors: Counter = Counter()
        for p in ws_posts:
            for c in p.get("competitors_mentioned", []):
                ws_competitors[c] += 1

        white_space.append({
            "pain_theme": signal,
            "frequency": freq,
            "sample_posts": [p["title"] for p in ws_posts[:3]],
            "buyer_readiness": round(ws_buyer_readiness, 2),
            "avg_relevance": round(ws_avg_relevance, 2),
            "competitors_seen": [c for c, _ in ws_competitors.most_common(3)],
        })
        if len(white_space) >= 8:
            break

    return {
        "total_relevant_posts": total_relevant,
        "features": feature_results,
        "white_space": white_space,
        "dead_weight": dead_weight,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_roadmap_report(validation: dict, metadata: dict | None = None) -> str:
    """Produce an actionable Markdown report from a validate_roadmap() result."""
    meta = metadata or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    features = validation.get("features", [])
    white_space = validation.get("white_space", [])
    dead_weight = validation.get("dead_weight", [])
    total = validation.get("total_relevant_posts", 0)

    lines: list[str] = [
        "# Roadmap Validation Report",
        f"*Generated {now}*",
        "",
        f"Cross-referenced **{len(features)} planned features** against "
        f"**{total} relevant Reddit posts** to measure real-world demand.",
        "",
        "---",
        "",
        "## Feature Priority Ranking",
        "",
        "Ranked by composite score: demand (40%) + buyer readiness (40%) + pain intensity (20%).",
        "",
        "| # | Feature | Posts | Demand | Buyer Readiness | Pain Intensity | Score |",
        "|---|---------|-------|--------|----------------|----------------|-------|",
    ]

    for f in features:
        rank = f["priority_rank"]
        demand_pct = f"{f['demand_score']:.0%}"
        buyer_pct = f"{f['buyer_readiness']:.0%}"
        pain_pct = f"{f['pain_intensity']:.0%}"
        score_pct = f"{f['priority_score']:.0%}"
        flag = " ⚡" if f["buyer_readiness"] >= 0.3 else ""
        lines.append(
            f"| {rank} | {f['name']}{flag} | {f['matched_posts']} | "
            f"{demand_pct} | {buyer_pct} | {pain_pct} | {score_pct} |"
        )

    lines += [
        "",
        "*⚡ = ≥30% of matching posts have active buying signals (renewal / trial / RFP / budget)*",
        "",
        "---",
        "",
        "## Feature Detail",
        "",
    ]

    for f in features:
        if f["matched_posts"] == 0:
            continue

        lines += [
            f"### {f['priority_rank']}. {f['name']}",
            "",
            f"*{f['description']}*",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Matching posts | {f['matched_posts']} of {total} relevant posts "
            f"({f['demand_score']:.0%} demand) |",
            f"| Buyer readiness | {f['buyer_readiness']:.0%} — posts with active buying signals |",
            f"| Evaluation intent | {f['eval_fraction']:.0%} — posts actively comparing tools |",
            f"| Pain intensity | {f['pain_intensity']:.0%} avg relevance score |",
        ]

        if f.get("competitors_in_context"):
            comps = ", ".join(f.get("competitors_in_context", []))
            lines.append(f"| Competitors in context | {comps} |")

        lines.append("")

        if f.get("representative_quotes"):
            lines.append("**What people are saying:**")
            for q in f["representative_quotes"]:
                lines.append(f"- *\"{q}\"*")
            lines.append("")

        if f.get("buyer_quotes"):
            lines.append("**Active buyers (renewal / budget / RFP signals):**")
            for q in f["buyer_quotes"]:
                lines.append(f"- *\"{q}\"*")
            lines.append("")

        if f.get("competitors_in_context"):
            lines += [
                "**Competitive differentiation opportunity:**",
                f"Users evaluating this pain space are also mentioning "
                f"{', '.join(f['competitors_in_context'][:2])}. "
                "These are in-market prospects already familiar with the category.",
                "",
            ]

        lines.append("---")
        lines.append("")

    # ---- White space -----------------------------------------------------------
    if white_space:
        lines += [
            "## White Space — Unaddressed Pain Themes",
            "",
            "These pain signals appear frequently in the Reddit data but are **not covered "
            "by any feature on your current roadmap**. Consider them for future sprints or "
            "as messaging hooks even if you solve them indirectly.",
            "",
        ]
        for ws in white_space:
            buyer_flag = " ⚡" if ws["buyer_readiness"] >= 0.25 else ""
            lines += [
                f"### \"{ws['pain_theme']}\"{buyer_flag}",
                "",
                f"- **Frequency:** {ws['frequency']} posts · "
                f"**Buyer readiness:** {ws['buyer_readiness']:.0%} · "
                f"**Avg relevance:** {ws['avg_relevance']:.0%}",
            ]
            if ws.get("competitors_seen"):
                lines.append(f"- **Competitors seen:** {', '.join(ws['competitors_seen'])}")
            if ws.get("sample_posts"):
                lines.append("- **Sample posts:**")
                for sp in ws["sample_posts"]:
                    lines.append(f"  - *\"{sp}\"*")
            lines.append("")

    # ---- Dead weight -----------------------------------------------------------
    if dead_weight:
        lines += [
            "## Dead Weight — Features With No Signal",
            "",
            "These planned features had **zero matching posts** in the Reddit data. "
            "This doesn't mean they're wrong — it may mean the pain is expressed differently, "
            "the audience uses different terms, or it's a supply-side capability users don't "
            "yet know to ask for. Worth investigating before investing significant engineering time.",
            "",
        ]
        for name in dead_weight:
            lines.append(f"- {name}")
        lines.append("")

    # ---- Recommendations -------------------------------------------------------
    top_features = [f for f in features if f["matched_posts"] > 0][:3]
    lines += [
        "---",
        "",
        "## Recommended Actions",
        "",
    ]
    if top_features:
        lines.append("**Build / accelerate these first (highest validated demand):**")
        for f in top_features:
            br = f"— {f['buyer_readiness']:.0%} buyer readiness" if f["buyer_readiness"] > 0 else ""
            lines.append(f"1. **{f['name']}** ({f['matched_posts']} posts {br})")
        lines.append("")

    if white_space:
        top_ws = sorted(white_space, key=lambda w: w["buyer_readiness"], reverse=True)[:2]
        lines.append("**Explore these white-space opportunities:**")
        for ws in top_ws:
            lines.append(
                f"- **\"{ws['pain_theme']}\"** — {ws['frequency']} posts, "
                f"{ws['buyer_readiness']:.0%} buyer readiness"
            )
        lines.append("")

    if dead_weight:
        lines.append(
            f"**Re-examine these before building** "
            f"(no Reddit signal found): {', '.join(dead_weight)}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _zero_result(name: str, description: str) -> dict:
    return {
        "name": name,
        "description": description,
        "matched_posts": 0,
        "demand_score": 0.0,
        "buyer_readiness": 0.0,
        "eval_fraction": 0.0,
        "pain_intensity": 0.0,
        "competitors_in_context": [],
        "representative_quotes": [],
        "buyer_quotes": [],
        "priority_score": 0.0,
    }
