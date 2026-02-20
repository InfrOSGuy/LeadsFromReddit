"""
Reddit scraper — uses public JSON API by default; switches to PRAW when
API credentials are present in config.

Rate limits:
  - Public (no auth): ~1 req/sec to stay safe (Reddit allows ~30/min unofficially)
  - PRAW (OAuth):     60 req/min (Reddit's official limit for script apps)

Privacy note: usernames are intentionally NOT collected. This tool extracts
pain-point signals and role/tech signals from post content only.
"""

import time
from datetime import datetime
from typing import Callable, Optional

import requests


class RedditScraper:
    def __init__(self, config: dict):
        self.config = config
        self.api_cfg = config["reddit"]["api"]
        self.use_praw = bool(self.api_cfg.get("client_id", "").strip())
        self._praw_reddit = None

        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": self.api_cfg.get(
                "user_agent", "InfrOS Lead Research Tool v1.0"
            )
        })

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def search_posts(
        self,
        keywords: list[str],
        subreddits: list[str],
        time_filter: str = "month",
        sort: str = "relevance",
        limit: int = 25,
        min_score: int = 3,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> list[dict]:
        """
        Search Reddit posts across the given subreddits for each keyword.

        Returns a deduplicated list of post dicts (no usernames stored).
        """
        if self.use_praw:
            return self._search_praw(
                keywords, subreddits, time_filter, sort, limit, min_score, progress_callback
            )
        return self._search_public(
            keywords, subreddits, time_filter, sort, limit, min_score, progress_callback
        )

    # ------------------------------------------------------------------
    # Public JSON API (no credentials)
    # ------------------------------------------------------------------

    def _search_public(
        self,
        keywords, subreddits, time_filter, sort, limit, min_score, progress_callback
    ) -> list[dict]:
        all_posts: list[dict] = []
        seen_ids: set[str] = set()
        total_steps = len(subreddits) * len(keywords)
        step = 0

        for subreddit in subreddits:
            for keyword in keywords:
                step += 1
                if progress_callback:
                    progress_callback(
                        step / total_steps,
                        f"Searching r/{subreddit} for "{keyword}"…",
                    )

                try:
                    posts = self._public_search_one(
                        subreddit, keyword, time_filter, sort, min(limit, 25)
                    )
                    for p in posts:
                        if p["id"] not in seen_ids and p["score"] >= min_score:
                            seen_ids.add(p["id"])
                            p["matched_keyword"] = keyword
                            all_posts.append(p)
                except Exception:
                    pass  # silently skip failed requests; partial results > nothing

                time.sleep(0.75)  # stay well under Reddit's unofficial limit

        if progress_callback:
            progress_callback(1.0, "Done!")
        return all_posts

    def _public_search_one(
        self, subreddit: str, keyword: str, time_filter: str, sort: str, limit: int
    ) -> list[dict]:
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": keyword,
            "restrict_sr": 1,
            "sort": sort,
            "t": time_filter,
            "limit": limit,
            "type": "link",
        }
        resp = self._session.get(url, params=params, timeout=12)

        if resp.status_code == 429:
            time.sleep(5)
            resp = self._session.get(url, params=params, timeout=12)

        resp.raise_for_status()
        children = resp.json().get("data", {}).get("children", [])
        return [self._normalise(c["data"]) for c in children if c.get("data")]

    # ------------------------------------------------------------------
    # PRAW (with credentials)
    # ------------------------------------------------------------------

    def _search_praw(
        self,
        keywords, subreddits, time_filter, sort, limit, min_score, progress_callback
    ) -> list[dict]:
        import praw  # only imported when credentials exist

        if self._praw_reddit is None:
            self._praw_reddit = praw.Reddit(
                client_id=self.api_cfg["client_id"],
                client_secret=self.api_cfg["client_secret"],
                username=self.api_cfg.get("username", ""),
                password=self.api_cfg.get("password", ""),
                user_agent=self.api_cfg.get("user_agent", "InfrOS Lead Research Tool v1.0"),
                read_only=True,
            )

        all_posts: list[dict] = []
        seen_ids: set[str] = set()
        total_steps = len(subreddits) * len(keywords)
        step = 0

        for subreddit in subreddits:
            sub = self._praw_reddit.subreddit(subreddit)
            for keyword in keywords:
                step += 1
                if progress_callback:
                    progress_callback(
                        step / total_steps,
                        f"[API] Searching r/{subreddit} for "{keyword}"…",
                    )
                try:
                    results = sub.search(
                        keyword, sort=sort, time_filter=time_filter, limit=limit
                    )
                    for submission in results:
                        if submission.id not in seen_ids and submission.score >= min_score:
                            seen_ids.add(submission.id)
                            post = self._normalise_praw(submission)
                            post["matched_keyword"] = keyword
                            all_posts.append(post)
                except Exception:
                    pass

        if progress_callback:
            progress_callback(1.0, "Done!")
        return all_posts

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------

    def _normalise(self, data: dict) -> dict:
        """Convert raw Reddit JSON post dict into our schema (no username)."""
        ts = data.get("created_utc", 0)
        return {
            "id": data.get("id", ""),
            "subreddit": data.get("subreddit", ""),
            "title": data.get("title", ""),
            "body": (data.get("selftext") or "")[:3000],
            "score": data.get("score", 0),
            "upvote_ratio": data.get("upvote_ratio", 0.0),
            "num_comments": data.get("num_comments", 0),
            "url": f"https://www.reddit.com{data.get('permalink', '')}",
            "created_utc": ts,
            "created_date": _ts_to_date(ts),
            "is_self": data.get("is_self", False),
            # username intentionally omitted
        }

    def _normalise_praw(self, sub) -> dict:
        ts = sub.created_utc or 0
        return {
            "id": sub.id,
            "subreddit": str(sub.subreddit),
            "title": sub.title or "",
            "body": (sub.selftext or "")[:3000],
            "score": sub.score or 0,
            "upvote_ratio": getattr(sub, "upvote_ratio", 0.0),
            "num_comments": sub.num_comments or 0,
            "url": f"https://www.reddit.com{sub.permalink}",
            "created_utc": ts,
            "created_date": _ts_to_date(ts),
            "is_self": sub.is_self,
        }


def _ts_to_date(ts: float) -> str:
    try:
        return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return "Unknown"
