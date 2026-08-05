# NewsDigest

A daily news fact-aggregator. Once per day a pipeline gathers articles from major
news publications, groups articles covering the same event, extracts neutral,
opinion-free fact lists, merges equivalent facts across outlets, and publishes a
JSON digest. A SwiftUI app (iOS + macOS) displays the digest with each fact linked
to every article that reported it, sorted most-corroborated first.

The digest contains **facts and links only** — never article text.

## Architecture

```
GitHub Actions (8:00am daily)
  └─ pipeline/main.py
       1. fetch.py        RSS feeds -> recent articles (+ full text where accessible)
       2. cluster.py      group articles by event (topics need >=2 outlets)
       3. extract.py      per-article neutral facts list        [Claude]
       4. corroborate.py  merge equivalent facts across outlets [Claude]
       5. write docs/digest/latest.json + YYYY-MM-DD.json + index.json
  └─ commit -> GitHub Pages serves docs/
NewsDigestApp (SwiftUI, iOS + macOS) fetches latest.json
```

Processing is centralized so the app is a thin client — App Store-ready: no API
keys in the app, cost is fixed per day regardless of user count, and the digest
is static JSON that scales via CDN.

## Setup

1. Create a GitHub repository and push this folder to it.
2. Repo **Settings → Secrets and variables → Actions**: add secret
   `ANTHROPIC_API_KEY` with your Anthropic API key.
3. Repo **Settings → Pages**: deploy from branch `main`, folder `/docs`.
4. The workflow runs daily (see `.github/workflows/daily.yml` — the cron is UTC;
   adjust to 8:00am in your timezone) or trigger it manually from the Actions tab.
5. In the app's Settings, point the digest URL at
   `https://<username>.github.io/<repo>/digest/`.

## Run the pipeline locally

```
cd pipeline
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python main.py
```

Output is written to `docs/digest/`. Sources are configured in
`pipeline/sources.yaml`. Rough cost: ~$3–8 per daily run with `claude-fable-5`
at 30–80 articles.

## Model backends

The pipeline supports two interchangeable LLM backends (`pipeline/llm.py`):

- `claude` (default) — Anthropic API, `claude-fable-5` (override with `DIGEST_CLAUDE_MODEL`). Needs `ANTHROPIC_API_KEY`.
  Used by the GitHub Actions workflow.
- `ollama` — a local model via [Ollama](https://ollama.com) structured outputs.
  Free, private, no API key; lower fact-extraction quality than Claude.
  Configure with `DIGEST_OLLAMA_MODEL` (default `qwen3:8b`) and `OLLAMA_URL`.

Backends are spec strings: `claude` (= `claude:claude-opus-5`),
`claude:claude-fable-5`, `ollama` (= `ollama:qwen3:8b`), `ollama:kimi-k3:cloud`
(needs an Ollama Pro/Max subscription — the model runs on Ollama's cloud), etc.
Select via `python main.py --backend <spec>` or `DIGEST_LLM_BACKEND=<spec>`.

### Comparing backends

`python compare.py` runs whichever backends are available over an **identical
snapshot** of fetched articles (saved to `compare/articles.json` on first run,
reused afterwards — so you can run the two sides days apart and still compare
fairly). Results: `compare/<backend>.json` and a two-column
`compare/report.html`. Use `--refetch` to take a fresh snapshot,
`--max-topics N` to bound runtime (default 8).
