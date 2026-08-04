"""Stage 4: merge equivalent facts across a topic's articles and rank by corroboration."""
from __future__ import annotations

import logging

from llm import structured_call
from schema import Fact, Topic

log = logging.getLogger(__name__)

SYSTEM = """You merge fact lists that different news articles reported about the
same event.

- Facts from different articles that state the same thing (even with different
  wording or levels of detail) are ONE fact. Merge them and credit every
  article that stated it.
- Facts are the same only if they genuinely assert the same thing. Different
  numbers, different actors, or materially different claims stay separate.
- For each merged fact, write one canonical phrasing: neutral, plain,
  declarative, keeping the most precise details any source gave (if sources
  conflict on a detail, keep the fact at the level of detail they agree on).
- Credit an article id only if that article's fact list supports the fact.
- Do not invent facts, drop facts, or use outside knowledge."""

SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "source_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}


def corroborate_topic(topic: Topic, facts_by_article: dict[str, list[str]]) -> None:
    # short aliases (s1..sN) keep model output lean — real ids are 12 hex chars
    by_alias = {f"s{i+1}": a for i, a in enumerate(topic.articles)}
    sections = []
    for alias, a in by_alias.items():
        facts = facts_by_article.get(a.id, [])
        fact_lines = "\n".join(f"- {f}" for f in facts) or "- (no facts extracted)"
        sections.append(f"Article {alias} ({a.outlet}):\n{fact_lines}")
    user = f"Event: {topic.title}\n\n" + "\n\n".join(sections)

    result = structured_call(SYSTEM, user, SCHEMA, max_tokens=3000, effort="high")
    if not result:
        return

    merged: list[Fact] = []
    for item in result["facts"]:
        sources = sorted({by_alias[s].id for s in item["source_ids"] if s in by_alias})
        if not sources:
            continue
        merged.append(Fact(text=item["text"], sources=sources))

    # most corroborated first; ties keep model order (usually importance order)
    merged.sort(key=lambda f: -len(f.sources))
    topic.facts = merged
    log.info("topic %s: %d merged facts", topic.id, len(merged))
