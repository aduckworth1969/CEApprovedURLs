"""
URL normalization shared by the builder, the link checker and the run history.

These two rules decide when two addresses count as "the same site". They live
in their own module because three separate things now depend on agreeing about
it: URL overrides, build-time duplicate collapsing, and matching a site across
runs in the history database. A second copy of the rule would let the history
disagree with the page about what a site is, which is exactly the bug the
overrides' comment warns about.
"""

import re
from urllib.parse import urlparse


def normalize_url(raw: str) -> str:
    """Normalize a URL by adding https:// when no scheme is present."""
    raw = str(raw or "").strip()
    if not raw:
        return ""
    if not raw.lower().startswith(("http://", "https://")):
        raw = "https://" + raw
    return urlparse(raw).geturl()


def url_key(url: str) -> str:
    """
    Matching key for a URL, so an address written one way still matches the
    same address written another: scheme, "www.", case and trailing slash are
    all ignored.
    """
    s = str(url or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    return s.rstrip("/")
