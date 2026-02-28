"""
Analyzer — extracts pain-point signals, role signals, tech-stack signals,
company-size, industry, evaluation-intent, competitor, buying-window, and
hiring signals from Reddit post text using rule-based pattern matching.

Deliberately does NOT identify or store individual users.  The output is
aggregated "prospect persona" data useful for LinkedIn search targeting.
"""

import re
import urllib.parse
from typing import Optional

# ---------------------------------------------------------------------------
# Signal pattern dictionaries
# ---------------------------------------------------------------------------

ROLE_PATTERNS: dict[str, list[str]] = {
    "DevOps / Platform Engineer": [
        r"\bdevops\b", r"\bdev ops\b", r"\bsite reliability\b", r"\bsre\b",
        r"\bplatform engineer", r"\binfrastructure engineer", r"\binfra engineer",
        r"\bdevsecops\b", r"\bplatform team\b",
    ],
    "Cloud Architect": [
        r"\bcloud architect\b", r"\bsolutions architect\b", r"\benterprise architect\b",
        r"\barchitecture team\b", r"\bcloud design\b",
    ],
    "Engineering Manager": [
        r"\bengineering manager\b", r"\beng manager\b", r"\bi manage\b",
        r"\bmy team of\b", r"\bhead of engineering\b", r"\bdirector of engineering\b",
        r"\bvp of engineering\b",
    ],
    "CTO / VP Engineering": [
        r"\bcto\b", r"\bchief technology officer\b", r"\bvp.*engineering\b",
        r"\bvp.*infrastructure\b", r"\bhead of tech\b",
    ],
    "FinOps / Cloud Economics": [
        r"\bfinops\b", r"\bcloud economist\b", r"\bcloud cost manager\b",
        r"\bcloud finance\b", r"\bcloud spend manager\b",
    ],
    "Systems / IT Admin": [
        r"\bsysadmin\b", r"\bsys admin\b", r"\bsystem administrator\b",
        r"\bit admin\b", r"\bnetwork admin\b",
    ],
    "Software Engineer": [
        r"\bsoftware engineer\b", r"\bsoftware developer\b", r"\bbackend engineer\b",
        r"\bfull.?stack\b", r"\bswe\b",
    ],
}

TECH_PATTERNS: dict[str, list[str]] = {
    "AWS": [r"\baws\b", r"\bamazon web services\b", r"\bec2\b", r"\bs3\b",
             r"\brds\b", r"\blambda\b", r"\beks\b", r"\biam\b", r"\bcloudwatch\b"],
    "Azure": [r"\bazure\b", r"\bmicrosoft azure\b", r"\baks\b", r"\bazure devops\b",
               r"\bazure functions\b"],
    "GCP": [r"\bgcp\b", r"\bgoogle cloud\b", r"\bgke\b", r"\bbigquery\b",
             r"\bcloud run\b", r"\bfirestore\b"],
    "Terraform": [r"\bterraform\b", r"\bhashicorp\b", r"\b\.tf\b", r"\btf state\b",
                   r"\bterragrunt\b"],
    "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b", r"\bkubectl\b", r"\bhelm\b",
                    r"\bkube\b"],
    "Pulumi": [r"\bpulumi\b"],
    "Ansible": [r"\bansible\b", r"\bplaybook\b"],
    "CloudFormation": [r"\bcloudformation\b", r"\bcfn\b", r"\bcdk\b"],
    "Docker": [r"\bdocker\b", r"\bcontainer\b", r"\bdocker.compose\b"],
    "GitHub Actions / CI-CD": [r"\bgithub actions\b", r"\bci.?cd\b", r"\bjenkins\b",
                                 r"\bgitlab ci\b", r"\bcircle.?ci\b"],
}

