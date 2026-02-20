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
