from __future__ import annotations


def normalize_command_text(text: str) -> str:
    """Normalize transcript text before assistant dispatch."""
    cleaned = " ".join((text or "").strip().split())

    replacements = {
        "dollar sign": "dollars",
        "bucks": "dollars",
        "grocery": "groceries",
    }

    lowered = cleaned.lower()
    for old, new in replacements.items():
        lowered = lowered.replace(old, new)

    return lowered
