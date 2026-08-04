"""Stage 1: gather recent articles from the configured RSS feeds."""
from __future__ import annotations

import hashlib
import html
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx
import trafilatura
import yaml

from schema import Article, MAX_ARTICLE_TEXT_CHARS

log = logging.getLogger(__name__)

USER_AGENT = "NewsDigestBot/1.0 (+personal news aggregator)"
FEED_TIMEOUT = 20
ARTICLE_TIMEOUT = 20
MAX_PER_OUTLET = 12
LOOKBACK_HOURS = 24


def load_sources(path: Path) -> dict[str, list[str]]:
    with open(path) as f:
        return yaml.safe_load(f)["sources"]


def _article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def _entry_published(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
    return None


def _fetch_feed(client: httpx.Client, outlet: str, feed_url: str) -> list[Article]:
    try:
        resp = client.get(feed_url, timeout=FEED_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        log.warning("feed failed %s (%s): %s", outlet, feed_url, e)
        return []

    parsed = feedparser.parse(resp.content)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    articles = []
    for entry in parsed.entries:
        url = getattr(entry, "link", None)
        title = _strip_html(getattr(entry, "title", ""))
        if not url or not title:
            continue
        published = _entry_published(entry)
        if published is None or published < cutoff:
            continue
        articles.append(
            Article(
                id=_article_id(url),
                outlet=outlet,
                title=title,
                url=url,
                published_at=published.isoformat(timespec="seconds"),
                summary=_strip_html(getattr(entry, "summary", ""))[:1000],
            )
        )
    return articles


def _fetch_article_text(client: httpx.Client, article: Article) -> None:
    """Try to fetch full article text; fall back to the RSS summary."""
    try:
        resp = client.get(
            article.url, timeout=ARTICLE_TIMEOUT, follow_redirects=True
        )
        resp.raise_for_status()
        extracted = trafilatura.extract(
            resp.text, include_comments=False, include_tables=False
        )
    except Exception as e:
        log.info("article fetch failed %s: %s", article.url, e)
        extracted = None

    if extracted and len(extracted) > 400:
        article.text = extracted[:MAX_ARTICLE_TEXT_CHARS]
        article.text_is_full = True
    else:
        article.text = article.summary
        article.text_is_full = False


def fetch_all(sources: dict[str, list[str]]) -> list[Article]:
    articles: list[Article] = []
    seen_urls: set[str] = set()

    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for outlet, feeds in sources.items():
            outlet_articles: list[Article] = []
            for feed_url in feeds:
                outlet_articles.extend(_fetch_feed(client, outlet, feed_url))
            # newest first, dedupe by url, cap per outlet
            outlet_articles.sort(key=lambda a: a.published_at, reverse=True)
            kept = []
            for a in outlet_articles:
                if a.url in seen_urls:
                    continue
                seen_urls.add(a.url)
                kept.append(a)
                if len(kept) >= MAX_PER_OUTLET:
                    break
            log.info("%s: %d articles", outlet, len(kept))
            articles.extend(kept)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda a: _fetch_article_text(client, a), articles))

    full = sum(1 for a in articles if a.text_is_full)
    log.info("fetched %d articles (%d with full text)", len(articles), full)
    return articles
