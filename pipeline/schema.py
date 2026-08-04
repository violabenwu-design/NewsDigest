"""Data model for the daily digest.

The JSON written here is the contract with the iOS/macOS app — bump
SCHEMA_VERSION on any breaking change.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

SCHEMA_VERSION = 2  # v2: topics[].paragraphs — fact-index groups in reading order

# Digest facts must never contain article body text — facts + links only.
MAX_ARTICLE_TEXT_CHARS = 8000  # cap on text sent to the model, not stored


@dataclass
class Article:
    id: str
    outlet: str
    title: str
    url: str
    published_at: str  # ISO 8601
    text: str = ""            # working data only; never serialized into the digest
    text_is_full: bool = False
    summary: str = ""         # working data only

    def digest_dict(self) -> dict:
        return {
            "id": self.id,
            "outlet": self.outlet,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
        }


@dataclass
class Fact:
    text: str
    sources: list[str]  # article ids


@dataclass
class Topic:
    id: str
    title: str
    articles: list[Article]
    facts: list[Fact] = field(default_factory=list)
    # groups of indexes into `facts`, one group per paragraph, in reading order
    paragraphs: list[list[int]] = field(default_factory=list)

    def digest_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "articles": [a.digest_dict() for a in self.articles],
            "facts": [asdict(f) for f in self.facts],
            "paragraphs": self.paragraphs,
        }


def build_digest(date: str, sources: dict[str, list[str]], topics: list[Topic]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": [
            {"outlet": outlet, "feeds": feeds} for outlet, feeds in sources.items()
        ],
        "topics": [t.digest_dict() for t in topics],
    }
