# AI Home Assistant UI/UX Design Guide

## Executive Summary
This guide provides comprehensive UI/UX recommendations for expanding your Finance Assistant into a multi-feature home assistant supporting Calendar, To-Do Lists, Shopping Lists, and a multi-agent AI system with remote voice capabilities.

---

## 1. Main Window Layout Strategy

### Recommended Architecture: Sidebar Navigation + Multi-Tab Feature Hub

The optimal layout combines:
- **Left Sidebar** (160-200px): Feature navigation + system status
- **Content Area** (70-75% of window): Dynamic tab-based feature container
- **Right Panel** (optional, 15-20%): Device status + AI agent status dock
- **Status Bar**: Voice indicator + connection status

```
┌─────────────────────────────────────────────────────────────────────┐
│ File Edit View Tools Help                                          │
├────┬───────────────────────────────────────────────────────────┬──────┤
│    │  [Finance Tab] [Calendar Tab] [To-Do Tab] [Shop Tab]     │      │
│    ├──────────────────────────────────────────────────────────┤      │
│ FE │                                                          │ DEV  │
│ AT │                                                          │ STA  │
│ UR │              PRIMARY CONTENT AREA                       │ TUS  │
│ ES │              (Responsive to tab content)                │      │
│    │                                                          │      │
│    ├──────────────────────────────────────────────────────────┤      │
│ [+]│ 🔍 Global Search / AI Agent Chat                         │      │
└────┴──────────────────────────────────────────────────────────┴──────┘
│ 🎤 Voice Ready | 2 Devices Connected | AI: Thinking...            │
└──────────────────────────────────────────────────────────────────────┘
```

### Why This Layout?

| Aspect | Benefit |
|--------|---------|
| **Left Sidebar** | Persistent feature navigation; clear visual hierarchy |
| **Tab-based Content** | Familiar pattern (users understand tabs); scales to 5+ features |
| **Right Status Panel** | Shows system health without cluttering main interface |
| **Central Search** | One unified AI agent interface across all features |
| **Status Bar** | Always visible device/voice/AI status |

### PyQt5 Implementation Pattern

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Home Assistant")
        self.setGeometry(100, 100, 1400, 900)
        
        # Create central widget with main layout
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left sidebar (fixed width)
        self.sidebar = self._create_sidebar()
        main_layout.addWidget(self.sidebar, 0)
        
        # Splitter for resizable content area
        splitter = QSplitter(Qt.Horizontal)
        
        # Content area (tabs)
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_finance_tab(), "💰 Finance")
        self.tab_widget.addTab(self._create_calendar_tab(), "📅 Calendar")
        self.tab_widget.addTab(self._create_todo_tab(), "✓ To-Do")
        self.tab_widget.addTab(self._create_shopping_tab(), "🛒 Shopping")
        splitter.addWidget(self.tab_widget)
        
        # Right status panel
        self.status_panel = self._create_status_panel()
        splitter.addWidget(self.status_panel)
        splitter.setStretchFactor(0, 3)  # Content gets 75%
        splitter.setStretchFactor(1, 1)  # Status panel gets 25%
        
        main_layout.addWidget(splitter, 1)
        self.setCentralWidget(central_widget)
        
        # AI Chat area (bottom)
        self._add_chat_dock()
        
        # Status bar (bottom)
        self._create_status_bar()
