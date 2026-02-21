"""
Session persistence helpers.

Serialises and restores the full analysis state (raw_posts, analyzed_posts,
lead_profiles) as a single JSON blob so sessions can be downloaded, shared,
and resumed later.  Also provides a lightweight auto-save to disk so that a
browser refresh does not wipe the results of a long search.
"""

import json
from datetime import datetime
from pathlib import Path

AUTOSAVE_PATH = Path("session_autosave.json")
SESSION_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_session(
    raw_posts: list,
    analyzed_posts: list,
    lead_profiles: list,
    metadata: dict | None = None,
) -> str:
    """Serialise the session to a JSON string and return it."""
    session = {
        "version": SESSION_VERSION,
        "saved_at": datetime.now().isoformat(),
        "metadata": metadata or {},
        "raw_posts": raw_posts,
        "analyzed_posts": analyzed_posts,
        "lead_profiles": lead_profiles,
    }
    return json.dumps(session, ensure_ascii=False, indent=2, default=str)


def load_session(json_content: str | bytes) -> tuple:
    """
    Parse a session JSON blob.

    Returns
    -------
    (raw_posts, analyzed_posts, lead_profiles, metadata, saved_at)
    Raises ValueError on parse errors.
    """
    if isinstance(json_content, bytes):
        json_content = json_content.decode("utf-8")
    try:
        session = json.loads(json_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid session file: {exc}") from exc

    return (
        session.get("raw_posts", []),
        session.get("analyzed_posts", []),
        session.get("lead_profiles", []),
        session.get("metadata", {}),
        session.get("saved_at", "unknown"),
    )


def autosave(raw_posts: list, analyzed_posts: list, lead_profiles: list) -> None:
    """Write a silent auto-save to disk.  Ignores filesystem errors."""
    try:
        content = save_session(
            raw_posts, analyzed_posts, lead_profiles, {"autosave": True}
        )
        AUTOSAVE_PATH.write_text(content, encoding="utf-8")
    except OSError:
        pass


def load_autosave() -> tuple | None:
    """
    Load the auto-save file if it exists.

    Returns the same tuple as load_session(), or None if no auto-save exists.
    """
    if AUTOSAVE_PATH.exists():
        try:
            return load_session(AUTOSAVE_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
    return None
