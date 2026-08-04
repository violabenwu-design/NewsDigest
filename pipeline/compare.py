"""Side-by-side backend comparison: run the digest stages on IDENTICAL articles.

Usage:
  python compare.py                       # run every available backend
  python compare.py --backends ollama     # just one
  python compare.py --refetch             # discard the article snapshot

The first run snapshots fetched articles to compare/articles.json; later runs
(e.g. the claude side, once an API key is available) reuse that snapshot so both
backends see exactly the same input. Results land in compare/<backend>.json and
a two-column compare/report.html.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path

import llm
from cluster import cluster_articles
from compose import compose_topic
from corroborate import corroborate_topic
from extract import extract_facts
from fetch import fetch_all, load_sources
from schema import Article, build_digest

log = logging.getLogger("compare")

COMPARE_DIR = Path(__file__).resolve().parent.parent / "compare"


def _slug(spec: str) -> str:
    return spec.replace(":", "-").replace("/", "-")


def get_articles(refetch: bool) -> list[Article]:
    snapshot = COMPARE_DIR / "articles.json"
    if snapshot.exists() and not refetch:
        data = json.loads(snapshot.read_text())
        log.info("reusing article snapshot from %s (%d articles)",
                 data["fetched_at"], len(data["articles"]))
        return [Article(**a) for a in data["articles"]]

    sources = load_sources(Path(__file__).resolve().parent / "sources.yaml")
    articles = fetch_all(sources)
    COMPARE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps({
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "articles": [asdict(a) for a in articles],
    }, ensure_ascii=False))
    log.info("snapshotted %d articles", len(articles))
    return articles


def backend_available(spec: str) -> bool:
    kind, model = llm.resolve(spec)
    if kind == "claude":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            log.warning("skipping %s: ANTHROPIC_API_KEY not set", spec)
            return False
        return True
    # ollama: check the server is up AND this model actually responds
    # (cloud models can 403 without a subscription)
    import httpx
    try:
        r = httpx.post(
            f"{llm.OLLAMA_URL}/api/chat",
            json={"model": model, "messages": [{"role": "user", "content": "hi"}],
                  "stream": False, "options": {"num_predict": 1}},
            timeout=120,
        )
        if r.status_code != 200:
            log.warning("skipping %s: %s", spec, r.json().get("error", r.text[:200]))
            return False
        return True
    except Exception as e:
        log.warning("skipping %s: %s", spec, e)
        return False


def run_backend(spec: str, articles: list[Article], max_topics: int) -> dict:
    llm.BACKEND = spec
    kind, model = llm.resolve(spec)
    log.info("=== %s (%s) ===", kind, model)
    timings = {}

    t0 = time.monotonic()
    topics = cluster_articles(articles)
    timings["cluster_s"] = round(time.monotonic() - t0, 1)

    # biggest stories first, capped for comparable runtime across backends
    topics.sort(key=lambda t: -len(t.articles))
    topics = topics[:max_topics]

    t0 = time.monotonic()
    facts_by_article = extract_facts(topics)
    timings["extract_s"] = round(time.monotonic() - t0, 1)

    t0 = time.monotonic()
    for topic in topics:
        corroborate_topic(topic, facts_by_article)
    timings["corroborate_s"] = round(time.monotonic() - t0, 1)

    topics = [t for t in topics if t.facts]

    t0 = time.monotonic()
    for topic in topics:
        compose_topic(topic)
    timings["compose_s"] = round(time.monotonic() - t0, 1)
    digest = build_digest(time.strftime("%Y-%m-%d"), {}, topics)
    digest["comparison_meta"] = {
        "backend": kind,
        "model": model,
        "timings": timings,
        "articles_in": len(articles),
    }
    out = COMPARE_DIR / f"{_slug(spec)}.json"
    out.write_text(json.dumps(digest, indent=2, ensure_ascii=False))
    log.info("%s done: %d topics, timings %s -> %s", spec, len(topics), timings, out)
    return digest


def render_report() -> Path:
    columns = []
    for path in sorted(COMPARE_DIR.glob("*.json")):
        if path.name == "articles.json":
            continue
        digest = json.loads(path.read_text())
        if "comparison_meta" in digest:
            columns.append((path.stem, digest))
    # claude columns first, then the rest, alphabetically within each group
    columns.sort(key=lambda c: (c[1]["comparison_meta"].get("backend") != "claude", c[0]))

    def esc(s: str) -> str:
        return html.escape(s, quote=False)

    def fact_html(f: dict, outlets: dict) -> str:
        chips = "".join(
            f"<span class='chip'>{esc(outlets.get(s, s))}</span>" for s in f["sources"]
        )
        return f"{esc(f['text'])} <span class='chips'>{chips}</span>"

    col_html = []
    for backend, digest in columns:
        meta = digest.get("comparison_meta", {})
        topics_html = []
        for t in digest["topics"]:
            outlets = {a["id"]: a["outlet"] for a in t["articles"]}
            if t.get("paragraphs"):
                body = "".join(
                    "<p class='para'>"
                    + " ".join(fact_html(t["facts"][i], outlets) for i in group)
                    + "</p>"
                    for group in t["paragraphs"]
                )
            else:
                body = "<ul>" + "".join(
                    f"<li><span class='badge n{min(len(f['sources']), 3)}'>{len(f['sources'])}</span> "
                    + fact_html(f, outlets) + "</li>"
                    for f in t["facts"]
                ) + "</ul>"
            arts = ", ".join(sorted({a["outlet"] for a in t["articles"]}))
            topics_html.append(
                f"<details open><summary>{esc(t['title'])} <small>({esc(arts)})</small></summary>"
                f"{body}</details>"
            )
        timings = meta.get("timings", {})
        total = sum(timings.values())
        col_html.append(
            f"<div class='col'><h2>{esc(meta.get('model', backend))}</h2>"
            f"<p class='meta'>{len(digest['topics'])} topics · generated {esc(digest['generated_at'])}"
            f" · cluster {timings.get('cluster_s', '?')}s, extract {timings.get('extract_s', '?')}s,"
            f" corroborate {timings.get('corroborate_s', '?')}s, compose {timings.get('compose_s', '?')}s"
            f" (total {total:.0f}s)</p>"
            + "".join(topics_html) + "</div>"
        )

    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>NewsDigest backend comparison</title>
<style>
 body {{ font: 15px/1.45 -apple-system, system-ui, sans-serif; margin: 1.5rem; color: #1a1a1a; }}
 .wrap {{ display: flex; gap: 2rem; align-items: flex-start; }}
 .col {{ flex: 1; min-width: 0; }}
 h2 {{ font-size: 1.1rem; border-bottom: 2px solid #ddd; padding-bottom: .4rem; }}
 .meta {{ color: #777; font-size: .8rem; }}
 details {{ margin: .8rem 0; }}
 summary {{ font-weight: 600; cursor: pointer; }}
 summary small {{ color: #888; font-weight: 400; }}
 ul {{ padding-left: 1.1rem; margin: .4rem 0; }}
 li {{ margin: .5rem 0; }}
 .badge {{ display: inline-block; min-width: 1.2em; text-align: center; border-radius: 999px;
          color: #fff; font-size: .75rem; font-weight: 700; padding: .05em .45em; }}
 .n1 {{ background: #9aa0a6; }} .n2 {{ background: #4285f4; }} .n3 {{ background: #34a853; }}
 .chips {{ margin-top: .15rem; }}
 .para {{ margin: .6rem 0; }}
 .chip {{ display: inline-block; background: #eee; border-radius: 999px; padding: .05em .6em;
         font-size: .72rem; margin-right: .3rem; color: #555; }}
 @media (prefers-color-scheme: dark) {{
   body {{ background: #1c1c1e; color: #eee; }}
   .chip {{ background: #333; color: #bbb; }} h2 {{ border-color: #444; }}
 }}
</style></head><body>
<h1>NewsDigest — backend comparison</h1>
<p class="meta">Same article snapshot, same prompts, same pipeline — only the model differs.
Badge = number of outlets corroborating the fact.</p>
<div class="wrap">{"".join(col_html) if col_html else "<p>No backend results yet.</p>"}</div>
</body></html>"""
    out = COMPARE_DIR / "report.html"
    out.write_text(page)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backends", default="claude,ollama")
    parser.add_argument("--max-topics", type=int, default=8)
    parser.add_argument("--refetch", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    articles = get_articles(args.refetch)

    for backend in [b.strip() for b in args.backends.split(",") if b.strip()]:
        if backend_available(backend):
            run_backend(backend, articles, args.max_topics)

    report = render_report()
    log.info("report: %s", report)


if __name__ == "__main__":
    main()
