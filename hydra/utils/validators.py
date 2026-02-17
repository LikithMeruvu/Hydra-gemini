"""Input validators."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def validate_keys_json(path: str) -> list[dict[str, str]]:
    """Load and validate a keys JSON file.

    Expected format — array of objects::

        [
          {"email": "user@gmail.com", "api_key": "AIzaSy...", "project_id": "projects/123"},
          ...
        ]

    Returns list of dicts, each with keys: email, api_key, project_id.
    Raises ValueError on invalid format.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"File not found: {path}")
    if not p.suffix == ".json":
        raise ValueError(f"Expected .json file, got: {p.suffix}")

    try:
        raw = p.read_bytes()
        # Strip UTF-16 LE BOM if present (PowerShell echo on Windows)
        if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
            text = raw.decode("utf-16")
        elif raw[:3] == b'\xef\xbb\xbf':
            text = raw[3:].decode("utf-8")
        else:
            text = raw.decode("utf-8")
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}")

    if not isinstance(data, list):
        raise ValueError("JSON must be an array of {email, api_key, project_id} objects")

    result: list[dict[str, str]] = []
    seen_projects: set[str] = set()

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry #{i + 1} is not an object")

        email = entry.get("email", "")
        api_key = entry.get("api_key", "")
        project_id = entry.get("project_id", "")

        if not email or not api_key:
            raise ValueError(f"Entry #{i + 1}: 'email' and 'api_key' are required")
        if not _looks_like_email(email):
            raise ValueError(f"Entry #{i + 1}: Invalid email format: {email}")
        if not api_key.startswith("AIza"):
            raise ValueError(
                f"Entry #{i + 1} ({email}): API key doesn't look like a Gemini key "
                "(should start with 'AIza')"
            )

        # Warn about duplicate project IDs (rate limits are per project!)
        if project_id and project_id in seen_projects:
            raise ValueError(
                f"Entry #{i + 1} ({email}): Duplicate project_id '{project_id}'. "
                "Rate limits are per project — duplicate projects don't add capacity!"
            )
        if project_id:
            seen_projects.add(project_id)

        result.append({
            "email": email,
            "api_key": api_key,
            "project_id": project_id,
        })

    if not result:
        raise ValueError("No keys found in JSON")

    return result


def _looks_like_email(s: str) -> bool:
    """Quick email format check."""
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s))


def validate_api_key_format(key: str) -> bool:
    """Check if a string looks like a Gemini API key."""
    return bool(key and key.startswith("AIza") and len(key) > 20)
