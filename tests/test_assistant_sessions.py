from __future__ import annotations

import unittest

from finance_app.services.assistant_sessions import (
    normalize_source_id,
    typed_assistant_session_key,
    voice_assistant_session_key,
    voice_confirmation_session_key,
)


class AssistantSessionKeyTests(unittest.TestCase):
    def test_normalize_source_id_defaults_local(self) -> None:
        self.assertEqual(normalize_source_id(None), "local-usb-mic")
        self.assertEqual(normalize_source_id("   "), "local-usb-mic")

    def test_voice_assistant_session_key(self) -> None:
        self.assertEqual(voice_assistant_session_key("node-1"), "voice::node-1")
        self.assertEqual(voice_assistant_session_key(" "), "voice::local-usb-mic")

    def test_voice_confirmation_session_key(self) -> None:
        self.assertEqual(voice_confirmation_session_key("node-2"), "assistant::node-2")
        self.assertEqual(voice_confirmation_session_key(""), "assistant::local-usb-mic")

    def test_typed_assistant_session_key(self) -> None:
        self.assertEqual(typed_assistant_session_key(), "typed-assistant")


if __name__ == "__main__":
    unittest.main()
