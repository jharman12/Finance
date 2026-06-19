from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)


class PairingDialog(QDialog):
    """Dialog for pairing a remote voice device."""

    pairing_confirmed = pyqtSignal(str)
    pairing_cancelled = pyqtSignal()

    def __init__(
        self,
        device_name: str,
        local_pairing_code: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.device_name = device_name
        self.local_pairing_code = local_pairing_code
        self.setWindowTitle("Pair Remote Voice Device")
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QVBoxLayout()

        title = QLabel(f"Pairing with: {device_name}")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "To confirm pairing, both devices must show the same 6-character code.\n"
            "Codes change every minute, so verify quickly."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        code_label = QLabel("Your pairing code:")
        layout.addWidget(code_label)

        code_display = QLabel(self.local_pairing_code)
        code_display.setObjectName("PairingCode")
        code_display.setAlignment(Qt.AlignCenter)
        code_display.setStyleSheet(
            "QLabel#PairingCode { font-size: 24px; font-weight: bold; padding: 10px; background-color: #f0f0f0; border-radius: 4px; }"
        )
        layout.addWidget(code_display)

        verify_label = QLabel("Enter the code from the remote device:")
        layout.addWidget(verify_label)

        self.remote_code_input = QLineEdit()
        self.remote_code_input.setPlaceholderText("Enter 6-character code...")
        self.remote_code_input.setMaxLength(6)
        self.remote_code_input.returnPressed.connect(self._on_verify)
        layout.addWidget(self.remote_code_input)

        button_layout = QHBoxLayout()

        confirm_button = QPushButton("Confirm Pairing")
        confirm_button.clicked.connect(self._on_verify)
        button_layout.addWidget(confirm_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _on_verify(self) -> None:
        remote_code = self.remote_code_input.text().strip().upper()

        if not remote_code:
            QMessageBox.warning(self, "Empty Code", "Please enter the code from the remote device.")
            return

        if remote_code != self.local_pairing_code:
            QMessageBox.warning(
                self,
                "Code Mismatch",
                f"The codes don't match.\nLocal: {self.local_pairing_code}\nRemote: {remote_code}\n\nCodes change every minute. Please try again.",
            )
            self.remote_code_input.clear()
            return

        self.pairing_confirmed.emit(remote_code)
        self.accept()

    def _on_cancel(self) -> None:
        self.pairing_cancelled.emit()
        self.reject()
