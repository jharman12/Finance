from __future__ import annotations

import math

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

VOICE_STATES = ("ready", "listening", "processing", "done")

_STATE_TEXT = {
    "ready": "Voice: Ready",
    "listening": "Voice: Listening",
    "processing": "Voice: Processing",
    "done": "Voice: Done",
}

# The glyph carries state without relying on colour alone.
_STATE_GLYPH = {
    "ready": "\u25cb",
    "listening": "\u25c9",
    "processing": "\u25d0",
    "done": "\u2713",
}

_STATE_COLOUR = {
    "ready": "#90a4bf",
    "listening": "#2ec4b6",
    "processing": "#ffd166",
    "done": "#8de59b",
}

CONNECTION_STATES = ("connected", "reconnecting", "disconnected", "none")

_CONNECTION_GLYPH = {
    "connected": "\u25cf",
    "reconnecting": "\u25d0",
    "disconnected": "\u25cb",
    "none": "\u25cb",
}


class VoiceWaveformWidget(QWidget):
    """Lightweight activity animation driven by a QTimer, never blocking the event loop."""

    BAR_COUNT = 5

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("VoiceWaveform")
        self.setFixedSize(56, 18)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAccessibleName("Voice activity animation")

        self._phase = 0.0
        self._levels = [0.25] * self.BAR_COUNT
        self._has_audio_levels = False
        self._bar_colour = QColor(_STATE_COLOUR["listening"])

        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._advance)

    def is_animating(self) -> bool:
        return self._timer.isActive()

    def set_active(self, active: bool) -> None:
        if active and not self._timer.isActive():
            self._timer.start()
        elif not active and self._timer.isActive():
            self._timer.stop()
            self._levels = [0.25] * self.BAR_COUNT
            self._has_audio_levels = False
            self.update()

    def set_interval_ms(self, interval_ms: int) -> None:
        self._timer.setInterval(max(16, int(interval_ms)))

    def set_bar_colour(self, colour: str) -> None:
        self._bar_colour = QColor(colour)
        self.update()

    def submit_level(self, level_0_1: float) -> None:
        """Feed real amplitude; switches the animation off its indeterminate pattern."""
        self._has_audio_levels = True
        self._levels = self._levels[1:] + [max(0.08, min(1.0, float(level_0_1)))]

    def _advance(self) -> None:
        self._phase += 0.45
        if not self._has_audio_levels:
            self._levels = [
                0.30 + 0.55 * (0.5 + 0.5 * math.sin(self._phase - index * 0.7))
                for index in range(self.BAR_COUNT)
            ]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._bar_colour)
        bar_width, gap = 6, 4
        for index, level in enumerate(self._levels):
            height = max(3, int(self.height() * level))
            x = index * (bar_width + gap)
            y = (self.height() - height) // 2
            painter.drawRoundedRect(x, y, bar_width, height, 2, 2)
        painter.end()


class VoiceIndicatorWidget(QFrame):
    """Four-state voice status shown in the status bar, visible from every tab."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("VoiceIndicator")
        self.setProperty("state", "ready")

        self.glyph_label = QLabel(_STATE_GLYPH["ready"])
        self.glyph_label.setObjectName("VoiceIndicatorGlyph")
        self.glyph_label.setProperty("state", "ready")

        self.waveform = VoiceWaveformWidget()
        self.waveform.setVisible(False)

        self.text_label = QLabel(_STATE_TEXT["ready"])
        self.text_label.setObjectName("VoiceIndicatorText")
        self.text_label.setProperty("state", "ready")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(8)
        layout.addWidget(self.glyph_label)
        layout.addWidget(self.waveform)
        layout.addWidget(self.text_label)

        self._state = "ready"
        self._detail = ""
        self._apply_accessible_text()

    def state(self) -> str:
        return self._state

    def detail(self) -> str:
        return self._detail

    def set_state(self, state: str, detail: str = "") -> None:
        state = state if state in VOICE_STATES else "ready"
        detail = str(detail or "").strip()
        if state == self._state and detail == self._detail:
            return

        self._state = state
        self._detail = detail

        self.glyph_label.setText(_STATE_GLYPH[state])
        self.text_label.setText(_STATE_TEXT[state])
        for widget in (self, self.glyph_label, self.text_label):
            widget.setProperty("state", state)
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)

        animating = state in ("listening", "processing")
        self.waveform.setVisible(animating)
        self.waveform.set_bar_colour(_STATE_COLOUR[state])
        self.waveform.set_interval_ms(90 if state == "processing" else 60)
        self.waveform.set_active(animating)
        self._apply_accessible_text()

    def stop_animation(self) -> None:
        self.waveform.set_active(False)

    def _apply_accessible_text(self) -> None:
        label = _STATE_TEXT[self._state]
        full = f"{label}. {self._detail}" if self._detail else label
        self.setAccessibleName(label)
        self.setAccessibleDescription(full)
        self.setToolTip(full)
        self.text_label.setAccessibleName(full)


class ConnectionStatusWidget(QFrame):
    """Compact remote-device summary derived from existing runtime state."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectionStatus")
        self.setProperty("state", "none")

        self.glyph_label = QLabel(_CONNECTION_GLYPH["none"])
        self.glyph_label.setObjectName("ConnectionStatusGlyph")
        self.glyph_label.setProperty("state", "none")

        self.text_label = QLabel("No remote devices")
        self.text_label.setObjectName("ConnectionStatusText")
        self.text_label.setProperty("state", "none")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(8)
        layout.addWidget(self.glyph_label)
        layout.addWidget(self.text_label)

        self._state = "none"
        self._apply_accessible_text("No remote devices")

    def state(self) -> str:
        return self._state

    def set_status(self, state: str, connected: int, known: int) -> None:
        state = state if state in CONNECTION_STATES else "none"
        if known <= 0:
            text = "No remote devices"
        elif state == "connected":
            text = f"Remote: {connected}/{known} connected"
        elif state == "reconnecting":
            text = f"Remote: reconnecting ({known} known)"
        else:
            text = f"Remote: disconnected ({known} known)"

        self._state = state
        self.glyph_label.setText(_CONNECTION_GLYPH[state])
        self.text_label.setText(text)
        for widget in (self, self.glyph_label, self.text_label):
            widget.setProperty("state", state)
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
        self._apply_accessible_text(text)

    def _apply_accessible_text(self, text: str) -> None:
        self.setAccessibleName("Remote device connection status")
        self.setAccessibleDescription(text)
        self.setToolTip(f"{text}. Open the Voice Test tab for details.")
        self.text_label.setAccessibleName(text)
