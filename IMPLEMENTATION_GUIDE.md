# Implementation Guide: Refactoring for Multi-Feature UI

This guide provides step-by-step refactoring patterns to transform your current `main_window.py` into a modern multi-feature assistant UI.

---

## Step 1: Extract Theme System

Create `finance_app/ui/theme.py`:

```python
"""Centralized theme and styling system."""

from PyQt5.QtGui import QColor, QFont
from PyQt5.QtCore import Qt

class AppTheme:
    """Theme colors and styles."""
    
    # Colors
    PRIMARY = "#2196F3"
    PRIMARY_DARK = "#1565C0"
    ACCENT = "#FF9800"
    SUCCESS = "#4CAF50"
    WARNING = "#FFC107"
    ERROR = "#f44336"
    
    BACKGROUND = "#FAFAFA"
    SURFACE = "#FFFFFF"
    TEXT_PRIMARY = "#212121"
    TEXT_SECONDARY = "#757575"
    BORDER = "#E0E0E0"
    
    # Spacing
    SPACING_XS = 4
    SPACING_SM = 8
    SPACING_MD = 16
    SPACING_LG = 24
    
    @staticmethod
    def get_button_style(variant="primary"):
        """Get button style."""
        styles = {
            "primary": f"""
                QPushButton {{
                    background-color: {AppTheme.PRIMARY};
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background-color: {AppTheme.PRIMARY_DARK}; }}
            """,
            "secondary": f"""
                QPushButton {{
                    background-color: transparent;
                    color: {AppTheme.PRIMARY};
                    border: 1px solid {AppTheme.PRIMARY};
                    padding: 8px 16px;
                    border-radius: 4px;
                }}
            """,
            "flat": f"""
                QPushButton {{
                    background-color: transparent;
                    color: {AppTheme.PRIMARY};
                    border: none;
                }}
            """
        }
        return styles.get(variant, styles["primary"])
    
    @staticmethod
    def get_card_style():
        """Get card/frame style."""
        return f"""
            QFrame {{
                background-color: {AppTheme.SURFACE};
                border: 1px solid {AppTheme.BORDER};
                border-radius: 4px;
                padding: 12px;
            }}
        """
    
    @staticmethod
    def get_sidebar_style():
        """Get sidebar style."""
        return f"""
            QFrame {{
                background-color: #f5f5f5;
                border-right: 1px solid {AppTheme.BORDER};
            }}
        """
```

---

## Step 2: Create Component Library

Create `finance_app/ui/components.py`:

```python
"""Reusable UI components."""

from PyQt5.QtWidgets import (
    QPushButton, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QWidget, QComboBox, QSpinBox, QLineEdit
)
from PyQt5.QtCore import Qt
from finance_app.ui.theme import AppTheme

class ThemedButton(QPushButton):
    """Button with theme applied."""
    def __init__(self, text, variant="primary", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(AppTheme.get_button_style(variant))
        self.setCursor(Qt.PointingHandCursor)

class ThemedCard(QFrame):
    """Card widget with theme."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(AppTheme.get_card_style())

class MetricCard(ThemedCard):
    """Card displaying a metric."""
    def __init__(self, title, value, unit="", icon="", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        
        # Icon + Title
        header = QHBoxLayout()
        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 20px;")
            header.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {AppTheme.TEXT_SECONDARY};")
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)
        
        # Value
        value_label = QLabel(f"{value} {unit}".strip())
        value_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {AppTheme.TEXT_PRIMARY};")
        layout.addWidget(value_label)

class FeatureButton(ThemedButton):
    """Sidebar feature navigation button."""
    def __init__(self, emoji, label, parent=None):
        super().__init__(f"{emoji} {label}", "flat", parent)
        self.setStyleSheet(f"""
            QPushButton {{
                border: none;
                padding: 10px 8px;
                text-align: left;
                font-size: 12px;
                color: {AppTheme.TEXT_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: #efefef;
            }}
            QPushButton:checked {{
                background-color: {AppTheme.PRIMARY};
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }}
        """)
        self.setCheckable(True)
        self.setFlat(True)
```

---

## Step 3: Create Sidebar Navigation

Create `finance_app/ui/sidebar.py`:

