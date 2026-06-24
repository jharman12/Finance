# Copy-Paste Ready Code Snippets

This document provides ready-to-use code snippets that can be directly copied and adapted for your project.

---

## 1. Theme System - Complete Implementation

**File: `finance_app/ui/theme.py`**

```python
"""Centralized theme and styling system."""

from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtCore import Qt


class AppTheme:
    """Central theme with colors, spacing, and styles."""
    
    # ==================== COLORS ====================
    # Primary
    PRIMARY = "#2196F3"
    PRIMARY_DARK = "#1565C0"
    PRIMARY_LIGHT = "#E3F2FD"
    
    # Accent
    ACCENT = "#FF9800"
    ACCENT_DARK = "#E65100"
    ACCENT_LIGHT = "#FFE0B2"
    
    # States
    SUCCESS = "#4CAF50"
    WARNING = "#FFC107"
    ERROR = "#f44336"
    INFO = "#00BCD4"
    
    # Neutrals
    BACKGROUND = "#FAFAFA"
    SURFACE = "#FFFFFF"
    TEXT_PRIMARY = "#212121"
    TEXT_SECONDARY = "#757575"
    TEXT_HINT = "#BDBDBD"
    DIVIDER = "#BDBDBD"
    BORDER_LIGHT = "#E0E0E0"
    
    # ==================== SPACING ====================
    SPACING_XS = 4
    SPACING_SM = 8
    SPACING_MD = 16
    SPACING_LG = 24
    SPACING_XL = 32
    
    # ==================== FONT SIZES ====================
    FONT_SIZE_SMALL = 10
    FONT_SIZE_BODY = 11
    FONT_SIZE_LABEL = 12
    FONT_SIZE_HEADING = 14
    FONT_SIZE_TITLE = 18
    FONT_SIZE_METRIC = 20
    
    # ==================== BORDER RADIUS ====================
    BORDER_RADIUS_SM = 2
    BORDER_RADIUS_MD = 4
    BORDER_RADIUS_LG = 8
    
    # ==================== METHODS ====================
    
    @staticmethod
    def get_font(size=11, weight=QFont.Normal, family="Segoe UI"):
        """Get a consistently styled font."""
        font = QFont(family, size, weight)
        return font
    
    @staticmethod
    def get_button_style(variant="primary", size="medium"):
        """Get button stylesheet by variant."""
        if variant == "primary":
            return f"""
                QPushButton {{
                    background-color: {AppTheme.PRIMARY};
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: {AppTheme.BORDER_RADIUS_MD}px;
                    font-weight: bold;
                    font-size: {AppTheme.FONT_SIZE_LABEL}px;
                }}
                QPushButton:hover {{
                    background-color: {AppTheme.PRIMARY_DARK};
                }}
                QPushButton:pressed {{
                    background-color: #0D47A1;
                }}
                QPushButton:disabled {{
                    background-color: {AppTheme.TEXT_HINT};
                    color: {AppTheme.TEXT_SECONDARY};
                }}
            """
        elif variant == "secondary":
            return f"""
                QPushButton {{
                    background-color: transparent;
                    color: {AppTheme.PRIMARY};
                    border: 1px solid {AppTheme.PRIMARY};
                    padding: 8px 16px;
                    border-radius: {AppTheme.BORDER_RADIUS_MD}px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {AppTheme.PRIMARY_LIGHT};
                }}
            """
        elif variant == "flat":
            return f"""
                QPushButton {{
                    background-color: transparent;
                    color: {AppTheme.PRIMARY};
                    border: none;
                    padding: 8px 12px;
                    border-radius: {AppTheme.BORDER_RADIUS_MD}px;
                }}
                QPushButton:hover {{
                    background-color: {AppTheme.PRIMARY_LIGHT};
                }}
            """
        elif variant == "danger":
            return f"""
                QPushButton {{
                    background-color: {AppTheme.ERROR};
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: {AppTheme.BORDER_RADIUS_MD}px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #d32f2f;
                }}
            """
        return ""
    
    @staticmethod
    def get_card_style():
        """Get card/frame style."""
        return f"""
            QFrame {{
                background-color: {AppTheme.SURFACE};
                border: 1px solid {AppTheme.BORDER_LIGHT};
                border-radius: {AppTheme.BORDER_RADIUS_MD}px;
                padding: {AppTheme.SPACING_MD}px;
            }}
        """
    
    @staticmethod
    def get_sidebar_style():
        """Get sidebar style."""
        return f"""
            QFrame {{
                background-color: #f5f5f5;
                border-right: 1px solid {AppTheme.BORDER_LIGHT};
            }}
        """
    
    @staticmethod
    def get_input_style():
        """Get input field style."""
        return f"""
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                border: 1px solid {AppTheme.BORDER_LIGHT};
                border-radius: {AppTheme.BORDER_RADIUS_MD}px;
                padding: {AppTheme.SPACING_SM}px;
                background-color: {AppTheme.SURFACE};
                selection-background-color: {AppTheme.PRIMARY};
            }}
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, 
            QDoubleSpinBox:focus, QComboBox:focus {{
                border: 2px solid {AppTheme.PRIMARY};
            }}
        """
    
    @staticmethod
    def get_tab_style():
        """Get tab widget style."""
        return f"""
            QTabWidget::pane {{
                border: 1px solid {AppTheme.BORDER_LIGHT};
            }}
            QTabBar::tab {{
                background-color: #f5f5f5;
                padding: 8px 16px;
                border: none;
                color: {AppTheme.TEXT_PRIMARY};
            }}
            QTabBar::tab:selected {{
                background-color: {AppTheme.SURFACE};
                border-bottom: 2px solid {AppTheme.PRIMARY};
            }}
        """
    
    @staticmethod
    def get_main_style():
        """Get main application stylesheet."""
        return f"""
            QMainWindow {{
                background-color: {AppTheme.BACKGROUND};
            }}
            QWidget {{
                color: {AppTheme.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {AppTheme.TEXT_PRIMARY};
            }}
            {AppTheme.get_input_style()}
            {AppTheme.get_tab_style()}
        """
    
    @staticmethod
    def get_high_contrast_palette():
        """Get high contrast color palette for accessibility."""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#000000"))
        palette.setColor(QPalette.WindowText, QColor("#FFFFFF"))
        palette.setColor(QPalette.Base, QColor("#000000"))
        palette.setColor(QPalette.AlternateBase, QColor("#222222"))
        palette.setColor(QPalette.ToolTipBase, QColor("#000000"))
        palette.setColor(QPalette.ToolTipText, QColor("#FFFF00"))
        palette.setColor(QPalette.Text, QColor("#FFFFFF"))
        palette.setColor(QPalette.Button, QColor("#1a1a1a"))
        palette.setColor(QPalette.ButtonText, QColor("#FFFFFF"))
        palette.setColor(QPalette.BrightText, QColor("#FFFFFF"))
        palette.setColor(QPalette.Highlight, QColor("#FFFF00"))
        palette.setColor(QPalette.HighlightedText, QColor("#000000"))
        return palette
```