COMPANY_SIZE_PATTERNS: dict[str, list[str]] = {
    "Startup": [
        r"\bstartup\b", r"\bstart.?up\b", r"\bearly stage\b", r"\bseed stage\b",
        r"\bseries [ab]\b", r"\bbootstrap\b", r"\bsmall company\b", r"\bsmall team\b",
    ],
    "Scale-up / Mid-size": [
        r"\bscale.?up\b", r"\bgrowing company\b", r"\bseries [cde]\b",
        r"\bmid.?size\b", r"\bmid.?market\b", r"\bhundred.* employee",
    ],
    "Enterprise": [
        r"\benterprise\b", r"\bfortune \d+\b", r"\blarge company\b",
        r"\bglobal company\b", r"\bpublicly traded\b", r"\bthousands of employee",
    ],
}

INDUSTRY_PATTERNS: dict[str, list[str]] = {
    "Computer Software / SaaS": [
        r"\bsaas\b", r"\bb2b\b", r"\bsoftware company\b", r"\bsoftware startup\b",
        r"\bproduct company\b", r"\btech company\b", r"\btech startup\b",
        r"\bproduct.led\b",
    ],
    "Financial Services / FinTech": [
        r"\bfintech\b", r"\bbanking\b", r"\bfinancial services\b", r"\bpayments?\b",
        r"\binsurance\b", r"\binvestment\b", r"\btrading platform\b", r"\bcrypto\b",
        r"\bneobank\b",
    ],
    "E-commerce / Retail": [
        r"\becommerce\b", r"\be.commerce\b", r"\bshopify\b", r"\bretail\b",
        r"\bonline store\b", r"\bmarketplace\b", r"\bd2c\b",
    ],
    "Healthcare / MedTech": [
        r"\bhealthcare\b", r"\bhealth.?tech\b", r"\bhospital\b", r"\bhipaa\b",
        r"\bmedical\b", r"\bpharmaceutical\b", r"\bclinical\b", r"\bmedtech\b",
    ],
    "Media / Entertainment / Gaming": [
        r"\bmedia company\b", r"\bstreaming\b", r"\bcontent platform\b",
        r"\bgaming\b", r"\bgame studio\b", r"\bentertainment\b", r"\bvideo platform\b",
    ],
    "Government / Public Sector": [
        r"\bgovernment\b", r"\bfederal\b", r"\bpublic sector\b",
        r"\bdod\b", r"\bdefense\b", r"\bgovtech\b",
    ],
    "Consulting / IT Services / MSP": [
        r"\bconsulting\b", r"\bmanaged service\b", r"\bmsp\b",
        r"\bsystem integrator\b", r"\bclient work\b", r"\bprofessional services\b",
    ],
    "Cybersecurity": [
        r"\bcybersecurity\b", r"\bsecurity company\b", r"\binfosec\b",
        r"\bsoc\b", r"\bthreat detection\b", r"\bsecurity vendor\b",
    ],
}

PAIN_PATTERNS: list[str] = [
    r"struggling with", r"can'?t figure out", r"\bfrustrat", r"\bnightmare\b",
    r"\bheadache\b", r"pain point", r"problem with", r"issue with",
    r"spending too much", r"costs? (are|is) (out of control|too high|killing us)",
    r"taking (too long|months|forever)", r"manual process", r"can'?t keep up",
    r"\bstuck\b", r"breaking point", r"inefficient", r"\bwasted\b",
    r"hard to (maintain|manage|scale|deploy)", r"overwhelm",
    r"doesn'?t scale", r"technical debt", r"months of work",
    r"help.*(with|on|for)", r"how do (i|we|you)", r"\bhelp\b.*\?",
]

SOLUTION_PATTERNS: list[str] = [
    r"we (solved|fixed|migrated|switched|moved|chose)",
    r"(works|worked) (for us|great|well)", r"recommend(ed)?",
    r"saved us", r"reduced (our|costs?|spend|bill)",
    r"cut (our|costs?|spend)", r"improved (our|performance|speed)",
    r"our solution", r"switched to", r"we use",
]