```

---

## 2. Navigation Pattern

### Recommended Approach: Hybrid Sidebar + Tab Navigation

**Primary Navigation (Sidebar)**
```python
def _create_sidebar(self):
    """Create left sidebar with feature buttons."""
    sidebar = QFrame()
    sidebar.setFrameStyle(QFrame.Box | QFrame.Plain)
    sidebar.setLineWidth(1)
    sidebar.setMaximumWidth(180)
    sidebar.setStyleSheet("""
        QFrame {
            background-color: #f5f5f5;
            border-right: 1px solid #e0e0e0;
        }
    """)
    
    layout = QVBoxLayout(sidebar)
    layout.setContentsMargins(0, 12, 0, 12)
    layout.setSpacing(4)
    
    # Feature buttons (clickable, highlighting active tab)
    self.feature_buttons = {}
    features = [
        ("💰 Finance", 0, self._navigate_to_tab),
        ("📅 Calendar", 1, self._navigate_to_tab),
        ("✓ To-Do", 2, self._navigate_to_tab),
        ("🛒 Shopping", 3, self._navigate_to_tab),
    ]
    
    for label, tab_index, callback in features:
        btn = QPushButton(label)
        btn.setFlat(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                border: none;
                padding: 10px 8px;
                text-align: left;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #efefef;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        """)
        btn.clicked.connect(lambda checked, idx=tab_index: callback(idx))
        layout.addWidget(btn)
        self.feature_buttons[tab_index] = btn
    
    layout.addSpacing(16)
    
    # Settings section
    settings_label = QLabel("SETTINGS")
    settings_label.setStyleSheet("color: #666; font-size: 10px; font-weight: bold;")
    layout.addWidget(settings_label)
    
    settings_btn = QPushButton("⚙ Agent Config")
    settings_btn.setFlat(True)
    settings_btn.clicked.connect(self._open_agent_settings)
    layout.addWidget(settings_btn)
    
    device_btn = QPushButton("📱 Devices")
    device_btn.setFlat(True)
    device_btn.clicked.connect(self._open_device_panel)
    layout.addWidget(device_btn)
    
    layout.addStretch()
    
    return sidebar

def _navigate_to_tab(self, tab_index):
    """Navigate to tab and update sidebar highlighting."""
    self.tab_widget.setCurrentIndex(tab_index)
    # Update button highlighting
    for idx, btn in self.feature_buttons.items():
        btn.setStyleSheet(self._get_button_style(idx == tab_index))

def _get_button_style(self, is_active):
    """Get button style based on active state."""
    if is_active:
        return """
            QPushButton {
                border: none;
                padding: 10px 8px;
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
        """
    return """
        QPushButton {
            border: none;
            padding: 10px 8px;
            text-align: left;
        }
    """
```

### Secondary Navigation (In-Tab Navigation)

Each tab should have its own toolbar with feature-specific filters:

```python
def _create_finance_tab(self):
    """Create Finance tab with secondary navigation."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    
    # Secondary toolbar (filters, view options)
    toolbar = QHBoxLayout()
    
    view_selector = QComboBox()
    view_selector.addItems(["Dashboard", "Transactions", "Analytics", "Budget"])
    view_selector.currentIndexChanged.connect(self._switch_finance_view)
    toolbar.addWidget(QLabel("View:"))
    toolbar.addWidget(view_selector)
    
    date_range = QComboBox()
    date_range.addItems(["This Month", "Last 30 Days", "This Year", "Custom Range"])
    toolbar.addWidget(QLabel("Period:"))
    toolbar.addWidget(date_range)
    
    toolbar.addStretch()
    
    layout.addLayout(toolbar)
    
    # Main content area (varies by view)
    self.finance_stack = QStackedWidget()
    self.finance_stack.addWidget(self._create_finance_dashboard())
    self.finance_stack.addWidget(self._create_transactions_view())
    self.finance_stack.addWidget(self._create_analytics_view())
    self.finance_stack.addWidget(self._create_budget_view())
    layout.addWidget(self.finance_stack)
    
    return tab
```

---

## 3. Agent Customization Interface

### Design: Agent Configuration Dialog with Real-time Preview

```python
class AgentCustomizationDialog(QDialog):
    """Configure and tune multiple AI agents."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Agent Configuration")
        self.setGeometry(200, 200, 900, 700)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # Agent selection (tabbed)
        agent_tabs = QTabWidget()
        
        # Finance Agent Tab
        finance_agent_widget = self._create_agent_config_panel(
            "Finance Advisor",
            "Expert financial guidance for budgeting and investments",
            [
                ("Model", "qwen2.5:latest", "select"),
                ("Temperature", 0.3, "slider"),  # Lower = more focused
                ("Max Context", 4096, "spinbox"),
                ("Response Style", ["Professional", "Casual", "Detailed"], "combo"),
                ("Risk Profile", ["Conservative", "Moderate", "Aggressive"], "combo"),
            ]
        )
        agent_tabs.addTab(finance_agent_widget, "💰 Finance Agent")
        
        # Calendar Agent Tab
        calendar_agent_widget = self._create_agent_config_panel(
            "Calendar Assistant",
            "Intelligent scheduling and event management",
            [
                ("Model", "qwen2.5:latest", "select"),
                ("Temperature", 0.5, "slider"),
                ("Suggest Events", True, "checkbox"),
                ("Auto-Optimize Schedule", True, "checkbox"),
            ]
        )
        agent_tabs.addTab(calendar_agent_widget, "📅 Calendar Agent")
        
        # To-Do Agent Tab
        todo_agent_widget = self._create_agent_config_panel(
            "Task Manager",
            "Priority management and productivity optimization",
            [
                ("Model", "qwen2.5:latest", "select"),
                ("Temperature", 0.4, "slider"),
                ("Priority Algorithm", ["Urgency", "Impact", "Effort"], "combo"),
                ("Smart Grouping", True, "checkbox"),
            ]
        )
        agent_tabs.addTab(todo_agent_widget, "✓ Task Agent")
        
        layout.addWidget(agent_tabs)
        
        # Preview panel (showing current configuration)
        preview_label = QLabel("Configuration Preview")
        preview_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(preview_label)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
        layout.addWidget(self.preview_text)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_to_defaults)
        button_layout.addWidget(reset_btn)
        
        test_btn = QPushButton("Test Agent")
        test_btn.clicked.connect(self._test_agent)
        button_layout.addWidget(test_btn)
        
        save_btn = QPushButton("Save Configuration")
        save_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        save_btn.clicked.connect(self.accept)
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
        
        self._update_preview()
    
    def _create_agent_config_panel(self, name, description, settings):
        """Create configuration panel for an agent."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Header
        header = QLabel(f"{name}\n{description}")
        header.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(header)
        
        # Separator
        sep = QFrame()
        sep.setFrameStyle(QFrame.HLine | QFrame.Sunken)
        layout.addWidget(sep)
        
        # Settings form
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        self.config_widgets = {}
        for label, default_value, widget_type in settings:
            if widget_type == "slider":
                widget = QSlider(Qt.Horizontal)
                widget.setMinimum(0)
                widget.setMaximum(100)
                widget.setValue(int(default_value * 100))
                widget.setTickPosition(QSlider.TicksBelow)
                widget.valueChanged.connect(self._on_config_changed)
            elif widget_type == "spinbox":
                widget = QSpinBox()
                widget.setValue(default_value)
                widget.setMaximum(8192)
                widget.valueChanged.connect(self._on_config_changed)
            elif widget_type == "checkbox":
                widget = QCheckBox()
                widget.setChecked(default_value)
                widget.stateChanged.connect(self._on_config_changed)
            elif widget_type == "combo":
                widget = QComboBox()
                widget.addItems(default_value)
                widget.currentIndexChanged.connect(self._on_config_changed)
            elif widget_type == "select":
                widget = QComboBox()
                widget.addItems(["qwen2.5:latest", "llama2", "mistral", "neural-chat"])
                widget.currentIndexChanged.connect(self._on_config_changed)
            
            form_layout.addRow(label, widget)
            self.config_widgets[label] = widget
        
        layout.addLayout(form_layout)
        layout.addStretch()
        
        return panel
    
    def _on_config_changed(self):
        """Update preview when configuration changes."""
        self._update_preview()
    
    def _update_preview(self):
        """Update the configuration preview display."""
        preview_text = "Current Agent Configuration:\n\n"
        preview_text += "├─ Finance Agent\n"
        preview_text += "│  ├─ Model: qwen2.5:latest\n"
        preview_text += "│  ├─ Temperature: 0.3 (Focused)\n"
        preview_text += "│  └─ Risk Profile: Conservative\n"
        preview_text += "├─ Calendar Agent\n"
        preview_text += "│  ├─ Model: qwen2.5:latest\n"
        preview_text += "│  └─ Auto-Optimize: Enabled\n"
        preview_text += "└─ Task Agent\n"
        preview_text += "   ├─ Model: qwen2.5:latest\n"
        preview_text += "   └─ Priority Algorithm: Urgency"
        
        self.preview_text.setText(preview_text)
    
    def _test_agent(self):
        """Test agent configuration with a sample prompt."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Test Agent")
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("Testing Finance Agent..."))
        
        result_text = QTextEdit()
        result_text.setReadOnly(True)
        result_text.setText("Agent response preview:\n\n✓ Agent is responding correctly\nResponse time: 1.2s\nContext usage: 45%")
        layout.addWidget(result_text)
        
        layout.addWidget(QPushButton("Close"))
        dialog.exec_()