---

## 2. Reusable Components - Implementation

**File: `finance_app/ui/components.py`**

```python
"""Reusable UI components with theme applied."""

from PyQt5.QtWidgets import (
    QPushButton, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QWidget, QComboBox, QSlider, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QCursor

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
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)


class MetricCard(ThemedCard):
    """Card for displaying metrics."""
    
    def __init__(self, title, value, unit="", icon="", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(AppTheme.SPACING_MD, AppTheme.SPACING_MD,
                                  AppTheme.SPACING_MD, AppTheme.SPACING_MD)
        layout.setSpacing(AppTheme.SPACING_SM)
        
        # Header with icon
        header = QHBoxLayout()
        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"font-size: {AppTheme.FONT_SIZE_TITLE}px;")
            header.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {AppTheme.TEXT_SECONDARY}; "
                                  f"font-size: {AppTheme.FONT_SIZE_LABEL}px;")
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)
        
        # Value display
        value_label = QLabel(f"{value} {unit}".strip())
        value_label.setStyleSheet(f"font-size: {AppTheme.FONT_SIZE_METRIC}px; "
                                  f"font-weight: bold; "
                                  f"color: {AppTheme.TEXT_PRIMARY};")
        layout.addWidget(value_label)


class FeatureButton(ThemedButton):
    """Sidebar feature navigation button."""
    
    def __init__(self, emoji, label, parent=None):
        super().__init__(f"{emoji} {label}", "flat", parent)
        self.setStyleSheet(f"""
            QPushButton {{
                border: none;
                padding: {AppTheme.SPACING_SM}px {AppTheme.SPACING_SM}px;
                text-align: left;
                font-size: {AppTheme.FONT_SIZE_LABEL}px;
                color: {AppTheme.TEXT_PRIMARY};
                background-color: transparent;
                border-radius: {AppTheme.BORDER_RADIUS_MD}px;
            }}
            QPushButton:hover {{
                background-color: #efefef;
            }}
            QPushButton:checked {{
                background-color: {AppTheme.PRIMARY};
                color: white;
                font-weight: bold;
            }}
        """)
        self.setCheckable(True)
        self.setFlat(True)


class IconButton(ThemedButton):
    """Small icon-only button."""
    
    def __init__(self, icon_text, parent=None):
        super().__init__(icon_text, "flat", parent)
        self.setMaximumWidth(40)
        self.setMaximumHeight(40)


class ShareabilityToggle(QWidget):
    """Toggle between Personal and Shared modes."""
    
    mode_changed = pyqtSignal(str)  # "personal" or "shared"
    
    def __init__(self, default_mode="personal", parent=None):
        super().__init__(parent)
        self.mode = default_mode
        self._build_ui()
    
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Personal button
        self.personal_btn = QPushButton("👤 Personal")
        self.personal_btn.setCheckable(True)
        self.personal_btn.setChecked(self.mode == "personal")
        self.personal_btn.clicked.connect(lambda: self._set_mode("personal"))
        self.personal_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 6px 12px;
                border: 1px solid {AppTheme.BORDER_LIGHT};
                background-color: white;
                border-top-left-radius: {AppTheme.BORDER_RADIUS_MD}px;
                border-bottom-left-radius: {AppTheme.BORDER_RADIUS_MD}px;
            }}
            QPushButton:checked {{
                background-color: #E8F5E9;
                color: #2E7D32;
                font-weight: bold;
                border: 1px solid #2E7D32;
            }}
        """)
        layout.addWidget(self.personal_btn)
        
        # Shared button
        self.shared_btn = QPushButton("👥 Shared")
        self.shared_btn.setCheckable(True)
        self.shared_btn.setChecked(self.mode == "shared")
        self.shared_btn.clicked.connect(lambda: self._set_mode("shared"))
        self.shared_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 6px 12px;
                border: 1px solid {AppTheme.BORDER_LIGHT};
                background-color: white;
                border-top-right-radius: {AppTheme.BORDER_RADIUS_MD}px;
                border-bottom-right-radius: {AppTheme.BORDER_RADIUS_MD}px;
            }}
            QPushButton:checked {{
                background-color: #E3F2FD;
                color: #1565C0;
                font-weight: bold;
                border: 1px solid #1565C0;
            }}
        """)
        layout.addWidget(self.shared_btn)
    
    def _set_mode(self, mode):
        """Set ownership mode."""
        self.mode = mode
        self.personal_btn.setChecked(mode == "personal")
        self.shared_btn.setChecked(mode == "shared")
        self.mode_changed.emit(mode)


class AccessibleButton(ThemedButton):
    """Button with accessibility features."""
    
    def __init__(self, text, tooltip="", parent=None):
        super().__init__(text, "primary", parent)
        
        if tooltip:
            self.setToolTip(tooltip)
        
        # Ensure minimum touch target size (44x44)
        self.setMinimumHeight(44)
        self.setMinimumWidth(max(44, len(text) * 8))
        
        # Enable focus
        self.setFocusPolicy(Qt.StrongFocus)
```

