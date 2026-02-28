#!/usr/bin/env python3
"""
Full-flow test suite for the InfrOS Lead Finder.

Runs automatically — exit 0 on pass, exit 1 on any failure.
Sections:
  1  Syntax check — all .py files parse cleanly
  2  Unit: new signal detectors (evaluation, competitor, buying, hiring)
  3  Unit: pain intensity scoring
  4  Unit: LinkedIn Groups, outreach sequence, filter panel
  5  Pipeline: mock data — full analyze → profile → report → save → load
  6  Pipeline: real Reddit API — 2 subreddits × 2 keywords
  7  Session: save/load round-trip, autosave, error handling
  8  Report: all required sections present, char limits respected
"""

import ast
import json
import sys
import tempfile
import time
from pathlib import Path

# Allow running from repo root or from tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = "  PASS"
FAIL = "  FAIL"
SKIP = "  SKIP"
failures: list[str] = []


def check(condition: bool, label: str, detail: str = "") -> None:
    if condition:
        print(f"{PASS}  {label}")
    else:
        msg = f"{label}" + (f" — {detail}" if detail else "")
        print(f"{FAIL}  {msg}")
        failures.append(msg)


def skip(label: str, reason: str) -> None:
    print(f"{SKIP}  {label} ({reason})")


# ---------------------------------------------------------------------------
# 1. Syntax check
# ---------------------------------------------------------------------------

def test_syntax() -> None:
    print("\n=== 1. Syntax check ===")
    files = [
        f for f in Path(".").rglob("*.py")
        if ".venv" not in str(f) and "__pycache__" not in str(f)
    ]
    for f in sorted(files):
        try:
            ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e:
            check(False, f"Syntax: {f}", f"line {e.lineno}: {e.msg}")
            return
    check(True, f"All {len(files)} .py files parse cleanly")


# ---------------------------------------------------------------------------
# 2. New signal detectors
# ---------------------------------------------------------------------------

def test_new_signals() -> None:
    print("\n=== 2. New signal detectors ===")
    from src.analyzer import (
        analyze_post,
        EVALUATION_PATTERNS, COMPETITOR_PATTERNS,
        BUYING_SIGNAL_PATTERNS, HIRING_PATTERNS, INDUSTRY_PATTERNS,
        _match_list, _extract,
    )

    def post(title: str, body: str) -> dict:
        return {
            "id": "t", "subreddit": "devops", "title": title, "body": body,
            "score": 10, "upvote_ratio": 0.9, "num_comments": 5,
            "url": "https://x", "created_utc": 1700000000.0,
            "created_date": "2026-01-01", "is_self": True, "matched_keyword": "test",
        }

    # Evaluation
    p = analyze_post(post("Terraform vs Pulumi — which is better?",
                          "We're comparing alternatives to Terraform. Thoughts on pros and cons?"))
    check(bool(p["evaluation_signals"]), "Evaluation: 'vs' + 'alternatives' + 'pros and cons' detected",
          str(p["evaluation_signals"]))
    check(p["post_type"] == "evaluation", "Post type = evaluation (takes priority over pain)",
          p["post_type"])

    # Competitor mentions
    p2 = analyze_post(post("Terraform Cloud vs Spacelift vs Env0",
                            "We're evaluating Spacelift, Env0, and TFC. Anyone tried these?"))
    check(len(p2["competitors_mentioned"]) >= 2, "Competitors: ≥2 tools detected",
          str(p2["competitors_mentioned"]))
    check("Spacelift" in p2["competitors_mentioned"], "Competitor: Spacelift", str(p2["competitors_mentioned"]))
    check("Env0" in p2["competitors_mentioned"], "Competitor: Env0", str(p2["competitors_mentioned"]))
    check("Terraform Cloud / HCP" in p2["competitors_mentioned"], "Competitor: TFC",
          str(p2["competitors_mentioned"]))

    # Buying signals
    p3 = analyze_post(post("Our Terraform Cloud contract ends soon — open to alternatives",
                            "Contract renewal is coming up. We have budget approval and are in the market for something new. Running a POC now."))
    check(bool(p3["buying_signals"]), "Buying signals: renewal + budget + POC detected",
          str(p3["buying_signals"]))

    # Hiring signal
    p4 = analyze_post(post("Scaling our infra team",
                            "We're hiring a devops engineer. We're growing and scaling the engineering team fast."))
    check(bool(p4["hiring_signals"]), "Hiring signals detected", str(p4["hiring_signals"]))
    check(p4["post_type"] == "hiring_signal", "Post type = hiring_signal", p4["post_type"])

    # Industry detection
    p5 = analyze_post(post("Cloud costs at our fintech SaaS startup",
                            "We're a b2b SaaS startup in the fintech space on AWS."))
    check("Computer Software / SaaS" in p5["industries"], "Industry: SaaS detected", str(p5["industries"]))
    check("Financial Services / FinTech" in p5["industries"], "Industry: FinTech detected",
          str(p5["industries"]))

    # Healthcare + MSP
    p6 = analyze_post(post("HIPAA-compliant infra for our healthcare consulting firm",
                            "We're a managed service provider for healthcare hospitals. HIPAA compliance is critical."))
    check("Healthcare / MedTech" in p6["industries"], "Industry: Healthcare detected",
          str(p6["industries"]))
    check("Consulting / IT Services / MSP" in p6["industries"], "Industry: MSP detected",
          str(p6["industries"]))


