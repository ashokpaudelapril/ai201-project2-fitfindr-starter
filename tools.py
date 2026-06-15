"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Model used by the two LLM-backed tools.
_MODEL = "llama-3.3-70b-versatile"

# Words that carry no search signal — dropped before scoring keyword overlap.
_STOPWORDS = {
    "a", "an", "the", "for", "of", "in", "on", "with", "and", "or", "to",
    "i", "im", "my", "me", "looking", "want", "need", "some", "any", "that",
    "this", "it", "is", "are", "under", "size", "something",
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _tokenize(text: str) -> set[str]:
    """Lowercase a string and split it into a set of alphanumeric word tokens."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Keywords from the description, minus stopwords, used for relevance scoring.
    query_terms = _tokenize(description) - _STOPWORDS

    scored: list[tuple[int, dict]] = []
    for item in listings:
        # 1. Price filter (inclusive).
        if max_price is not None and item["price"] > max_price:
            continue

        # 2. Size filter — case-insensitive substring so "M" matches "S/M", "M/L".
        if size is not None and size.strip():
            if size.strip().lower() not in item["size"].lower():
                continue

        # 3. Score by keyword overlap against the item's searchable text.
        haystack = _tokenize(
            " ".join([
                item["title"],
                item["description"],
                item["category"],
                " ".join(item["style_tags"]),
            ])
        )
        score = len(query_terms & haystack)

        # 4. Drop items with no keyword overlap (unless no terms were given).
        if query_terms and score == 0:
            continue

        scored.append((score, item))

    # 5. Sort by score, highest first (stable: ties keep dataset order).
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = (
        f"{new_item.get('title', 'an item')} "
        f"(category: {new_item.get('category', 'unknown')}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'}, "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'})"
    )

    items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []

    if not items:
        # Empty wardrobe → general styling advice instead of specific pairings.
        prompt = (
            f"A shopper is considering buying this secondhand piece: {item_desc}.\n"
            "They haven't told us what's in their closet yet. In 2-3 sentences, give "
            "general styling advice: what kinds of pieces pair well with it, what vibe "
            "it suits, and one concrete way to wear it. Be specific and friendly."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {it.get('name', 'item')} "
            f"({it.get('category', '?')}; {', '.join(it.get('colors', []))})"
            for it in items
        )
        prompt = (
            f"A shopper is considering buying this secondhand piece: {item_desc}.\n\n"
            f"Here is their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair the new piece with specific items "
            "from their wardrobe (refer to the wardrobe pieces by name). Keep it to "
            "3-4 sentences total and include one concrete styling tip (e.g. cuff, tuck, "
            "layer)."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        text = response.choices[0].message.content.strip()
        if not text:
            raise ValueError("empty LLM response")
        return text
    except Exception:
        # LLM/network failure → graceful fallback so the loop can still continue.
        return (
            f"Couldn't reach the styling model right now, but {new_item.get('title', 'this piece')} "
            "pairs easily with neutral basics — think simple denim or trousers and clean sneakers."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty or whitespace-only outfit string.
    if not outfit or not outfit.strip():
        return (
            "Can't write a fit card without an outfit suggestion to base it on — "
            "run suggest_outfit first."
        )

    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else "a steal"

    prompt = (
        "Write a short, casual social-media caption for a secondhand fashion find "
        "(like a real OOTD / thrift-haul post, NOT a product description).\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Outfit: {outfit}\n\n"
        "Rules: 2-4 sentences, lowercase-casual is fine, mention the item, price, and "
        "platform naturally (once each), capture the vibe in specific terms, and feel "
        "free to use an emoji or two. Make it sound like a real person, not an ad."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,  # higher temp → varied captions across calls
        )
        text = response.choices[0].message.content.strip()
        if not text:
            raise ValueError("empty LLM response")
        return text
    except Exception:
        # LLM/network failure → fallback caption built from the item fields.
        return (
            f"thrifted this {title.lower()} off {platform or 'a resale app'} for "
            f"{price_str} and i'm obsessed ✨ styled it exactly how i wanted."
        )