```

---

## 4. Remote Device Status Display

### Design: Device Dashboard with Live Status Indicators

```python
class DeviceStatusPanel(QWidget):
    """Display status of paired remote voice devices."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.device_status = {}
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Header
        header = QLabel("Connected Devices")
        header.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(header)
        
        # Device list (scroll area)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #e0e0e0; }")
        
        self.device_container = QWidget()
        self.device_layout = QVBoxLayout(self.device_container)
        self.device_layout.setSpacing(8)
        self.device_layout.setContentsMargins(4, 4, 4, 4)
        
        scroll.setWidget(self.device_container)
        layout.addWidget(scroll)
        
        # Add device button
        add_device_btn = QPushButton("+ Add Device")
        add_device_btn.clicked.connect(self._open_pairing_dialog)
        layout.addWidget(add_device_btn)
    
    def add_device_status(self, device_id, device_name, status="online"):
        """Add or update device status card."""
        device_card = self._create_device_card(device_id, device_name, status)
        self.device_layout.addWidget(device_card)
        self.device_status[device_id] = {"card": device_card, "status": status}
    
    def _create_device_card(self, device_id, device_name, status="online"):
        """Create a device status card."""
        card = QFrame()
        card.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        card.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        
        layout = QHBoxLayout(card)
        
        # Status indicator (green/red/yellow circle)
        status_indicator = QLabel("●")
        status_color = {
            "online": "#4CAF50",
            "offline": "#f44336",
            "idle": "#FFC107",
        }.get(status, "#999")
        status_indicator.setStyleSheet(f"color: {status_color}; font-size: 16px;")
        layout.addWidget(status_indicator)
        
        # Device info
        info_layout = QVBoxLayout()
        name_label = QLabel(device_name)
        name_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        info_layout.addWidget(name_label)
        
        status_label = QLabel(f"Status: {status} • ID: {device_id[:8]}...")
        status_label.setStyleSheet("color: #666; font-size: 9px;")
        info_layout.addWidget(status_label)
        
        layout.addLayout(info_layout, 1)
        
        # Signal strength indicator
        signal_label = QLabel("📶 -45dBm")
        signal_label.setStyleSheet("color: #666; font-size: 9px;")
        layout.addWidget(signal_label)
        
        # Menu button
        menu_btn = QPushButton("⋮")
        menu_btn.setMaximumWidth(30)
        menu_btn.setFlat(True)
        menu_btn.clicked.connect(lambda: self._show_device_menu(device_id))
        layout.addWidget(menu_btn)
        
        return card
    
    def update_device_status(self, device_id, new_status):
        """Update device status (online/offline/idle)."""
        if device_id in self.device_status:
            self.device_status[device_id]["status"] = new_status
            # Refresh card styling
            card = self.device_status[device_id]["card"]
            # Re-render would happen here
    
    def _show_device_menu(self, device_id):
        """Show context menu for device."""
        menu = QMenu(self)
        menu.addAction("Test Connection", lambda: self._test_device(device_id))
        menu.addAction("Rename", lambda: self._rename_device(device_id))
        menu.addSeparator()
        menu.addAction("Unpair Device", lambda: self._unpair_device(device_id))
        menu.exec_(QCursor.pos())
    
    def _open_pairing_dialog(self):
        """Open device pairing dialog."""
        from finance_app.ui.device_pairing_dialog import DevicePairingDialog
        pairing_dialog = DevicePairingDialog(auth_token="your_token", parent=self)
        pairing_dialog.exec_()
```

### Device Status JSON Structure (Backend)

```python
# In models.py
@dataclass
class RemoteDeviceStatus:
    device_id: str
    device_name: str
    status: Literal["online", "offline", "idle"]
    last_seen: datetime
    signal_strength: int  # -100 to -30 dBm
    battery_level: int | None  # 0-100 for mobile
    voice_support: bool
    last_command: str | None
    command_count_today: int
```

---

## 5. Voice Input Indicator

### Design: Multi-State Voice Indicator in Status Bar

```python
class VoiceIndicator(QWidget):
    """Visual indicator for voice processing state."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"  # idle, listening, processing, error
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animation)
        self.animation_frame = 0
        self._build_ui()
    
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        # Visual indicator
        self.indicator = QLabel("●")
        self.indicator.setStyleSheet("color: #999; font-size: 12px;")
        layout.addWidget(self.indicator)
        
        # Status text
        self.status_text = QLabel("Ready")
        self.status_text.setStyleSheet("font-size: 10px; color: #666;")
        layout.addWidget(self.status_text)
        
        # Waveform animation (simple)
        self.waveform = QLabel("▁ ▂ ▃ ▄ ▅ ▄ ▃ ▂")
        self.waveform.setStyleSheet("font-size: 8px; color: #2196F3;")
        self.waveform.setVisible(False)
        layout.addWidget(self.waveform)
    
    def set_listening(self):
        """Set to listening state."""
        self.state = "listening"
        self.indicator.setStyleSheet("color: #FFC107; font-size: 12px;")
        self.indicator.setText("● ")  # Pulsing will animate
        self.status_text.setText("🎤 Listening...")
        self.waveform.setVisible(True)
        self.animation_timer.start(100)
    
    def set_processing(self):
        """Set to processing state."""
        self.state = "processing"
        self.indicator.setStyleSheet("color: #2196F3; font-size: 12px;")
        self.status_text.setText("⚙ Processing...")
        self.waveform.setVisible(True)
        self.animation_timer.start(100)
    
    def set_ready(self):
        """Set to ready state."""
        self.state = "idle"
        self.indicator.setStyleSheet("color: #4CAF50; font-size: 12px;")
        self.indicator.setText("●")
        self.status_text.setText("🎤 Ready")
        self.waveform.setVisible(False)
        self.animation_timer.stop()
    
    def set_error(self, error_msg="Error"):
        """Set to error state."""
        self.state = "error"
        self.indicator.setStyleSheet("color: #f44336; font-size: 12px;")
        self.status_text.setText(f"⚠ {error_msg}")
        self.waveform.setVisible(False)
        self.animation_timer.stop()
    
    def _update_animation(self):
        """Update waveform animation."""
        waves = [
            "▁ ▂ ▃ ▄ ▅ ▄ ▃ ▂",
            "▂ ▃ ▄ ▅ ▆ ▅ ▄ ▃",
            "▃ ▄ ▅ ▆ ▇ ▆ ▅ ▄",
            "▄ ▅ ▆ ▇ █ ▇ ▆ ▅",
        ]
        self.waveform.setText(waves[self.animation_frame % len(waves)])
        self.animation_frame += 1

