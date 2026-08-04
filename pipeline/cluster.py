"""Stage 2: group articles into topics — one topic per real-world event.

Only events covered by at least two distinct outlets become topics.
"""
from __future__ import annotations

import logging

from llm import structured_call
from schema import Article, Topic

log = logging.getLogger(__name__)

SYSTEM = """You group news articles by the real-world event or story they cover.

Rules:
- Two articles belong to the same group only if they cover the same specific
  event or ongoing story (e.g. the same incident, ruling, vote, disaster, or
  announcement) — not merely the same broad subject area.
- Every group needs at least 2 articles. Articles that no other article covers
  the same event as must be left out of all groups.
- Give each group a short, strictly neutral, descriptive title. No loaded or
  evaluative words; describe what happened, not how to feel about it.
- Use only the article ids you were given, and list each id at most once
  across all groups."""

SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "article_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "article_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["groups"],
    "additionalProperties": False,
}


def cluster_articles(articles: list[Article]) -> list[Topic]:
    # short aliases (a1..aN) keep model output lean — real ids are 12 hex chars
    by_alias = {f"a{i+1}": a for i, a in enumerate(articles)}
    listing = "\n".join(
        f"{alias} | {a.outlet} | {a.title} | {a.summary[:160]}"
        for alias, a in by_alias.items()
    )
    user = (
        "Group these articles by the event they cover. "
        "Format: id | outlet | title | summary\n\n" + listing
    )
    result = structured_call(SYSTEM, user, SCHEMA, max_tokens=4000, effort="high")
    if not result:
        return []

    topics: list[Topic] = []
    used: set[str] = set()
    for i, group in enumerate(result["groups"]):
        members = [
            by_alias[aid]
            for aid in group["article_ids"]
            if aid in by_alias and by_alias[aid].id not in used
        ]
        outlets = {a.outlet for a in members}
        if len(outlets) < 2:
            continue  # per spec: topics require coverage by more than one outlet
        used.update(a.id for a in members)
        members.sort(key=lambda a: a.published_at)
        topics.append(Topic(id=f"t{i+1}", title=group["title"], articles=members))

    log.info("clustered %d articles into %d multi-outlet topics", len(used), len(topics))
    return topics