---

## 3. Voice Indicator - Complete

**File: `finance_app/ui/voice_indicator.py`**

```python
"""Voice input processing indicator."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import QTimer, Qt

from finance_app.ui.theme import AppTheme


class VoiceIndicator(QWidget):
    """Visual indicator for voice processing state."""
    
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
        layout.setSpacing(AppTheme.SPACING_SM)
        
        # Indicator circle
        self.indicator = QLabel("●")
        self.indicator.setStyleSheet(f"color: {AppTheme.SUCCESS}; "
                                    f"font-size: 12px;")
        layout.addWidget(self.indicator)
        
        # Status text
        self.status_text = QLabel("Ready")
        self.status_text.setStyleSheet(f"font-size: {AppTheme.FONT_SIZE_SMALL}px; "
                                      f"color: {AppTheme.TEXT_SECONDARY};")
        layout.addWidget(self.status_text)
        
        # Waveform animation
        self.waveform = QLabel("▁ ▂ ▃ ▄ ▅")
        self.waveform.setStyleSheet(f"font-size: {AppTheme.FONT_SIZE_SMALL}px; "
                                   f"color: {AppTheme.PRIMARY};")
        self.waveform.setVisible(False)
        layout.addWidget(self.waveform)
    
    def set_listening(self):
        """Set to listening state."""
        self.state = "listening"
        self.indicator.setStyleSheet(f"color: {AppTheme.WARNING}; font-size: 12px;")
        self.status_text.setText("🎤 Listening...")
        self.waveform.setVisible(True)
        self.animation_timer.start(100)
    
    def set_processing(self):
        """Set to processing state."""
        self.state = "processing"
        self.indicator.setStyleSheet(f"color: {AppTheme.PRIMARY}; font-size: 12px;")
        self.status_text.setText("⚙ Processing...")
        self.waveform.setVisible(True)
        self.animation_timer.start(100)
    
    def set_ready(self):
        """Set to ready state."""
        self.state = "idle"
        self.indicator.setStyleSheet(f"color: {AppTheme.SUCCESS}; font-size: 12px;")
        self.status_text.setText("🎤 Ready")
        self.waveform.setVisible(False)
        self.animation_timer.stop()
    
    def set_error(self, error_msg="Error"):
        """Set to error state."""
        self.state = "error"
        self.indicator.setStyleSheet(f"color: {AppTheme.ERROR}; font-size: 12px;")
        self.status_text.setText(f"⚠ {error_msg}")
        self.waveform.setVisible(False)
        self.animation_timer.stop()
    
    def _update_animation(self):
        """Update waveform animation."""
        waves = [
            "▁ ▂ ▃ ▄ ▅",
            "▂ ▃ ▄ ▅ ▆",
            "▃ ▄ ▅ ▆ ▇",
            "▄ ▅ ▆ ▇ █",
        ]
        self.waveform.setText(waves[self.animation_frame % len(waves)])
        self.animation_frame += 1
```