# Active evaluation / tool comparison — highest buying-intent signal
EVALUATION_PATTERNS: list[str] = [
    r"\bvs\.?\b", r"\bversus\b",
    r"\bcompar(e|ing|ison)\b",
    r"\balternatives? to\b", r"\blooking for alternatives?\b",
    r"\bwhich (is|would|should|do)\b",
    r"\bshould (i|we) (use|choose|go with)\b",
    r"\b(best|better) (option|choice|tool|solution|platform|approach)\b",
    r"\bevaluat(e|ing|ed)\b",
    r"\banyone (tried|using|recommend)\b",
    r"\bthoughts? on\b", r"\bpros? (and|&) cons?\b",
    r"\bopen (to|for) (suggestions?|recommendations?)\b",
]

# Competing or adjacent tools — signals the person is actively in-market
COMPETITOR_PATTERNS: dict[str, list[str]] = {
    "Spacelift": [r"\bspacelift\b"],
    "Scalr": [r"\bscalr\b"],
    "Env0": [r"\benv0\b"],
    "Atlantis": [r"\batlantis\b"],
    "Terraform Cloud / HCP": [r"\bterraform cloud\b", r"\bhcp terraform\b", r"\btfc\b"],
    "Pulumi Cloud": [r"\bpulumi cloud\b"],
    "CloudHealth": [r"\bcloudhealth\b"],
    "Apptio": [r"\bapptio\b"],
    "Kubecost": [r"\bkubecost\b"],
    "Infracost": [r"\binfracost\b"],
    "Spot.io": [r"\bspot\.io\b", r"\bspot by netapp\b"],
    "AWS Cost Explorer": [r"\bcost explorer\b"],
    "Datadog": [r"\bdatadog\b"],
    "Grafana Cloud": [r"\bgrafana cloud\b"],
}

# Active buying window signals — contract renewal, trial, budget, RFP
BUYING_SIGNAL_PATTERNS: list[str] = [
    r"\brenewal\b", r"\bcontract (end|expir|up for renewal)\b",
    r"\blooking for alternatives?\b",
    r"\bopen to (suggestions?|alternatives?|tools?|solutions?)\b",
    r"\bevaluat(e|ing|ed) (options?|tools?|vendors?|solutions?)\b",
    r"\bpoc\b", r"\bproof of concept\b",
    r"\btrial(ing|led)?\b",
    r"\bnew budget\b", r"\bbudget (for|to|approval)\b",
    r"\bjust (got|raised|closed) (fund|series|seed|round)\b",
    r"\bseries [abcde]\b",
    r"\brfp\b", r"\brequest for (proposal|quote)\b",
    r"\bin the market for\b", r"\bshopping for\b",
]

# Scaling / hiring signals — leading indicator of future infra pain
HIRING_PATTERNS: list[str] = [
    r"\bhiring\b.*\b(devops|sre|platform|infra|cloud)\b",
    r"\b(devops|sre|platform|infra|cloud)\b.*\bhiring\b",
    r"\blooking to hire\b",
    r"\bwe.?re (growing|scaling)\b.*\bteam\b",
    r"\bscaling (the|our) (team|engineering|infra)\b",
]

# ---------------------------------------------------------------------------
# LinkedIn search mappings
# ---------------------------------------------------------------------------

_LINKEDIN_ROLE_TERMS: dict[str, str] = {
    "DevOps / Platform Engineer": (
        'DevOps OR "Platform Engineer" OR "Infrastructure Engineer" OR SRE OR "Cloud Engineer"'
    ),
    "Cloud Architect": (
        '"Cloud Architect" OR "Solutions Architect" OR "Infrastructure Architect"'
    ),
    "Engineering Manager": (
        '"Engineering Manager" OR "Director of Engineering" OR "VP Engineering"'
    ),
    "CTO / VP Engineering": (
        'CTO OR "VP Engineering" OR "VP of Engineering" OR "Head of Engineering"'
    ),
    "FinOps / Cloud Economics": (
        'FinOps OR "Cloud Economist" OR "Cloud Cost Manager" OR "Cloud FinOps"'
    ),
    "Systems / IT Admin": (
        '"Systems Administrator" OR "Cloud Administrator" OR SysAdmin OR "IT Admin"'
    ),
    "Software Engineer": (
        '"Software Engineer" OR "Backend Engineer" OR "Cloud Developer"'
    ),
}