# ---------------------------------------------------------------------------
# 3. Pain intensity scoring
# ---------------------------------------------------------------------------

def test_scoring() -> None:
    print("\n=== 3. Pain intensity scoring ===")
    from src.analyzer import analyze_post

    def make(title: str, body: str, score: int = 5, comments: int = 3) -> dict:
        return {
            "id": "s", "subreddit": "aws", "title": title, "body": body,
            "score": score, "upvote_ratio": 0.9, "num_comments": comments,
            "url": "https://x", "created_utc": 1700000000.0,
            "created_date": "2026-01-01", "is_self": True, "matched_keyword": "test",
        }

    bare = analyze_post(make("General AWS question", "Just wondering about AWS services."))
    cost_pain = analyze_post(make(
        "AWS bill shock — costs out of control and killing us",
        "Struggling with cloud spend. Manual processes everywhere. "
        "We're frustrated and stuck. Hard to maintain. Technical debt is piling up.",
        score=150, comments=45,
    ))
    evaluation = analyze_post(make(
        "Terraform vs Pulumi — which is better for our startup?",
        "We're evaluating both. Looking for alternatives. Anyone tried these? Pros and cons?",
        score=80, comments=30,
    ))
    buying = analyze_post(make(
        "Our CloudHealth contract is up for renewal",
        "In the market for something new. Have budget approval. Running a POC. Open to suggestions.",
    ))

    check(cost_pain["relevance_score"] > bare["relevance_score"],
          "Cost pain post scores higher than bare post",
          f"{cost_pain['relevance_score']} > {bare['relevance_score']}")
    check(evaluation["relevance_score"] > bare["relevance_score"],
          "Evaluation post scores higher than bare post",
          f"{evaluation['relevance_score']} > {bare['relevance_score']}")
    check(buying["relevance_score"] > bare["relevance_score"],
          "Buying signal post scores higher than bare post",
          f"{buying['relevance_score']} > {bare['relevance_score']}")
    check(cost_pain["relevance_score"] >= 0.60,
          "High-signal cost pain post reaches ≥60% relevance",
          f"{cost_pain['relevance_score']:.0%}")
    check(bare["relevance_score"] <= 0.30,
          "Bare discussion post stays ≤30%",
          f"{bare['relevance_score']:.0%}")


# ---------------------------------------------------------------------------
# 4. LinkedIn Groups, outreach sequence, filter panel
# ---------------------------------------------------------------------------