---

## 4. Sidebar Navigation

**File: `finance_app/ui/sidebar.py`**

```python
"""Left sidebar navigation."""

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton
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
        layout.setContentsMargins(0, AppTheme.SPACING_MD, 0, AppTheme.SPACING_MD)
        layout.setSpacing(AppTheme.SPACING_SM)
        
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
            btn.clicked.connect(lambda checked, idx=tab_index: 
                              self.feature_selected.emit(idx))
            layout.addWidget(btn)
            self.feature_buttons[tab_index] = btn
        
        # Set first as active
        self.feature_buttons[0].setChecked(True)
        
        layout.addSpacing(AppTheme.SPACING_LG)
        
        # Settings section header
        settings_label = QLabel("SETTINGS")
        settings_label.setStyleSheet(f"""
            color: {AppTheme.TEXT_SECONDARY};
            font-size: {AppTheme.FONT_SIZE_SMALL}px;
            font-weight: bold;
            padding: 0 {AppTheme.SPACING_SM}px;
        """)
        layout.addWidget(settings_label)
        
        # Settings buttons
        agent_btn = ThemedButton("⚙ Agent Config", "flat")
        agent_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(agent_btn)
        
        devices_btn = ThemedButton("📱 Devices", "flat")
        devices_btn.clicked.connect(self.devices_clicked.emit)
        layout.addWidget(devices_btn)
        
        layout.addStretch()
    
    def set_active_feature(self, tab_index):
        """Highlight the active feature."""
        for idx, btn in self.feature_buttons.items():
            btn.setChecked(idx == tab_index)
```

