from __future__ import annotations

from dataclasses import dataclass

from finance_app.services.voice.command_event import VoiceCommandEvent


@dataclass(slots=True)
class VoiceExecutionDecision:
    mode: str  # execute | confirm | clarify
    reason: str


def evaluate_voice_command_event(
    event: VoiceCommandEvent,
    auto_execute_threshold: float = 0.80,
    confirm_threshold: float = 0.60,
) -> VoiceExecutionDecision:
    """Classify how a spoken command should be handled before assistant execution."""

    confidence = event.confidence_0_1
    text = (event.text or "").strip()
    if not text:
        return VoiceExecutionDecision(mode="clarify", reason="empty_command")

    # Backward-compatible behavior for providers/tests that do not supply confidence.
    if confidence is None:
        return VoiceExecutionDecision(mode="execute", reason="missing_confidence")

    if confidence < confirm_threshold:
        return VoiceExecutionDecision(mode="clarify", reason="low_confidence")

    if confidence < auto_execute_threshold and _is_mutation_request(text):
        return VoiceExecutionDecision(mode="confirm", reason="medium_confidence_mutation")

    return VoiceExecutionDecision(mode="execute", reason="confidence_ok")


def is_confirmation_phrase(text: str) -> bool:
    normalized = _normalize_text(text)
    return normalized in {
        "yes",
        "confirm",
        "yes confirm",
        "go ahead",
        "do it",
        "proceed",
    }


def is_rejection_phrase(text: str) -> bool:
    normalized = _normalize_text(text)
    return normalized in {
        "no",
        "cancel",
        "stop",
        "never mind",
        "dont do it",
        "do not do it",
    }


def _is_mutation_request(prompt_text: str) -> bool:
    text = _normalize_text(prompt_text)
    mutation_keywords = (
        "add ",
        "create",
        "edit",
        "update",
        "change",
        "reassign",
        "assign",
        "move",
        "rename",
        "delete",
        "remove",
    )
    return any(keyword in text for keyword in mutation_keywords)


def _normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in lowered)
    return " ".join(cleaned.split())