# Alternative title searches — reach different title buckets within the same persona
_LINKEDIN_ROLE_VARIANTS: dict[str, list[str]] = {
    "DevOps / Platform Engineer": [
        '"Cloud Operations Engineer" OR CloudOps OR "Cloud Reliability Engineer"',
        '"Head of Platform" OR "Principal Infrastructure Engineer" OR "Staff Platform Engineer"',
    ],
    "Cloud Architect": [
        '"Principal Architect" OR "Distinguished Engineer" OR "Cloud Practice Lead"',
        '"Head of Cloud" OR "Director of Architecture"',
    ],
    "Engineering Manager": [
        '"Head of Infrastructure" OR "Head of Platform Engineering" OR "Director of Cloud"',
        '"Tech Lead Manager" OR "Group Engineering Manager" OR "Engineering Lead"',
    ],
    "CTO / VP Engineering": [
        '"Chief Infrastructure Officer" OR "VP of Technology" OR "CIO"',
    ],
    "FinOps / Cloud Economics": [
        '"Cloud Financial Analyst" OR "Cloud Cost Analyst" OR "Cloud Billing Analyst"',
        '"Head of FinOps" OR "Director of Cloud Finance" OR "Principal FinOps"',
    ],
    "Systems / IT Admin": [
        '"Cloud Administrator" OR "Infrastructure Administrator" OR "IT Operations"',
    ],
    "Software Engineer": [
        '"Platform Engineer" OR "Infrastructure Software Engineer" OR "Cloud Native Engineer"',
    ],
}

# Sales Navigator seniority level values per role
_SENIORITY_MAP: dict[str, list[str]] = {
    "DevOps / Platform Engineer": ["Senior", "Manager"],
    "Cloud Architect": ["Senior", "Director"],
    "Engineering Manager": ["Manager", "Director"],
    "CTO / VP Engineering": ["VP", "CXO"],
    "FinOps / Cloud Economics": ["Senior", "Manager", "Director"],
    "Systems / IT Admin": ["Senior"],
    "Software Engineer": ["Senior"],
    "Technical Professional": ["Senior"],
}

# Sales Navigator job function per role
_FUNCTION_MAP: dict[str, str] = {
    "DevOps / Platform Engineer": "Engineering",
    "Cloud Architect": "Engineering",
    "Engineering Manager": "Engineering",
    "CTO / VP Engineering": "Engineering",
    "FinOps / Cloud Economics": "Finance",
    "Systems / IT Admin": "Information Technology",
    "Software Engineer": "Engineering",
    "Technical Professional": "Engineering",
}

# Sales Navigator headcount ranges per detected company size
_HEADCOUNT_MAP: dict[str, list[str]] = {
    "Startup": ["1-10", "11-50", "51-200"],
    "Scale-up / Mid-size": ["201-500", "501-1,000", "1,001-5,000"],
    "Enterprise": ["5,001-10,000", "10,001+"],
}

# LinkedIn Groups by tech/role — self-identified practitioners, warmer than keyword search
_LINKEDIN_GROUPS: dict[str, list[str]] = {
    "AWS": ["Amazon Web Services (AWS) Users", "AWS Cloud Practitioners"],
    "Azure": ["Microsoft Azure", "Azure DevOps & Cloud Architects"],
    "GCP": ["Google Cloud Platform (GCP)", "Google Cloud Users Community"],
    "Terraform": ["HashiCorp User Group", "Terraform IaC Community"],
    "Kubernetes": ["Kubernetes Community (CNCF)", "Kubernetes & Cloud Native"],
    "DevOps / Platform Engineer": ["DevOps Engineers", "Platform Engineering Community"],
    "FinOps / Cloud Economics": ["FinOps Foundation", "Cloud FinOps & Cost Optimization"],
    "Engineering Manager": ["Engineering Leadership", "CTO Craft Community"],
    "CTO / VP Engineering": ["CTO Craft Community", "Technology Executives Network"],
    "Cloud Architect": ["Cloud Architecture", "Enterprise Architecture Network"],
}