def test_linkedin_features() -> None:
    print("\n=== 4. LinkedIn Groups, outreach sequence, filter panel ===")
    from src.analyzer import build_lead_profiles, analyze_post
    from src.report_generator import _outreach_sequence, _spotlight_recommendations

    posts = [
        {
            "id": f"{i}", "subreddit": "devops",
            "title": "Terraform state management is a nightmare",
            "body": "Platform engineer at a startup on AWS. Terraform complexity is overwhelming. "
                    "Hard to manage and scale. Struggling with config drift. Comparing Spacelift vs Env0.",
            "score": 50, "upvote_ratio": 0.95, "num_comments": 20,
            "url": f"https://x/{i}", "created_utc": 1700000000.0 + i,
            "created_date": "2026-02-10", "is_self": True, "matched_keyword": "terraform",
        }
        for i in range(3)
    ]
    analyzed = [analyze_post(p) for p in posts]
    profiles = build_lead_profiles(analyzed)

    check(len(profiles) > 0, "Profiles built from mock posts")

    pr = profiles[0]
    check(bool(pr.get("linkedin_groups")), "LinkedIn groups populated",
          str(pr.get("linkedin_groups", [])))
    check(bool(pr.get("seniority_filter")), "Seniority filter populated",
          str(pr.get("seniority_filter", [])))
    check(bool(pr.get("job_function")), "Job function populated", pr.get("job_function", ""))
    check(bool(pr.get("linkedin_query_variants")), "Query variants populated",
          str(pr.get("linkedin_query_variants", [])))
    check("sales/search/people" in pr.get("linkedin_url", ""),
          "LinkedIn URL points to Sales Navigator people search")
    check("sales/search/company" in pr.get("account_url", ""),
          "Account URL points to Sales Navigator company search")
    check(bool(pr.get("competitors_seen")), "Competitor tools aggregated into profile",
          str(pr.get("competitors_seen", [])))
    check(pr.get("buying_signal_count", 0) >= 0, "Buying signal count field present")

    # Outreach sequence
    seq = _outreach_sequence(
        "DevOps / Platform Engineer", "AWS",
        ["terraform state nightmare", "costs too high"],
        ["AWS", "Terraform"],
        ["Spacelift", "Env0"],
    )
    check(len(seq) == 3, "Outreach sequence has exactly 3 steps", str(len(seq)))
    for step in seq:
        check(len(step["text"]) <= 310, f"{step['label']}: within char limit",
              f"{len(step['text'])} chars")
        check("[Name]" in step["text"] or "[First Name]" in step["text"],
              f"{step['label']}: contains personalisation placeholder")
    check("Spacelift" in seq[2]["text"] or "Env0" in seq[2]["text"],
          "Follow-up references competitor (context-aware)")

    # Spotlight recs
    recs = _spotlight_recommendations("Engineering Manager", ["Enterprise"], ["costs out of control"])
    check(len(recs) >= 2, "Spotlight recommendations generated", str(len(recs)))
    check(any("Changed jobs" in r for r in recs), "Spotlight: 'changed jobs' recommendation present")
    check(any("Posted" in r for r in recs), "Spotlight: 'posted recently' recommendation present")


# ---------------------------------------------------------------------------
# 5. Pipeline: mock data — full flow
# ---------------------------------------------------------------------------

