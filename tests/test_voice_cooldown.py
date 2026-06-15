from __future__ import annotations

import unittest

from finance_app.services.voice_pipeline import VoiceCoordinator


class VoiceCooldownTests(unittest.TestCase):
    def test_in_cooldown_true_before_expiry(self) -> None:
        coordinator = VoiceCoordinator(wake_phrase="hey steven")
        coordinator._cooldown_until = 100.0  # noqa: SLF001

        self.assertTrue(coordinator._in_cooldown(now=99.0))  # noqa: SLF001

    def test_in_cooldown_false_after_expiry_and_resets(self) -> None:
        coordinator = VoiceCoordinator(wake_phrase="hey steven")
        coordinator._cooldown_until = 100.0  # noqa: SLF001

        self.assertFalse(coordinator._in_cooldown(now=100.1))  # noqa: SLF001
        self.assertEqual(coordinator._cooldown_until, 0.0)  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
