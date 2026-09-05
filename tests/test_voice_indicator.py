from __future__ import annotations

import unittest

from PyQt5.QtWidgets import QApplication

from finance_app.ui.voice_indicator import (
    ConnectionStatusWidget,
    VoiceIndicatorWidget,
    VoiceWaveformWidget,
)


class VoiceIndicatorWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_starts_in_ready_state(self) -> None:
        widget = VoiceIndicatorWidget()

        self.assertEqual(widget.state(), "ready")
        self.assertFalse(widget.waveform.isVisible())

    def test_state_transitions_update_text_and_property(self) -> None:
        widget = VoiceIndicatorWidget()

        widget.set_state("listening")

        self.assertEqual(widget.state(), "listening")
        self.assertEqual(widget.property("state"), "listening")
        self.assertIn("Listening", widget.text_label.text())

    def test_unknown_state_falls_back_to_ready(self) -> None:
        widget = VoiceIndicatorWidget()

        widget.set_state("exploded")

        self.assertEqual(widget.state(), "ready")

    def test_glyph_differs_per_state_so_colour_is_not_the_only_signal(self) -> None:
        widget = VoiceIndicatorWidget()
        glyphs = set()
        for state in ("ready", "listening", "processing", "done"):
            widget.set_state(state)
            glyphs.add(widget.glyph_label.text())

        self.assertEqual(len(glyphs), 4)

    def test_detail_is_exposed_for_screen_readers(self) -> None:
        widget = VoiceIndicatorWidget()

        widget.set_state("processing", "transcribing your command")

        self.assertIn("transcribing your command", widget.accessibleDescription())
        self.assertIn("transcribing your command", widget.toolTip())

    def test_animation_runs_only_in_active_states(self) -> None:
        widget = VoiceIndicatorWidget()

        widget.set_state("listening")
        self.assertTrue(widget.waveform.is_animating())

        widget.set_state("done")
        self.assertFalse(widget.waveform.is_animating())

    def test_stop_animation_halts_timer(self) -> None:
        widget = VoiceIndicatorWidget()
        widget.set_state("processing")

        widget.stop_animation()

        self.assertFalse(widget.waveform.is_animating())


class VoiceWaveformWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_indeterminate_levels_change_over_time(self) -> None:
        widget = VoiceWaveformWidget()
        first = list(widget._levels)

        widget._advance()

        self.assertNotEqual(first, widget._levels)

    def test_submitted_levels_are_clamped(self) -> None:
        widget = VoiceWaveformWidget()

        widget.submit_level(5.0)
        widget.submit_level(-2.0)

        self.assertLessEqual(max(widget._levels), 1.0)
        self.assertGreaterEqual(min(widget._levels), 0.08)

    def test_real_levels_suppress_indeterminate_pattern(self) -> None:
        widget = VoiceWaveformWidget()
        widget.submit_level(0.9)
        levels_before = list(widget._levels)

        widget._advance()

        self.assertEqual(levels_before, widget._levels)

    def test_deactivating_resets_to_idle(self) -> None:
        widget = VoiceWaveformWidget()
        widget.set_active(True)
        widget.submit_level(0.9)

        widget.set_active(False)

        self.assertFalse(widget.is_animating())
        self.assertEqual(widget._levels, [0.25] * VoiceWaveformWidget.BAR_COUNT)


class ConnectionStatusWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_default_reports_no_devices(self) -> None:
        widget = ConnectionStatusWidget()

        self.assertEqual(widget.state(), "none")
        self.assertIn("No remote devices", widget.text_label.text())

    def test_connected_shows_counts(self) -> None:
        widget = ConnectionStatusWidget()

        widget.set_status("connected", connected=2, known=3)

        self.assertEqual(widget.state(), "connected")
        self.assertIn("2/3", widget.text_label.text())

    def test_reconnecting_state(self) -> None:
        widget = ConnectionStatusWidget()

        widget.set_status("reconnecting", connected=0, known=1)

        self.assertEqual(widget.property("state"), "reconnecting")
        self.assertIn("reconnecting", widget.text_label.text())

    def test_known_zero_overrides_state_text(self) -> None:
        widget = ConnectionStatusWidget()

        widget.set_status("connected", connected=0, known=0)

        self.assertIn("No remote devices", widget.text_label.text())


if __name__ == "__main__":
    unittest.main()
