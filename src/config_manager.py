import yaml
import copy
from pathlib import Path

CONFIG_PATH = Path("config.yaml")

DEFAULT_CONFIG = {
    "reddit": {
        "api": {
            "client_id": "",
            "client_secret": "",
            "username": "",
            "password": "",
            "user_agent": "InfrOS Lead Research Tool v1.0",
        },
        "subreddits": [
            "devops", "aws", "azure", "googlecloud", "terraform",
            "kubernetes", "sysadmin", "cloudcomputing", "FinOps",
        ],
        "keywords": [
            "cloud costs", "terraform", "infrastructure automation",
            "cloud migration", "multi-cloud", "cloud spend",
            "infrastructure as code", "cloud architecture", "IaC",
        ],
        "topics": [
            {
                "name": "Cloud Cost Pain",
                "description": "Teams struggling with unexpectedly high cloud bills",
                "keywords": ["cloud bill too high", "reduce cloud costs", "AWS bill", "FinOps"],
            },
            {
                "name": "Infrastructure Complexity",
                "description": "Teams buried in manual, hard-to-manage infrastructure",
                "keywords": ["terraform complexity", "configuration drift", "infrastructure debt"],
            },
            {
                "name": "Cloud Migration",
                "description": "Companies moving to or between cloud providers",
                "keywords": ["cloud migration", "lift and shift", "on-prem to cloud"],
            },
        ],
        "search": {
            "time_filter": "month",
            "sort": "relevance",
            "max_results": 50,
            "min_score": 3,
        },
    },
    "linkedin": {
        "base_search_url": "https://www.linkedin.com/search/results/people/",
    },
    "roadmap": {
        "features": [
            {
                "name": "Cloud cost visibility & optimization",
                "description": "Real-time spend tracking, waste detection, and right-sizing recommendations across cloud providers",
                "keywords": ["cloud cost", "cloud bill", "cloud spend", "aws bill", "reduce cost", "right-siz", "rightsiz", "cost optim", "waste", "finops", "billing", "overspend", "cost control"],
            },
            {
                "name": "Terraform state management",
                "description": "Centralised, versioned Terraform state with locking, history, and audit trail",
                "keywords": ["terraform state", "state file", "state lock", "remote state", "tfstate", "terragrunt", "state management"],
            },
            {
                "name": "Infrastructure drift detection",
                "description": "Automatically detect when live cloud resources diverge from their IaC definitions",
                "keywords": ["drift", "configuration drift", "out of sync", "manual change", "infra drift", "detect drift"],
            },
            {
                "name": "Team collaboration on IaC",
                "description": "Shared Terraform workspaces, plan reviews, approvals, and audit log for infrastructure changes",
                "keywords": ["team", "collaborate", "approval", "workflow", "plan review", "terraform workflow", "shared infra", "multi-team"],
            },
            {
                "name": "Policy enforcement / guardrails",
                "description": "Prevent non-compliant infrastructure changes with policy-as-code (OPA, Sentinel)",
                "keywords": ["policy", "compliance", "guardrail", "sentinel", "opa", "governance", "security policy", "enforce"],
            },
            {
                "name": "Multi-cloud management",
                "description": "Single pane of glass for AWS, Azure, and GCP resources, costs, and operations",
                "keywords": ["multi-cloud", "multi cloud", "cloud agnostic", "multiple cloud", "cross-cloud", "aws and azure", "azure and gcp"],
            },
            {
                "name": "CI/CD pipeline integration",
                "description": "Integrate infrastructure change workflows into existing GitHub/GitLab CI pipelines",
                "keywords": ["ci/cd", "pipeline", "github actions", "gitlab ci", "atlantis", "gitops", "pr plan", "pull request", "automate deploy"],
            },
            {
                "name": "Automated resource tagging",
                "description": "Enforce consistent resource tagging for cost allocation, compliance, and governance",
                "keywords": ["tagging", "tag enforcement", "cost allocation", "resource label", "untagged", "tag policy"],
            },
        ],
    },
}


def load_config() -> dict:
    """Load config from disk, falling back to defaults for missing keys."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            on_disk = yaml.safe_load(f) or {}
        return _deep_merge(copy.deepcopy(DEFAULT_CONFIG), on_disk)
    return copy.deepcopy(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    """Persist config to disk."""
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (override wins on conflicts)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