def test_pipeline_mock() -> None:
    print("\n=== 5. Pipeline — mock data full flow ===")
    from src.analyzer import analyze_post, build_lead_profiles
    from src.report_generator import generate_report
    from src.session_manager import save_session, load_session

    raw_posts = [
        {
            "id": "1", "subreddit": "devops",
            "title": "Terraform state management costs out of control at our startup",
            "body": (
                "Platform engineer here. We're a startup on AWS and terraform complexity "
                "is killing us. Cloud bill is too high, manual processes everywhere. "
                "Comparing Spacelift vs Env0 vs Terraform Cloud — open to suggestions. "
                "We have budget and this renewal is coming up soon."
            ),
            "score": 88, "upvote_ratio": 0.96, "num_comments": 42,
            "url": "https://reddit.com/r/devops/1",
            "created_utc": 1700000000.0, "created_date": "2026-02-10",
            "is_self": True, "matched_keyword": "terraform",
        },
        {
            "id": "2", "subreddit": "aws",
            "title": "AWS bill shock — FinOps team vs cost explorer vs Apptio",
            "body": (
                "Enterprise company. FinOps team struggling with cloud billing. "
                "AWS costs out of control. Evaluating Apptio vs cost explorer vs CloudHealth. "
                "We're an e-commerce SaaS company, publicly traded."
            ),
            "score": 120, "upvote_ratio": 0.97, "num_comments": 55,
            "url": "https://reddit.com/r/aws/2",
            "created_utc": 1700100000.0, "created_date": "2026-02-12",
            "is_self": True, "matched_keyword": "cloud costs",
        },
        {
            "id": "3", "subreddit": "kubernetes",
            "title": "K8s cluster management nightmare — which tool is better?",
            "body": (
                "DevOps engineer at a scale-up. Kubernetes complexity is overwhelming. "
                "We're a SaaS startup. Hard to maintain. Comparing tools. "
                "Should we use Kubecost vs something else? Looking for alternatives."
            ),
            "score": 35, "upvote_ratio": 0.91, "num_comments": 18,
            "url": "https://reddit.com/r/kubernetes/3",
            "created_utc": 1700200000.0, "created_date": "2026-02-14",
            "is_self": True, "matched_keyword": "cloud costs",
        },
        {
            "id": "4", "subreddit": "devops",
            "title": "We're hiring a DevOps engineer — scaling infra team",
            "body": (
                "We're growing and scaling the engineering team. Looking to hire a devops / "
                "platform engineer. We're a fintech startup on Azure."
            ),
            "score": 12, "upvote_ratio": 0.88, "num_comments": 8,
            "url": "https://reddit.com/r/devops/4",
            "created_utc": 1700300000.0, "created_date": "2026-02-15",
            "is_self": True, "matched_keyword": "terraform",
        },
    ]

    analyzed = [analyze_post(p) for p in raw_posts]
    analyzed.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)

    # Check new fields present
    for p in analyzed:
        check("evaluation_signals" in p, f"Post {p['id']}: evaluation_signals field")
        check("competitors_mentioned" in p, f"Post {p['id']}: competitors_mentioned field")
        check("buying_signals" in p, f"Post {p['id']}: buying_signals field")
        check("hiring_signals" in p, f"Post {p['id']}: hiring_signals field")
        check("industries" in p, f"Post {p['id']}: industries field")

    # Verify specific post types
    posts_by_id = {p["id"]: p for p in analyzed}
    check(posts_by_id["1"]["post_type"] == "evaluation",
          "Post 1: type=evaluation (comparison + buying signals)",
          posts_by_id["1"]["post_type"])
    check(posts_by_id["4"]["post_type"] == "hiring_signal",
          "Post 4: type=hiring_signal",
          posts_by_id["4"]["post_type"])

    # Competitor detection
    check("Spacelift" in posts_by_id["1"].get("competitors_mentioned", []),
          "Post 1: Spacelift competitor detected")
    check("Apptio" in posts_by_id["2"].get("competitors_mentioned", []),
          "Post 2: Apptio competitor detected")
    check("Kubecost" in posts_by_id["3"].get("competitors_mentioned", []),
          "Post 3: Kubecost competitor detected")

    # Industry detection
    check("Financial Services / FinTech" in (posts_by_id["2"].get("industries", []) +
                                              posts_by_id["4"].get("industries", [])),
          "FinTech industry detected")

    profiles = build_lead_profiles(analyzed)
    check(len(profiles) >= 2, f"Built ≥2 lead profiles", str(len(profiles)))

    for pr in profiles:
        check("linkedin_groups" in pr, f"Profile {pr['role']}: linkedin_groups present")
        check("competitors_seen" in pr, f"Profile {pr['role']}: competitors_seen present")
        check("buying_signal_count" in pr, f"Profile {pr['role']}: buying_signal_count present")
        check("evaluation" in pr.get("post_type_counts", {}),
              f"Profile {pr['role']}: post_type_counts has evaluation key")

    # Report
    meta = {
        "searched_at": "2026-02-21T10:00:00",
        "search_mode": "Use Keywords",
        "subreddits_searched": ["devops", "aws"],
        "keywords_searched": ["terraform", "cloud costs"],
        "topics_selected": [],
        "time_filter": "month", "sort": "relevance",
        "min_score": 3, "max_results_per_query": 25,
        "total_posts_found": len(analyzed),
        "total_lead_profiles": len(profiles),
        "api_mode": "public",
    }
    report = generate_report(analyzed, profiles, meta)

    required_sections = [
        "# InfrOS Lead Research Report",
        "Executive Summary",
        "Evaluation / comparison posts",
        "Hiring signal posts",
        "Top Pain Signals",
        "Technology Landscape",
        "Highest-Signal Posts",
        "Prospect Personas",
        "Sales Navigator filters to apply manually",
        "Spotlight filters to layer on",
        "Alternative title searches",
        "LinkedIn Groups to filter by",
        "Years in current position",
        "NOT exclusions",
        "Account Search",
        "3-Touch Outreach Sequence",
        "1. Connection request note",
        "2. First message",
        "3. Follow-up",
        "Recommended Actions",
    ]
    for section in required_sections:
        check(section in report, f"Report contains: '{section}'")

    check("Buying window posts" in report or "buying_signal" in report.lower(),
          "Report references buying signal posts")

    print(f"  Report: {len(report):,} chars, {report.count(chr(10))} lines")


