"""Claude synthesis: turn a (sprint goal, matched item) pair into a single
actionable takeaway tailored to how the item impacts that specific goal."""

import anthropic

from app.core.config import settings

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


SYSTEM_PROMPT = (
    "You are FocusStream's synthesis engine. Given a user's learning goal (an "
    "'Intent Sprint') and a piece of content that matched it, write a single, "
    "actionable one-sentence takeaway explaining how this item impacts the user's "
    "specific goal. Be concrete and specific. Output only the sentence — no preamble, "
    "no quotation marks."
)


def synthesize_takeaway(
    sprint_title: str,
    sprint_description: str,
    item_title: str,
    item_body: str,
) -> str:
    prompt = (
        f"Intent Sprint goal: {sprint_title}\n"
        f"Goal details: {sprint_description}\n\n"
        f"Matched content title: {item_title}\n"
        f"Matched content excerpt: {item_body[:2000]}\n\n"
        "Write the one-sentence actionable takeaway."
    )
    message = _get_client().messages.create(
        model=settings.synthesis_model,
        max_tokens=150,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()