# ---------------------------------------------------------------------------
# Per-post analysis
# ---------------------------------------------------------------------------

def analyze_post(post: dict) -> dict:
    """Enrich a raw post dict with extracted signals and a relevance score."""
    text = f"{post.get('title', '')} {post.get('body', '')}".lower()

    roles = _extract(text, ROLE_PATTERNS)
    tech_stack = _extract(text, TECH_PATTERNS)
    company_size = _extract(text, COMPANY_SIZE_PATTERNS)
    industries = _extract(text, INDUSTRY_PATTERNS)
    pain_signals = _match_list(text, PAIN_PATTERNS)
    solution_signals = _match_list(text, SOLUTION_PATTERNS)
    evaluation_signals = _match_list(text, EVALUATION_PATTERNS)
    competitors_mentioned = _extract(text, COMPETITOR_PATTERNS)
    buying_signals = _match_list(text, BUYING_SIGNAL_PATTERNS)
    hiring_signals = _match_list(text, HIRING_PATTERNS)

    # Post type priority: evaluation > pain > mixed > solution > hiring_signal > discussion
    if evaluation_signals:
        post_type = "evaluation"
    elif pain_signals and not solution_signals:
        post_type = "pain"
    elif solution_signals and not pain_signals:
        post_type = "solution"
    elif pain_signals and solution_signals:
        post_type = "mixed"
    elif hiring_signals:
        post_type = "hiring_signal"
    else:
        post_type = "discussion"

    relevance_score = _score(
        post, roles, tech_stack, pain_signals, solution_signals,
        evaluation_signals, buying_signals, competitors_mentioned, hiring_signals,
    )

    return {
        **post,
        "roles": roles,
        "tech_stack": tech_stack,
        "company_size": company_size,
        "industries": industries,
        "pain_signals": pain_signals,
        "solution_signals": solution_signals,
        "evaluation_signals": evaluation_signals,
        "competitors_mentioned": competitors_mentioned,
        "buying_signals": buying_signals,
        "hiring_signals": hiring_signals,
        "post_type": post_type,
        "relevance_score": round(relevance_score, 2),
        "pain_summary": _summarise(post, tech_stack),
    }


# ---------------------------------------------------------------------------
# Lead-profile aggregation
# ---------------------------------------------------------------------------

def build_lead_profiles(analyzed_posts: list[dict]) -> list[dict]:
    """
    Cluster analyzed posts into prospect personas for LinkedIn targeting.

    Returns a list of profile dicts sorted by how many posts map to them.
    """
    bucket: dict[str, dict] = {}

    for post in analyzed_posts:
        if post.get("relevance_score", 0) < 0.25:
            continue

        roles = post.get("roles") or ["Technical Professional"]
        tech = post.get("tech_stack", [])

        primary_role = roles[0]
        primary_cloud = next(
            (t for t in tech if t in {"AWS", "Azure", "GCP"}), "Multi-Cloud"
        )
        key = f"{primary_role}|{primary_cloud}"

        if key not in bucket:
            bucket[key] = {
                "role": primary_role,
                "cloud_platform": primary_cloud,
                "tech_stack": set(),
                "company_sizes": set(),
                "industries": set(),
                "competitors_seen": set(),
                "pain_summaries": [],
                "sample_titles": [],
                "post_count": 0,
                "total_score": 0,
                "buying_signal_count": 0,
                "post_type_counts": {
                    "evaluation": 0, "pain": 0, "solution": 0,
                    "mixed": 0, "hiring_signal": 0, "discussion": 0,
                },
            }

        p = bucket[key]
        p["tech_stack"].update(tech)
        p["company_sizes"].update(post.get("company_size", []))
        p["industries"].update(post.get("industries", []))
        p["competitors_seen"].update(post.get("competitors_mentioned", []))
        p["post_count"] += 1
        p["total_score"] += post.get("score", 0)
        if post.get("buying_signals"):
            p["buying_signal_count"] += 1
        post_type = post.get("post_type", "discussion")
        if post_type in p["post_type_counts"]:
            p["post_type_counts"][post_type] += 1
        else:
            p["post_type_counts"]["discussion"] += 1

        summary = post.get("pain_summary", "")
        if summary and summary not in p["pain_summaries"]:
            p["pain_summaries"].append(summary)

        title = post.get("title", "")
        if title and title not in p["sample_titles"] and len(p["sample_titles"]) < 5:
            p["sample_titles"].append(title)

    profiles = []
    for profile in bucket.values():
        profile["tech_stack"] = sorted(profile["tech_stack"])
        profile["company_sizes"] = sorted(profile["company_sizes"])
        profile["industries"] = sorted(profile["industries"])
        profile["competitors_seen"] = sorted(profile["competitors_seen"])
        profile["pain_summaries"] = profile["pain_summaries"][:8]
        profile["linkedin_query"] = _build_linkedin_query(profile)
        profile["linkedin_url"] = _build_linkedin_url(profile)
        profile["linkedin_query_variants"] = _build_linkedin_query_variants(profile)
        profile["account_url"] = _build_account_url(profile)
        profile["seniority_filter"] = _SENIORITY_MAP.get(profile["role"], ["Senior"])
        profile["job_function"] = _FUNCTION_MAP.get(profile["role"], "Engineering")
        profile["headcount_ranges"] = _derive_headcount_ranges(profile["company_sizes"])
        profile["linkedin_groups"] = _build_linkedin_groups(profile)
        profiles.append(profile)

    profiles.sort(key=lambda p: p["post_count"], reverse=True)
    return profiles


