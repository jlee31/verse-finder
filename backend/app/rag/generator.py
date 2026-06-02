"""Grounded reflection generation with Claude Haiku."""
import anthropic

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = (
    "You are a thoughtful companion. Someone shares what they are going "
    "through, and you respond by reflecting on a small set of quotes you are "
    "given.\n\n"
    "Rules:\n"
    "- Ground your reflection ONLY in the provided quotes. Never invent quotes "
    "or attribute ideas to authors not listed.\n"
    "- Write 2-4 sentences. Be warm and direct, not preachy.\n"
    "- Weave in the ideas from the quotes; don't just repeat them verbatim.\n"
    "- If none of the quotes genuinely fit the situation, say so honestly."
)

# Lazily created so the module imports even without ANTHROPIC_API_KEY set —
# retrieval and /docs still work; only generation needs the key.
_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def generate_reflection(query: str, quotes: list[dict]) -> str:
    """Write a short reflection on the query, grounded in the retrieved quotes."""
    context = "\n".join(
        f'{i + 1}. "{q["text"]}" — {q["author"]}' for i, q in enumerate(quotes)
    )
    user_message = (
        f'Here is what someone shared:\n"{query}"\n\n'
        f"Here are some quotes that may be relevant:\n{context}\n\n"
        "Write a short reflection grounded in these quotes."
    )

    response = _get_client().messages.create(
        model=MODEL,
        max_tokens=512,
        # Marked cacheable for when the prompt grows. Haiku only caches prefixes
        # >= 4096 tokens, so it's a no-op at the current length.
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    return next(block.text for block in response.content if block.type == "text")
