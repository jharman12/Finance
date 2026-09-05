from __future__ import annotations

import re
from dataclasses import dataclass, field

from finance_app.models import AssistantResult

MAX_AUDIO_SCRIPT_CHARS = 600

_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
_MARKDOWN_BULLET = re.compile(r"^\s*[-*+]\s+")
_MARKDOWN_ORDERED = re.compile(r"^\s*\d+[.)]\s+")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_DIVIDER = re.compile(r"^\s*\|?[\s:-]+\|[\s:|-]*$")
_INLINE_MARKUP = re.compile(r"(\*\*|__|\*|_|`)")
_CURRENCY = re.compile(r"\$\s?(-?\d[\d,]*)(?:\.(\d{1,2}))?")


@dataclass(slots=True)
class FormattedAssistantResponse:
    display_text: str
    audio_script: str
    applied_actions: list[str] = field(default_factory=list)
    truncated: bool = False


def format_assistant_response(
    result: AssistantResult,
    max_audio_chars: int = MAX_AUDIO_SCRIPT_CHARS,
) -> FormattedAssistantResponse:
    """Produce display text plus a speech-friendly script from one assistant result."""
    display_text = (result.reply or "").strip()
    applied_actions = [str(action).strip() for action in result.applied_actions if str(action).strip()]

    spoken_body = _to_spoken_text(display_text)
    audio_script, truncated = _limit_for_speech(spoken_body, max_audio_chars)

    if not audio_script and applied_actions:
        audio_script = _summarize_actions(applied_actions)

    return FormattedAssistantResponse(
        display_text=display_text,
        audio_script=audio_script,
        applied_actions=applied_actions,
        truncated=truncated,
    )


def _to_spoken_text(text: str) -> str:
    if not text:
        return ""

    spoken_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _TABLE_DIVIDER.match(line):
            continue
        if _TABLE_ROW.match(line):
            line = " ".join(cell.strip() for cell in line.strip("|").split("|") if cell.strip())
        line = _MARKDOWN_HEADING.sub("", line)
        line = _MARKDOWN_BULLET.sub("", line)
        line = _MARKDOWN_ORDERED.sub("", line)
        line = _INLINE_MARKUP.sub("", line)
        line = _CURRENCY.sub(_speak_currency, line)
        line = " ".join(line.split())
        if line:
            spoken_lines.append(_ensure_sentence_end(line))

    return " ".join(spoken_lines).strip()


def _speak_currency(match: re.Match[str]) -> str:
    whole = match.group(1).replace(",", "")
    cents = match.group(2)
    try:
        amount = int(whole)
    except ValueError:
        return match.group(0)

    dollar_word = "dollar" if abs(amount) == 1 else "dollars"
    if not cents:
        return f"{amount} {dollar_word}"

    cent_value = int(cents.ljust(2, "0"))
    if cent_value == 0:
        return f"{amount} {dollar_word}"
    cent_word = "cent" if cent_value == 1 else "cents"
    return f"{amount} {dollar_word} and {cent_value} {cent_word}"


def _ensure_sentence_end(line: str) -> str:
    return line if line[-1] in ".!?:" else f"{line}."


def _limit_for_speech(text: str, max_chars: int) -> tuple[str, bool]:
    limit = max(1, int(max_chars))
    if len(text) <= limit:
        return text, False

    window = text[:limit]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut > 0:
        return window[: cut + 1].strip(), True
    return f"{window.rsplit(' ', 1)[0].strip()}...", True


def _summarize_actions(applied_actions: list[str]) -> str:
    count = len(applied_actions)
    if count == 1:
        return f"Done. {_ensure_sentence_end(applied_actions[0])}"
    return f"Done. Applied {count} updates."
