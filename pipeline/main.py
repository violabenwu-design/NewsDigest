"""Daily news digest pipeline: fetch -> cluster -> extract -> corroborate -> publish."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from cluster import cluster_articles
from compose import compose_topic
from corroborate import corroborate_topic
from extract import extract_facts
from fetch import fetch_all, load_sources
from schema import build_digest

log = logging.getLogger("digest")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs" / "digest",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path(__file__).resolve().parent / "sources.yaml",
    )
    parser.add_argument(
        "--backend",
        default=None,
        help="LLM backend spec, e.g. claude, claude:claude-fable-5, ollama, "
        "ollama:kimi-k3:cloud (default: DIGEST_LLM_BACKEND env var, else claude)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    import llm

    if args.backend:
        llm.BACKEND = args.backend
    kind, _ = llm.resolve(llm.BACKEND)
    if kind == "claude" and not os.environ.get("ANTHROPIC_API_KEY"):
        log.error("ANTHROPIC_API_KEY is not set (required for the claude backend)")
        return 1

    sources = load_sources(args.sources)

    log.info("stage 1: fetching feeds from %d outlets", len(sources))
    articles = fetch_all(sources)
    if not articles:
        log.error("no articles fetched; aborting without writing a digest")
        return 1

    log.info("stage 2: clustering %d articles", len(articles))
    topics = cluster_articles(articles)
    if not topics:
        log.error("no multi-outlet topics found; aborting without writing a digest")
        return 1

    log.info("stage 3: extracting facts for %d topics", len(topics))
    facts_by_article = extract_facts(topics)

    log.info("stage 4: corroborating facts per topic")
    for topic in topics:
        corroborate_topic(topic, facts_by_article)
    dropped = [t.id for t in topics if not t.facts]
    if dropped:
        log.warning("dropping %d topic(s) with no facts: %s", len(dropped), dropped)
    topics = [t for t in topics if t.facts]
    if not topics:
        log.error("every topic failed; keeping the previous digest untouched")
        return 1
    # busiest stories first
    topics.sort(key=lambda t: (-len(t.articles), t.title))

    log.info("stage 5: composing paragraphs for %d topics", len(topics))
    for topic in topics:
        compose_topic(topic)

    log.info("stage 6: writing digest (%d topics)", len(topics))
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = build_digest(date, sources, topics)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(digest, indent=2, ensure_ascii=False)
    (args.output_dir / f"{date}.json").write_text(payload)
    (args.output_dir / "latest.json").write_text(payload)

    # index of available dates, for the app's archive browser
    index_path = args.output_dir / "index.json"
    dates = sorted(
        p.stem for p in args.output_dir.glob("????-??-??.json")
    )
    index_path.write_text(json.dumps({"dates": dates}, indent=2))

    log.info("wrote %s and latest.json", f"{date}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