```python
"""Left sidebar navigation."""

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton, QSpacing
)
from PyQt5.QtCore import pyqtSignal, Qt
from finance_app.ui.theme import AppTheme
from finance_app.ui.components import FeatureButton, ThemedButton

class Sidebar(QFrame):
    """Left sidebar with feature navigation."""
    
    feature_selected = pyqtSignal(int)  # Tab index
    settings_clicked = pyqtSignal()
    devices_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.setMaximumWidth(200)
        self.setStyleSheet(AppTheme.get_sidebar_style())
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(4)
        
        # Feature buttons
        self.feature_buttons = {}
        features = [
            ("💰", "Finance", 0),
            ("📅", "Calendar", 1),
            ("✓", "To-Do", 2),
            ("🛒", "Shopping", 3),
        ]
        
        for emoji, label, tab_index in features:
            btn = FeatureButton(emoji, label)
            btn.clicked.connect(lambda checked, idx=tab_index: self.feature_selected.emit(idx))
            layout.addWidget(btn)
            self.feature_buttons[tab_index] = btn
        
        # Set first as active
        self.feature_buttons[0].setChecked(True)
        
        layout.addSpacing(16)
        
        # Settings section
        settings_label = QLabel("SETTINGS")
        settings_label.setStyleSheet(f"""
            color: {AppTheme.TEXT_SECONDARY};
            font-size: 10px;
            font-weight: bold;
            padding: 0 8px;
        """)
        layout.addWidget(settings_label)
        
        agent_btn = ThemedButton("⚙ Agent Config", "flat")
        agent_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(agent_btn)
        
        devices_btn = ThemedButton("📱 Devices", "flat")
        devices_btn.clicked.connect(self.devices_clicked.emit)
        layout.addWidget(devices_btn)
        
        layout.addStretch()
    
    def set_active_feature(self, tab_index):
        """Set feature as active."""
        for idx, btn in self.feature_buttons.items():
            btn.setChecked(idx == tab_index)
```

---

## Step 4: Create Status Panel

Create `finance_app/ui/status_panel.py`:

```python
"""Right status panel showing device and AI status."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QScrollArea,
    QHBoxLayout, QPushButton, QMenu, QCursor
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from finance_app.ui.theme import AppTheme

class DeviceStatusCard(QFrame):
    """Card showing device status."""
    
    def __init__(self, device_id, device_name, status="online", parent=None):
        super().__init__(parent)
        self.device_id = device_id
        self.status = status
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #fafafa;
                border: 1px solid {AppTheme.BORDER};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        
        layout = QHBoxLayout(self)
        
        # Status indicator
        status_color = {
            "online": "#4CAF50",
            "offline": "#f44336",
            "idle": "#FFC107"
        }.get(status, "#999")
        
        indicator = QLabel("●")
        indicator.setStyleSheet(f"color: {status_color}; font-size: 14px;")
        layout.addWidget(indicator)
        
        # Device info
        info_layout = QVBoxLayout()
        name_label = QLabel(device_name)
        name_label.setStyleSheet("font-weight: bold; font-size: 10px;")
        info_layout.addWidget(name_label)
        
        status_label = QLabel(f"Status: {status}")
        status_label.setStyleSheet(f"color: {AppTheme.TEXT_SECONDARY}; font-size: 9px;")
        info_layout.addWidget(status_label)
        
        layout.addLayout(info_layout, 1)
        
        # Menu button
        menu_btn = QPushButton("⋮")
        menu_btn.setMaximumWidth(30)
        menu_btn.setFlat(True)
        layout.addWidget(menu_btn)

class StatusPanel(QWidget):
    """Right panel showing connected devices and AI agent status."""
    
    add_device_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.devices = {}
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Connected Devices")
        header.setStyleSheet(f"font-weight: bold; font-size: 12px;")
        layout.addWidget(header)
        
        # Devices scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        self.device_container = QWidget()
        self.device_layout = QVBoxLayout(self.device_container)
        self.device_layout.setSpacing(8)
        self.device_layout.setContentsMargins(4, 4, 4, 4)
        
        scroll.setWidget(self.device_container)
        layout.addWidget(scroll)
        
        # Add device button
        add_btn = QPushButton("+ Add Device")
        add_btn.clicked.connect(self.add_device_clicked.emit)
        layout.addWidget(add_btn)
        
        # AI Status section
        ai_header = QLabel("AI Agent Status")
        ai_header.setStyleSheet(f"font-weight: bold; font-size: 12px;")
        layout.addWidget(ai_header)
        
        self.ai_status = QLabel("✓ Ready")
        self.ai_status.setStyleSheet(f"color: {AppTheme.SUCCESS};")
        layout.addWidget(self.ai_status)
    
    def add_device(self, device_id, device_name, status="online"):
        """Add device to status panel."""
        card = DeviceStatusCard(device_id, device_name, status)
        self.device_layout.addWidget(card)
        self.devices[device_id] = {"card": card, "status": status}
    
    def update_device_status(self, device_id, new_status):
        """Update device status."""
        if device_id in self.devices:
            self.devices[device_id]["status"] = new_status
```

