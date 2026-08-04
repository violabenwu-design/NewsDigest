"""Stage 5: arrange each topic's corroborated facts into readable paragraphs.

The model never writes prose here — it only returns fact ids grouped and
ordered into paragraphs. The digest stores index lists into the topic's facts
array, so every fact's wording and source links are preserved verbatim.
"""
from __future__ import annotations

import logging

from llm import structured_call
from schema import Topic

log = logging.getLogger(__name__)

SYSTEM = """You arrange the fact sentences of one news story into readable
paragraphs. You are given numbered facts (f1, f2, ...) that all relate to the
same event.

- Group related facts into the same paragraph and order facts so the whole
  sequence reads naturally: what happened first, then key details, then
  responses, reactions, and context.
- Use 1-5 paragraphs. Short topics may need only one.
- Use only the given fact ids. Use every id exactly once.
- You are NOT writing text. Output only the ids, grouped into paragraphs."""

SCHEMA = {
    "type": "object",
    "properties": {
        "paragraphs": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "string"}},
        }
    },
    "required": ["paragraphs"],
    "additionalProperties": False,
}


def compose_topic(topic: Topic) -> None:
    """Set topic.paragraphs to ordered fact-index groups."""
    if not topic.facts:
        topic.paragraphs = []
        return
    if len(topic.facts) <= 2:
        topic.paragraphs = [list(range(len(topic.facts)))]
        return

    listing = "\n".join(f"f{i+1}: {f.text}" for i, f in enumerate(topic.facts))
    user = f"Event: {topic.title}\n\nFacts:\n{listing}"
    result = structured_call(SYSTEM, user, SCHEMA, max_tokens=1500)

    paragraphs: list[list[int]] = []
    seen: set[int] = set()
    if result:
        for group in result.get("paragraphs", []):
            indices = []
            for fid in group:
                try:
                    idx = int(str(fid).lstrip("f")) - 1
                except ValueError:
                    continue
                if 0 <= idx < len(topic.facts) and idx not in seen:
                    seen.add(idx)
                    indices.append(idx)
            if indices:
                paragraphs.append(indices)

    # never lose a fact: anything the model didn't place goes in a final paragraph
    leftover = [i for i in range(len(topic.facts)) if i not in seen]
    if leftover:
        paragraphs.append(leftover)
    topic.paragraphs = paragraphs
    log.info("topic %s: %d facts -> %d paragraphs", topic.id, len(topic.facts), len(paragraphs))