def _create_status_bar(self):
    """Create enhanced status bar with voice indicator."""
    status_bar = self.statusBar()
    
    # Left side: Connection status
    connection_label = QLabel("✓ Connected")
    connection_label.setStyleSheet("color: #4CAF50; font-size: 10px;")
    status_bar.addWidget(connection_label, 0)
    
    # Middle: Voice indicator
    self.voice_indicator = VoiceIndicator()
    status_bar.addWidget(self.voice_indicator, 1)
    
    # Right side: AI Agent status
    ai_status = QLabel("AI: Ready")
    ai_status.setStyleSheet("color: #666; font-size: 10px;")
    status_bar.addPermanentWidget(ai_status, 0)
    
    # Device count
    device_label = QLabel("📱 2 Devices")
    device_label.setStyleSheet("color: #666; font-size: 10px;")
    status_bar.addPermanentWidget(device_label, 0)
```

### Integration with Voice Pipeline

```python
# In main_window.py, connect voice signals

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
```

---

## 6. Multi-Calendar Display (Google Calendar Style)

### Design: Month/Week/Agenda Views with Event Management

```python
class CalendarTab(QWidget):
    """Calendar tab with multiple views (Month, Week, Agenda)."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        # View selector
        view_combo = QComboBox()
        view_combo.addItems(["Month", "Week", "Agenda", "Day"])
        view_combo.currentIndexChanged.connect(self._on_view_changed)
        toolbar_layout.addWidget(QLabel("View:"))
        toolbar_layout.addWidget(view_combo)
        
        toolbar_layout.addSpacing(16)
        
        # Calendar selector (show/hide calendars)
        cal_btn = QPushButton("📅 Calendars")
        cal_btn.clicked.connect(self._open_calendar_selector)
        toolbar_layout.addWidget(cal_btn)
        
        # Search
        search_box = QLineEdit()
        search_box.setPlaceholderText("Search events...")
        search_box.setMaximumWidth(200)
        toolbar_layout.addWidget(search_box)
        
        toolbar_layout.addStretch()
        
        # Today button
        today_btn = QPushButton("Today")
        today_btn.clicked.connect(self._go_to_today)
        toolbar_layout.addWidget(today_btn)
        
        layout.addLayout(toolbar_layout)
        
        # Main calendar view (using stacked widget for different views)
        self.calendar_stack = QStackedWidget()
        self.calendar_stack.addWidget(self._create_month_view())
        self.calendar_stack.addWidget(self._create_week_view())
        self.calendar_stack.addWidget(self._create_agenda_view())
        self.calendar_stack.addWidget(self._create_day_view())
        
        layout.addWidget(self.calendar_stack)
    
    def _create_month_view(self):
        """Create month view calendar."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Month/year header
        header = QHBoxLayout()
        header.addStretch()
        month_label = QLabel("June 2026")
        month_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(month_label)
        header.addStretch()
        
        nav_layout = QHBoxLayout()
        prev_btn = QPushButton("<")
        prev_btn.setMaximumWidth(30)
        next_btn = QPushButton(">")
        next_btn.setMaximumWidth(30)
        nav_layout.addWidget(prev_btn)
        nav_layout.addWidget(next_btn)
        header.addLayout(nav_layout)
        
        layout.addLayout(header)
        
        # Calendar grid (7 columns for days of week)
        calendar_grid = QGridLayout()
        
        # Day headers
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        for col, day in enumerate(days):
            day_label = QLabel(day)
            day_label.setAlignment(Qt.AlignCenter)
            day_label.setStyleSheet("font-weight: bold; padding: 8px; background-color: #f0f0f0;")
            calendar_grid.addWidget(day_label, 0, col)
        
        # Calendar days (simplified - would generate from actual calendar)
        day_num = 1
        for row in range(1, 7):  # 6 rows for weeks
            for col in range(7):
                if day_num <= 30:  # June has 30 days
                    day_cell = self._create_day_cell(day_num)
                    calendar_grid.addWidget(day_cell, row, col)
                    day_num += 1
        
        layout.addLayout(calendar_grid)
        return widget
    
    def _create_day_cell(self, day_num):
        """Create a day cell with events."""
        cell = QFrame()
        cell.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        cell.setStyleSheet("""
            QFrame {
                border: 1px solid #e0e0e0;
                background-color: #fafafa;
                min-height: 100px;
            }
            QFrame:hover {
                background-color: #f0f0f0;
            }
        """)
        
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        # Day number
        day_label = QLabel(str(day_num))
        day_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(day_label)
        
        # Sample events
        if day_num in [14, 15, 20, 25]:  # Sample event days
            event_label = QLabel("Team Meeting")
            event_label.setStyleSheet("""
                background-color: #2196F3;
                color: white;
                padding: 2px 4px;
                border-radius: 2px;
                font-size: 9px;
            """)
            layout.addWidget(event_label)
        
        layout.addStretch()
        return cell
    
    def _create_week_view(self):
        """Create week view calendar."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Week View - June 24-30, 2026"))
        
        # Time grid (hours 6am-11pm)
        grid = QGridLayout()
        
        # Time labels (left column)
        for hour in range(6, 23):
            time_label = QLabel(f"{hour:02d}:00")
            time_label.setStyleSheet("font-size: 9px; color: #666;")
            grid.addWidget(time_label, hour - 6, 0)
        
        # Days of week (top row)
        days = ["Mon 24", "Tue 25", "Wed 26", "Thu 27", "Fri 28", "Sat 29", "Sun 30"]
        for col, day in enumerate(days):
            day_label = QLabel(day)
            day_label.setAlignment(Qt.AlignCenter)
            day_label.setStyleSheet("font-weight: bold; padding: 4px;")
            grid.addWidget(day_label, 0, col + 1)
        
        # Add event blocks (simplified)
        event = QLabel("Team\nMeeting")
        event.setAlignment(Qt.AlignCenter)
        event.setStyleSheet("""
            background-color: #2196F3;
            color: white;
            border-radius: 4px;
            padding: 4px;
            font-size: 9px;
        """)
        grid.addWidget(event, 3, 2)  # Monday 10:00
        
        layout.addLayout(grid)
        return widget
    
    def _create_agenda_view(self):
        """Create agenda list view."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        agenda_list = QListWidget()
        
        # Sample events
        events = [
            ("Mon, Jun 24", "09:00", "Team Meeting", "📅 Work"),
            ("Mon, Jun 24", "14:00", "Dentist Appointment", "📅 Personal"),
            ("Tue, Jun 25", "10:00", "Project Review", "📅 Work"),
            ("Wed, Jun 26", "18:30", "Dinner with Sarah", "📅 Personal"),
        ]
        
        for date, time, title, calendar in events:
            item = QListWidgetItem()
            widget_item = self._create_agenda_item(date, time, title, calendar)
            item.setSizeHint(widget_item.sizeHint())
            agenda_list.addItem(item)
            agenda_list.setItemWidget(item, widget_item)
        
        layout.addWidget(agenda_list)
        return widget
    
    def _create_agenda_item(self, date, time, title, calendar):
        """Create an agenda list item."""
        item_widget = QFrame()
        item_widget.setStyleSheet("""
            QFrame {
                border-bottom: 1px solid #e0e0e0;
                padding: 8px;
            }
        """)
        
        layout = QHBoxLayout(item_widget)
        
        # Time badge
        time_label = QLabel(f"{time}\n{date}")
        time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        time_label.setStyleSheet("color: #666; font-size: 10px; min-width: 60px;")
        layout.addWidget(time_label)
        
        # Event details
        details_layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        details_layout.addWidget(title_label)
        
        cal_label = QLabel(calendar)
        cal_label.setStyleSheet("color: #999; font-size: 9px;")
        details_layout.addWidget(cal_label)
        
        layout.addLayout(details_layout, 1)
        
        # Action buttons
        edit_btn = QPushButton("✎")
        edit_btn.setMaximumWidth(30)
        edit_btn.setFlat(True)
        layout.addWidget(edit_btn)
        
        return item_widget
    
    def _create_day_view(self):
        """Create single day detailed view."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Day View - June 24, 2026"))
        layout.addStretch()
        return widget
    
    def _open_calendar_selector(self):
        """Show dialog to select which calendars to display."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Calendars")
        layout = QVBoxLayout(dialog)
        
        calendars = [
            ("Personal", True),
            ("Work", True),
            ("Family", False),
            ("Holidays", True),
        ]
        
        checkboxes = {}
        for cal_name, is_visible in calendars:
            cb = QCheckBox(cal_name)
            cb.setChecked(is_visible)
            layout.addWidget(cb)
            checkboxes[cal_name] = cb
        
        layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec_()
    
    def _on_view_changed(self, index):
        """Switch between calendar views."""
        self.calendar_stack.setCurrentIndex(index)
    
    def _go_to_today(self):
        """Navigate to today's date."""
        pass
