from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout

from finance_app.services.assistant_service import AssistantService


class AssistantWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, assistant_service: AssistantService, prompt_text: str, session_key: str | None = None) -> None:
        super().__init__()
        self.assistant_service = assistant_service
        self.prompt_text = prompt_text
        self.session_key = session_key

    def run(self) -> None:
        try:
            result = self.assistant_service.handle_prompt(self.prompt_text, session_key=self.session_key)
        except Exception as exc:  # pragma: no cover - surface to the UI
            self.failed.emit(str(exc))
            return
        self.result_ready.emit(result)


class OllamaWarmupWorker(QThread):
    ready = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, assistant_service: AssistantService) -> None:
        super().__init__()
        self.assistant_service = assistant_service

    def run(self) -> None:
        try:
            self.assistant_service.client.ensure_running()
        except Exception as exc:  # pragma: no cover - surface to the UI
            self.failed.emit(str(exc))
            return
        self.ready.emit()


class MetricCard(QFrame):
    def __init__(self, title: str, value: str) -> None:
        super().__init__()
        self.setObjectName("MetricCard")
        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricCardTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricCardValue")
        self.value_label.setProperty("tone", "default")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str, is_warning: bool = False) -> None:
        self.value_label.setText(value)
        tone = "warning" if is_warning else "default"
        self.value_label.setProperty("tone", tone)
        style = self.value_label.style()
        style.unpolish(self.value_label)
        style.polish(self.value_label)