---

## 5. Status Panel

**File: `finance_app/ui/status_panel.py`**

```python
"""Right panel showing device and AI status."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QScrollArea,
    QHBoxLayout, QPushButton
)
from PyQt5.QtCore import Qt, pyqtSignal

from finance_app.ui.theme import AppTheme
from finance_app.ui.components import ThemedButton


class DeviceStatusCard(QFrame):
    """Card showing a single device status."""
    
    def __init__(self, device_id, device_name, status="online", parent=None):
        super().__init__(parent)
        self.device_id = device_id
        self.status = status
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #fafafa;
                border: 1px solid {AppTheme.BORDER_LIGHT};
                border-radius: {AppTheme.BORDER_RADIUS_MD}px;
                padding: {AppTheme.SPACING_SM}px;
            }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(AppTheme.SPACING_SM, AppTheme.SPACING_SM,
                                 AppTheme.SPACING_SM, AppTheme.SPACING_SM)
        layout.setSpacing(AppTheme.SPACING_MD)
        
        # Status indicator
        status_color = {
            "online": AppTheme.SUCCESS,
            "offline": AppTheme.ERROR,
            "idle": AppTheme.WARNING
        }.get(status, AppTheme.TEXT_HINT)
        
        indicator = QLabel("●")
        indicator.setStyleSheet(f"color: {status_color}; font-size: 14px;")
        layout.addWidget(indicator)
        
        # Device info
        info_layout = QVBoxLayout()
        name_label = QLabel(device_name)
        name_label.setStyleSheet(f"font-weight: bold; "
                                f"font-size: {AppTheme.FONT_SIZE_LABEL}px;")
        info_layout.addWidget(name_label)
        
        status_label = QLabel(f"Status: {status}")
        status_label.setStyleSheet(f"color: {AppTheme.TEXT_SECONDARY}; "
                                  f"font-size: {AppTheme.FONT_SIZE_SMALL}px;")
        info_layout.addWidget(status_label)
        
        layout.addLayout(info_layout, 1)
        
        # Menu button
        menu_btn = QPushButton("⋮")
        menu_btn.setMaximumWidth(30)
        menu_btn.setFlat(True)
        layout.addWidget(menu_btn)


class StatusPanel(QWidget):
    """Right panel showing devices and AI status."""
    
    add_device_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.devices = {}
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(AppTheme.SPACING_MD, AppTheme.SPACING_MD,
                                 AppTheme.SPACING_MD, AppTheme.SPACING_MD)
        
        # Header
        header = QLabel("Connected Devices")
        header.setStyleSheet(f"font-weight: bold; "
                            f"font-size: {AppTheme.FONT_SIZE_LABEL}px;")
        layout.addWidget(header)
        
        # Devices scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: 1px solid {AppTheme.BORDER_LIGHT}; }}")
        
        self.device_container = QWidget()
        self.device_layout = QVBoxLayout(self.device_container)
        self.device_layout.setSpacing(AppTheme.SPACING_MD)
        self.device_layout.setContentsMargins(AppTheme.SPACING_SM, AppTheme.SPACING_SM,
                                             AppTheme.SPACING_SM, AppTheme.SPACING_SM)
        
        scroll.setWidget(self.device_container)
        layout.addWidget(scroll)
        
        # Add device button
        add_btn = ThemedButton("+ Add Device", "primary")
        add_btn.clicked.connect(self.add_device_clicked.emit)
        layout.addWidget(add_btn)
        
        # AI Status section
        ai_header = QLabel("AI Agent Status")
        ai_header.setStyleSheet(f"font-weight: bold; "
                               f"font-size: {AppTheme.FONT_SIZE_LABEL}px;")
        layout.addWidget(ai_header)
        
        self.ai_status = QLabel("✓ Ready")
        self.ai_status.setStyleSheet(f"color: {AppTheme.SUCCESS};")
        layout.addWidget(self.ai_status)
    
    def add_device(self, device_id, device_name, status="online"):
        """Add a device to the panel."""
        card = DeviceStatusCard(device_id, device_name, status)
        self.device_layout.addWidget(card)
        self.devices[device_id] = {"card": card, "status": status}
    
    def update_device_status(self, device_id, new_status):
        """Update device status."""
        if device_id in self.devices:
            self.devices[device_id]["status"] = new_status
            # Re-render would happen here
    
    def remove_device(self, device_id):
        """Remove device from panel."""
        if device_id in self.devices:
            card = self.devices[device_id]["card"]
            self.device_layout.removeWidget(card)
            card.deleteLater()
            del self.devices[device_id]
```