```

---

## 7. Shared/Household vs Personal Item Organization

### Design: Ownership & Sharing Controls

```python
class ShareabilityToggle(QWidget):
    """Toggle between Personal and Shared ownership."""
    
    def __init__(self, default_mode="personal", parent=None):
        super().__init__(parent)
        self.mode = default_mode
        self._build_ui()
    
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Personal button
        self.personal_btn = QPushButton("👤 Personal")
        self.personal_btn.setCheckable(True)
        self.personal_btn.setChecked(self.mode == "personal")
        self.personal_btn.clicked.connect(lambda: self._set_mode("personal"))
        self.personal_btn.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #ddd;
                background-color: white;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
            }
            QPushButton:checked {
                background-color: #E8F5E9;
                color: #2E7D32;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.personal_btn)
        
        # Shared button
        self.shared_btn = QPushButton("👥 Shared")
        self.shared_btn.setCheckable(True)
        self.shared_btn.setChecked(self.mode == "shared")
        self.shared_btn.clicked.connect(lambda: self._set_mode("shared"))
        self.shared_btn.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #ddd;
                background-color: white;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QPushButton:checked {
                background-color: #E3F2FD;
                color: #1565C0;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.shared_btn)
    
    def _set_mode(self, mode):
        """Set ownership mode."""
        self.mode = mode
        self.personal_btn.setChecked(mode == "personal")
        self.shared_btn.setChecked(mode == "shared")

class TodoTab(QWidget):
    """To-Do tab with shared/personal organization."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        # View toggle
        self.shareability_toggle = ShareabilityToggle("personal")
        toolbar.addWidget(self.shareability_toggle)
        
        toolbar.addSpacing(16)
        
        # Filter buttons
        all_btn = QPushButton("All")
        all_btn.setFlat(True)
        toolbar.addWidget(all_btn)
        
        today_btn = QPushButton("Today")
        today_btn.setFlat(True)
        toolbar.addWidget(today_btn)
        
        overdue_btn = QPushButton("Overdue")
        overdue_btn.setFlat(True)
        toolbar.addWidget(overdue_btn)
        
        toolbar.addStretch()
        
        # Add button
        add_btn = QPushButton("+ Add Task")
        add_btn.clicked.connect(self._add_new_task)
        toolbar.addWidget(add_btn)
        
        layout.addLayout(toolbar)
        
        # Task list
        self.task_list = QListWidget()
        self.task_list.setStyleSheet("QListWidget { border: 1px solid #e0e0e0; }")
        
        # Sample tasks
        tasks = [
            {"text": "Buy groceries", "shared": False, "priority": "high", "due": "Today"},
            {"text": "Team meeting - Q3 planning", "shared": True, "priority": "high", "due": "Today"},
            {"text": "Call dentist", "shared": False, "priority": "medium", "due": "Tomorrow"},
            {"text": "Household: Fix kitchen tap", "shared": True, "priority": "low", "due": "Sat"},
        ]
        
        for task in tasks:
            item_widget = self._create_task_item(task)
            item = QListWidgetItem()
            item.setSizeHint(item_widget.sizeHint())
            self.task_list.addItem(item)
            self.task_list.setItemWidget(item, item_widget)
        
        layout.addWidget(self.task_list)
    
    def _create_task_item(self, task):
        """Create a task list item with ownership indicator."""
        item_widget = QFrame()
        item_widget.setStyleSheet("""
            QFrame {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px;
                margin-bottom: 4px;
            }
            QFrame:hover {
                background-color: #fafafa;
            }
        """)
        
        layout = QHBoxLayout(item_widget)
        
        # Checkbox
        checkbox = QCheckBox()
        layout.addWidget(checkbox)
        
        # Task info
        info_layout = QVBoxLayout()
        
        # Title with owner indicator
        title_layout = QHBoxLayout()
        title_label = QLabel(task["text"])
        title_label.setStyleSheet("font-weight: bold;")
        title_layout.addWidget(title_label)
        
        owner_badge = QLabel("👥" if task["shared"] else "👤")
        owner_badge.setToolTip("Shared" if task["shared"] else "Personal")
        owner_badge.setStyleSheet("font-size: 11px;")
        title_layout.addWidget(owner_badge)
        
        # Priority and due date
        meta_layout = QHBoxLayout()
        priority_color = {
            "high": "#f44336",
            "medium": "#FFC107",
            "low": "#4CAF50"
        }[task["priority"]]
        
        priority_label = QLabel(f"● {task['priority'].title()}")
        priority_label.setStyleSheet(f"color: {priority_color}; font-size: 9px;")
        meta_layout.addWidget(priority_label)
        
        due_label = QLabel(f"Due: {task['due']}")
        due_label.setStyleSheet("color: #999; font-size: 9px;")
        meta_layout.addWidget(due_label)
        
        info_layout.addLayout(title_layout)
        info_layout.addLayout(meta_layout)
        layout.addLayout(info_layout, 1)
        
        # Action buttons
        edit_btn = QPushButton("✎")
        edit_btn.setMaximumWidth(30)
        edit_btn.setFlat(True)
        layout.addWidget(edit_btn)
        
        delete_btn = QPushButton("✕")
        delete_btn.setMaximumWidth(30)
        delete_btn.setFlat(True)
        layout.addWidget(delete_btn)
        
        return item_widget
    
    def _add_new_task(self):
        """Add a new task dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add New Task")
        layout = QFormLayout(dialog)
        
        task_input = QLineEdit()
        layout.addRow("Task:", task_input)
        
        # Ownership selector
        ownership = ShareabilityToggle("personal")
        layout.addRow("Ownership:", ownership)
        
        priority_combo = QComboBox()
        priority_combo.addItems(["Low", "Medium", "High"])
        layout.addRow("Priority:", priority_combo)
        
        due_date = QDateEdit()
        layout.addRow("Due Date:", due_date)
        
        save_btn = QPushButton("Add Task")
        save_btn.clicked.connect(dialog.accept)
        layout.addRow(save_btn)
        
        dialog.exec_()
```

---

## 8. Design Consistency Across All Features

### Create a Custom Theme/Style System

```python
# Create a new file: finance_app/ui/theme.py

from PyQt5.QtGui import QColor, QFont
from PyQt5.QtCore import Qt

class AppTheme:
    """Centralized theme and styling system."""
    
    # Color palette
    PRIMARY = "#2196F3"
    PRIMARY_DARK = "#1565C0"
    ACCENT = "#FF9800"
    ACCENT_DARK = "#E65100"
    
    SUCCESS = "#4CAF50"
    WARNING = "#FFC107"
    ERROR = "#f44336"
    INFO = "#00BCD4"
    
    BACKGROUND = "#FAFAFA"
    SURFACE = "#FFFFFF"
    TEXT_PRIMARY = "#212121"
    TEXT_SECONDARY = "#757575"
    DIVIDER = "#BDBDBD"
    BORDER_LIGHT = "#E0E0E0"
    
    # Spacing
    SPACING_XS = 4
    SPACING_SM = 8
    SPACING_MD = 16
    SPACING_LG = 24
    SPACING_XL = 32
    
    # Fonts
    @staticmethod
    def get_font(size=11, weight=QFont.Normal, family="Segoe UI"):
        """Get a font with consistent styling."""
        font = QFont(family, size, weight)
        return font
    
    # Button styles
    @staticmethod
    def get_button_style(variant="primary", size="medium"):
        """Get button stylesheet."""
        if variant == "primary":
            return """
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
                QPushButton:pressed {
                    background-color: #1565C0;
                }
            """
        elif variant == "secondary":
            return """
                QPushButton {
                    background-color: transparent;
                    color: #2196F3;
                    border: 1px solid #2196F3;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: rgba(33, 150, 243, 0.1);
                }
            """
        elif variant == "flat":
            return """
                QPushButton {
                    background-color: transparent;
                    color: #2196F3;
                    border: none;
                    padding: 8px 16px;
                }
                QPushButton:hover {
                    background-color: rgba(33, 150, 243, 0.1);
                }
            """
    
    # Card styles
    @staticmethod
    def get_card_style():
        return """
            QFrame {
                background-color: white;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 12px;
            }
        """
    
    # Input field styles
    @staticmethod
    def get_input_style():
        return """
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 8px;
                background-color: white;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 2px solid #2196F3;
            }
        """
    
    # Tab widget styles
    @staticmethod
    def get_tab_style():
        return """
            QTabWidget::pane {
                border: 1px solid #E0E0E0;
            }
            QTabBar::tab {
                background-color: #f5f5f5;
                padding: 8px 16px;
                border: none;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 2px solid #2196F3;
            }
        """

# Apply theme globally
class ThemedWidget(QWidget):
    """Base widget with theme applied."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(AppTheme.get_input_style())

# Usage in main_window.py
from finance_app.ui.theme import AppTheme

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {AppTheme.BACKGROUND};
            }}
            QTabWidget {{
                background-color: white;
            }}
            {AppTheme.get_tab_style()}
            {AppTheme.get_input_style()}
        """)
```

### Component Library Reference

Create reusable components for consistency:

```python
# finance_app/ui/components.py

class ThemedButton(QPushButton):
    def __init__(self, text, variant="primary", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(AppTheme.get_button_style(variant))

class ThemedCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(AppTheme.get_card_style())
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)

class MetricCard(ThemedCard):
    """Card for displaying metrics."""
    def __init__(self, title, value, unit="", icon="", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        
        # Header
        header = QHBoxLayout()
        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"font-size: 20px;")
            header.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; color: #666;")
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)
        
        # Value
        value_label = QLabel(f"{value} {unit}")
        value_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(value_label)