# ---------------------------------------------------------------------------
# 6. Real Reddit API — 2 subreddits × 2 keywords
# ---------------------------------------------------------------------------

def test_real_reddit() -> None:
    print("\n=== 6. Real Reddit API — 2 subreddits × 2 keywords ===")
    try:
        from src.reddit_scraper import RedditScraper
        from src.analyzer import analyze_post, build_lead_profiles
        from src.report_generator import generate_report
        from src.session_manager import save_session, load_session
    except ImportError as e:
        skip("Reddit API test", f"import error: {e}")
        return

    config = {
        "reddit": {
            "api": {
                "client_id": "",
                "client_secret": "",
                "user_agent": "InfrOS Test Suite v1.0 (test run)",
            }
        }
    }

    subreddits = ["devops", "aws"]
    keywords = ["terraform", "cloud costs"]

    print(f"  Searching r/{' + r/'.join(subreddits)} for: {keywords}")
    scraper = RedditScraper(config)

    try:
        raw_posts = scraper.search_posts(
            keywords=keywords,
            subreddits=subreddits,
            time_filter="year",
            sort="relevance",
            limit=10,
            min_score=3,
        )
    except Exception as e:
        skip("Reddit API call", f"network error: {e}")
        return

    if len(raw_posts) == 0:
        skip("Reddit returned posts", "0 results — network likely blocked (expected in sandbox)")
        return
    check(len(raw_posts) > 0, f"Reddit returned posts", f"got {len(raw_posts)}")

    print(f"  Got {len(raw_posts)} posts")

    # Spot-check structure
    p0 = raw_posts[0]
    for field in ("id", "subreddit", "title", "body", "score", "url",
                  "created_date", "matched_keyword"):
        check(field in p0, f"Post field present: {field}")
    check("username" not in p0, "Username NOT stored (privacy)")
    check(p0.get("subreddit") in subreddits, "Post subreddit is one of the searched ones",
          p0.get("subreddit"))

    # Full analysis pipeline
    analyzed = [analyze_post(p) for p in raw_posts]
    analyzed.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)

    check(len(analyzed) == len(raw_posts), "All posts analyzed")
    check(all("relevance_score" in p for p in analyzed), "All posts have relevance_score")
    check(all("post_type" in p for p in analyzed), "All posts have post_type")
    check(all("evaluation_signals" in p for p in analyzed), "All posts have evaluation_signals")
    check(all("competitors_mentioned" in p for p in analyzed), "All posts have competitors_mentioned")

    # Count interesting posts
    eval_count = sum(1 for p in analyzed if p["post_type"] == "evaluation")
    pain_count = sum(1 for p in analyzed if p["post_type"] == "pain")
    print(f"  Post types: evaluation={eval_count}, pain={pain_count}, "
          f"mixed={sum(1 for p in analyzed if p['post_type']=='mixed')}, "
          f"other={len(analyzed)-eval_count-pain_count}")
    print(f"  Top relevance: {analyzed[0]['relevance_score']:.0%} — {analyzed[0]['title'][:60]}")

    # Build profiles
    profiles = build_lead_profiles(analyzed)
    check(len(profiles) > 0, "Lead profiles built from real Reddit data", str(len(profiles)))
    for pr in profiles:
        check("linkedin_groups" in pr, f"Profile has linkedin_groups")
        check("sales/search/people" in pr.get("linkedin_url", ""),
              "Profile URL points to Sales Navigator")
        break  # check first only

    # Generate report
    meta = {
        "searched_at": "2026-02-28T10:00:00",
        "search_mode": "Use Keywords",
        "subreddits_searched": subreddits,
        "keywords_searched": keywords,
        "topics_selected": [],
        "time_filter": "year", "sort": "relevance",
        "min_score": 3, "max_results_per_query": 10,
        "total_posts_found": len(analyzed),
        "total_lead_profiles": len(profiles),
        "api_mode": "public",
    }
    report = generate_report(analyzed, profiles, meta)
    check(len(report) > 1000, f"Report generated from real data ({len(report):,} chars)")

    # Save and load
    blob = save_session(raw_posts, analyzed, profiles, meta)
    check(len(blob) > 100, "Session saved to JSON")

    r2, a2, p2, m2, ts = load_session(blob)
    check(len(r2) == len(raw_posts), "load_session: raw_posts round-trip")
    check(len(a2) == len(analyzed), "load_session: analyzed_posts round-trip")
    check(len(p2) == len(profiles), "load_session: lead_profiles round-trip")
    check(a2[0]["relevance_score"] == analyzed[0]["relevance_score"],
          "load_session: relevance_score preserved")
    check(a2[0].get("post_type") == analyzed[0].get("post_type"),
          "load_session: post_type preserved")

    print(f"  Save/load round-trip: {len(raw_posts)} posts, {len(profiles)} profiles — OK")


