"""Stage 3: extract a neutral, opinion-free facts list from each article."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from llm import structured_call
from schema import Article, Topic

log = logging.getLogger(__name__)

SYSTEM = """You extract facts from a news article.

Include a statement ONLY if all of these hold:
- It is stated in the article text provided (never from your own knowledge).
- It is a factual claim, not an opinion, characterization, prediction,
  speculation, or evaluative framing.
- It is grammatically unambiguous: one clear subject, action, and object;
  no pronouns whose referent is unclear; no dangling modifiers.
- Statements of opinion by named people or organizations may be included only
  when rewritten as attribution ("X said ...", "Y stated that ..."), which makes
  the fact the act of saying it.

Phrase every fact in maximally neutral tone:
- Plain declarative sentences. No loaded, emotive, or evaluative vocabulary.
- Prefer the article's concrete specifics (names, numbers, places, dates).
- Each fact must stand alone, understandable without the others.
- Do not copy sentences verbatim from the article; restate them neutrally in
  your own words.

Output 3-12 facts. If the text is only a headline and short summary, extract
the few facts it supports — never pad."""

SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {"type": "string"}}},
    "required": ["facts"],
    "additionalProperties": False,
}


def _extract_one(article: Article) -> tuple[str, list[str]]:
    coverage = "full article text" if article.text_is_full else "headline and summary only"
    user = (
        f"Outlet: {article.outlet}\n"
        f"Headline: {article.title}\n"
        f"Available text ({coverage}):\n\n{article.text or article.summary}"
    )
    result = structured_call(SYSTEM, user, SCHEMA, max_tokens=1500)
    facts = result["facts"] if result else []
    log.info("extracted %d facts from %s (%s)", len(facts), article.id, article.outlet)
    return article.id, facts


def extract_facts(topics: list[Topic]) -> dict[str, list[str]]:
    """Return article_id -> facts for every article in the given topics."""
    articles = [a for t in topics for a in t.articles]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = dict(pool.map(_extract_one, articles))
    return results
