"""Device pairing dialog for remote voice senders."""

from __future__ import annotations

import socket
import uuid
from typing import Any

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
)

from finance_app.services.voice.discovery import (
    RemoteVoiceDiscoveryBrowser,
    RemoteVoiceDiscoveryDevice,
    SERVICE_TYPE_SENDER,
    resolve_local_ipv4,
)
from finance_app.services.voice.pairing import PairingCodeGenerator
from finance_app.services.voice.pairing_manager import RemoteVoicePairingManager


class DevicePairingDialog(QDialog):
    """Dialog for discovering and pairing with remote voice senders."""

    pairing_confirmed = pyqtSignal(str, str, object)  # Signals (source_id, pairing_code, device)
    pairing_cancelled = pyqtSignal()
    device_discovered_signal = pyqtSignal(object)
    diagnostic_signal = pyqtSignal(object)
    pairing_verified_signal = pyqtSignal(str, str)

    def __init__(self, auth_token: str, pairing_manager: RemoteVoicePairingManager | None = None, parent: Any = None) -> None:
        super().__init__(parent)
        self.auth_token = auth_token
        self.pairing_manager = pairing_manager
        self._selected_device: RemoteVoiceDiscoveryDevice | None = None
        self._discovered_devices: dict[str, RemoteVoiceDiscoveryDevice] = {}
        self._local_hosts = self._collect_local_hosts()
        self._discovery_browser: RemoteVoiceDiscoveryBrowser | None = None
        self._pairing_session_id = ""  # Phase 2: Unique session ID for current pairing attempt
        self._pairing_timeout_timer = QTimer()
        self._pairing_timeout_timer.setSingleShot(True)
        self._pairing_timeout_timer.timeout.connect(self._on_pairing_timeout)
        self._finalized = False
        self.device_discovered_signal.connect(self._handle_discovered_device)
        self.diagnostic_signal.connect(self._handle_diagnostic)
        self.pairing_verified_signal.connect(self.on_pairing_confirmed)

        self.setWindowTitle("Pair Remote Voice Device")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self._build_ui()
        self._start_discovery()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        # Discovery phase
        self._discovery_label = QLabel("Searching for available remote devices...")
        layout.addWidget(self._discovery_label)

        self._device_list = QListWidget()
        self._device_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._device_list)

        # Button layout
        button_layout = QHBoxLayout()
        self._pair_button = QPushButton("Pair Selected Device")
        self._pair_button.setEnabled(False)
        self._pair_button.clicked.connect(self._on_pair_clicked)
        button_layout.addWidget(self._pair_button)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        button_layout.addWidget(self._cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _start_discovery(self) -> None:
        """Start discovering remote senders."""
        self._discovery_browser = RemoteVoiceDiscoveryBrowser(service_type=SERVICE_TYPE_SENDER)
        started = self._discovery_browser.start(
            on_device=lambda device: self.device_discovered_signal.emit(device),
            on_diagnostic=lambda payload: self.diagnostic_signal.emit(payload),
        )
        if not started:
            self._discovery_label.setText("Discovery unavailable. Ensure zeroconf is installed and try again.")
            self._pair_button.setEnabled(False)
            return
        self._discovery_label.setText("Searching for available remote devices...")

    def _handle_discovered_device(self, device: RemoteVoiceDiscoveryDevice) -> None:
        """Handle a newly discovered remote device."""
        # Only show explicitly tagged remote senders in this dialog.
        if device.role != "remote-sender":
            return
        if not device.source_id:
            return
        if device.source_id == "finance-main-pc":
            return
        if device.host and device.host in self._local_hosts:
            return
        self._discovered_devices[device.source_id] = device

        # Add to list
        self._device_list.clear()
        for src_id, dev in self._discovered_devices.items():
            host_suffix = f" - {dev.host}" if dev.host else ""
            item_text = f"{dev.device_name} ({src_id[:8]}...){host_suffix}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, src_id)
            self._device_list.addItem(item)

        # Update label
        count = len(self._discovered_devices)
        self._discovery_label.setText(f"Found {count} remote device(s). Select one to pair.")

        self._pair_button.setEnabled(self._device_list.currentItem() is not None)

    def _handle_diagnostic(self, payload: dict[str, object]) -> None:
        """Handle diagnostic messages from discovery."""
        event = str(payload.get("event", "")).strip().lower()
        if event == "mdns_browser_started":
            self._discovery_label.setText("Discovery started. Waiting for devices...")
            return
        if event == "mdns_service_state":
            service_name = str(payload.get("service_name", "")).strip()
            state = str(payload.get("state", "")).strip()
            if service_name and state:
                self._discovery_label.setText(f"Discovery update: {state} - {service_name}")

    def _on_selection_changed(self) -> None:
        self._pair_button.setEnabled(self._device_list.currentItem() is not None)

    def _collect_local_hosts(self) -> set[str]:
        hosts = {"127.0.0.1", "localhost"}
        try:
            hosts.add(resolve_local_ipv4())
        except Exception:
            pass
        try:
            for entry in socket.gethostbyname_ex(socket.gethostname())[2]:
                if entry:
                    hosts.add(entry)
        except Exception:
            pass
        return hosts

    def _on_pair_clicked(self) -> None:
        """Handle pair button clicked."""
        current_item = self._device_list.currentItem()
        if current_item is None:
            self._discovery_label.setText("Select a device before pairing.")
            return

        source_id = current_item.data(Qt.UserRole)
        device = self._discovered_devices.get(source_id)
        if device is None:
            self._discovery_label.setText("Selected device no longer available. Refreshing discovery...")
            return

        self._selected_device = device

        # Stop discovery
        if self._discovery_browser is not None:
            try:
                self._discovery_browser.stop()
            except Exception:
                pass
            self._discovery_browser = None

        # Phase 2: Generate unique session ID for this pairing attempt
        self._pairing_session_id = str(uuid.uuid4())

        # Generate pairing code with session ID (Phase 2)
        pairing_code = PairingCodeGenerator.generate(
            self.auth_token, source_id, self._pairing_session_id
        ).code
        self._show_pairing_code(device, pairing_code)

    def _show_pairing_code(self, device: RemoteVoiceDiscoveryDevice, pairing_code: str) -> None:
        """Show pairing code and wait for confirmation."""
        self._device_list.setEnabled(False)
        self._pair_button.setEnabled(False)
        self._pair_button.setText("Pairing In Progress")

        # Register with pairing manager (Phase 2: include session_id)
        if self.pairing_manager is not None:
            self.pairing_manager.start_pairing(
                device.source_id, pairing_code, self._pairing_session_id
            )

        # Clear and show pairing info
        self._device_list.clear()
        message = (
            f"Pairing with: {device.device_name}\n\n"
            f"Pairing Code: {pairing_code}\n\n"
            "Remote steps:\n"
            "1. Look at the remote device console.\n"
            "2. Confirm it shows the same pairing code.\n"
            "3. Wait for the paired confirmation.\n\n"
            "No extra button press is needed on this screen."
        )
        item = QListWidgetItem(message)
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self._device_list.addItem(item)

        self._discovery_label.setText("Waiting for device to connect...")

        # Set timeout for pairing (30-60 seconds per Phase 2 spec)
        self._pairing_timeout_timer.start(60000)

    def get_discovered_device(self, source_id: str) -> RemoteVoiceDiscoveryDevice | None:
        return self._discovered_devices.get(source_id)

    def get_pairing_session_id(self) -> str:
        """Get the current pairing session ID (Phase 2)."""
        return self._pairing_session_id

    def _on_pairing_timeout(self) -> None:
        """Handle pairing timeout."""
        if self.pairing_manager is not None:
            self.pairing_manager.cancel_pairing()

        if self._selected_device is not None:
            self._discovery_label.setText("Pairing token expired. Starting over...")
            self._selected_device = None
            self._device_list.clear()
            self._device_list.setEnabled(True)
            self._pair_button.setEnabled(True)
            self._pair_button.setText("Pair Selected Device")
            self._start_discovery()

    def on_pairing_confirmed(self, source_id: str, pairing_code: str) -> None:
        """Called when pairing is confirmed by connection handler."""
        # Guard: if we were already accepted/rejected (e.g. a late queued signal
        # arrives after dialog was closed), do nothing.
        if self._finalized:
            return
        self._finalized = True
        # Explicitly stop and disconnect the timer before accept() so that the
        # QTimer is inert before any possible GC, breaking the reference cycle.
        try:
            self._pairing_timeout_timer.stop()
            self._pairing_timeout_timer.timeout.disconnect()
        except RuntimeError:
            pass
        if self.pairing_manager is not None:
            self.pairing_manager.cancel_pairing()
        self._pair_button.setText("Paired")
        self.pairing_confirmed.emit(source_id, pairing_code, self.get_discovered_device(source_id))
        self.accept()
        # Break all reference cycles so CPython's refcount (not cyclic GC) can
        # free the dialog immediately on the main thread when exec_() returns.
        # (accept() hides the dialog but does NOT call closeEvent.)
        self._break_signal_cycles()

    def _on_cancel_clicked(self) -> None:
        """Handle cancel button."""
        self._finalized = True
        if self.pairing_manager is not None:
            self.pairing_manager.cancel_pairing()
        if self._discovery_browser is not None:
            try:
                self._discovery_browser.stop()
            except Exception:
                pass
            self._discovery_browser = None

        try:
            self._pairing_timeout_timer.stop()
            self._pairing_timeout_timer.timeout.disconnect()
        except RuntimeError:
            pass
        self._break_signal_cycles()
        self.pairing_cancelled.emit()
        self.reject()

    def closeEvent(self, event: Any) -> None:
        """Handle dialog close event."""
        self._finalized = True
        if self.pairing_manager is not None:
            self.pairing_manager.cancel_pairing()
        if self._discovery_browser is not None:
            try:
                self._discovery_browser.stop()
            except Exception:
                pass
        # Fully neutralise the QTimer before the dialog can be garbage-collected
        # on any thread.  Disconnecting the signal breaks the reference cycle
        # dialog → timer → connection → dialog, preventing cyclic-GC from
        # destroying the QTimer on a background thread.
        try:
            self._pairing_timeout_timer.stop()
            self._pairing_timeout_timer.timeout.disconnect()
        except RuntimeError:
            pass
        self._break_signal_cycles()
        super().closeEvent(event)

    def _break_signal_cycles(self) -> None:
        """Disconnect all outbound signals to eliminate reference cycles.

        The pairing_confirmed signal has a lambda connected that captures
        ``self`` (the dialog).  This creates a cycle::

            dialog → pairing_confirmed → connection → lambda → dialog

        Python’s cyclic GC can collect this cycle on any thread, including
        background socket-handler threads, causing QTimer destruction there
        and the crash::

            QObject::~QObject: Timers cannot be stopped from another thread
        """
        for sig in (self.pairing_confirmed, self.pairing_cancelled,
                    self.pairing_verified_signal, self.device_discovered_signal,
                    self.diagnostic_signal):
            try:
                sig.disconnect()
            except (RuntimeError, TypeError):
                pass

    def confirm_pairing(self) -> None:
        """Confirm pairing (called when connection from sender received)."""
        self._pairing_timeout_timer.stop()
        if self._selected_device is not None:
            source_id = self._selected_device.source_id
            pairing_code = PairingCodeGenerator.generate(self.auth_token, source_id).code
            self.pairing_confirmed.emit(source_id, pairing_code, self._selected_device)
            self.accept()