# ---------------------------------------------------------------------------
# LinkedIn helpers
# ---------------------------------------------------------------------------

def _build_linkedin_query(profile: dict) -> str:
    parts: list[str] = []

    role_term = _LINKEDIN_ROLE_TERMS.get(profile["role"], f'"{profile["role"]}"')
    parts.append(f"({role_term})")

    cloud = profile.get("cloud_platform", "")
    if cloud and cloud != "Multi-Cloud":
        parts.append(cloud)

    extra_tech = [
        t for t in profile.get("tech_stack", [])
        if t not in {"AWS", "Azure", "GCP"} and t in {"Terraform", "Kubernetes", "Pulumi"}
    ]
    if extra_tech:
        parts.append(" OR ".join(f'"{t}"' if " " in t else t for t in extra_tech[:2]))

    return " ".join(parts)


def _build_linkedin_url(profile: dict) -> str:
    query = _build_linkedin_query(profile)
    encoded = urllib.parse.quote(query)
    return f"https://www.linkedin.com/sales/search/people?keywords={encoded}"


def _build_linkedin_query_variants(profile: dict) -> list[tuple[str, str]]:
    """Return [(query_string, url), ...] for alternative title searches."""
    role = profile.get("role", "")
    cloud = profile.get("cloud_platform", "")
    cloud_suffix = f" {cloud}" if cloud and cloud != "Multi-Cloud" else ""
    results = []
    for variant_titles in _LINKEDIN_ROLE_VARIANTS.get(role, []):
        q = f"({variant_titles}){cloud_suffix}"
        url = f"https://www.linkedin.com/sales/search/people?keywords={urllib.parse.quote(q)}"
        results.append((q, url))
    return results


def _build_account_url(profile: dict) -> str:
    """Return a Sales Navigator company search URL for targeting the right accounts."""
    cloud = profile.get("cloud_platform", "")
    tech = profile.get("tech_stack", [])
    role = profile.get("role", "")

    parts: list[str] = []
    if cloud and cloud != "Multi-Cloud":
        parts.append(cloud)
    extra_tech = [
        t for t in tech
        if t not in {"AWS", "Azure", "GCP"}
        and t in {"Terraform", "Kubernetes", "Pulumi", "Ansible"}
    ]
    parts.extend(extra_tech[:2])
    if "FinOps" in role or "Cloud Economics" in role:
        parts.append("cloud cost")
    if not parts:
        parts = ["cloud infrastructure"]

    encoded = urllib.parse.quote(" ".join(parts))
    return f"https://www.linkedin.com/sales/search/company?keywords={encoded}"