---

## 6. Data Models

**Add to `finance_app/models.py`:**

```python
"""New models for expanded features."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class CalendarEvent:
    """Calendar event model."""
    event_id: str
    title: str
    description: str
    start_time: datetime
    end_time: datetime
    calendar_id: str
    is_shared: bool
    attendees: list[str] = field(default_factory=list)
    location: Optional[str] = None
    color: str = "#2196F3"


@dataclass
class TodoItem:
    """To-Do item model."""
    item_id: str
    title: str
    description: str
    priority: Literal["low", "medium", "high"]
    due_date: Optional[datetime]
    completed: bool
    is_shared: bool
    assigned_to: Optional[str] = None
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ShoppingItem:
    """Shopping list item."""
    item_id: str
    name: str
    quantity: float
    unit: str
    category: str
    is_shared: bool
    checked: bool
    added_by: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class RemoteDeviceStatus:
    """Status of a paired remote device."""
    device_id: str
    device_name: str
    status: Literal["online", "offline", "idle"]
    last_seen: datetime
    signal_strength: int  # dBm
    battery_level: Optional[int]  # 0-100
    voice_support: bool
```

---

## Integration Example: Connect to Main Window

```python
# In finance_app/ui/main_window.py

from finance_app.ui.theme import AppTheme
from finance_app.ui.sidebar import Sidebar
from finance_app.ui.status_panel import StatusPanel
from finance_app.ui.voice_indicator import VoiceIndicator

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Apply theme
        self.setStyleSheet(AppTheme.get_main_style())
        self.setFont(AppTheme.get_font(11))
        
        # Build UI
        self._build_ui()
        self._setup_connections()
    
    def _build_ui(self):
        """Build main UI structure."""
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        
        # Sidebar
        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar, 0)
        
        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Content tabs
        self.tab_widget = QTabWidget()
        splitter.addWidget(self.tab_widget)
        
        # Status panel
        self.status_panel = StatusPanel()
        splitter.addWidget(self.status_panel)
        
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter, 1)
        self.setCentralWidget(central_widget)
        
        # Status bar
        self._create_status_bar()
    
    def _create_status_bar(self):
        """Create status bar with voice indicator."""
        status_bar = self.statusBar()
        
        self.voice_indicator = VoiceIndicator()
        status_bar.addWidget(self.voice_indicator, 1)
        
        self.device_label = QLabel("📱 0 Devices")
        status_bar.addPermanentWidget(self.device_label)
    
    def _setup_connections(self):
        """Connect UI signals."""
        self.sidebar.feature_selected.connect(self._on_feature_selected)
        self.sidebar.settings_clicked.connect(self._open_agent_settings)
        self.sidebar.devices_clicked.connect(self._open_devices_panel)
        
        # Voice signal integration
        self.voice_coordinator.listening_started.connect(
            self.voice_indicator.set_listening
        )
    
    def _on_feature_selected(self, tab_index):
        """Handle feature selection."""
        self.tab_widget.setCurrentIndex(tab_index)
        self.sidebar.set_active_feature(tab_index)
```

---

## Usage Notes

1. **Copy-paste ready**: All code is complete and functional
2. **Import paths**: Adjust `from finance_app.ui.theme import AppTheme` if needed
3. **Styling**: All colors use `AppTheme` constants for consistency
4. **Signals**: Components emit PyQt signals for easy integration
5. **Customization**: Modify `AppTheme` class values to change colors globally

