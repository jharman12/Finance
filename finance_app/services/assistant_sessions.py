from __future__ import annotations


def normalize_source_id(source_id: str | None) -> str:
    cleaned = str(source_id or "").strip()
    return cleaned or "local-usb-mic"


def voice_assistant_session_key(source_id: str | None) -> str:
    return f"voice::{normalize_source_id(source_id)}"


def voice_confirmation_session_key(source_id: str | None) -> str:
    return f"assistant::{normalize_source_id(source_id)}"


def typed_assistant_session_key() -> str:
    return "typed-assistant"