def _derive_headcount_ranges(company_sizes: list[str]) -> list[str]:
    """Map detected company sizes to Sales Navigator headcount range strings."""
    seen: set[str] = set()
    ranges: list[str] = []
    for size in company_sizes:
        for r in _HEADCOUNT_MAP.get(size, []):
            if r not in seen:
                seen.add(r)
                ranges.append(r)
    return ranges


def _build_linkedin_groups(profile: dict) -> list[str]:
    """Compile relevant LinkedIn Groups based on tech stack and role."""
    groups: list[str] = []
    seen: set[str] = set()

    def _add(items: list[str]) -> None:
        for g in items:
            if g not in seen:
                seen.add(g)
                groups.append(g)

    cloud = profile.get("cloud_platform", "")
    if cloud and cloud != "Multi-Cloud":
        _add(_LINKEDIN_GROUPS.get(cloud, []))

    for tech in profile.get("tech_stack", []):
        if tech in _LINKEDIN_GROUPS:
            _add(_LINKEDIN_GROUPS[tech])

    role = profile.get("role", "")
    if role in _LINKEDIN_GROUPS:
        _add(_LINKEDIN_GROUPS[role])

    return groups[:6]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract(text: str, pattern_dict: dict[str, list[str]]) -> list[str]:
    matches: list[str] = []
    for category, patterns in pattern_dict.items():
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                matches.append(category)
                break
    return matches


def _match_list(text: str, patterns: list[str]) -> list[str]:
    found: list[str] = []
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            snippet = m.group(0).strip()
            if snippet not in found:
                found.append(snippet)
    return found[:6]


def _score(
    post: dict,
    roles: list,
    tech_stack: list,
    pain_signals: list,
    solution_signals: list,
    evaluation_signals: Optional[list] = None,
    buying_signals: Optional[list] = None,
    competitors_mentioned: Optional[list] = None,
    hiring_signals: Optional[list] = None,
) -> float:
    s = 0.0

    # Evaluation intent — active comparison is the highest buying-intent signal
    if evaluation_signals:
        s += 0.25
    # Buying window — contract renewal, trial, RFP, POC
    if buying_signals:
        s += 0.20
    # Competitor mentions — named a tool = actively in-market
    if competitors_mentioned:
        s += 0.10
    # Hiring signal — scaling team = future infra pain
    if hiring_signals:
        s += 0.08

    # Pain signals
    if pain_signals:
        s += 0.25
    if len(pain_signals) > 2:
        s += 0.05  # multiple pain phrases = deeper, more urgent pain

    # Solution signals (less valuable for us, but still relevant context)
    if solution_signals and not pain_signals:
        s += 0.08
    elif solution_signals and pain_signals:
        s += 0.03

    # Tech stack match
    cloud_hit = bool({"AWS", "Azure", "GCP"} & set(tech_stack))
    if cloud_hit:
        s += 0.15
    if "Terraform" in tech_stack:
        s += 0.08
    if "Kubernetes" in tech_stack:
        s += 0.05

    # Role match
    if roles:
        s += 0.08

    # Community engagement — proxy for widespread pain (not just one person)
    score = post.get("score", 0)
    if score > 100:
        s += 0.10
    elif score > 30:
        s += 0.05
    elif score > 10:
        s += 0.02

    num_comments = post.get("num_comments", 0)
    if num_comments > 30:
        s += 0.07
    elif num_comments > 10:
        s += 0.04

    body_len = len(post.get("body") or "")
    if body_len > 500:
        s += 0.05
    elif body_len > 200:
        s += 0.03

    return min(s, 1.0)


def _summarise(post: dict, tech_stack: list[str]) -> str:
    title = post.get("title", "").strip()
    if tech_stack:
        tags = ", ".join(tech_stack[:3])
        return f"{title}  [{tags}]"
    return title