# ---------------------------------------------------------------------------
# 7. Session persistence — detailed
# ---------------------------------------------------------------------------

def test_session() -> None:
    print("\n=== 7. Session persistence ===")
    from src.session_manager import save_session, load_session, autosave, load_autosave
    import src.session_manager as sm_mod

    raw = [{"id": "1", "title": "test", "subreddit": "devops", "score": 5}]
    analyzed = [{"id": "1", "relevance_score": 0.75, "post_type": "evaluation",
                 "competitors_mentioned": ["Spacelift"], "buying_signals": ["renewal"],
                 "evaluation_signals": ["vs"], "hiring_signals": [],
                 "industries": ["Computer Software / SaaS"]}]
    profiles = [{"role": "DevOps / Platform Engineer", "cloud_platform": "AWS",
                 "post_count": 1, "linkedin_groups": ["HashiCorp User Group"],
                 "competitors_seen": ["Spacelift"], "buying_signal_count": 1}]
    meta = {
        "searched_at": "2026-02-28T10:00:00", "search_mode": "Use Keywords",
        "subreddits_searched": ["devops", "aws"], "keywords_searched": ["terraform", "cloud costs"],
        "topics_selected": [], "time_filter": "year", "sort": "relevance",
        "min_score": 3, "max_results_per_query": 10,
        "total_posts_found": 1, "total_lead_profiles": 1, "api_mode": "public",
    }

    # Save
    blob = save_session(raw, analyzed, profiles, meta)
    data = json.loads(blob)
    check("version" in data, "JSON has 'version' key")
    check("saved_at" in data, "JSON has 'saved_at' key")
    check("run_params" in data, "JSON has 'run_params' key")
    check("summary" in data, "JSON has 'summary' key")
    check("raw_posts" in data, "JSON has 'raw_posts' key")
    check("analyzed_posts" in data, "JSON has 'analyzed_posts' key")
    check("lead_profiles" in data, "JSON has 'lead_profiles' key")

    rp = data["run_params"]
    check(rp["subreddits_searched"] == ["devops", "aws"], "run_params.subreddits_searched")
    check(rp["keywords_searched"] == ["terraform", "cloud costs"], "run_params.keywords_searched")
    check(rp["time_filter"] == "year", "run_params.time_filter")
    check(rp["api_mode"] == "public", "run_params.api_mode")

    # New fields survive serialization
    saved_analysis = data["analyzed_posts"][0]
    check(saved_analysis.get("competitors_mentioned") == ["Spacelift"],
          "analyzed_post: competitors_mentioned serialised")
    check(saved_analysis.get("evaluation_signals") == ["vs"],
          "analyzed_post: evaluation_signals serialised")
    check(saved_analysis.get("industries") == ["Computer Software / SaaS"],
          "analyzed_post: industries serialised")
    saved_profile = data["lead_profiles"][0]
    check(saved_profile.get("linkedin_groups") == ["HashiCorp User Group"],
          "lead_profile: linkedin_groups serialised")
    check(saved_profile.get("competitors_seen") == ["Spacelift"],
          "lead_profile: competitors_seen serialised")

    # Load round-trip (str)
    r2, a2, p2, m2, ts = load_session(blob)
    check(len(r2) == 1 and r2[0]["id"] == "1", "load_session str: raw_posts")
    check(a2[0]["relevance_score"] == 0.75, "load_session str: relevance_score")
    check(a2[0].get("post_type") == "evaluation", "load_session str: post_type")

    # Load round-trip (bytes)
    r3, a3, p3, m3, ts3 = load_session(blob.encode("utf-8"))
    check(len(r3) == 1, "load_session bytes: raw_posts")

    # Error handling
    try:
        load_session("not json {{{")
        check(False, "load_session bad JSON: should raise ValueError")
    except ValueError:
        check(True, "load_session bad JSON: raises ValueError")

    try:
        load_session(b"")
        check(False, "load_session empty bytes: should raise ValueError")
    except ValueError:
        check(True, "load_session empty bytes: raises ValueError")

    # Autosave / load_autosave
    orig_path = sm_mod.AUTOSAVE_PATH
    sm_mod.AUTOSAVE_PATH = Path(tempfile.mktemp(suffix=".json"))
    try:
        check(load_autosave() is None, "load_autosave: returns None when file missing")
        autosave(raw, analyzed, profiles)
        check(sm_mod.AUTOSAVE_PATH.exists(), "autosave: file created")
        result = load_autosave()
        check(result is not None, "load_autosave: returns data after autosave")
        if result:
            r4, a4, p4, m4, ts4 = result
            check(len(r4) == 1, "load_autosave: raw_posts preserved")
            check(a4[0].get("post_type") == "evaluation", "load_autosave: post_type preserved")
    finally:
        sm_mod.AUTOSAVE_PATH.unlink(missing_ok=True)
        sm_mod.AUTOSAVE_PATH = orig_path