---

## Step 5: Refactor MainWindow

This is the key refactoring:

```python
# In finance_app/ui/main_window.py

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTabWidget, QStatusBar, QLabel
)
from PyQt5.QtCore import Qt, pyqtSignal

from finance_app.ui.sidebar import Sidebar
from finance_app.ui.status_panel import StatusPanel
from finance_app.ui.voice_indicator import VoiceIndicator
from finance_app.ui.theme import AppTheme
from finance_app.ui.tabs.finance_tab import FinanceTab
from finance_app.ui.tabs.calendar_tab import CalendarTab
from finance_app.ui.tabs.todo_tab import TodoTab
from finance_app.ui.tabs.shopping_tab import ShoppingTab

class MainWindow(QMainWindow):
    """Main application window."""
    
    # Keep existing signals
    voice_status_signal = pyqtSignal(str)
    voice_error_signal = pyqtSignal(str)
    voice_wake_signal = pyqtSignal(str)
    voice_command_signal = pyqtSignal(object)
    voice_partial_signal = pyqtSignal(str)
    voice_diagnostic_signal = pyqtSignal(object)
    _pairing_handshake_signal = pyqtSignal(str, str)
    
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Home Assistant")
        self.setGeometry(100, 100, 1400, 900)
        
        # Initialize services and controllers (existing code)
        self.repository = FinanceRepository()
        self.app_controller = AppController(self.repository)
        self.analytics_controller = AnalyticsController(self.repository)
        self.assets_controller = AssetsController(self.repository)
        self.budget_controller = BudgetController(self.repository)
        self.category_controller = CategoryController(self.repository)
        self.recurring_controller = RecurringController(self.repository)
        self.transaction_controller = TransactionController(self.repository)
        self.assistant_service = AssistantService(self.repository)
        self._wake_phrase = self._load_wake_phrase_setting()
        self.voice_coordinator = VoiceCoordinator(wake_phrase=self._wake_phrase)
        self._ui_scale = self._load_ui_scale_setting()
        self._density_mode = self._load_ui_density_setting()
        
        # Apply theme
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {AppTheme.BACKGROUND}; }}
            {AppTheme.get_card_style()}
        """)
        
        # Build new UI structure
        self._build_ui()
        self._setup_signals()
    
    def _build_ui(self):
        """Build main UI with sidebar, content, and status panel."""
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.feature_selected.connect(self._on_feature_selected)
        self.sidebar.settings_clicked.connect(self._open_agent_settings)
        self.sidebar.devices_clicked.connect(self._open_device_panel)
        main_layout.addWidget(self.sidebar, 0)
        
        # Splitter for resizable content/status
        splitter = QSplitter(Qt.Horizontal)
        
        # Content area (tabs)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)
        
        # Create tabs
        self.finance_tab = FinanceTab(self.finance_controller)
        self.calendar_tab = CalendarTab()
        self.todo_tab = TodoTab()
        self.shopping_tab = ShoppingTab()
        
        self.tab_widget.addTab(self.finance_tab, "💰 Finance")
        self.tab_widget.addTab(self.calendar_tab, "📅 Calendar")
        self.tab_widget.addTab(self.todo_tab, "✓ To-Do")
        self.tab_widget.addTab(self.shopping_tab, "🛒 Shopping")
        
        splitter.addWidget(self.tab_widget)
        
        # Status panel
        self.status_panel = StatusPanel()
        self.status_panel.add_device_clicked.connect(self._open_device_pairing)
        splitter.addWidget(self.status_panel)
        
        # Set splitter proportions (75% content, 25% status)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter, 1)
        
        self.setCentralWidget(central_widget)
        
        # Status bar with voice indicator
        self._create_status_bar()
    
    def _create_status_bar(self):
        """Create status bar with voice indicator."""
        status_bar = self.statusBar()
        
        # Connection status
        connection_label = QLabel("✓ Connected")
        connection_label.setStyleSheet(f"color: {AppTheme.SUCCESS};")
        status_bar.addWidget(connection_label)
        
        # Voice indicator
        self.voice_indicator = VoiceIndicator()
        status_bar.addWidget(self.voice_indicator, 1)
        
        # Device count
        self.device_label = QLabel("📱 0 Devices")
        status_bar.addPermanentWidget(self.device_label)
    
    def _on_feature_selected(self, tab_index):
        """Handle feature selection from sidebar."""
        self.tab_widget.setCurrentIndex(tab_index)
        self.sidebar.set_active_feature(tab_index)
    
    def _setup_signals(self):
        """Connect voice signals to UI indicators."""
        self.voice_coordinator.listening_started.connect(
            self.voice_indicator.set_listening
        )
        self.voice_coordinator.processing_started.connect(
            self.voice_indicator.set_processing
        )
        self.voice_coordinator.ready.connect(
            self.voice_indicator.set_ready
        )
        self.voice_coordinator.error_occurred.connect(
            lambda msg: self.voice_indicator.set_error(msg)
        )
    
    def _open_agent_settings(self):
        """Open agent configuration dialog."""
        from finance_app.ui.dialogs.agent_config_dialog import AgentConfigDialog
        dialog = AgentConfigDialog(self)
        dialog.exec_()
    
    def _open_device_panel(self):
        """Show device management panel."""
        self.status_panel.raise_()
    
    def _open_device_pairing(self):
        """Open device pairing dialog."""
        from finance_app.ui.device_pairing_dialog import DevicePairingDialog
        dialog = DevicePairingDialog(auth_token="token", parent=self)
        dialog.pairing_confirmed.connect(self._on_device_paired)
        dialog.exec_()
    
    def _on_device_paired(self, source_id, pairing_code, device):
        """Handle device pairing."""
        device_name = f"Device {len(self.status_panel.devices) + 1}"
        self.status_panel.add_device(source_id, device_name, "online")
        
        # Update device count
        count = len(self.status_panel.devices)
        self.device_label.setText(f"📱 {count} Device{'s' if count != 1 else ''}")
```