class IconButton(QPushButton):
    """Button with icon and optional text."""
    def __init__(self, icon_text, text="", parent=None):
        super().__init__(f"{icon_text} {text}".strip(), parent)
        self.setFlat(True)
        self.setCursor(Qt.PointingHandCursor)
```

---

## 9. Responsive Design Considerations

### Adaptive Layout Based on Window Size

```python
class ResponsiveMainWindow(QMainWindow):
    """Main window that adapts to different screen sizes."""
    
    BREAKPOINT_MOBILE = 800
    BREAKPOINT_TABLET = 1200
    
    def __init__(self):
        super().__init__()
        self.current_size_class = "desktop"
        self._build_ui()
        self.resizeEvent = self._on_resize
    
    def _on_resize(self, event):
        """Adjust layout based on window width."""
        width = event.size().width()
        
        if width < self.BREAKPOINT_MOBILE:
            self._set_mobile_layout()
        elif width < self.BREAKPOINT_TABLET:
            self._set_tablet_layout()
        else:
            self._set_desktop_layout()
        
        super().resizeEvent(event)
    
    def _set_mobile_layout(self):
        """Optimize for mobile devices (< 800px)."""
        if self.current_size_class == "mobile":
            return
        
        self.current_size_class = "mobile"
        
        # Hide sidebar, use drawer or bottom nav
        self.sidebar.setVisible(False)
        
        # Reduce spacing
        main_layout = self.centralWidget().layout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        
        # Switch to bottom navigation
        if not hasattr(self, 'bottom_nav'):
            self._create_bottom_navigation()
        
        self.bottom_nav.setVisible(True)
    
    def _set_tablet_layout(self):
        """Optimize for tablets (800-1200px)."""
        if self.current_size_class == "tablet":
            return
        
        self.current_size_class = "tablet"
        
        # Show compact sidebar
        self.sidebar.setVisible(True)
        self.sidebar.setMaximumWidth(120)
        
        # Show bottom nav if exists
        if hasattr(self, 'bottom_nav'):
            self.bottom_nav.setVisible(False)
    
    def _set_desktop_layout(self):
        """Full desktop layout (> 1200px)."""
        if self.current_size_class == "desktop":
            return
        
        self.current_size_class = "desktop"
        
        # Show full sidebar
        self.sidebar.setVisible(True)
        self.sidebar.setMaximumWidth(200)
        
        # Hide bottom nav if exists
        if hasattr(self, 'bottom_nav'):
            self.bottom_nav.setVisible(False)
    
    def _create_bottom_navigation(self):
        """Create mobile-friendly bottom navigation."""
        bottom_nav = QWidget()
        layout = QHBoxLayout(bottom_nav)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        nav_items = [
            ("💰", "Finance", 0),
            ("📅", "Calendar", 1),
            ("✓", "To-Do", 2),
            ("🛒", "Shopping", 3),
        ]
        
        for icon, label, tab_index in nav_items:
            btn = QPushButton(f"{icon}\n{label}")
            btn.setFlat(True)
            btn.setMinimumHeight(60)
            btn.clicked.connect(lambda checked, idx=tab_index: self.tab_widget.setCurrentIndex(idx))
            layout.addWidget(btn)
        
        self.addToolBar(bottom_nav)
        self.bottom_nav = bottom_nav
