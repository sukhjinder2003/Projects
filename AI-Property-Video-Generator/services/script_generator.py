"""Script, caption and headline generation.

Two modes:
  1. Template-based (always available, zero setup).
  2. Optional LLM (Anthropic Claude) when ANTHROPIC_API_KEY is set.

Both modes may ONLY use facts the user typed in. For the LLM path this is
enforced twice: in the prompt, and by a post-check that rejects any output
containing a number that is not present in the user's input.
"""
from __future__ import annotations

import json
import logging
import re

import requests

from config import Config

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Facts
# --------------------------------------------------------------------------- #
def build_facts(prop: dict) -> list[str]:
    """Short, factual phrases derived strictly from the user's own input."""
    facts = [f"{prop['property_type']} in {prop['location']}", f"Priced at {prop['price']}"]
    if prop["bedrooms"] or prop["bathrooms"]:
        parts = []
        if prop["bedrooms"]:
            parts.append(f"{prop['bedrooms']} Bedroom{'s' if prop['bedrooms'] != 1 else ''}")
        if prop["bathrooms"]:
            parts.append(f"{prop['bathrooms']} Bathroom{'s' if prop['bathrooms'] != 1 else ''}")
        facts.append(" · ".join(parts))
    facts.append(f"{prop['area']} sq. ft.")
    facts.extend(prop["features"])
    return facts


# --------------------------------------------------------------------------- #
# Template fallback
# --------------------------------------------------------------------------- #
def template_script(prop: dict, image_count: int) -> dict:
    facts = build_facts(prop)
    # Spread captions: first image shows type/location, the rest cycle the facts.
    captions = [facts[i % len(facts)] for i in range(image_count)]

    highlights = []
    if prop["bedrooms"] or prop["bathrooms"]:
        highlights.append(facts[2])
    highlights.append(f"{prop['area']} sq. ft.")
    highlights.extend(prop["features"])
    return {
        "headline": f"Discover {prop['name']}",
        "tagline": f"{prop['property_type']} in {prop['location']}",
        "captions": captions,
        "highlights": highlights[:6],
        "closing": "Get in touch to enquire or arrange a viewing.",
        "source": "template",
        "note": "",
    }


# --------------------------------------------------------------------------- #
# Optional LLM path
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = (
    "You write short, polished real-estate video copy. You may ONLY use the facts "
    "provided by the user. Never invent prices, locations, amenities, distances, "
    "years, awards or any number. If something is not provided, do not mention it. "
    "Reply with a single JSON object and nothing else."
)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", text))


def _llm_script(prop: dict, image_count: int) -> dict:
    facts = {k: v for k, v in prop.items() if k != "contact"}
    user_prompt = (
        f"Property facts (JSON):\n{json.dumps(facts, ensure_ascii=False)}\n\n"
        f"Return JSON with exactly these keys:\n"
        f'  "headline": opening headline, max 8 words\n'
        f'  "tagline": one line under the headline, max 14 words\n'
        f'  "captions": list of exactly {image_count} scene captions, max 7 words each\n'
        f'  "highlights": list of 3 to 6 highlights, max 6 words each\n'
        f'  "closing": final enquiry message, max 16 words (do not include contact details)\n'
        f"Use only the facts above."
    )
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": Config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": Config.ANTHROPIC_MODEL, "max_tokens": 800, "system": SYSTEM_PROMPT,
              "messages": [{"role": "user", "content": user_prompt}]},
        timeout=Config.LLM_TIMEOUT,
    )
    resp.raise_for_status()
    text = "".join(b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI reply did not contain JSON")
    data = json.loads(text[start:end + 1])

    out = {
        "headline": str(data["headline"]).strip()[:80],
        "tagline": str(data.get("tagline", "")).strip()[:120],
        "captions": [str(c).strip()[:60] for c in data["captions"]],
        "highlights": [str(h).strip()[:50] for h in data["highlights"]][:6],
        "closing": str(data.get("closing", "")).strip()[:120],
    }
    if not out["headline"] or len(out["captions"]) != image_count or len(out["highlights"]) < 2:
        raise ValueError("AI reply had the wrong shape")

    # Anti-hallucination guard: every number in the output must exist in the input.
    allowed = _numbers(json.dumps(prop, ensure_ascii=False))
    produced = _numbers(json.dumps(out, ensure_ascii=False))
    if not produced <= allowed:
        raise ValueError(f"AI output contained numbers not in the input: {sorted(produced - allowed)}")
    out.update(source="ai", note="")
    return out


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def llm_available() -> bool:
    return bool(Config.ANTHROPIC_API_KEY)


def generate_script(prop: dict, image_count: int, use_ai: bool = True) -> dict:
    """Return the script dict. Never raises: falls back to templates on any problem."""
    base = template_script(prop, image_count)
    if not (use_ai and llm_available()):
        return base
    try:
        script = _llm_script(prop, image_count)
        if not script["closing"]:
            script["closing"] = base["closing"]
        if not script["tagline"]:
            script["tagline"] = base["tagline"]
        return script
    except Exception as exc:  # network, auth, bad JSON, guard rejection...
        log.warning("AI script generation failed, using templates: %s", exc)
        base["note"] = "The AI service was unavailable or returned unusable text, so the template script was used."
        return base