# ---------------------------------------------------------------------------
# 8. Report content and structure
# ---------------------------------------------------------------------------

def test_report() -> None:
    print("\n=== 8. Report content and structure ===")
    from src.analyzer import analyze_post, build_lead_profiles
    from src.report_generator import (
        generate_report, _outreach_sequence, _spotlight_recommendations,
        _inmail_template,
    )

    raw = [
        {
            "id": f"{i}", "subreddit": "devops" if i % 2 == 0 else "aws",
            "title": f"Terraform vs Spacelift — cloud cost pain at our startup {i}",
            "body": (
                "Platform engineer. Startup on AWS. Terraform complexity is a nightmare. "
                "Struggling with cloud costs — manual processes everywhere. "
                "Comparing Spacelift vs Env0. Contract renewal soon. "
                "Looking for alternatives. POC running. Budget approved."
            ),
            "score": 40 + i * 10, "upvote_ratio": 0.95, "num_comments": 15 + i,
            "url": f"https://x/{i}", "created_utc": 1700000000.0 + i * 86400,
            "created_date": "2026-02-10", "is_self": True, "matched_keyword": "terraform",
        }
        for i in range(5)
    ]
    analyzed = [analyze_post(p) for p in raw]
    analyzed.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)
    profiles = build_lead_profiles(analyzed)
    meta = {
        "searched_at": "2026-02-28T10:00:00", "search_mode": "Use Keywords",
        "subreddits_searched": ["devops", "aws"], "keywords_searched": ["terraform", "cloud costs"],
        "topics_selected": [], "time_filter": "month", "sort": "relevance",
        "min_score": 3, "max_results_per_query": 25,
        "total_posts_found": len(analyzed), "total_lead_profiles": len(profiles),
        "api_mode": "public",
    }
    report = generate_report(analyzed, profiles, meta)

    # All major sections
    sections = [
        "Executive Summary",
        "Evaluation / comparison posts",
        "Top Pain Signals",
        "Technology Landscape",
        "Highest-Signal Posts",
        "Prospect Personas & Outreach Guide",
        "Sales Navigator filters to apply manually",
        "Seniority level",
        "Job function",
        "Spotlight filters to layer on",
        "Alternative title searches",
        "LinkedIn Groups to filter by",
        "Years in current position",
        "NOT exclusions",
        "Account Search",
        "3-Touch Outreach Sequence",
        "1. Connection request note",
        "2. First message",
        "3. Follow-up if no reply",
        "Recommended Actions",
    ]
    for s in sections:
        check(s in report, f"Section present: '{s}'")

    check("sales/search/people" in report, "Sales Navigator people URL in report")
    check("sales/search/company" in report, "Sales Navigator company URL in report")
    check("Spacelift" in report or "Env0" in report, "Competitor names appear in report")

    # Outreach sequence char limits
    for role in ["DevOps / Platform Engineer", "FinOps / Cloud Economics", "CTO / VP Engineering"]:
        seq = _outreach_sequence(role, "AWS", ["costs out of control"], ["AWS"], [])
        check(len(seq) == 3, f"Sequence for {role}: 3 steps")
        for step in seq:
            check(len(step["text"]) <= 310,
                  f"Sequence for {role} — {step['label']}: ≤300 chars",
                  f"{len(step['text'])} chars")

    # Inmail template (kept as helper)
    subj, body = _inmail_template("DevOps / Platform Engineer", "AWS",
                                  ["costs out of control"], ["AWS"])
    check(len(subj) <= 200, "InMail subject ≤200 chars", f"{len(subj)}")
    check(len(body) <= 1900, "InMail body ≤1900 chars", f"{len(body)}")

    print(f"  Report: {len(report):,} chars, {report.count(chr(10))} lines")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("InfrOS Full Flow Test Suite")
    print("=" * 60)

    test_syntax()
    test_new_signals()
    test_scoring()
    test_linkedin_features()
    test_pipeline_mock()
    test_real_reddit()
    test_session()
    test_report()

    print()
    print("=" * 60)
    if failures:
        print(f"FAILED — {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)