```

### Responsive Grid Layouts

```python
class ResponsiveGridLayout(QGridLayout):
    """Grid that adapts column count based on available width."""
    
    def __init__(self, min_column_width=300):
        super().__init__()
        self.min_column_width = min_column_width
        self._items = []
    
    def add_item_responsive(self, widget):
        """Add item and reflow based on available space."""
        self._items.append(widget)
        self._reflow()
    
    def _reflow(self):
        """Recalculate columns and redistribute items."""
        # Calculate available width
        available_width = self.geometry().width()
        columns = max(1, available_width // self.min_column_width)
        
        # Clear layout
        while self.count():
            self.takeAt(0)
        
        # Redistribute items
        for idx, item in enumerate(self._items):
            row = idx // columns
            col = idx % columns
            self.addWidget(item, row, col)
```

---

## 10. Accessibility Features

### Implement WCAG 2.1 AA Compliance

```python
# finance_app/ui/accessibility.py

class AccessibilityManager:
    """Manage accessibility features across the app."""
    
    # High contrast mode
    @staticmethod
    def get_high_contrast_palette():
        """Return high contrast color palette."""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#000000"))
        palette.setColor(QPalette.WindowText, QColor("#FFFFFF"))
        palette.setColor(QPalette.Button, QColor("#1a1a1a"))
        palette.setColor(QPalette.ButtonText, QColor("#FFFFFF"))
        return palette
    
    # Font scaling
    @staticmethod
    def get_scaled_font(base_size=11, scale_factor=1.0):
        """Get font scaled for readability."""
        font = QFont("Segoe UI", int(base_size * scale_factor))
        return font
    
    # Keyboard navigation
    @staticmethod
    def add_keyboard_shortcuts(main_window):
        """Add keyboard shortcuts for accessibility."""
        QShortcut(QKeySequence("Ctrl+1"), main_window, lambda: main_window._navigate_to_tab(0))
        QShortcut(QKeySequence("Ctrl+2"), main_window, lambda: main_window._navigate_to_tab(1))
        QShortcut(QKeySequence("Ctrl+3"), main_window, lambda: main_window._navigate_to_tab(2))
        QShortcut(QKeySequence("Ctrl+4"), main_window, lambda: main_window._navigate_to_tab(3))
        QShortcut(QKeySequence("Ctrl+?"), main_window, lambda: main_window._show_help())

class AccessibleButton(QPushButton):
    """Button with enhanced accessibility."""
    
    def __init__(self, text, tooltip="", parent=None):
        super().__init__(text, parent)
        if tooltip:
            self.setToolTip(tooltip)
        
        # Ensure minimum size for touch targets (44x44px)
        self.setMinimumHeight(44)
        self.setMinimumWidth(44)
        
        # Add focus rectangle
        self.setFocusPolicy(Qt.StrongFocus)

class AccessibleLabel(QLabel):
    """Label with screen reader support."""
    
    def __init__(self, text, for_widget=None, parent=None):
        super().__init__(text, parent)
        if for_widget:
            self.setBuddy(for_widget)
        
        # Set minimum text contrast
        self.setStyleSheet("""
            QLabel {
                color: #212121;  /* WCAG AA compliant dark text */
            }
        """)

class AccessibleComboBox(QComboBox):
    """ComboBox with screen reader accessible labels."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(44)
        
        # Announce selected item to screen readers
        self.currentIndexChanged.connect(self._announce_selection)
    
    def _announce_selection(self):
        """Announce selection (would integrate with screen reader)."""
        current_text = self.currentText()
        # In a real implementation, this would use accessibility APIs
        pass

# Usage in main window
class AccessibleMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Enable accessibility manager
        self.accessibility_mgr = AccessibilityManager()
        
        # Add keyboard shortcuts
        AccessibilityManager.add_keyboard_shortcuts(self)
        
        # Check for high contrast preference
        if self._is_high_contrast_enabled():
            self.setPalette(AccessibilityManager.get_high_contrast_palette())
        
        # Set minimum font size for readability
        self.setFont(AccessibilityManager.get_scaled_font(12))
    
    def _is_high_contrast_enabled(self):
        """Check if system high contrast mode is enabled."""
        # Platform-specific check
        import platform
        if platform.system() == "Windows":
            # Read Windows Registry for high contrast
            pass
        return False
```

---

## User Flow Diagrams

### Main User Flow: Feature Navigation

```
Application Launch
    ↓
┌─────────────────────────────────┐
│   Choose Feature (Sidebar)      │
├─────────────────────────────────┤
│  ├─ 💰 Finance                  │
│  ├─ 📅 Calendar                 │
│  ├─ ✓ To-Do                     │
│  └─ 🛒 Shopping                 │
└──────────┬──────────────────────┘
           ├──→ Finance Dashboard
           │    ├─ View Transactions
           │    ├─ Analyze Budget
           │    └─ Chat with AI Agent
           │
           ├──→ Calendar View
           │    ├─ Month/Week/Agenda
           │    ├─ Create/Edit Events
           │    └─ Manage Calendars
           │
           ├──→ To-Do Manager
           │    ├─ Personal Tasks
           │    ├─ Shared Household Tasks
           │    └─ Set Priorities
           │
           └──→ Shopping List
                ├─ Personal Items
                └─ Shared Household Items
```

### Voice Command Flow

```
User Initiates Voice Input
    ↓
┌──────────────────────────┐
│ Voice Indicator State    │
├──────────────────────────┤
│ Ready 🎤 (Green)         │
└──────────────┬───────────┘
               ↓
     User Speaks Command
               ↓
┌──────────────────────────┐
│ Listening 🎤 (Yellow)    │
├──────────────────────────┤
│ ▁ ▂ ▃ ▄ ▅ (Waveform)    │
└──────────────┬───────────┘
               ↓
     ASR Processing
               ↓
┌──────────────────────────┐
│ Processing ⚙ (Blue)     │
├──────────────────────────┤
│ "Analyzing voice..."     │
└──────────────┬───────────┘
               ├─ Voice Command Parsed
               │
               └──→ Agent Processing
                   ├─ Finance: "Budget analysis"
                   ├─ Calendar: "Schedule meeting"
                   ├─ To-Do: "Create task"
                   └─ Shopping: "Add item"
                       ↓
                   ┌────────────────┐
                   │ Ready ✓ (Green)│
                   └────────────────┘
```

### Device Pairing Flow

```
User Clicks "+ Add Device"
    ↓
┌────────────────────────────┐
│ Device Discovery Phase     │
├────────────────────────────┤
│ Searching for devices... 🔍│
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ Discovery Results          │
├────────────────────────────┤
│ ☐ Device1 (Ready)         │
│ ☐ Device2 (Ready)         │
│ ☐ Device3 (Battery Low)   │
└──────────────┬─────────────┘
               ↓
    User Selects Device
               ↓
┌────────────────────────────┐
│ Pairing Code Verification  │
├────────────────────────────┤
│ Code: 123456               │
│ Confirm on device          │
└──────────────┬─────────────┘
               ↓
    User Confirms
               ↓
┌────────────────────────────┐
│ Connected! ✓               │
├────────────────────────────┤
│ Device added to list       │
│ Voice input enabled        │
└────────────────────────────┘
```

---

## Implementation Checklist

### Phase 1: Core UI Structure (Week 1-2)
- [ ] Refactor `main_window.py` with sidebar + tab layout
- [ ] Create theme system (`ui/theme.py`)
- [ ] Implement responsive layout system
- [ ] Create reusable component library (`ui/components.py`)
- [ ] Update existing Finance tab to match theme

### Phase 2: Calendar Tab (Week 2-3)
- [ ] Calendar controller in `ui/controllers/`
- [ ] Implement month/week/agenda views
- [ ] Add calendar selection (shared calendars)
- [ ] Integrate with AI agent for scheduling

### Phase 3: To-Do Tab (Week 3)
- [ ] To-Do controller
- [ ] Implement personal/shared toggle
- [ ] Task management UI
- [ ] Priority and due date handling

### Phase 4: Shopping Tab (Week 4)
- [ ] Shopping controller
- [ ] List management (personal/shared)
- [ ] Item categorization
- [ ] Household vs personal views

### Phase 5: Agent Customization (Week 4-5)
- [ ] Agent configuration dialog
- [ ] Agent settings persistence
- [ ] Model selection UI
- [ ] Real-time preview

### Phase 6: Device Status & Voice (Week 5-6)
- [ ] Device status panel
- [ ] Voice indicator animation
- [ ] Integration with voice pipeline
- [ ] Device management UI

### Phase 7: Polish & Accessibility (Week 6-7)
- [ ] High contrast mode
- [ ] Keyboard navigation
- [ ] Font scaling
- [ ] Screen reader support

---

## Additional Resources

### PyQt5 Best Practices
- Use QStyledItemDelegate for custom table/list rendering
- Leverage QSplitter for resizable panels
- Use QStackedWidget for multi-view interfaces
- Apply stylesheets centrally for consistency

### Recommended PyQt5 Libraries
- **PyQtWebEngine** - For rich text/web content display
- **pyqtdeploy** - For packaging and distribution
- **PyQtGraph** - For advanced charting (alternative to Matplotlib)

### Design References
- Google Material Design 3
- Apple Human Interface Guidelines
- macOS Ventura Design System
- Fluent Design System (Microsoft)