---

## Step 6: Create Tab Modules

Create `finance_app/ui/tabs/` directory with:

### `finance_app/ui/tabs/__init__.py`
```python
"""Tab modules."""
```

### `finance_app/ui/tabs/finance_tab.py`
```python
"""Finance tab."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit

from finance_app.ui.components import ThemedButton

class FinanceTab(QWidget):
    """Finance management tab."""
    
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._build_ui()
    
    def _build_ui(self):
        """Build finance tab UI."""
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        # View selector
        view_combo = QComboBox()
        view_combo.addItems(["Dashboard", "Transactions", "Analytics", "Budget"])
        toolbar.addWidget(QLabel("View:"))
        toolbar.addWidget(view_combo)
        
        # Period selector
        period_combo = QComboBox()
        period_combo.addItems(["This Month", "Last 30 Days", "This Year"])
        toolbar.addWidget(QLabel("Period:"))
        toolbar.addWidget(period_combo)
        
        toolbar.addStretch()
        
        layout.addLayout(toolbar)
        
        # Main content (existing code would go here)
        layout.addStretch()
```

### `finance_app/ui/tabs/calendar_tab.py`
```python
"""Calendar tab."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel

class CalendarTab(QWidget):
    """Calendar management tab."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Calendar Tab (To be implemented)"))
        layout.addStretch()
```

### `finance_app/ui/tabs/todo_tab.py`
```python
"""To-Do tab."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel

class TodoTab(QWidget):
    """Task management tab."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("To-Do Tab (To be implemented)"))
        layout.addStretch()
```

### `finance_app/ui/tabs/shopping_tab.py`
```python
"""Shopping list tab."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel

class ShoppingTab(QWidget):
    """Shopping list tab."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Shopping Tab (To be implemented)"))
        layout.addStretch()
```

---

## Step 7: Create Voice Indicator

Create `finance_app/ui/voice_indicator.py`:

```python
"""Voice input indicator widget."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import QTimer
from finance_app.ui.theme import AppTheme

class VoiceIndicator(QWidget):
    """Visual voice processing indicator."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"
        self.animation_frame = 0
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animation)
        self._build_ui()
    
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        self.indicator = QLabel("●")
        self.indicator.setStyleSheet(f"color: {AppTheme.SUCCESS};")
        layout.addWidget(self.indicator)
        
        self.status_text = QLabel("Ready")
        self.status_text.setStyleSheet(f"color: {AppTheme.TEXT_SECONDARY}; font-size: 10px;")
        layout.addWidget(self.status_text)
        
        self.waveform = QLabel("▁ ▂ ▃ ▄ ▅")
        self.waveform.setStyleSheet(f"color: {AppTheme.PRIMARY};")
        self.waveform.setVisible(False)
        layout.addWidget(self.waveform)
    
    def set_listening(self):
        """Set to listening state."""
        self.state = "listening"
        self.indicator.setStyleSheet(f"color: {AppTheme.WARNING};")
        self.status_text.setText("🎤 Listening...")
        self.waveform.setVisible(True)
        self.animation_timer.start(100)
    
    def set_processing(self):
        """Set to processing state."""
        self.state = "processing"
        self.indicator.setStyleSheet(f"color: {AppTheme.PRIMARY};")
        self.status_text.setText("⚙ Processing...")
        self.waveform.setVisible(True)
        self.animation_timer.start(100)
    
    def set_ready(self):
        """Set to ready state."""
        self.state = "idle"
        self.indicator.setStyleSheet(f"color: {AppTheme.SUCCESS};")
        self.status_text.setText("🎤 Ready")
        self.waveform.setVisible(False)
        self.animation_timer.stop()
    
    def set_error(self, msg="Error"):
        """Set to error state."""
        self.state = "error"
        self.indicator.setStyleSheet(f"color: {AppTheme.ERROR};")
        self.status_text.setText(f"⚠ {msg}")
        self.waveform.setVisible(False)
        self.animation_timer.stop()
    
    def _update_animation(self):
        """Update waveform animation."""
        waves = ["▁ ▂ ▃ ▄ ▅", "▂ ▃ ▄ ▅ ▆", "▃ ▄ ▅ ▆ ▇", "▄ ▅ ▆ ▇ █"]
        self.waveform.setText(waves[self.animation_frame % len(waves)])
        self.animation_frame += 1
```

---

## Step 8: Data Models

Create `finance_app/models.py` additions for new features:

```python
"""New data models for Calendar, To-Do, Shopping."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# Calendar
@dataclass
class CalendarEvent:
    event_id: str
    title: str
    description: str
    start_time: datetime
    end_time: datetime
    calendar_id: str
    is_shared: bool
    attendees: list[str]

# To-Do
@dataclass
class TodoItem:
    item_id: str
    title: str
    description: str
    priority: Literal["low", "medium", "high"]
    due_date: datetime | None
    completed: bool
    is_shared: bool
    assigned_to: str | None

# Shopping
@dataclass
class ShoppingItem:
    item_id: str
    name: str
    quantity: int
    unit: str
    category: str
    is_shared: bool
    checked: bool
    added_by: str
```

---

## Migration Checklist

- [ ] Create `finance_app/ui/theme.py`
- [ ] Create `finance_app/ui/components.py`
- [ ] Create `finance_app/ui/sidebar.py`
- [ ] Create `finance_app/ui/status_panel.py`
- [ ] Create `finance_app/ui/voice_indicator.py`
- [ ] Create `finance_app/ui/tabs/` directory
- [ ] Create individual tab modules
- [ ] Refactor `main_window.py` to use new structure
- [ ] Update `finance_app/models.py` with new data types
- [ ] Test sidebar navigation
- [ ] Test device pairing integration
- [ ] Test voice indicator signals

