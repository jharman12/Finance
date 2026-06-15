from __future__ import annotations

import csv
from datetime import date
import calendar
import html
import math
import re

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtCore import QDate, QEvent, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QKeySequence, QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QAction,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from finance_app.config import APP_NAME
from finance_app.chart_models import CashflowChartsPayload, PositionChartsPayload
from finance_app.models import Asset, AssistantResult, Transaction
from finance_app.services.assistant_service import AssistantService
from finance_app.services.voice_pipeline import VoiceCoordinator
from finance_app.storage import FinanceRepository
from finance_app.ui.controllers.app_controller import AppController
from finance_app.ui.controllers.analytics_controller import AnalyticsController
from finance_app.ui.controllers.assets_controller import AssetsController
from finance_app.ui.controllers.budget_controller import BudgetController
from finance_app.ui.controllers.category_controller import CategoryController
from finance_app.ui.controllers.recurring_controller import RecurringController
from finance_app.ui.controllers.transaction_controller import TransactionController
from finance_app.ui.support import AssistantWorker, MetricCard, OllamaWarmupWorker


class MainWindow(QMainWindow):
    voice_status_signal = pyqtSignal(str)
    voice_error_signal = pyqtSignal(str)
    voice_wake_signal = pyqtSignal(str)
    voice_command_signal = pyqtSignal(str)
    voice_partial_signal = pyqtSignal(str)
    voice_diagnostic_signal = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
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
        self._layout_base_metrics: dict[int, tuple[tuple[int, int, int, int], int]] = {}
        self._density_actions: dict[str, QAction] = {}
        self.voice_enabled = False
        self._voice_active_surface: str | None = None
        self._voice_ui: dict[str, dict[str, object]] = {}
        self._assistant_worker: AssistantWorker | None = None
        self._ollama_warmup_worker: OllamaWarmupWorker | None = None
        self._selected_year = date.today().year
        self._selected_month = date.today().month
        self._selected_asset_id: int | None = None
        self._is_refreshing_asset_selector = False
        self._is_loading_budget_goal = False

        self.setWindowTitle(APP_NAME)
        self.resize(1400, 880)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)

        self.dashboard_tab = QWidget()
        self.charts_tab = QWidget()
        self.ledger_tab = QWidget()
        self.recurring_tab = QWidget()
        self.budget_tab = QWidget()
        self.assets_tab = QWidget()
        self.assistant_tab = QWidget()
        self.voice_test_tab = QWidget()

        self.tabs.addTab(self.dashboard_tab, "Overview")
        self.tabs.addTab(self.charts_tab, "Charts")
        self.tabs.addTab(self.ledger_tab, "Ledger")
        self.tabs.addTab(self.recurring_tab, "Recurring")
        self.tabs.addTab(self.budget_tab, "Budget")
        self.tabs.addTab(self.assets_tab, "Assets")
        self.tabs.addTab(self.assistant_tab, "Assistant")
        self.tabs.addTab(self.voice_test_tab, "Voice Test")

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Syncing recurring items with transactions...", 0)

        self._build_dashboard_tab()
        self._build_charts_tab()
        self._build_ledger_tab()
        self._build_recurring_tab()
        self._build_budget_tab()
        self._build_assets_tab()
        self._build_assistant_tab()
        self._build_voice_test_tab()
        self._build_menu_bar()
        self._capture_layout_base_metrics()
        self._setup_ui_scale_controls()

        # Route all voice callbacks through Qt signals so UI updates always run on the main thread.
        self.voice_status_signal.connect(self._handle_voice_status)
        self.voice_error_signal.connect(self._handle_voice_error)
        self.voice_wake_signal.connect(self._handle_voice_wake)
        self.voice_command_signal.connect(self._handle_voice_command)
        self.voice_partial_signal.connect(self._handle_voice_partial)
        self.voice_diagnostic_signal.connect(self._handle_voice_diagnostic)

        self._bind_voice_coordinator_callbacks()
        
        # Load saved model preference
        saved_model = self.app_controller.get_setting("selected_model")
        if saved_model:
            self.assistant_service.client.set_model(saved_model)
            available_models = self.assistant_service.client.list_available_models()
            if saved_model in available_models:
                self.model_selector.setCurrentText(saved_model)

        self._apply_ui_scale(persist=False, show_status=False)
        
        # Sync all recurring items with their transactions to fix any category mismatches
        sync_result = self.app_controller.sync_recurring_with_transactions()
        if sync_result["total_synced"] > 0:
            self.status_bar.showMessage(
                f"Fixed {sync_result['total_synced']} transaction categories to match recurring items.",
                5000
            )
        else:
            self.status_bar.showMessage("", 0)
        
        self.refresh_all()
        self._warmup_ollama()

    def _build_scrollable_tab_layout(self, tab: QWidget) -> QVBoxLayout:
        outer_layout = QVBoxLayout(tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        outer_layout.addWidget(scroll_area)

        content = QWidget()
        scroll_area.setWidget(content)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(18)
        return content_layout

    def _build_dashboard_tab(self) -> None:
        layout = self._build_scrollable_tab_layout(self.dashboard_tab)

        header = QLabel("Personal Finance Command Center")
        header.setObjectName("PageTitle")
        subtitle = QLabel(
            "Track cash flow, capture transactions quickly, and let the local assistant update the ledger."
        )
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(header)
        layout.addWidget(subtitle)

        period_row = QHBoxLayout()
        period_label = QLabel("Viewing period")
        self.month_toggle = QComboBox()
        self.year_toggle = QComboBox()
        self._populate_period_selectors(self.month_toggle, self.year_toggle)
        self.month_toggle.currentIndexChanged.connect(self._handle_period_changed)
        self.year_toggle.currentIndexChanged.connect(self._handle_period_changed)

        period_row.addWidget(period_label)
        period_row.addWidget(self.month_toggle)
        period_row.addWidget(self.year_toggle)
        period_row.addStretch(1)
        
        # Add manage categories button
        self.manage_categories_button = QPushButton("Manage Categories")
        self.manage_categories_button.clicked.connect(self._open_category_manager)
        period_row.addWidget(self.manage_categories_button)
        
        layout.addLayout(period_row)

        metrics_row = QGridLayout()
        metrics_row.setHorizontalSpacing(16)
        metrics_row.setVerticalSpacing(16)
        self.income_card = MetricCard("Income", "$0.00")
        self.expense_card = MetricCard("Expenses", "$0.00")
        self.net_card = MetricCard("Net Position", "$0.00")
        self.count_card = MetricCard("Transactions", "0")
        metrics_row.addWidget(self.income_card, 0, 0)
        metrics_row.addWidget(self.expense_card, 0, 1)
        metrics_row.addWidget(self.net_card, 1, 0)
        metrics_row.addWidget(self.count_card, 1, 1)
        layout.addLayout(metrics_row)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_quick_entry_panel())
        splitter.addWidget(self._build_recent_activity_panel())
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([420, 760])
        layout.addWidget(splitter, 1)

        dashboard_actions = QHBoxLayout()
        self.edit_recent_button = QPushButton("Edit Selected Recent Entry")
        self.edit_recent_button.clicked.connect(self.edit_selected_recent_transaction)
        dashboard_actions.addWidget(self.edit_recent_button)
        self.delete_recent_button = QPushButton("Delete Selected Recent Entry")
        self.delete_recent_button.clicked.connect(lambda: self.delete_selected_transaction(self.recent_table))
        dashboard_actions.addWidget(self.delete_recent_button)
        dashboard_actions.addStretch(1)
        layout.addLayout(dashboard_actions)

    def _build_charts_tab(self) -> None:
        layout = self._build_scrollable_tab_layout(self.charts_tab)

        title = QLabel("Personal Finance Charts")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Analyze cash flow, net worth, debt, and personal financial position for the selected period."
        )
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        period_row = QHBoxLayout()
        period_row.addWidget(QLabel("Chart period"))
        self.charts_month_toggle = QComboBox()
        self.charts_year_toggle = QComboBox()
        self._populate_period_selectors(self.charts_month_toggle, self.charts_year_toggle)
        self.charts_month_toggle.currentIndexChanged.connect(self._handle_chart_period_changed)
        self.charts_year_toggle.currentIndexChanged.connect(self._handle_chart_period_changed)
        period_row.addWidget(self.charts_month_toggle)
        period_row.addWidget(self.charts_year_toggle)
        period_row.addWidget(QLabel("View"))
        self.charts_view_selector = QComboBox()
        self.charts_view_selector.addItem("Cash Flow", "cashflow")
        self.charts_view_selector.addItem("Personal Position", "position")
        self.charts_view_selector.setCurrentIndex(1)
        self.charts_view_selector.currentIndexChanged.connect(self.refresh_charts)
        period_row.addWidget(self.charts_view_selector)
        period_row.addStretch(1)
        layout.addLayout(period_row)

        charts_panel = QFrame()
        charts_panel.setObjectName("Panel")
        charts_layout = QVBoxLayout(charts_panel)
        charts_layout.setContentsMargins(18, 18, 18, 18)
        charts_layout.setSpacing(12)

        self.charts_summary = QLabel("")
        self.charts_summary.setObjectName("PageSubtitle")
        charts_layout.addWidget(self.charts_summary)

        self.analytics_figure = Figure(figsize=(12, 8), facecolor="#111a27")
        self.analytics_canvas = FigureCanvas(self.analytics_figure)
        charts_layout.addWidget(self.analytics_canvas, 1)
        layout.addWidget(charts_panel, 1)

    def _build_quick_entry_panel(self) -> QWidget:
        container = QFrame()
        container.setObjectName("Panel")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = QLabel("Quick Entry")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        expense_form = QFormLayout()
        self.expense_amount = QDoubleSpinBox()
        self.expense_amount.setMaximum(1_000_000)
        self.expense_amount.setDecimals(2)
        self.expense_amount.setPrefix("$")
        self.expense_category = QComboBox()
        self.expense_description = QLineEdit()
        self.expense_description.setPlaceholderText("Coffee, grocery run, utilities")
        self.expense_date = QDateEdit()
        self.expense_date.setCalendarPopup(True)
        self.expense_date.setDate(QDate.currentDate())
        self.expense_asset_link_combo = QComboBox()
        self.expense_asset_payment_kind_combo = QComboBox()
        self.expense_asset_payment_kind_combo.addItem("Mortgage", "mortgage")
        self.expense_asset_payment_kind_combo.addItem("Principal", "principal")
        expense_form.addRow("Amount", self.expense_amount)
        expense_form.addRow("Category", self.expense_category)
        expense_form.addRow("Description", self.expense_description)
        expense_form.addRow("Date", self.expense_date)
        expense_form.addRow("Link To Asset", self.expense_asset_link_combo)
        expense_form.addRow("Apply As", self.expense_asset_payment_kind_combo)
        layout.addLayout(expense_form)

        expense_button = QPushButton("Add Expense")
        expense_button.clicked.connect(self.add_expense)
        layout.addWidget(expense_button)

        income_form = QFormLayout()
        self.income_amount = QDoubleSpinBox()
        self.income_amount.setMaximum(1_000_000)
        self.income_amount.setDecimals(2)
        self.income_amount.setPrefix("$")
        self.income_category = QComboBox()
        self.income_description = QLineEdit()
        self.income_description.setPlaceholderText("Salary, refund, dividend")
        self.income_date = QDateEdit()
        self.income_date.setCalendarPopup(True)
        self.income_date.setDate(QDate.currentDate())
        income_form.addRow("Amount", self.income_amount)
        income_form.addRow("Category", self.income_category)
        income_form.addRow("Description", self.income_description)
        income_form.addRow("Date", self.income_date)
        layout.addSpacing(8)
        layout.addLayout(income_form)

        income_button = QPushButton("Add Income")
        income_button.clicked.connect(self.add_income)
        layout.addWidget(income_button)

        layout.addStretch(1)
        return container

    def _build_recurring_tab(self) -> None:
        layout = self._build_scrollable_tab_layout(self.recurring_tab)

        title = QLabel("Recurring Budget Items")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Create repeating expenses or income entries that automatically post when they are due.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QGridLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setHorizontalSpacing(16)
        panel_layout.setVerticalSpacing(12)

        self.recurring_kind = QComboBox()
        self.recurring_kind.addItems(["expense", "income"])
        self.recurring_kind.currentTextChanged.connect(self.refresh_recurring_category_controls)

        self.recurring_amount = QDoubleSpinBox()
        self.recurring_amount.setMaximum(1_000_000)
        self.recurring_amount.setDecimals(2)
        self.recurring_amount.setPrefix("$")

        self.recurring_category = QComboBox()

        self.recurring_description = QLineEdit()
        self.recurring_description.setPlaceholderText("Mortgage, paycheck, subscriptions, transfer")

        self.recurring_interval_count = QSpinBox()
        self.recurring_interval_count.setMinimum(1)
        self.recurring_interval_count.setMaximum(3650)
        self.recurring_interval_count.setValue(1)

        self.recurring_interval_unit = QComboBox()
        self.recurring_interval_unit.addItem("months")
        self.recurring_interval_unit.setEnabled(False)

        self.recurring_start_date = QDateEdit()
        self.recurring_start_date.setCalendarPopup(True)
        self.recurring_start_date.setDate(QDate.currentDate())
        self.recurring_asset_link_combo = QComboBox()
        self.recurring_asset_payment_kind_combo = QComboBox()
        self.recurring_asset_payment_kind_combo.addItem("Mortgage", "mortgage")
        self.recurring_asset_payment_kind_combo.addItem("Principal", "principal")

        panel_layout.addWidget(QLabel("Type"), 0, 0)
        panel_layout.addWidget(self.recurring_kind, 0, 1)
        panel_layout.addWidget(QLabel("Amount"), 0, 2)
        panel_layout.addWidget(self.recurring_amount, 0, 3)
        panel_layout.addWidget(QLabel("Category"), 1, 0)
        panel_layout.addWidget(self.recurring_category, 1, 1)
        panel_layout.addWidget(QLabel("Description"), 1, 2)
        panel_layout.addWidget(self.recurring_description, 1, 3)
        panel_layout.addWidget(QLabel("Every month(s)"), 2, 0)
        panel_layout.addWidget(self.recurring_interval_count, 2, 1)
        panel_layout.addWidget(QLabel("Cadence"), 2, 2)
        panel_layout.addWidget(self.recurring_interval_unit, 2, 3)
        panel_layout.addWidget(QLabel("Start date"), 3, 0)
        panel_layout.addWidget(self.recurring_start_date, 3, 1)
        panel_layout.addWidget(QLabel("Link To Asset"), 3, 2)
        panel_layout.addWidget(self.recurring_asset_link_combo, 3, 3)
        panel_layout.addWidget(QLabel("Apply As"), 4, 0)
        panel_layout.addWidget(self.recurring_asset_payment_kind_combo, 4, 1)

        self.recurring_add_button = QPushButton("Add Recurring Item")
        self.recurring_add_button.clicked.connect(self.add_recurring_item)
        panel_layout.addWidget(self.recurring_add_button, 4, 0, 1, 4)

        layout.addWidget(panel)

        self.recurring_table = QTableWidget(0, 8)
        self.recurring_table.setHorizontalHeaderLabels(
            ["Type", "Amount", "Category", "Description", "Cadence", "Next Due", "Last Run", "Active"]
        )
        self.recurring_table.verticalHeader().setVisible(False)
        self.recurring_table.setAlternatingRowColors(True)
        self.recurring_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.recurring_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recurring_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.recurring_table, 1)

        recurring_actions = QHBoxLayout()
        self.edit_recurring_button = QPushButton("Edit Selected Item")
        self.edit_recurring_button.clicked.connect(self.edit_selected_recurring)
        self.delete_recurring_button = QPushButton("Delete Selected Item")
        self.delete_recurring_button.clicked.connect(self.delete_selected_recurring)
        recurring_actions.addWidget(self.edit_recurring_button)
        recurring_actions.addWidget(self.delete_recurring_button)
        recurring_actions.addStretch(1)
        layout.addLayout(recurring_actions)

        self.recurring_status = QLabel("Recurring items are posted automatically when their due date arrives.")
        self.recurring_status.setObjectName("PageSubtitle")
        layout.addWidget(self.recurring_status)

    def _build_recent_activity_panel(self) -> QWidget:
        container = QFrame()
        container.setObjectName("Panel")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = QLabel("Recent Activity")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.recent_table = QTableWidget(0, 5)
        self.recent_table.setHorizontalHeaderLabels(["Date", "Type", "Category", "Description", "Amount"])
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.recent_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.recent_table, 1)

        self.category_summary = QTextEdit()
        self.category_summary.setReadOnly(True)
        self.category_summary.setPlaceholderText("Top expense categories will appear here.")
        layout.addWidget(self.category_summary)

        return container

    def _build_ledger_tab(self) -> None:
        layout = self._build_scrollable_tab_layout(self.ledger_tab)

        title = QLabel("Ledger")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Everything is stored locally in SQLite as soon as you add it.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        ledger_filter_row = QHBoxLayout()
        ledger_filter_row.addWidget(QLabel("Category Filter"))
        self.ledger_category_filter = QComboBox()
        self.ledger_category_filter.currentIndexChanged.connect(self.refresh_ledger_tables)
        ledger_filter_row.addWidget(self.ledger_category_filter)
        self.clear_ledger_filter_button = QPushButton("Clear Filter")
        self.clear_ledger_filter_button.clicked.connect(self._clear_ledger_filters)
        ledger_filter_row.addWidget(self.clear_ledger_filter_button)
        ledger_filter_row.addStretch(1)
        layout.addLayout(ledger_filter_row)

        self.full_ledger_table = QTableWidget(0, 5)
        self.full_ledger_table.setHorizontalHeaderLabels(["Date", "Type", "Category", "Description", "Amount"])
        self.full_ledger_table.verticalHeader().setVisible(False)
        self.full_ledger_table.setAlternatingRowColors(True)
        self.full_ledger_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.full_ledger_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.full_ledger_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.full_ledger_table, 1)

        ledger_actions = QHBoxLayout()
        self.delete_ledger_button = QPushButton("Delete Selected Ledger Entry")
        self.delete_ledger_button.clicked.connect(lambda: self.delete_selected_transaction(self.full_ledger_table))
        ledger_actions.addWidget(self.delete_ledger_button)
        ledger_actions.addStretch(1)
        layout.addLayout(ledger_actions)

    def _build_budget_tab(self) -> None:
        outer_layout = QVBoxLayout(self.budget_tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        outer_layout.addWidget(scroll_area)

        budget_content = QWidget()
        scroll_area.setWidget(budget_content)

        layout = QVBoxLayout(budget_content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        title = QLabel("Monthly Budget & Forecast")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Understand your income, expenses, and net for the month.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Period selector
        period_row = QHBoxLayout()
        period_label = QLabel("Budget period")
        self.budget_month_toggle = QComboBox()
        self.budget_year_toggle = QComboBox()
        self._populate_period_selectors(self.budget_month_toggle, self.budget_year_toggle)
        self.budget_month_toggle.currentIndexChanged.connect(self._handle_budget_period_changed)
        self.budget_year_toggle.currentIndexChanged.connect(self._handle_budget_period_changed)
        period_row.addWidget(period_label)
        period_row.addWidget(self.budget_month_toggle)
        period_row.addWidget(self.budget_year_toggle)
        period_row.addStretch(1)
        layout.addLayout(period_row)

        # Key insights summary section
        insight_panel = QFrame()
        insight_panel.setObjectName("Panel")
        insight_layout = QGridLayout(insight_panel)
        insight_layout.setContentsMargins(18, 18, 18, 18)
        insight_layout.setSpacing(18)

        # Top row: Income, total spend, net
        self.budget_income_insight = MetricCard("Monthly Income", "$0.00")
        self.budget_total_spend_insight = MetricCard("Expected Total Spend", "$0.00")
        self.budget_net_on_target = MetricCard("Break-even Left to Spend", "$0.00")

        insight_layout.addWidget(self.budget_income_insight, 0, 0)
        insight_layout.addWidget(self.budget_total_spend_insight, 0, 1)
        insight_layout.addWidget(self.budget_net_on_target, 0, 2)

        # Bottom row: Savings goal, remaining to spend budget
        self.budget_savings_goal_card = MetricCard("Savings Goal", "$0.00")
        self.budget_expected_net = MetricCard("Expected Net This Month", "$0.00")
        self.budget_remaining_to_spend = MetricCard("Goal Left to Spend", "$0.00")

        self.budget_overspent_count_card = MetricCard("Overspent Categories", "0")
        self.budget_under_budget_count_card = MetricCard("Under-Budget Categories", "0")

        insight_layout.addWidget(self.budget_savings_goal_card, 1, 0)
        insight_layout.addWidget(self.budget_expected_net, 1, 1)
        insight_layout.addWidget(self.budget_remaining_to_spend, 1, 2)
        insight_layout.addWidget(self.budget_overspent_count_card, 2, 0)
        insight_layout.addWidget(self.budget_under_budget_count_card, 2, 1)
        insight_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout.addWidget(insight_panel)

        # Goal savings input section
        goal_panel = QFrame()
        goal_panel.setObjectName("Panel")
        goal_layout = QGridLayout(goal_panel)
        goal_layout.setContentsMargins(18, 18, 18, 18)
        goal_layout.setSpacing(12)

        goal_label = QLabel("Set Monthly Savings Goal")
        goal_label.setObjectName("SectionTitle")
        self.savings_goal_input = QDoubleSpinBox()
        self.savings_goal_input.setMaximum(1_000_000)
        self.savings_goal_input.setDecimals(2)
        self.savings_goal_input.setPrefix("$")
        self.savings_goal_input.setSingleStep(100.0)
        self.savings_goal_input.valueChanged.connect(self._handle_savings_goal_changed)
        self.budget_goal_status_label = QLabel("Goal status: No goal set for this month.")
        self.budget_goal_status_label.setObjectName("PageSubtitle")
        self.budget_goal_status_label.setProperty("tone", "muted")

        goal_layout.addWidget(goal_label, 0, 0)
        goal_layout.addWidget(self.savings_goal_input, 0, 1)
        goal_layout.addWidget(self.budget_goal_status_label, 1, 0, 1, 3)
        goal_layout.setColumnStretch(2, 1)
        goal_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(goal_panel)

        # Budget allocation section
        budget_panel = QFrame()
        budget_panel.setObjectName("Panel")
        budget_layout = QVBoxLayout(budget_panel)
        budget_layout.setContentsMargins(18, 18, 18, 18)
        budget_layout.setSpacing(12)
        budget_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        budget_header = QLabel("Category Budget Breakdown")
        budget_header.setObjectName("SectionTitle")
        budget_layout.addWidget(budget_header)

        # Budget table
        self.budget_table = QTableWidget()
        self.budget_table.setColumnCount(6)
        self.budget_table.setHorizontalHeaderLabels(["Category", "Budgeted", "Actual Spent", "Remaining", "% Used", "Notes"])
        self.budget_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.budget_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.budget_table.setAlternatingRowColors(True)
        self.budget_table.horizontalHeader().setStretchLastSection(True)
        self.budget_table.setMinimumHeight(760)
        self.budget_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.budget_table.itemChanged.connect(self._handle_budget_table_item_changed)
        self.budget_table.cellDoubleClicked.connect(self._handle_budget_table_cell_double_clicked)
        budget_layout.addWidget(self.budget_table)

        # Controls
        button_row = QGridLayout()
        button_row.setHorizontalSpacing(12)
        button_row.setVerticalSpacing(12)
        self.budget_ai_suggest_button = QPushButton("AI Reallocate Next Month")
        self.budget_ai_suggest_button.clicked.connect(self._suggest_budget_with_ai)
        self.budget_save_button = QPushButton("Save Changes")
        self.budget_save_button.clicked.connect(self._save_budget)
        self.budget_delete_button = QPushButton("Delete Selected")
        self.budget_delete_button.clicked.connect(self._delete_budget_entry)
        self.budget_export_month_button = QPushButton("Export Month CSV")
        self.budget_export_month_button.clicked.connect(self._export_budget_month_csv)
        self.budget_import_month_button = QPushButton("Import Month CSV")
        self.budget_import_month_button.clicked.connect(self._import_budget_month_csv)
        self.budget_ai_history_button = QPushButton("AI Plan History")
        self.budget_ai_history_button.clicked.connect(self._open_reallocation_audit_history_dialog)

        button_row.addWidget(self.budget_ai_suggest_button, 0, 0)
        button_row.addWidget(self.budget_save_button, 0, 1)
        button_row.addWidget(self.budget_delete_button, 0, 2)
        button_row.addWidget(self.budget_export_month_button, 1, 0)
        button_row.addWidget(self.budget_import_month_button, 1, 1)
        button_row.addWidget(self.budget_ai_history_button, 1, 2)
        button_row.setColumnStretch(0, 1)
        button_row.setColumnStretch(1, 1)
        button_row.setColumnStretch(2, 1)
        budget_layout.addLayout(button_row)
        budget_layout.setStretch(1, 1)

        layout.addWidget(budget_panel, 1)

        # Add new budget category section
        add_panel = QFrame()
        add_panel.setObjectName("Panel")
        add_layout = QGridLayout(add_panel)
        add_layout.setContentsMargins(18, 18, 18, 18)
        add_layout.setSpacing(12)

        add_label = QLabel("Quick Add Category")
        add_label.setObjectName("SectionTitle")
        self.new_budget_category = QComboBox()
        self.new_budget_category.setEditable(False)
        self.new_budget_amount = QDoubleSpinBox()
        self.new_budget_amount.setMaximum(1_000_000)
        self.new_budget_amount.setDecimals(2)
        self.new_budget_amount.setPrefix("$")
        self.new_budget_notes = QLineEdit()
        self.new_budget_notes.setPlaceholderText("Optional notes")
        add_button = QPushButton("Add Category to Budget")
        add_button.clicked.connect(self._add_budget_entry)

        add_layout.addWidget(add_label, 0, 0, 1, 4)
        add_layout.addWidget(QLabel("Category:"), 1, 0)
        add_layout.addWidget(self.new_budget_category, 1, 1)
        add_layout.addWidget(QLabel("Amount:"), 1, 2)
        add_layout.addWidget(self.new_budget_amount, 1, 3)
        add_layout.addWidget(QLabel("Notes:"), 2, 0)
        add_layout.addWidget(self.new_budget_notes, 2, 1, 1, 2)
        add_layout.addWidget(add_button, 2, 3)
        add_layout.setColumnStretch(1, 1)
        add_layout.setColumnStretch(2, 0)
        add_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(add_panel)
        layout.setStretch(0, 0)
        layout.setStretch(1, 0)
        layout.setStretch(2, 1)
        layout.setStretch(3, 0)

        # Load the persisted goal for the selected budget period.
        self._load_savings_goal_for_selected_period()

    def _handle_budget_period_changed(self) -> None:
        """Update budget display when period changes."""
        self._load_savings_goal_for_selected_period()
        self.refresh_budget()
        month_name = calendar.month_name[int(self.budget_month_toggle.currentData())]
        year = int(self.budget_year_toggle.currentData())
        self.status_bar.showMessage(f"Viewing budget for {month_name} {year}.", 3000)

    def _handle_savings_goal_changed(self) -> None:
        """Update insights when savings goal changes."""
        if getattr(self, "_is_loading_budget_goal", False):
            return

        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())
        self.budget_controller.set_monthly_savings_goal(selected_year, selected_month, self.savings_goal_input.value())
        self.refresh_budget()

    def _load_savings_goal_for_selected_period(self) -> None:
        """Load persisted monthly savings goal into the UI for the selected period."""
        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())
        saved_goal = self.budget_controller.get_monthly_savings_goal(selected_year, selected_month, default=0.0)

        self._is_loading_budget_goal = True
        self.savings_goal_input.blockSignals(True)
        self.savings_goal_input.setValue(saved_goal)
        self.savings_goal_input.blockSignals(False)
        self._is_loading_budget_goal = False

    def refresh_budget(self) -> None:
        """Refresh the budget tab with current data and calculate insights."""
        if not hasattr(self, 'budget_table'):
            return

        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())
        savings_goal = self.savings_goal_input.value()
        month_view = self.budget_controller.build_budget_month_view(selected_year, selected_month, savings_goal)
        budgets = month_view.budgets

        # Update insight cards
        self._set_metric_value(self.budget_income_insight, month_view.total_income)
        self._set_metric_value(self.budget_total_spend_insight, month_view.total_expected_spend)
        self._set_metric_value(
            self.budget_net_on_target,
            month_view.break_even_left_to_spend,
            is_warning=month_view.break_even_left_to_spend < 0,
        )
        self._set_metric_value(self.budget_savings_goal_card, savings_goal)

        if month_view.expected_net < 0:
            # Show in red/warning color
            self._set_metric_value(self.budget_expected_net, month_view.expected_net, is_warning=True)
        else:
            self._set_metric_value(self.budget_expected_net, month_view.expected_net)

        # Remaining to spend in budget
        self._set_metric_value(
            self.budget_remaining_to_spend,
            month_view.remaining_to_spend,
            is_warning=month_view.remaining_to_spend < 0,
        )
        self.budget_overspent_count_card.set_value(
            str(month_view.overspent_count),
            is_warning=month_view.overspent_count > 0,
        )
        self.budget_under_budget_count_card.set_value(str(month_view.under_budget_count))
        self._update_budget_goal_status(selected_year, selected_month, savings_goal)

        # Populate budget table
        self._is_refreshing_budget_table = True
        self.budget_table.setRowCount(len(budgets))
        for row_index, budget in enumerate(budgets):
            remaining = budget.remaining
            pct_used = budget.budget_percentage

            # Color coding: red if over budget, yellow if > 80%, green otherwise
            color = "#111a27"  # default dark background
            if pct_used > 100:
                color = "#3d2a2a"  # dark red
            elif pct_used > 80:
                color = "#3d3a2a"  # dark yellow

            cells = [
                budget.category,
                f"${budget.budgeted_amount:,.2f}",
                f"${budget.actual_spent:,.2f}",
                f"${remaining:,.2f}",
                f"{pct_used:.1f}%",
                budget.notes,
            ]

            for column_index, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, budget.id)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if column_index == 1:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                if column_index > 0:  # Align numbers to right
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if column_index in [1, 2, 3, 4]:  # Color number columns
                    item.setBackground(QColor(color))
                self.budget_table.setItem(row_index, column_index, item)
        self._is_refreshing_budget_table = False

        # Update category dropdown for new entries
        self._refresh_budget_category_dropdown(selected_year, selected_month)

    def _handle_budget_table_cell_double_clicked(self, row: int, column: int) -> None:
        """Jump to ledger with month/category context when users inspect actual spend."""
        # Phase 1 drilldown targets the Actual Spent column.
        if column != 2:
            return

        category_item = self.budget_table.item(row, 0)
        if not category_item:
            return

        category = category_item.text().strip()
        if not category:
            return

        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())

        # Align global period controls with the budget period before opening ledger.
        self._selected_month = selected_month
        self._selected_year = selected_year
        self._sync_period_controls(self.budget_month_toggle, self.budget_year_toggle, self.month_toggle, self.year_toggle)
        self._sync_period_controls(self.budget_month_toggle, self.budget_year_toggle, self.charts_month_toggle, self.charts_year_toggle)

        self.refresh_dashboard()
        self.refresh_ledger_tables()
        self.refresh_charts()

        # Apply category filter in Ledger for drilldown context.
        self._set_ledger_category_filter(category)

        self.tabs.setCurrentWidget(self.ledger_tab)
        matches = self.full_ledger_table.rowCount()
        if matches > 0:
            self.full_ledger_table.selectRow(0)
            self.full_ledger_table.scrollToItem(self.full_ledger_table.item(0, 0))

        month_name = calendar.month_name[selected_month]
        self.status_bar.showMessage(
            f"Ledger drilldown: {category} in {month_name} {selected_year} ({matches} matching rows).",
            5000,
        )

    def _set_ledger_category_filter(self, category: str | None) -> None:
        """Set ledger category filter and refresh the table."""
        target_value = category.strip() if category else ""
        self.ledger_category_filter.blockSignals(True)

        if not target_value:
            index = self.ledger_category_filter.findData("")
            if index >= 0:
                self.ledger_category_filter.setCurrentIndex(index)
            self.ledger_category_filter.blockSignals(False)
            self.refresh_ledger_tables()
            return

        index = self.ledger_category_filter.findData(target_value)
        if index < 0:
            self.ledger_category_filter.addItem(target_value, target_value)
            index = self.ledger_category_filter.findData(target_value)

        self.ledger_category_filter.setCurrentIndex(index)
        self.ledger_category_filter.blockSignals(False)
        self.refresh_ledger_tables()

    def _clear_ledger_filters(self) -> None:
        """Clear ledger filters and show all rows for the selected month."""
        self._set_ledger_category_filter(None)

    def _refresh_ledger_category_filter_options(self, transactions: list[Transaction]) -> None:
        """Refresh filter options while preserving current selection where possible."""
        selected_value = self.ledger_category_filter.currentData() if self.ledger_category_filter.count() > 0 else ""
        categories = sorted({tx.category for tx in transactions if tx.category})

        self.ledger_category_filter.blockSignals(True)
        self.ledger_category_filter.clear()
        self.ledger_category_filter.addItem("All Categories", "")
        for category in categories:
            self.ledger_category_filter.addItem(category, category)

        index = self.ledger_category_filter.findData(selected_value)
        if index < 0:
            index = 0
        self.ledger_category_filter.setCurrentIndex(index)
        self.ledger_category_filter.blockSignals(False)

    def _update_budget_goal_status(self, year: int, month: int, savings_goal: float) -> None:
        """Update the goal pacing status for the selected month."""
        today = date.today()
        days_in_month = calendar.monthrange(year, month)[1]

        if year < today.year or (year == today.year and month < today.month):
            elapsed_days = days_in_month
        elif year == today.year and month == today.month:
            elapsed_days = today.day
        else:
            elapsed_days = 0

        snapshot = self.budget_controller.snapshot_for_month(year, month)
        actual_net = snapshot.net_total

        if savings_goal <= 0:
            self.budget_goal_status_label.setText("Goal status: No goal set for this month.")
            self._set_widget_tone(self.budget_goal_status_label, "muted")
            return

        if elapsed_days <= 0:
            self.budget_goal_status_label.setText(
                f"Goal status: Month has not started. Target savings is ${savings_goal:,.2f}."
            )
            self._set_widget_tone(self.budget_goal_status_label, "muted")
            return

        target_to_date = savings_goal * (elapsed_days / days_in_month)
        delta = actual_net - target_to_date

        if delta >= 0:
            self.budget_goal_status_label.setText(
                f"Goal status: On track by ${delta:,.2f} (saved ${actual_net:,.2f} vs ${target_to_date:,.2f} expected)."
            )
            self._set_widget_tone(self.budget_goal_status_label, "success")
        elif delta >= -(savings_goal * 0.1):
            self.budget_goal_status_label.setText(
                f"Goal status: Slightly behind by ${abs(delta):,.2f} (saved ${actual_net:,.2f} vs ${target_to_date:,.2f} expected)."
            )
            self._set_widget_tone(self.budget_goal_status_label, "warning")
        else:
            self.budget_goal_status_label.setText(
                f"Goal status: Behind by ${abs(delta):,.2f} (saved ${actual_net:,.2f} vs ${target_to_date:,.2f} expected)."
            )
            self._set_widget_tone(self.budget_goal_status_label, "danger")

    def _export_budget_month_csv(self) -> None:
        """Export current month budget rows to a CSV file."""
        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())
        default_name = f"budget_{selected_year}_{selected_month:02d}.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export budget month CSV",
            default_name,
            "CSV Files (*.csv)",
        )
        if not file_path:
            return

        rows = self.budget_controller.export_budget_rows_for_month(selected_year, selected_month)
        if not rows:
            QMessageBox.information(self, APP_NAME, "No budget entries for this month to export.")
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=["year", "month", "category", "kind", "budgeted_amount", "notes"],
                )
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)

            self.status_bar.showMessage(f"Exported budget month CSV to {file_path}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Budget CSV export failed: {exc}")

    def _import_budget_month_csv(self) -> None:
        """Import budget rows into the currently selected month from a CSV file."""
        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import budget month CSV",
            "",
            "CSV Files (*.csv)",
        )
        if not file_path:
            return

        reply = QMessageBox.question(
            self,
            APP_NAME,
            "Replace existing budgets for this month before importing?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.No,
        )
        if reply == QMessageBox.Cancel:
            return

        try:
            with open(file_path, "r", newline="", encoding="utf-8") as csv_file:
                reader = csv.DictReader(csv_file)
                rows = list(reader)

            imported_count, skipped_count = self.budget_controller.import_budget_rows_for_month(
                year=selected_year,
                month=selected_month,
                rows=rows,
                replace_existing=(reply == QMessageBox.Yes),
            )

            self.refresh_budget()
            self.status_bar.showMessage(
                f"Imported {imported_count} budget rows for {calendar.month_name[selected_month]} {selected_year}.",
                5000,
            )
            if skipped_count > 0:
                QMessageBox.information(
                    self,
                    APP_NAME,
                    f"Imported {imported_count} rows. Skipped {skipped_count} invalid rows.",
                )
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Budget CSV import failed: {exc}")

    def _handle_budget_table_item_changed(self, item: QTableWidgetItem) -> None:
        """Persist inline budget amount edits and refresh dependent insights."""
        if getattr(self, "_is_refreshing_budget_table", False):
            return

        # Only the Budgeted column is editable.
        if item.column() != 1:
            return

        row = item.row()
        category_item = self.budget_table.item(row, 0)
        notes_item = self.budget_table.item(row, 5)
        if not category_item:
            return

        raw_text = item.text().strip().replace("$", "").replace(",", "")
        try:
            amount = float(raw_text)
        except ValueError:
            QMessageBox.warning(self, APP_NAME, "Please enter a valid numeric amount.")
            self.refresh_budget()
            return

        if amount <= 0:
            QMessageBox.warning(self, APP_NAME, "Budget amount must be greater than zero.")
            self.refresh_budget()
            return

        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())
        category = category_item.text().strip()
        notes = notes_item.text().strip() if notes_item else ""

        self.budget_controller.add_or_update_budget(
            year=selected_year,
            month=selected_month,
            category=category,
            kind="expense",
            budgeted_amount=amount,
            notes=notes,
        )

        self.status_bar.showMessage(f"Updated budget amount for {category}.", 2500)
        self.refresh_budget()

    def _refresh_budget_category_dropdown(self, year: int, month: int) -> None:
        """Populate the category dropdown with unbudgeted expense categories."""
        self.new_budget_category.blockSignals(True)
        self.new_budget_category.clear()

        # Get all expense categories
        all_categories = self.budget_controller.list_expense_categories()

        # Get already-budgeted categories
        existing_budgets = self.budget_controller.list_budgets_for_month(year, month, kind="expense")
        budgeted_categories = {b.category for b in existing_budgets}

        # Add categories that aren't already budgeted
        for category in all_categories:
            if category.name not in budgeted_categories:
                self.new_budget_category.addItem(category.name, category.name)

        self.new_budget_category.blockSignals(False)

    def _add_budget_entry(self) -> None:
        """Add a new budget entry."""
        category = self.new_budget_category.currentText().strip()
        amount = self.new_budget_amount.value()
        notes = self.new_budget_notes.text().strip()

        if not category:
            QMessageBox.warning(self, APP_NAME, "Please select a category.")
            return

        if amount <= 0:
            QMessageBox.warning(self, APP_NAME, "Enter a budget amount greater than zero.")
            return

        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())

        self.budget_controller.add_or_update_budget(
            year=selected_year,
            month=selected_month,
            category=category,
            kind="expense",
            budgeted_amount=amount,
            notes=notes,
        )

        self.status_bar.showMessage(f"Added budget for {category}.", 3000)
        self.new_budget_amount.setValue(0.0)
        self.new_budget_notes.clear()
        self.refresh_budget()

    def _save_budget(self) -> None:
        """Save all edits to budget entries."""
        reply = QMessageBox.information(
            self, APP_NAME, "Save all budget changes?", QMessageBox.Ok | QMessageBox.Cancel
        )
        if reply != QMessageBox.Ok:
            return

        for row in range(self.budget_table.rowCount()):
            budget_id_item = self.budget_table.item(row, 0)
            budget_id = budget_id_item.data(Qt.UserRole)

            # In this version, we save on-add. This button is for confirmation.
            # Could be extended to allow editable cells in the future.

        self.status_bar.showMessage("Budget saved.", 3000)

    def _delete_budget_entry(self) -> None:
        """Delete selected budget entry."""
        current_row = self.budget_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, APP_NAME, "Select a budget entry to delete.")
            return

        item = self.budget_table.item(current_row, 0)
        budget_id = item.data(Qt.UserRole)
        category_name = item.text()

        reply = QMessageBox.question(
            self, APP_NAME, f"Delete budget for {category_name}?", QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.budget_controller.delete_budget(budget_id)
            self.status_bar.showMessage(f"Deleted budget for {category_name}.", 3000)
            self.refresh_budget()

    def _suggest_budget_with_ai(self) -> None:
        """Generate and optionally apply AI reallocation for next month."""
        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())

        self.budget_ai_suggest_button.setEnabled(False)
        self.budget_ai_suggest_button.setText("Generating reallocation...")

        try:
            plan = self.assistant_service.generate_next_month_reallocation(
                reference_year=selected_year,
                reference_month=selected_month,
                min_history_months=3,
            )

            if plan.get("status") == "insufficient_history":
                self._show_insufficient_history_state(plan)
                return

            recommendations = plan.get("recommendations", [])
            if not isinstance(recommendations, list) or len(recommendations) == 0:
                QMessageBox.information(self, APP_NAME, "No reallocation changes were recommended for next month.")
                return

            selected_map = self._open_reallocation_review_dialog(plan)
            if not selected_map:
                self.status_bar.showMessage("AI reallocation preview generated. No changes applied.", 3500)
                return

            self._apply_selected_reallocation_rows(plan, selected_map)

        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Error generating suggestions: {str(e)}")
        finally:
            self.budget_ai_suggest_button.setEnabled(True)
            self.budget_ai_suggest_button.setText("AI Reallocate Next Month")

    def _show_insufficient_history_state(self, plan: dict) -> None:
        min_history = int(plan.get("min_history_months", 3) or 3)
        available = int(plan.get("history_available_months", 0) or 0)
        message = str(plan.get("insufficient_history_message", "")).strip()
        details = (
            f"Not enough history for AI reallocation.\n\n"
            f"Required: {min_history} full months\n"
            f"Available: {available} months"
        )
        if message:
            details = f"{details}\n\n{message}"
        QMessageBox.information(self, APP_NAME, details)

    def _open_reallocation_review_dialog(self, plan: dict) -> dict[str, float]:
        """Show review table and return selected category amounts to apply."""
        recommendations = plan.get("recommendations", [])
        if not isinstance(recommendations, list) or not recommendations:
            return {}

        target_year = int(plan.get("target_year", 0) or 0)
        target_month = int(plan.get("target_month", 1) or 1)
        target_total = float(plan.get("discretionary_target_budget", 0.0) or 0.0)
        goal_message = str(plan.get("goal_message", "")).strip()

        dialog = QDialog(self)
        dialog.setWindowTitle("AI Reallocation Review")
        dialog.setMinimumSize(760, 480)
        dialog.resize(980, 560)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel(f"Review AI Reallocation for {calendar.month_name[target_month]} {target_year}")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        summary = QLabel(f"Target discretionary total: ${target_total:,.2f}")
        summary.setObjectName("PageSubtitle")
        layout.addWidget(summary)

        if goal_message:
            goal = QLabel(f"Goal: {goal_message}")
            goal.setObjectName("PageSubtitle")
            goal.setWordWrap(True)
            layout.addWidget(goal)

        table = QTableWidget(len(recommendations), 7)
        table.setHorizontalHeaderLabels(["Apply", "Category", "Current", "Recommended", "Change %", "Confidence", "Reason"])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)

        for row_index, row in enumerate(recommendations):
            category = str(row.get("category", "")).strip()
            old_amount = float(row.get("old_amount", 0.0) or 0.0)
            new_amount = float(row.get("new_amount", 0.0) or 0.0)
            change_pct = float(row.get("change_percent", 0.0) or 0.0)
            confidence = float(row.get("confidence", 0.0) or 0.0)
            explanation = str(row.get("explanation", "")).strip()

            apply_item = QTableWidgetItem("")
            apply_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            apply_item.setCheckState(Qt.Checked)
            apply_item.setData(Qt.UserRole, (category, new_amount))
            table.setItem(row_index, 0, apply_item)

            cells = [
                category,
                f"${old_amount:,.2f}",
                f"${new_amount:,.2f}",
                f"{change_pct:+.1f}%",
                f"{confidence:.2f}",
                explanation,
            ]
            for column_offset, text in enumerate(cells, start=1):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if column_offset in (2, 3, 4, 5):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(row_index, column_offset, item)

        layout.addWidget(table, 1)

        button_row = QHBoxLayout()
        select_all = QPushButton("Select All")
        clear_all = QPushButton("Clear All")
        apply_selected = QPushButton("Apply Selected")
        cancel = QPushButton("Cancel")
        button_row.addWidget(select_all)
        button_row.addWidget(clear_all)
        button_row.addStretch(1)
        button_row.addWidget(apply_selected)
        button_row.addWidget(cancel)
        layout.addLayout(button_row)

        def _set_all_checks(checked: bool) -> None:
            state = Qt.Checked if checked else Qt.Unchecked
            for row_index in range(table.rowCount()):
                item = table.item(row_index, 0)
                if item:
                    item.setCheckState(state)

        select_all.clicked.connect(lambda: _set_all_checks(True))
        clear_all.clicked.connect(lambda: _set_all_checks(False))
        apply_selected.clicked.connect(dialog.accept)
        cancel.clicked.connect(dialog.reject)

        if dialog.exec_() != QDialog.Accepted:
            return {}

        selected_map: dict[str, float] = {}
        for row_index in range(table.rowCount()):
            apply_item = table.item(row_index, 0)
            if not apply_item or apply_item.checkState() != Qt.Checked:
                continue
            data = apply_item.data(Qt.UserRole)
            if not data or len(data) != 2:
                continue
            category, amount = data
            category_text = str(category).strip()
            numeric_amount = float(amount)
            if category_text and numeric_amount > 0:
                selected_map[category_text] = numeric_amount

        if not selected_map:
            QMessageBox.information(self, APP_NAME, "No rows selected to apply.")
        return selected_map

    def _apply_selected_reallocation_rows(self, plan: dict, selected_map: dict[str, float]) -> None:
        """Apply selected recommendation rows to target month budgets."""
        target_year = int(plan.get("target_year", 0) or 0)
        target_month = int(plan.get("target_month", 0) or 0)
        if target_year <= 0 or target_month < 1 or target_month > 12:
            QMessageBox.warning(self, APP_NAME, "Invalid target month returned by AI reallocation.")
            return

        saved_ids = self.assistant_service.apply_reallocation_plan(
            target_year=target_year,
            target_month=target_month,
            category_amounts=selected_map,
        )

        self.status_bar.showMessage(
            f"Applied AI reallocation: {len(saved_ids)} categories updated for {calendar.month_name[target_month]} {target_year}.",
            5000,
        )

        selected_year = int(self.budget_year_toggle.currentData())
        selected_month = int(self.budget_month_toggle.currentData())
        if target_year == selected_year and target_month == selected_month:
            self.refresh_budget()

    def _open_reallocation_audit_history_dialog(self) -> None:
        """Display saved AI reallocation plans with filters, export, and rich detail view."""
        audits = self.budget_controller.list_budget_reallocation_audits(limit=100)
        if not audits:
            QMessageBox.information(self, APP_NAME, "No AI reallocation history found yet.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("AI Reallocation History")
        dialog.setMinimumSize(860, 540)
        dialog.resize(1180, 680)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Saved AI Reallocation Plans")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        # Filter row
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter by Status:"))
        status_filter = QComboBox()
        status_filter.addItems(["All", "ready", "insufficient_history", "infeasible"])
        filter_layout.addWidget(status_filter)

        filter_layout.addWidget(QLabel("Target Month:"))
        month_filter = QComboBox()
        month_filter.addItem("All")
        for month_index in range(1, 13):
            month_filter.addItem(calendar.month_name[month_index], month_index)
        filter_layout.addWidget(month_filter)
        filter_layout.addStretch(1)
        layout.addLayout(filter_layout)

        table = QTableWidget()
        table.setHorizontalHeaderLabels(["Created", "Reference", "Target", "Status", "Changes", "Goal", "Audit ID"])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)

        def _populate_table(audits_to_show: list[dict]) -> None:
            table.setRowCount(0)
            for row_index, audit in enumerate(audits_to_show):
                table.insertRow(row_index)
                payload = audit.get("payload", {}) if isinstance(audit.get("payload"), dict) else {}
                recs = payload.get("recommendations", []) if isinstance(payload.get("recommendations"), list) else []
                goal_message = str(payload.get("goal_message", "")).strip()

                created = str(audit.get("created_at", ""))
                reference_label = f"{calendar.month_name[int(audit.get('reference_month', 1))]} {int(audit.get('reference_year', 0))}"
                target_label = f"{calendar.month_name[int(audit.get('target_month', 1))]} {int(audit.get('target_year', 0))}"

                row_values = [
                    created,
                    reference_label,
                    target_label,
                    str(audit.get("status", "")),
                    str(len(recs)),
                    goal_message,
                    str(audit.get("id", "")),
                ]

                for column_index, value in enumerate(row_values):
                    item = QTableWidgetItem(value)
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    if column_index == 0:
                        item.setData(Qt.UserRole, (payload, audit))
                    table.setItem(row_index, column_index, item)

        _populate_table(audits)

        def _apply_filters() -> None:
            status_val = status_filter.currentText()
            month_val = month_filter.currentData()
            filtered = [
                audit for audit in audits
                if (status_val == "All" or audit.get("status") == status_val)
                and (month_val is None or audit.get("target_month") == month_val)
            ]
            _populate_table(filtered)

        status_filter.currentTextChanged.connect(_apply_filters)
        month_filter.currentIndexChanged.connect(_apply_filters)

        layout.addWidget(table, 1)

        button_row = QHBoxLayout()
        view_details = QPushButton("View Details")
        reapply_plan = QPushButton("Apply Plan Again")
        rollback_plan = QPushButton("Rollback Using Old Amounts")
        export_button = QPushButton("Export Audit")
        close_button = QPushButton("Close")
        button_row.addWidget(view_details)
        button_row.addWidget(reapply_plan)
        button_row.addWidget(rollback_plan)
        button_row.addWidget(export_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        def _selected_data() -> tuple[dict, dict] | tuple[dict, dict]:
            current_row = table.currentRow()
            if current_row < 0:
                return {}, {}
            cell = table.item(current_row, 0)
            data = cell.data(Qt.UserRole) if cell else None
            if isinstance(data, tuple) and len(data) == 2:
                return data
            return {}, {}

        def _view_details() -> None:
            payload, audit_row = _selected_data()
            if not payload:
                QMessageBox.information(self, APP_NAME, "Select an audit row first.")
                return

            recommendations = payload.get("recommendations", [])
            if not isinstance(recommendations, list):
                recommendations = []

            detail_dialog = QDialog(self)
            detail_dialog.setWindowTitle("AI Reallocation Details")
            detail_dialog.setMinimumSize(760, 460)
            detail_dialog.resize(1000, 560)

            detail_layout = QVBoxLayout(detail_dialog)
            detail_layout.setContentsMargins(12, 12, 12, 12)
            detail_layout.setSpacing(8)

            header = QLabel(f"Audit ID {audit_row.get('id', 'N/A')} | Status: {payload.get('status', 'unknown')}")
            header.setObjectName("SectionTitle")
            detail_layout.addWidget(header)

            goal_text = str(payload.get("goal_message", "")).strip()
            if goal_text:
                goal_label = QLabel(f"Goal: {goal_text}")
                goal_label.setWordWrap(True)
                detail_layout.addWidget(goal_label)

            detail_table = QTableWidget(len(recommendations), 6)
            detail_table.setHorizontalHeaderLabels(["Category", "Current→Recommended", "Change %", "Confidence", "Reason Tags", "Explanation"])
            detail_table.verticalHeader().setVisible(False)
            detail_table.setAlternatingRowColors(True)
            detail_table.horizontalHeader().setStretchLastSection(True)

            for rec_idx, row in enumerate(recommendations):
                category = str(row.get("category", "")).strip()
                old_amount = float(row.get("old_amount", 0.0) or 0.0)
                new_amount = float(row.get("new_amount", 0.0) or 0.0)
                change_pct = float(row.get("change_percent", 0.0) or 0.0)
                confidence = float(row.get("confidence", 0.0) or 0.0)
                reason_tags = row.get("reason_tags", [])
                explanation = str(row.get("explanation", "")).strip()

                cells = [
                    category,
                    f"${old_amount:,.2f} → ${new_amount:,.2f}",
                    f"{change_pct:+.1f}%",
                    f"{confidence:.3f}",
                    ", ".join(reason_tags) if isinstance(reason_tags, list) else str(reason_tags),
                    explanation,
                ]

                for col_idx, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    if col_idx in (1, 2, 3):
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    detail_table.setItem(rec_idx, col_idx, item)

            detail_layout.addWidget(detail_table, 1)
            detail_dialog.exec_()

        def _export_audit() -> None:
            payload, audit_row = _selected_data()
            if not payload:
                QMessageBox.information(self, APP_NAME, "Select an audit row first.")
                return

            target_year = int(payload.get("target_year", 0) or 0)
            target_month = int(payload.get("target_month", 1) or 1)
            default_name = f"audit_reallocation_{target_year}_{target_month:02d}.json"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Audit to JSON",
                default_name,
                "JSON Files (*.json)",
            )
            if not file_path:
                return

            try:
                import json
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                self.status_bar.showMessage(f"Audit exported to {file_path}", 4000)
            except Exception as e:
                QMessageBox.critical(self, APP_NAME, f"Export failed: {str(e)}")

        def _reapply() -> None:
            payload, audit_row = _selected_data()
            if not payload:
                QMessageBox.information(self, APP_NAME, "Select an audit row first.")
                return

            selected_map = self._open_reallocation_review_dialog(payload)
            if not selected_map:
                return
            self._apply_selected_reallocation_rows(payload, selected_map)

        def _rollback() -> None:
            payload, audit_row = _selected_data()
            if not payload:
                QMessageBox.information(self, APP_NAME, "Select an audit row first.")
                return

            target_year = int(payload.get("target_year", 0) or 0)
            target_month = int(payload.get("target_month", 0) or 0)
            if target_year <= 0 or target_month < 1 or target_month > 12:
                QMessageBox.warning(self, APP_NAME, "Selected audit payload has invalid target month.")
                return

            recommendations = payload.get("recommendations", [])
            if not isinstance(recommendations, list) or not recommendations:
                QMessageBox.information(self, APP_NAME, "No recommendation rows available for rollback.")
                return

            rollback_map: dict[str, float] = {}
            for row in recommendations:
                category = str(row.get("category", "")).strip()
                old_amount = float(row.get("old_amount", 0.0) or 0.0)
                if category and old_amount > 0:
                    rollback_map[category] = old_amount

            if not rollback_map:
                QMessageBox.information(self, APP_NAME, "No positive old amounts found to rollback.")
                return

            saved_ids = self.assistant_service.apply_reallocation_plan(
                target_year=target_year,
                target_month=target_month,
                category_amounts=rollback_map,
                note_prefix="AI-rollback",
            )
            self.status_bar.showMessage(
                f"Rollback applied: {len(saved_ids)} categories restored for {calendar.month_name[target_month]} {target_year}.",
                5000,
            )

            selected_year = int(self.budget_year_toggle.currentData())
            selected_month = int(self.budget_month_toggle.currentData())
            if target_year == selected_year and target_month == selected_month:
                self.refresh_budget()

        view_details.clicked.connect(_view_details)
        reapply_plan.clicked.connect(_reapply)
        rollback_plan.clicked.connect(_rollback)
        export_button.clicked.connect(_export_audit)
        close_button.clicked.connect(dialog.accept)

        dialog.exec_()

    def _open_category_manager(self) -> None:
        """Open the category management dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Categories")
        dialog.setMinimumSize(520, 360)
        dialog.resize(680, 460)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Title
        title = QLabel("Manage Categories")
        title_font = title.font()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Two-column layout for expense and income categories
        columns_layout = QHBoxLayout()

        # EXPENSE CATEGORIES COLUMN
        expense_layout = QVBoxLayout()
        expense_label = QLabel("Expense Categories")
        expense_label_font = expense_label.font()
        expense_label_font.setBold(True)
        expense_label.setFont(expense_label_font)
        expense_layout.addWidget(expense_label)

        self.category_mgr_expense_list = QListWidget()
        self.category_mgr_expense_list.setSelectionMode(QAbstractItemView.SingleSelection)
        expense_categories = self.category_controller.list_categories(kind="expense")
        for cat in sorted(expense_categories, key=lambda c: c.name):
            self.category_mgr_expense_list.addItem(cat.name)
        expense_layout.addWidget(self.category_mgr_expense_list, 1)

        # Add expense category
        expense_add_layout = QHBoxLayout()
        self.category_mgr_expense_input = QLineEdit()
        self.category_mgr_expense_input.setPlaceholderText("New expense category")
        self.category_mgr_expense_add_btn = QPushButton("Add")
        self.category_mgr_expense_add_btn.clicked.connect(
            lambda: self._add_category_from_dialog("expense", self.category_mgr_expense_input, self.category_mgr_expense_list)
        )
        expense_add_layout.addWidget(self.category_mgr_expense_input, 1)
        expense_add_layout.addWidget(self.category_mgr_expense_add_btn)
        expense_layout.addLayout(expense_add_layout)

        # Delete expense category
        self.category_mgr_expense_delete_btn = QPushButton("Delete Selected")
        self.category_mgr_expense_delete_btn.clicked.connect(
            lambda: self._delete_category_from_dialog("expense", self.category_mgr_expense_list)
        )
        expense_layout.addWidget(self.category_mgr_expense_delete_btn)

        columns_layout.addLayout(expense_layout, 1)

        # INCOME CATEGORIES COLUMN
        income_layout = QVBoxLayout()
        income_label = QLabel("Income Categories")
        income_label_font = income_label.font()
        income_label_font.setBold(True)
        income_label.setFont(income_label_font)
        income_layout.addWidget(income_label)

        self.category_mgr_income_list = QListWidget()
        self.category_mgr_income_list.setSelectionMode(QAbstractItemView.SingleSelection)
        income_categories = self.category_controller.list_categories(kind="income")
        for cat in sorted(income_categories, key=lambda c: c.name):
            self.category_mgr_income_list.addItem(cat.name)
        income_layout.addWidget(self.category_mgr_income_list, 1)

        # Add income category
        income_add_layout = QHBoxLayout()
        self.category_mgr_income_input = QLineEdit()
        self.category_mgr_income_input.setPlaceholderText("New income category")
        self.category_mgr_income_add_btn = QPushButton("Add")
        self.category_mgr_income_add_btn.clicked.connect(
            lambda: self._add_category_from_dialog("income", self.category_mgr_income_input, self.category_mgr_income_list)
        )
        income_add_layout.addWidget(self.category_mgr_income_input, 1)
        income_add_layout.addWidget(self.category_mgr_income_add_btn)
        income_layout.addLayout(income_add_layout)

        # Delete income category
        self.category_mgr_income_delete_btn = QPushButton("Delete Selected")
        self.category_mgr_income_delete_btn.clicked.connect(
            lambda: self._delete_category_from_dialog("income", self.category_mgr_income_list)
        )
        income_layout.addWidget(self.category_mgr_income_delete_btn)

        columns_layout.addLayout(income_layout, 1)

        layout.addLayout(columns_layout, 1)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec_()

    def _add_category_from_dialog(self, kind: str, input_field: QLineEdit, list_widget: QListWidget) -> None:
        """Add a category from the category manager dialog."""
        category_name = input_field.text().strip()

        if not category_name:
            QMessageBox.warning(self, APP_NAME, "Enter a category name.")
            return

        # Check if category already exists
        if self.category_controller.category_exists(kind=kind, category_name=category_name):
            QMessageBox.warning(self, APP_NAME, f"Category '{category_name}' already exists.")
            return

        # Add the category
        self.category_controller.ensure_category(category_name, kind)
        list_widget.addItem(category_name)
        list_widget.sortItems()
        input_field.clear()

        # Refresh all dropdowns
        self.refresh_category_controls()
        self.refresh_recurring_category_controls()
        if hasattr(self, 'budget_month_toggle'):
            self.refresh_budget()

        self.status_bar.showMessage(f"Added category: {category_name}", 3000)

    def _delete_category_from_dialog(self, kind: str, list_widget: QListWidget) -> None:
        """Delete a category from the category manager dialog."""
        current_item = list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, APP_NAME, "Select a category to delete.")
            return

        category_name = current_item.text()
        reply = QMessageBox.question(
            self,
            APP_NAME,
            f"Delete category '{category_name}'?\n\nTransactions using this category will remain.",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            success = self.category_controller.delete_category(category_name, kind)
            if success:
                list_widget.takeItem(list_widget.row(current_item))
                self.status_bar.showMessage(f"Deleted category: {category_name}", 3000)

                # Refresh all dropdowns
                self.refresh_category_controls()
                self.refresh_recurring_category_controls()
                if hasattr(self, 'budget_month_toggle'):
                    self.refresh_budget()
            else:
                QMessageBox.critical(self, APP_NAME, "Failed to delete category.")

    def _build_assets_tab(self) -> None:
        layout = QVBoxLayout(self.assets_tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        title = QLabel("Asset Portfolio")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Manage houses and investments with linked expenses and asset-level performance.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Keep top summary group unchanged.
        overview_panel = QFrame()
        overview_panel.setObjectName("Panel")
        overview_layout = QGridLayout(overview_panel)
        overview_layout.setContentsMargins(18, 18, 18, 18)
        overview_layout.setSpacing(16)
        self.assets_total_net_worth_card = MetricCard("Overall Net Worth", "$0.00")
        self.assets_total_value_card = MetricCard("Total Asset Value", "$0.00")
        self.assets_total_debt_card = MetricCard("Total Principal", "$0.00")
        self.assets_total_invested_card = MetricCard("Total Contributed", "$0.00")
        overview_layout.addWidget(self.assets_total_net_worth_card, 0, 0)
        overview_layout.addWidget(self.assets_total_value_card, 0, 1)
        overview_layout.addWidget(self.assets_total_debt_card, 1, 0)
        overview_layout.addWidget(self.assets_total_invested_card, 1, 1)
        layout.addWidget(overview_panel)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        layout.addWidget(scroll_area, 1)

        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(14)

        selector_panel = QFrame()
        selector_panel.setObjectName("Panel")
        selector_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        selector_layout = QHBoxLayout(selector_panel)
        selector_layout.setContentsMargins(18, 18, 18, 18)
        selector_layout.setSpacing(12)
        selector_layout.addWidget(QLabel("Owned Asset"))
        self.asset_selector_combo = QComboBox()
        self.asset_selector_combo.currentIndexChanged.connect(self._handle_asset_selection_changed)
        selector_layout.addWidget(self.asset_selector_combo, 1)
        self.asset_add_new_button = QPushButton("Add New Asset")
        self.asset_add_new_button.clicked.connect(self._add_new_asset_dialog)
        selector_layout.addWidget(self.asset_add_new_button)
        scroll_layout.addWidget(selector_panel)

        self.asset_detail_panel = QFrame()
        self.asset_detail_panel.setObjectName("Panel")
        self.asset_detail_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        detail_layout = QVBoxLayout(self.asset_detail_panel)
        detail_layout.setContentsMargins(18, 18, 18, 18)
        detail_layout.setSpacing(14)
        self.asset_name_label = QLabel("No asset selected")
        self.asset_name_label.setObjectName("SectionTitle")
        detail_layout.addWidget(self.asset_name_label)

        # House inputs.
        self.house_panel = QFrame()
        house_layout = QVBoxLayout(self.house_panel)
        house_layout.setContentsMargins(0, 0, 0, 0)
        house_layout.setSpacing(10)
        self.house_tracking_hint = QLabel(
            "Add mortgage payments in Expenses or Recurring, then set Link To Asset and Apply As to auto-track principal and interest."
        )
        self.house_tracking_hint.setObjectName("PageSubtitle")
        self.house_tracking_hint.setWordWrap(True)
        house_layout.addWidget(self.house_tracking_hint)
        self.house_warning_label = QLabel("")
        self.house_warning_label.setObjectName("PageSubtitle")
        self.house_warning_label.setProperty("tone", "warning")
        self.house_warning_label.setWordWrap(True)
        self.house_warning_label.setVisible(False)
        house_layout.addWidget(self.house_warning_label)
        house_grid = QGridLayout()
        self.house_value_input = QDoubleSpinBox(); self.house_value_input.setMaximum(1_000_000_000); self.house_value_input.setDecimals(2); self.house_value_input.setPrefix("$")
        self.house_principal_input = QDoubleSpinBox(); self.house_principal_input.setMaximum(1_000_000_000); self.house_principal_input.setDecimals(2); self.house_principal_input.setPrefix("$")
        self.house_rate_input = QDoubleSpinBox(); self.house_rate_input.setMaximum(1000); self.house_rate_input.setDecimals(3); self.house_rate_input.setSuffix("%")
        self.house_term_years_input = QDoubleSpinBox(); self.house_term_years_input.setMaximum(100); self.house_term_years_input.setDecimals(2); self.house_term_years_input.setValue(30)
        self.house_loan_start_input = QDateEdit(); self.house_loan_start_input.setCalendarPopup(True); self.house_loan_start_input.setDate(QDate.currentDate())
        self.house_escrow_input = QDoubleSpinBox(); self.house_escrow_input.setMaximum(1_000_000_000); self.house_escrow_input.setDecimals(2); self.house_escrow_input.setPrefix("$")
        self.house_base_total_paid_input = QDoubleSpinBox(); self.house_base_total_paid_input.setMaximum(1_000_000_000); self.house_base_total_paid_input.setDecimals(2); self.house_base_total_paid_input.setPrefix("$")
        self.house_base_interest_paid_input = QDoubleSpinBox(); self.house_base_interest_paid_input.setMaximum(1_000_000_000); self.house_base_interest_paid_input.setDecimals(2); self.house_base_interest_paid_input.setPrefix("$")
        self.house_base_principal_paid_input = QDoubleSpinBox(); self.house_base_principal_paid_input.setMaximum(1_000_000_000); self.house_base_principal_paid_input.setDecimals(2); self.house_base_principal_paid_input.setPrefix("$")
        house_grid.addWidget(QLabel("House Value"), 0, 0); house_grid.addWidget(self.house_value_input, 0, 1)
        house_grid.addWidget(QLabel("Current Principal"), 0, 2); house_grid.addWidget(self.house_principal_input, 0, 3)
        house_grid.addWidget(QLabel("Interest Rate"), 1, 0); house_grid.addWidget(self.house_rate_input, 1, 1)
        house_grid.addWidget(QLabel("Total Mortgage Years"), 1, 2); house_grid.addWidget(self.house_term_years_input, 1, 3)
        house_grid.addWidget(QLabel("Loan Start"), 2, 0); house_grid.addWidget(self.house_loan_start_input, 2, 1)
        house_grid.addWidget(QLabel("Escrow Amount"), 2, 2); house_grid.addWidget(self.house_escrow_input, 2, 3)
        house_grid.addWidget(QLabel("Base Total Paid"), 3, 0); house_grid.addWidget(self.house_base_total_paid_input, 3, 1)
        house_grid.addWidget(QLabel("Base Interest Paid"), 3, 2); house_grid.addWidget(self.house_base_interest_paid_input, 3, 3)
        house_grid.addWidget(QLabel("Base Principal Paid"), 4, 0); house_grid.addWidget(self.house_base_principal_paid_input, 4, 1)
        house_layout.addLayout(house_grid)
        for _w in [self.house_value_input, self.house_principal_input, self.house_rate_input,
                   self.house_term_years_input, self.house_loan_start_input, self.house_escrow_input,
                   self.house_base_total_paid_input, self.house_base_interest_paid_input,
                   self.house_base_principal_paid_input]:
            _w.setEnabled(False)

        house_metrics = QGridLayout()
        self.house_total_paid_card = MetricCard("Total Paid", "$0.00")
        self.house_total_principal_paid_card = MetricCard("Total Principal Paid", "$0.00")
        self.house_total_interest_paid_card = MetricCard("Total Interest Paid", "$0.00")
        self.house_total_escrow_paid_card = MetricCard("Total Escrow Paid", "$0.00")
        self.house_total_housing_cost_card = MetricCard("Total Housing Cost", "$0.00")
        self.house_years_elapsed_card = MetricCard("Mortgage Years (Elapsed)", "0.00")
        self.house_years_left_card = MetricCard("Years Left", "0.00")
        self.house_asset_net_worth_card = MetricCard("Asset Net Worth", "$0.00")
        house_metrics.addWidget(self.house_total_paid_card, 0, 0)
        house_metrics.addWidget(self.house_total_principal_paid_card, 0, 1)
        house_metrics.addWidget(self.house_total_interest_paid_card, 0, 2)
        house_metrics.addWidget(self.house_total_escrow_paid_card, 1, 0)
        house_metrics.addWidget(self.house_total_housing_cost_card, 1, 1)
        house_metrics.addWidget(self.house_asset_net_worth_card, 1, 2)
        house_metrics.addWidget(self.house_years_elapsed_card, 2, 0)
        house_metrics.addWidget(self.house_years_left_card, 2, 1)
        house_layout.addLayout(house_metrics)

        self.house_payment_breakdown_table = QTableWidget(0, 10)
        self.house_payment_breakdown_table.setHorizontalHeaderLabels(
            [
                "Date",
                "Source",
                "Payment Type",
                "Gross Payment",
                "Escrow",
                "Mortgage Net",
                "Interest",
                "Principal",
                "Running Principal",
                "Running Total Paid",
            ]
        )
        self.house_payment_breakdown_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.house_payment_breakdown_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.house_payment_breakdown_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.house_payment_breakdown_table.horizontalHeader().setStretchLastSection(True)
        house_layout.addWidget(self.house_payment_breakdown_table)

        self.asset_house_chart_figure = Figure(figsize=(8, 3.2))
        self.asset_house_chart_canvas = FigureCanvas(self.asset_house_chart_figure)
        house_layout.addWidget(self.asset_house_chart_canvas)
        detail_layout.addWidget(self.house_panel)

        # Investment inputs.
        self.investment_panel = QFrame()
        investment_layout = QVBoxLayout(self.investment_panel)
        investment_layout.setContentsMargins(0, 0, 0, 0)
        investment_layout.setSpacing(10)
        invest_grid = QGridLayout()
        self.investment_worth_input = QDoubleSpinBox(); self.investment_worth_input.setMaximum(1_000_000_000); self.investment_worth_input.setDecimals(2); self.investment_worth_input.setPrefix("$")
        self.investment_base_invested_input = QDoubleSpinBox(); self.investment_base_invested_input.setMaximum(1_000_000_000); self.investment_base_invested_input.setDecimals(2); self.investment_base_invested_input.setPrefix("$")
        invest_grid.addWidget(QLabel("Investment Worth"), 0, 0)
        invest_grid.addWidget(self.investment_worth_input, 0, 1)
        invest_grid.addWidget(QLabel("Total Invested (Manual Base)"), 0, 2)
        invest_grid.addWidget(self.investment_base_invested_input, 0, 3)
        investment_layout.addLayout(invest_grid)

        valuation_row = QGridLayout()
        self.investment_valuation_date = QDateEdit(); self.investment_valuation_date.setCalendarPopup(True); self.investment_valuation_date.setDate(QDate.currentDate())
        self.investment_valuation_value = QDoubleSpinBox(); self.investment_valuation_value.setMaximum(1_000_000_000); self.investment_valuation_value.setDecimals(2); self.investment_valuation_value.setPrefix("$")
        self.investment_valuation_notes = QLineEdit(); self.investment_valuation_notes.setPlaceholderText("Optional: month-end balance")
        self.investment_record_value_button = QPushButton("Record Value Snapshot")
        self.investment_record_value_button.clicked.connect(self._record_investment_value_snapshot)
        valuation_row.addWidget(QLabel("Valuation Date"), 0, 0)
        valuation_row.addWidget(self.investment_valuation_date, 0, 1)
        valuation_row.addWidget(QLabel("Hard Set Current Value"), 0, 2)
        valuation_row.addWidget(self.investment_valuation_value, 0, 3)
        valuation_row.addWidget(self.investment_valuation_notes, 1, 0, 1, 3)
        valuation_row.addWidget(self.investment_record_value_button, 1, 3)
        investment_layout.addLayout(valuation_row)

        for _w in [self.investment_worth_input, self.investment_base_invested_input]:
            _w.setEnabled(False)
        invest_metrics = QGridLayout()
        self.investment_total_invested_card = MetricCard("Total Invested", "$0.00")
        self.investment_roi_card = MetricCard("Return On Investment", "0.00%")
        self.investment_asset_net_worth_card = MetricCard("Asset Net Worth", "$0.00")
        invest_metrics.addWidget(self.investment_total_invested_card, 0, 0)
        invest_metrics.addWidget(self.investment_roi_card, 0, 1)
        invest_metrics.addWidget(self.investment_asset_net_worth_card, 0, 2)
        investment_layout.addLayout(invest_metrics)

        self.investment_snapshots_table = QTableWidget(0, 3)
        self.investment_snapshots_table.setHorizontalHeaderLabels(["Date", "Value", "Notes"])
        self.investment_snapshots_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.investment_snapshots_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.investment_snapshots_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.investment_snapshots_table.horizontalHeader().setStretchLastSection(True)
        investment_layout.addWidget(self.investment_snapshots_table)
        detail_layout.addWidget(self.investment_panel)

        links_panel = QFrame()
        links_panel.setObjectName("Panel")
        links_layout = QVBoxLayout(links_panel)
        links_layout.setContentsMargins(14, 14, 14, 14)
        links_layout.setSpacing(10)
        self.asset_linked_expenses_table = QTableWidget(0, 5)
        self.asset_linked_expenses_table.setHorizontalHeaderLabels(["Source", "Description", "Amount", "Date/Start", "Link ID"])
        self.asset_linked_expenses_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.asset_linked_expenses_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.asset_linked_expenses_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.asset_linked_expenses_table.horizontalHeader().setStretchLastSection(True)
        links_layout.addWidget(self.asset_linked_expenses_table)
        detail_layout.addWidget(links_panel)

        action_row = QHBoxLayout()
        self.asset_edit_btn = QPushButton("Edit Details")
        self.asset_edit_btn.clicked.connect(self._start_asset_edit)
        self.asset_save_btn = QPushButton("Save Changes")
        self.asset_save_btn.clicked.connect(self._save_selected_asset_details)
        self.asset_save_btn.setVisible(False)
        self.asset_cancel_btn = QPushButton("Cancel Edit")
        self.asset_cancel_btn.clicked.connect(self._cancel_asset_edit)
        self.asset_cancel_btn.setVisible(False)
        asset_delete_btn = QPushButton("Delete Asset")
        asset_delete_btn.clicked.connect(self._delete_selected_asset)
        action_row.addWidget(self.asset_edit_btn)
        action_row.addWidget(self.asset_save_btn)
        action_row.addWidget(self.asset_cancel_btn)
        action_row.addWidget(asset_delete_btn)
        action_row.addStretch(1)
        detail_layout.addLayout(action_row)
        scroll_layout.addWidget(self.asset_detail_panel, 1)

    def _add_new_asset_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Add New Asset")
        dialog.setMinimumSize(420, 420)
        dialog.resize(560, 560)
        form = QFormLayout(dialog)

        type_combo = QComboBox(); type_combo.addItems(["house", "investment"])
        name_input = QLineEdit(); name_input.setPlaceholderText("Asset name")

        # House-specific fields
        add_house_value = QDoubleSpinBox(); add_house_value.setMaximum(1_000_000_000); add_house_value.setDecimals(2); add_house_value.setPrefix("$")
        add_principal = QDoubleSpinBox(); add_principal.setMaximum(1_000_000_000); add_principal.setDecimals(2); add_principal.setPrefix("$")
        add_rate = QDoubleSpinBox(); add_rate.setMaximum(1000); add_rate.setDecimals(3); add_rate.setSuffix("%")
        add_term_years = QDoubleSpinBox(); add_term_years.setMaximum(100); add_term_years.setDecimals(2); add_term_years.setValue(30)
        add_loan_start = QDateEdit(); add_loan_start.setCalendarPopup(True); add_loan_start.setDate(QDate.currentDate())
        escrow_input = QDoubleSpinBox(); escrow_input.setMaximum(1_000_000_000); escrow_input.setDecimals(2); escrow_input.setPrefix("$")
        add_house_base_total_paid = QDoubleSpinBox(); add_house_base_total_paid.setMaximum(1_000_000_000); add_house_base_total_paid.setDecimals(2); add_house_base_total_paid.setPrefix("$")
        add_house_base_interest_paid = QDoubleSpinBox(); add_house_base_interest_paid.setMaximum(1_000_000_000); add_house_base_interest_paid.setDecimals(2); add_house_base_interest_paid.setPrefix("$")
        add_house_base_principal_paid = QDoubleSpinBox(); add_house_base_principal_paid.setMaximum(1_000_000_000); add_house_base_principal_paid.setDecimals(2); add_house_base_principal_paid.setPrefix("$")

        # Investment-specific fields
        add_invest_worth = QDoubleSpinBox(); add_invest_worth.setMaximum(1_000_000_000); add_invest_worth.setDecimals(2); add_invest_worth.setPrefix("$")
        add_invest_base = QDoubleSpinBox(); add_invest_base.setMaximum(1_000_000_000); add_invest_base.setDecimals(2); add_invest_base.setPrefix("$")

        form.addRow("Type", type_combo)
        form.addRow("Name", name_input)
        form.addRow("House Value", add_house_value)
        form.addRow("Current Principal", add_principal)
        form.addRow("Interest Rate", add_rate)
        form.addRow("Mortgage Term (years)", add_term_years)
        form.addRow("Loan Start Date", add_loan_start)
        form.addRow("Escrow Amount", escrow_input)
        form.addRow("Base Total Paid", add_house_base_total_paid)
        form.addRow("Base Interest Paid", add_house_base_interest_paid)
        form.addRow("Base Principal Paid", add_house_base_principal_paid)
        form.addRow("Investment Worth", add_invest_worth)
        form.addRow("Total Invested (Base)", add_invest_base)

        btn_row = QHBoxLayout(); add_btn = QPushButton("Add"); cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(add_btn); btn_row.addWidget(cancel_btn); form.addRow(btn_row)

        _house_widgets = [
            add_house_value, add_principal, add_rate, add_term_years, add_loan_start,
            escrow_input, add_house_base_total_paid, add_house_base_interest_paid, add_house_base_principal_paid,
        ]
        _invest_widgets = [add_invest_worth, add_invest_base]

        # Collect all QLabel companions so we can hide them together with their fields
        def _set_form_row_visible(widget: object, visible: bool) -> None:
            if hasattr(widget, "setVisible"):
                widget.setVisible(visible)
            label = form.labelForField(widget)
            if label:
                label.setVisible(visible)

        def _toggle_type() -> None:
            is_house = type_combo.currentText().strip().lower() == "house"
            for _w in _house_widgets:
                _set_form_row_visible(_w, is_house)
            for _w in _invest_widgets:
                _set_form_row_visible(_w, not is_house)

        type_combo.currentTextChanged.connect(lambda _: _toggle_type())
        _toggle_type()

        def _save() -> None:
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(self, APP_NAME, "Please enter an asset name.")
                return
            asset_type = type_combo.currentText().strip().lower()
            is_house = asset_type == "house"
            asset_id = self.assets_controller.add_asset(
                name=name,
                asset_type=asset_type,
                house_value=add_house_value.value() if is_house else 0.0,
                current_principal=add_principal.value() if is_house else 0.0,
                interest_rate_percent=add_rate.value() if is_house else 0.0,
                total_mortgage_years=add_term_years.value() if is_house else 30.0,
                loan_start_on=self._qdate_to_date(add_loan_start.date()) if is_house else None,
                escrow_amount=escrow_input.value() if is_house else 0.0,
                house_base_total_paid=add_house_base_total_paid.value() if is_house else 0.0,
                house_base_interest_paid=add_house_base_interest_paid.value() if is_house else 0.0,
                house_base_principal_paid=add_house_base_principal_paid.value() if is_house else 0.0,
                investment_worth=add_invest_worth.value() if not is_house else 0.0,
                base_total_invested=add_invest_base.value() if not is_house else 0.0,
            )
            dialog.accept()
            self.refresh_assets(select_asset_id=asset_id)

        add_btn.clicked.connect(_save)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec_()

    def _handle_asset_selection_changed(self) -> None:
        if self._is_refreshing_asset_selector:
            return
        asset_id = self.asset_selector_combo.currentData()
        if asset_id is None:
            self._selected_asset_id = None
            self._show_empty_asset_state()
            return

        self._selected_asset_id = int(asset_id)
        asset = self.assets_controller.get_asset_by_id(self._selected_asset_id)
        if asset is None:
            self._show_empty_asset_state()
            return
        self._populate_asset_details(asset)
        self._refresh_asset_links_views(asset.id)

    def _show_empty_asset_state(self) -> None:
        self.asset_name_label.setText("No asset selected")
        self.house_panel.setVisible(False)
        self.investment_panel.setVisible(False)
        self.asset_linked_expenses_table.setRowCount(0)
        if hasattr(self, "house_payment_breakdown_table"):
            self.house_payment_breakdown_table.setRowCount(0)
        if hasattr(self, "house_warning_label"):
            self.house_warning_label.clear()
            self.house_warning_label.setVisible(False)
        if hasattr(self, "investment_snapshots_table"):
            self.investment_snapshots_table.setRowCount(0)
        if hasattr(self, "asset_tx_link_combo"):
            self.asset_tx_link_combo.clear()
        if hasattr(self, "asset_recurring_link_combo"):
            self.asset_recurring_link_combo.clear()

    def _populate_asset_details(self, asset: Asset) -> None:
        self.asset_name_label.setText(f"{asset.name} ({asset.asset_type.title()})")
        is_house = asset.asset_type == "house"
        self.house_panel.setVisible(is_house)
        self.investment_panel.setVisible(not is_house)

        self.house_value_input.setValue(asset.house_value)
        self.house_principal_input.setValue(asset.current_principal)
        self.house_rate_input.setValue(asset.interest_rate_percent)
        self.house_term_years_input.setValue(asset.total_mortgage_years)
        self.house_escrow_input.setValue(asset.escrow_amount)
        self.house_base_total_paid_input.setValue(asset.house_base_total_paid)
        self.house_base_interest_paid_input.setValue(asset.house_base_interest_paid)
        self.house_base_principal_paid_input.setValue(asset.house_base_principal_paid)
        if asset.loan_start_on:
            self.house_loan_start_input.setDate(QDate(asset.loan_start_on.year, asset.loan_start_on.month, asset.loan_start_on.day))

        self.investment_worth_input.setValue(asset.investment_worth)
        self.investment_base_invested_input.setValue(asset.base_total_invested)

        payment_events = self._build_asset_payment_events(asset)
        if is_house:
            breakdown = self._calculate_house_breakdown(asset, payment_events)
            self._set_metric_value(self.house_total_paid_card, breakdown["total_paid"])
            self._set_metric_value(self.house_total_principal_paid_card, breakdown["principal_paid"])
            self._set_metric_value(self.house_total_interest_paid_card, breakdown["interest_paid"])
            self._set_metric_value(self.house_total_escrow_paid_card, breakdown["escrow_paid"])
            self._set_metric_value(self.house_total_housing_cost_card, breakdown["housing_cost"])
            self.house_years_elapsed_card.set_value(f"{breakdown['years_elapsed']:.2f}")
            if breakdown["years_left"] is None:
                self.house_years_left_card.set_value("N/A", is_warning=True)
            else:
                self.house_years_left_card.set_value(f"{breakdown['years_left']:.2f}")
            self._set_metric_value(self.house_asset_net_worth_card, asset.house_value - asset.current_principal)
            self._draw_house_payment_chart(breakdown["points"])
            self._populate_house_payment_breakdown_table(breakdown["rows"])
            warnings = breakdown["warnings"]
            if warnings:
                self.house_warning_label.setText(" | ".join(warnings))
                self.house_warning_label.setVisible(True)
            else:
                self.house_warning_label.clear()
                self.house_warning_label.setVisible(False)
        else:
            linked_contributions = sum(float(event["amount"]) for event in payment_events)
            total_invested = asset.base_total_invested + linked_contributions
            current_worth = asset.investment_worth
            roi_percent = ((current_worth - total_invested) / total_invested * 100.0) if total_invested > 0 else 0.0
            self._set_metric_value(self.investment_total_invested_card, total_invested)
            self.investment_roi_card.set_value(f"{roi_percent:,.2f}%", is_warning=roi_percent < 0)
            self._set_metric_value(self.investment_asset_net_worth_card, current_worth)
            self.investment_valuation_value.setValue(current_worth)
            self._refresh_investment_snapshots(asset.id)
            self.house_warning_label.clear()
            self.house_warning_label.setVisible(False)
        # Always return to locked (read-only) view after populating
        self._set_asset_inputs_enabled(False)

    def _save_selected_asset_details(self) -> None:
        if self._selected_asset_id is None:
            return
        asset = self.assets_controller.get_asset_by_id(self._selected_asset_id)
        if asset is None:
            return

        updated = self.assets_controller.update_asset(
            asset_id=self._selected_asset_id,
            name=asset.name,
            asset_type=asset.asset_type,
            house_value=self.house_value_input.value(),
            current_principal=self.house_principal_input.value(),
            interest_rate_percent=self.house_rate_input.value(),
            total_mortgage_years=self.house_term_years_input.value(),
            loan_start_on=self._qdate_to_date(self.house_loan_start_input.date()),
            escrow_amount=self.house_escrow_input.value(),
            house_base_total_paid=self.house_base_total_paid_input.value(),
            house_base_interest_paid=self.house_base_interest_paid_input.value(),
            house_base_principal_paid=self.house_base_principal_paid_input.value(),
            investment_worth=self.investment_worth_input.value(),
            base_total_invested=self.investment_base_invested_input.value(),
            notes=asset.notes,
        )
        if updated:
            self.refresh_assets(select_asset_id=self._selected_asset_id)
        # Lock inputs after save regardless of outcome
        self._set_asset_inputs_enabled(False)

    def _start_asset_edit(self) -> None:
        self._set_asset_inputs_enabled(True)

    def _cancel_asset_edit(self) -> None:
        if self._selected_asset_id is not None:
            asset = self.assets_controller.get_asset_by_id(self._selected_asset_id)
            if asset:
                self._populate_asset_details(asset)
                return
        self._set_asset_inputs_enabled(False)

    def _set_asset_inputs_enabled(self, enabled: bool) -> None:
        """Enable or disable all asset detail inputs and toggle edit/save/cancel button visibility."""
        house_inputs = [
            self.house_value_input, self.house_principal_input, self.house_rate_input,
            self.house_term_years_input, self.house_loan_start_input, self.house_escrow_input,
            self.house_base_total_paid_input, self.house_base_interest_paid_input,
            self.house_base_principal_paid_input,
        ]
        invest_inputs = [self.investment_worth_input, self.investment_base_invested_input]
        for _w in house_inputs + invest_inputs:
            _w.setEnabled(enabled)
        if hasattr(self, "asset_edit_btn"):
            self.asset_edit_btn.setVisible(not enabled)
            self.asset_save_btn.setVisible(enabled)
            self.asset_cancel_btn.setVisible(enabled)

    def _delete_selected_asset(self) -> None:
        if self._selected_asset_id is None:
            return
        if self.assets_controller.delete_asset(self._selected_asset_id):
            self._selected_asset_id = None
            self.refresh_assets()

    def _record_investment_value_snapshot(self) -> None:
        if self._selected_asset_id is None:
            return
        asset = self.assets_controller.get_asset_by_id(self._selected_asset_id)
        if asset is None or asset.asset_type != "investment":
            return

        value = self.investment_valuation_value.value()
        if value < 0:
            QMessageBox.warning(self, APP_NAME, "Current value must be zero or greater.")
            return

        saved = self.assets_controller.record_investment_value_snapshot(
            asset_id=int(self._selected_asset_id),
            value=value,
            valued_on=self._qdate_to_date(self.investment_valuation_date.date()),
            notes=self.investment_valuation_notes.text(),
        )
        if not saved:
            QMessageBox.warning(self, APP_NAME, "Could not save investment value snapshot.")
            return

        self.investment_valuation_notes.clear()
        self.status_bar.showMessage("Saved investment value snapshot and updated current value.", 4000)
        self.refresh_assets(select_asset_id=self._selected_asset_id)

    def _refresh_investment_snapshots(self, asset_id: int | None) -> None:
        if asset_id is None:
            self.investment_snapshots_table.setRowCount(0)
            return

        snapshots = self.assets_controller.list_asset_value_snapshots(int(asset_id), limit=24)
        self.investment_snapshots_table.setRowCount(len(snapshots))
        for row_index, snapshot in enumerate(snapshots):
            cells = [
                snapshot["valued_on"].isoformat(),
                f"${float(snapshot['value']):,.2f}",
                str(snapshot["notes"]),
            ]
            for column_index, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column_index == 1:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.investment_snapshots_table.setItem(row_index, column_index, item)

    def _refresh_asset_links_views(self, asset_id: int | None) -> None:
        if asset_id is None:
            self.asset_linked_expenses_table.setRowCount(0)
            if hasattr(self, "asset_tx_link_combo"):
                self.asset_tx_link_combo.clear()
            if hasattr(self, "asset_recurring_link_combo"):
                self.asset_recurring_link_combo.clear()
            return

        links = self.assets_controller.list_asset_expense_links(asset_id)
        self.asset_linked_expenses_table.setRowCount(len(links))
        for row_index, link in enumerate(links):
            source_label = "One-Time" if link["source_type"] == "transaction" else "Recurring"
            payment_kind = str(link.get("payment_kind", "mortgage")).title()
            date_value = link["date"]
            date_label = date_value.isoformat() if isinstance(date_value, date) else "-"
            cells = [f"{source_label} ({payment_kind})", str(link["label"]), f"${float(link['amount']):,.2f}", date_label, str(link["link_id"])]
            for column_index, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column_index == 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if column_index == 4:
                    item.setData(Qt.UserRole, int(link["link_id"]))
                self.asset_linked_expenses_table.setItem(row_index, column_index, item)

        if hasattr(self, "asset_tx_link_combo"):
            self.asset_tx_link_combo.clear()
            for transaction in self.assets_controller.list_unlinked_expense_transactions(limit=300):
                label = f"{transaction.occurred_on.isoformat()} | {transaction.category} | {transaction.description} | ${transaction.amount:,.2f}"
                self.asset_tx_link_combo.addItem(label, int(transaction.id))

        if hasattr(self, "asset_recurring_link_combo"):
            self.asset_recurring_link_combo.clear()
            for recurring_item in self.assets_controller.list_unlinked_recurring_expenses():
                label = f"{recurring_item.category} | {recurring_item.description} | ${recurring_item.amount:,.2f}"
                self.asset_recurring_link_combo.addItem(label, int(recurring_item.id))

    def _link_selected_transaction_expense(self) -> None:
        if self._selected_asset_id is None:
            return
        tx_id = self.asset_tx_link_combo.currentData()
        if tx_id is None:
            return
        try:
            self.assets_controller.link_expense_to_asset(self._selected_asset_id, "transaction", int(tx_id))
            self.refresh_assets(select_asset_id=self._selected_asset_id)
        except Exception:
            QMessageBox.warning(self, APP_NAME, "Could not link selected one-time expense.")

    def _link_selected_recurring_expense(self) -> None:
        if self._selected_asset_id is None:
            return
        recurring_id = self.asset_recurring_link_combo.currentData()
        if recurring_id is None:
            return
        try:
            self.assets_controller.link_expense_to_asset(self._selected_asset_id, "recurring", int(recurring_id))
            self.refresh_assets(select_asset_id=self._selected_asset_id)
        except Exception:
            QMessageBox.warning(self, APP_NAME, "Could not link selected recurring expense.")

    def _unlink_selected_asset_expense(self) -> None:
        row = self.asset_linked_expenses_table.currentRow()
        if row < 0:
            return
        link_item = self.asset_linked_expenses_table.item(row, 4)
        if link_item is None:
            return
        link_id = int(link_item.data(Qt.UserRole))
        self.assets_controller.unlink_expense_from_asset(link_id)
        self.refresh_assets(select_asset_id=self._selected_asset_id)

    def _build_asset_payment_events(self, asset: Asset) -> list[dict[str, object]]:
        if asset.id is None:
            return []
        links = self.assets_controller.list_asset_expense_links(asset.id)
        events: list[dict[str, object]] = []
        for link in links:
            amount = float(link["amount"])
            source_date = link["date"]
            payment_kind = str(link.get("payment_kind", "mortgage"))
            if not isinstance(source_date, date):
                continue
            events.append(
                {
                    "date": source_date,
                    "amount": amount,
                    "payment_kind": payment_kind,
                    "source_type": str(link["source_type"]),
                    "label": str(link["label"]),
                }
            )
        events.sort(key=lambda item: item["date"])
        return events

    def _calculate_house_breakdown(self, asset: Asset, payment_events: list[dict[str, object]]) -> dict[str, object]:
        annual_rate = max(asset.interest_rate_percent, 0.0) / 100.0
        monthly_rate = annual_rate / 12.0
        total_paid = max(asset.house_base_total_paid, 0.0)
        principal_paid = max(asset.house_base_principal_paid, 0.0)
        interest_paid = max(asset.house_base_interest_paid, 0.0)
        escrow_paid = 0.0
        warnings: list[str] = []
        points: list[tuple[date, float, float, float]] = []
        rows: list[dict[str, object]] = []

        if asset.house_base_interest_paid + asset.house_base_principal_paid > asset.house_base_total_paid + 0.01:
            warnings.append("Base principal + interest exceeds base total paid.")

        starting_balance = self._estimate_opening_principal(asset, payment_events)
        balance = starting_balance

        if total_paid > 0 or principal_paid > 0 or interest_paid > 0:
            baseline_date = (asset.loan_start_on or date.today())
            points.append((baseline_date, total_paid, principal_paid, interest_paid))

        previous_date = asset.loan_start_on or (payment_events[0]["date"] if payment_events else date.today())
        escrow_per_payment = max(asset.escrow_amount, 0.0)
        for event in payment_events:
            payment_date = event["date"]
            amount = float(event["amount"])
            payment_kind = str(event["payment_kind"])
            months_elapsed = self._months_between(previous_date, payment_date)
            accrued_interest = balance * monthly_rate * months_elapsed
            escrow_component = min(amount, escrow_per_payment) if payment_kind == "mortgage" else 0.0
            mortgage_payment = amount if payment_kind == "principal" else max(amount - escrow_component, 0.0)
            if payment_kind == "principal":
                interest_component = 0.0
                principal_component = max(0.0, min(balance, mortgage_payment))
            else:
                interest_component = min(mortgage_payment, accrued_interest)
                principal_component = max(0.0, min(balance, mortgage_payment - interest_component))
            balance = max(0.0, balance - principal_component)

            total_paid += amount
            principal_paid += principal_component
            interest_paid += interest_component
            escrow_paid += escrow_component
            points.append((payment_date, total_paid, principal_paid, interest_paid))
            rows.append(
                {
                    "date": payment_date,
                    "source": "One-Time" if str(event["source_type"]) == "transaction" else "Recurring",
                    "payment_type": payment_kind,
                    "gross_payment": amount,
                    "escrow": escrow_component,
                    "mortgage_net": mortgage_payment,
                    "interest": interest_component,
                    "principal": principal_component,
                    "running_principal": balance,
                    "running_total_paid": total_paid,
                }
            )
            previous_date = payment_date

        if payment_events and asset.loan_start_on is None:
            warnings.append("Loan start date is missing. Add it to improve elapsed-year and interest timing accuracy.")
        if payment_events and max(asset.current_principal, 0.0) <= 0:
            warnings.append("Current principal is zero while payments are linked. Verify payoff status and payment links.")
        if any(row["mortgage_net"] <= 0 and row["payment_type"] == "mortgage" for row in rows):
            warnings.append("One or more mortgage payments are fully consumed by escrow. Verify escrow amount.")

        loan_start = asset.loan_start_on or date.today()
        years_elapsed = max(0.0, (date.today() - loan_start).days / 365.25)
        monthly_payment = self._estimate_monthly_mortgage_payment(payment_events, asset)
        years_left = self._calculate_mortgage_years_left(
            current_principal=max(asset.current_principal, 0.0),
            annual_interest_rate_percent=max(asset.interest_rate_percent, 0.0),
            monthly_payment=monthly_payment,
        )
        if years_left is None:
            warnings.append("Monthly mortgage payment does not cover interest. Years left cannot be estimated.")

        housing_cost = principal_paid + interest_paid + escrow_paid
        return {
            "total_paid": total_paid,
            "principal_paid": principal_paid,
            "interest_paid": interest_paid,
            "escrow_paid": escrow_paid,
            "housing_cost": housing_cost,
            "years_elapsed": years_elapsed,
            "years_left": years_left,
            "points": points,
            "rows": rows,
            "warnings": warnings,
        }

    def _estimate_opening_principal(self, asset: Asset, payment_events: list[dict[str, object]]) -> float:
        """Reverse-linked payment events to estimate principal at tracking start."""
        if not payment_events:
            return max(asset.current_principal, 0.0)

        monthly_rate = max(asset.interest_rate_percent, 0.0) / 100.0 / 12.0
        escrow_per_payment = max(asset.escrow_amount, 0.0)
        end_balance = max(asset.current_principal, 0.0)

        indexed_events = list(enumerate(payment_events))
        reverse_events = sorted(indexed_events, key=lambda pair: pair[1]["date"], reverse=True)
        first_date = payment_events[0]["date"]

        for index, event in reverse_events:
            event_date = event["date"]
            payment_kind = str(event["payment_kind"])
            amount = float(event["amount"])
            prior_date = asset.loan_start_on if index == 0 else payment_events[index - 1]["date"]
            if prior_date is None:
                prior_date = first_date
            months_elapsed = self._months_between(prior_date, event_date)
            factor = 1.0 + (monthly_rate * months_elapsed)

            if payment_kind == "principal":
                end_balance = end_balance + max(amount, 0.0)
                continue

            net_payment = max(amount - min(amount, escrow_per_payment), 0.0)
            if factor <= 0:
                end_balance = end_balance + net_payment
                continue

            candidate_start = (end_balance + net_payment) / factor
            interest_only_threshold = candidate_start * (monthly_rate * months_elapsed)
            if net_payment <= interest_only_threshold + 1e-9:
                start_balance = end_balance
            else:
                start_balance = max(end_balance, candidate_start)
            end_balance = start_balance

        return max(end_balance, 0.0)

    def _estimate_monthly_mortgage_payment(self, payment_events: list[dict[str, object]], asset: Asset) -> float:
        """Estimate monthly payment using linked events; fallback to amortized term estimate."""
        if payment_events:
            start_of_this_month = date.today().replace(day=1)
            one_year_ago = self._advance_months(start_of_this_month, -12)
            monthly_totals: dict[tuple[int, int], float] = {}
            for event in payment_events:
                payment_date = event["date"]
                amount = float(event["amount"])
                payment_kind = str(event["payment_kind"])
                if payment_kind != "mortgage" or payment_date < one_year_ago:
                    continue
                key = (payment_date.year, payment_date.month)
                monthly_totals[key] = monthly_totals.get(key, 0.0) + max(amount - max(asset.escrow_amount, 0.0), 0.0)
            if monthly_totals:
                return sum(monthly_totals.values()) / len(monthly_totals)

        principal = max(asset.current_principal, 0.0)
        annual_rate = max(asset.interest_rate_percent, 0.0) / 100.0
        total_months = max(int(round(max(asset.total_mortgage_years, 0.0) * 12)), 1)
        if principal <= 0:
            return 0.0
        if annual_rate <= 0:
            return principal / total_months

        monthly_rate = annual_rate / 12.0
        growth = (1 + monthly_rate) ** total_months
        return principal * (monthly_rate * growth) / (growth - 1)

    def _calculate_mortgage_years_left(
        self,
        current_principal: float,
        annual_interest_rate_percent: float,
        monthly_payment: float,
    ) -> float | None:
        if current_principal <= 0:
            return 0.0
        if monthly_payment <= 0:
            return None

        monthly_rate = (annual_interest_rate_percent / 100.0) / 12.0
        if monthly_rate <= 0:
            return current_principal / monthly_payment / 12.0

        # Payment must exceed monthly interest to amortize.
        min_interest_payment = current_principal * monthly_rate
        if monthly_payment <= min_interest_payment:
            return None

        months_left = -math.log(1 - (monthly_rate * current_principal / monthly_payment)) / math.log(1 + monthly_rate)
        return max(0.0, months_left / 12.0)

    def _months_between(self, earlier: date, later: date) -> int:
        if later <= earlier:
            return 0
        return max(0, (later.year - earlier.year) * 12 + (later.month - earlier.month))

    def _populate_house_payment_breakdown_table(self, rows: list[dict[str, object]]) -> None:
        self.house_payment_breakdown_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            cells = [
                str(row["date"].isoformat()),
                str(row["source"]),
                str(row["payment_type"]).title(),
                f"${float(row['gross_payment']):,.2f}",
                f"${float(row['escrow']):,.2f}",
                f"${float(row['mortgage_net']):,.2f}",
                f"${float(row['interest']):,.2f}",
                f"${float(row['principal']):,.2f}",
                f"${float(row['running_principal']):,.2f}",
                f"${float(row['running_total_paid']):,.2f}",
            ]
            for column_index, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column_index >= 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.house_payment_breakdown_table.setItem(row_index, column_index, item)

    def _draw_house_payment_chart(self, points: list[tuple[date, float, float, float]]) -> None:
        self.asset_house_chart_figure.clear()
        axis = self.asset_house_chart_figure.add_subplot(111)
        self._style_chart_axis(axis)
        if not points:
            axis.text(0.5, 0.5, "Link expenses to view payment history.", color="#e7edf7", ha="center", va="center")
            axis.set_title("Mortgage Payment Breakdown", color="#f5f8ff")
            self.asset_house_chart_figure.tight_layout()
            self.asset_house_chart_canvas.draw_idle()
            return

        labels = [entry[0].isoformat() for entry in points]
        total_paid = [entry[1] for entry in points]
        principal_paid = [entry[2] for entry in points]
        interest_paid = [entry[3] for entry in points]
        axis.plot(labels, total_paid, color="#2ec4b6", linewidth=2.0, label="Total Paid")
        axis.plot(labels, principal_paid, color="#4cc9f0", linewidth=2.0, label="Principal Paid")
        axis.plot(labels, interest_paid, color="#ff7b72", linewidth=2.0, label="Interest Paid")
        axis.tick_params(axis="x", rotation=20)
        axis.set_title("Mortgage Payment Breakdown", color="#f5f8ff")
        axis.legend(facecolor="#111a27", edgecolor="#233247", labelcolor="#e7edf7")
        self.asset_house_chart_figure.tight_layout()
        self.asset_house_chart_canvas.draw_idle()

    def _advance_months(self, value: date, interval_count: int) -> date:
        month_index = value.month - 1 + int(interval_count)
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    def refresh_assets(self, select_asset_id: int | None = None) -> None:
        overview = self.assets_controller.assets_overview()
        self._set_metric_value(self.assets_total_net_worth_card, overview["total_net_worth"], is_warning=overview["total_net_worth"] < 0)
        self._set_metric_value(self.assets_total_value_card, overview["total_value"])
        self._set_metric_value(self.assets_total_debt_card, overview["total_debt"])
        self._set_metric_value(self.assets_total_invested_card, overview["total_invested"])

        assets = self.assets_controller.list_assets()
        self._is_refreshing_asset_selector = True
        self.asset_selector_combo.clear()
        for asset in assets:
            self.asset_selector_combo.addItem(f"{asset.name} ({asset.asset_type.title()})", int(asset.id))
        self._is_refreshing_asset_selector = False

        if self.asset_selector_combo.count() == 0:
            self._selected_asset_id = None
            self._show_empty_asset_state()
            return

        target_asset_id = select_asset_id if select_asset_id is not None else self._selected_asset_id
        target_index = 0
        if target_asset_id is not None:
            found_index = self.asset_selector_combo.findData(int(target_asset_id))
            if found_index >= 0:
                target_index = found_index

        self.asset_selector_combo.setCurrentIndex(target_index)
        self._handle_asset_selection_changed()
        self._refresh_asset_link_entry_controls()

    def _refresh_asset_link_entry_controls(self) -> None:
        assets = self.assets_controller.list_assets()

        if hasattr(self, "expense_asset_link_combo"):
            previous_data = self.expense_asset_link_combo.currentData() if self.expense_asset_link_combo.count() > 0 else None
            self.expense_asset_link_combo.blockSignals(True)
            self.expense_asset_link_combo.clear()
            self.expense_asset_link_combo.addItem("No asset link", None)
            for asset in assets:
                self.expense_asset_link_combo.addItem(f"{asset.name} ({asset.asset_type.title()})", int(asset.id))
            restore_index = self.expense_asset_link_combo.findData(previous_data)
            self.expense_asset_link_combo.setCurrentIndex(restore_index if restore_index >= 0 else 0)
            self.expense_asset_link_combo.blockSignals(False)

        if hasattr(self, "recurring_asset_link_combo"):
            previous_data = self.recurring_asset_link_combo.currentData() if self.recurring_asset_link_combo.count() > 0 else None
            self.recurring_asset_link_combo.blockSignals(True)
            self.recurring_asset_link_combo.clear()
            self.recurring_asset_link_combo.addItem("No asset link", None)
            for asset in assets:
                self.recurring_asset_link_combo.addItem(f"{asset.name} ({asset.asset_type.title()})", int(asset.id))
            restore_index = self.recurring_asset_link_combo.findData(previous_data)
            self.recurring_asset_link_combo.setCurrentIndex(restore_index if restore_index >= 0 else 0)
            self.recurring_asset_link_combo.blockSignals(False)

    def _build_assistant_tab(self) -> None:
        layout = self._build_scrollable_tab_layout(self.assistant_tab)

        title = QLabel("Local AI Assistant")
        title.setObjectName("PageTitle")
        subtitle = QLabel("The assistant can answer questions, start Ollama if needed, and write directly to the ledger.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._build_voice_surface_section(layout, mode="assistant", output_placeholder=None)

        # Model selector
        model_selector_row = QHBoxLayout()
        model_label = QLabel("Ollama Model:")
        self.model_selector = QComboBox()
        self.model_selector.currentTextChanged.connect(self._handle_model_changed)
        self._refresh_available_models()
        refresh_models_btn = QPushButton("Refresh Models")
        refresh_models_btn.setMaximumWidth(120)
        refresh_models_btn.clicked.connect(self._refresh_available_models)
        model_selector_row.addWidget(model_label)
        model_selector_row.addWidget(self.model_selector, 1)
        model_selector_row.addWidget(refresh_models_btn)
        layout.addLayout(model_selector_row)

        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setObjectName("ChatLog")
        layout.addWidget(self.chat_log, 1)

        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask about spending, add an expense, create a category, or summarize your month...")
        self.chat_input.returnPressed.connect(self.send_prompt)
        self.send_button = QPushButton("Send to Assistant")
        self.send_button.clicked.connect(self.send_prompt)
        input_row.addWidget(self.chat_input, 1)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

    def _build_voice_test_tab(self) -> None:
        layout = self._build_scrollable_tab_layout(self.voice_test_tab)

        title = QLabel("Voice Testing")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Use this tab to validate speech-to-text behavior, wake detection, and diagnostics without sending anything to the AI assistant."
        )
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._build_voice_surface_section(
            layout,
            mode="testing",
            output_placeholder="Recognized voice commands will appear here without being sent to the assistant...",
        )

    def _build_voice_surface_section(
        self,
        layout: QVBoxLayout,
        mode: str,
        output_placeholder: str | None,
    ) -> None:
        voice_row = QHBoxLayout()
        button = QPushButton(self._voice_start_button_label())
        if mode == "assistant":
            button.clicked.connect(self._toggle_voice_listener)
        else:
            button.clicked.connect(self._toggle_voice_test_listener)

        status_label = QLabel("Voice: Off")
        status_label.setObjectName("PageSubtitle")
        voice_row.addWidget(button)
        voice_row.addWidget(status_label, 1)
        layout.addLayout(voice_row)

        wake_row = QHBoxLayout()
        wake_row.addWidget(QLabel("Wake phrase:"))
        wake_input = QLineEdit()
        wake_input.setText(self._wake_phrase)
        wake_input.setPlaceholderText("hey steven")
        wake_apply_button = QPushButton("Apply Wake Phrase")
        wake_apply_button.clicked.connect(lambda: self._apply_wake_phrase_from_surface(mode))
        wake_input.returnPressed.connect(lambda: self._apply_wake_phrase_from_surface(mode))
        wake_row.addWidget(wake_input, 1)
        wake_row.addWidget(wake_apply_button)
        layout.addLayout(wake_row)

        last_command_label = QLabel("Last voice command: (none)")
        last_command_label.setObjectName("PageSubtitle")
        last_command_label.setWordWrap(True)
        layout.addWidget(last_command_label)

        partial_label = QLabel("Live transcript: (waiting)")
        partial_label.setObjectName("PageSubtitle")
        partial_label.setWordWrap(True)
        layout.addWidget(partial_label)

        diagnostics_panel = QFrame()
        diagnostics_panel.setObjectName("Panel")
        diagnostics_layout = QGridLayout(diagnostics_panel)
        diagnostics_layout.setContentsMargins(12, 10, 12, 10)
        diagnostics_layout.setHorizontalSpacing(10)
        diagnostics_layout.setVerticalSpacing(6)

        diagnostics_layout.addWidget(QLabel("Voice Diagnostics"), 0, 0, 1, 4)
        diagnostics_layout.addWidget(QLabel("Stage"), 1, 0)
        diagnostics_layout.addWidget(QLabel("Provider"), 1, 1)
        diagnostics_layout.addWidget(QLabel("Confidence"), 1, 2)
        diagnostics_layout.addWidget(QLabel("Latency"), 1, 3)

        diag_stage = QLabel("-")
        diag_provider = QLabel("-")
        diag_confidence = QLabel("-")
        diag_latency = QLabel("-")
        diagnostics_layout.addWidget(diag_stage, 2, 0)
        diagnostics_layout.addWidget(diag_provider, 2, 1)
        diagnostics_layout.addWidget(diag_confidence, 2, 2)
        diagnostics_layout.addWidget(diag_latency, 2, 3)

        diagnostics_layout.addWidget(QLabel("Fallback"), 3, 0)
        diagnostics_layout.addWidget(QLabel("Endpoint"), 3, 1)
        diagnostics_layout.addWidget(QLabel("Speech ms"), 3, 2)
        diagnostics_layout.addWidget(QLabel("Wake mode"), 3, 3)

        diag_fallback = QLabel("-")
        diag_endpoint = QLabel("-")
        diag_speech_ms = QLabel("-")
        diag_wake_mode = QLabel("-")
        diagnostics_layout.addWidget(diag_fallback, 4, 0)
        diagnostics_layout.addWidget(diag_endpoint, 4, 1)
        diagnostics_layout.addWidget(diag_speech_ms, 4, 2)
        diagnostics_layout.addWidget(diag_wake_mode, 4, 3)
        layout.addWidget(diagnostics_panel)

        output_box: QTextEdit | None = None
        if output_placeholder is not None:
            output_box = QTextEdit()
            output_box.setReadOnly(True)
            output_box.setObjectName("ChatLog")
            output_box.setPlaceholderText(output_placeholder)
            layout.addWidget(output_box, 1)
            if mode == "testing":
                self.voice_test_output = output_box

        self._voice_ui[mode] = {
            "button": button,
            "status": status_label,
            "wake_input": wake_input,
            "last_command": last_command_label,
            "partial": partial_label,
            "diag_stage": diag_stage,
            "diag_provider": diag_provider,
            "diag_confidence": diag_confidence,
            "diag_latency": diag_latency,
            "diag_fallback": diag_fallback,
            "diag_endpoint": diag_endpoint,
            "diag_speech_ms": diag_speech_ms,
            "diag_wake_mode": diag_wake_mode,
            "output": output_box,
        }

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")

        export_action = QAction("Export data to CSV...", self)
        export_action.setStatusTip("Export all transactions, categories, recurring items and budgets to CSV files")
        export_action.triggered.connect(self._handle_export_csv)
        file_menu.addAction(export_action)

        import_action = QAction("Import data from CSV...", self)
        import_action.setStatusTip("Import CSV seed files into the database")
        import_action.triggered.connect(self._handle_import_csv)
        file_menu.addAction(import_action)

        view_menu = menu_bar.addMenu("View")

        reset_zoom_action = QAction("Reset Zoom", self)
        reset_zoom_action.setStatusTip("Reset UI zoom to 100%")
        reset_zoom_action.triggered.connect(self._reset_ui_scale)
        view_menu.addAction(reset_zoom_action)

        density_menu = view_menu.addMenu("Density")
        density_options = [
            ("compact", "Compact"),
            ("comfortable", "Comfortable"),
            ("spacious", "Spacious"),
        ]
        for density_value, density_label in density_options:
            action = QAction(density_label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked, mode=density_value: self._set_density_mode(mode) if checked else None
            )
            density_menu.addAction(action)
            self._density_actions[density_value] = action

        self._refresh_density_actions()

    def _handle_export_csv(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select export directory",
            "seeds",
        )
        if not directory:
            return
        try:
            counts = self.app_controller.export_to_csv(directory)
            summary = "\n".join(f"  {table}: {n} rows" for table, n in counts.items())
            QMessageBox.information(
                self,
                "Export complete",
                f"Exported to:\n{directory}\n\n{summary}\n\nCommit these CSV files to share with your team.",
            )
            self.status_bar.showMessage(f"Exported to {directory}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _handle_import_csv(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select seeds directory to import",
            "seeds",
        )
        if not directory:
            return

        reply = QMessageBox.question(
            self,
            "Import CSV data",
            "How do you want to import?\n\n"
            "- Yes: clear all existing data first, then import (full reset)\n"
            "- No: add imported data on top of existing data\n"
            "- Cancel: abort",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Cancel:
            return

        clear_first = reply == QMessageBox.Yes
        try:
            counts = self.app_controller.import_from_csv(directory, clear_first=clear_first)
            if not counts:
                QMessageBox.information(self, "Import", "No CSV files found in the selected directory.")
                return
            summary = "\n".join(f"  {table}: {n} rows" for table, n in counts.items())
            QMessageBox.information(self, "Import complete", f"Imported from:\n{directory}\n\n{summary}")
            self.refresh_all()
            self.status_bar.showMessage("Import complete.", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))

    def _load_ui_scale_setting(self) -> float:
        raw_value = self.app_controller.get_setting("ui_scale", "1.00") or "1.00"
        try:
            parsed = float(raw_value)
        except ValueError:
            return 1.0
        return self._clamp_ui_scale(parsed)

    def _load_ui_density_setting(self) -> str:
        saved_mode = (self.app_controller.get_setting("ui_density", "comfortable") or "comfortable").strip().lower()
        return saved_mode if saved_mode in {"compact", "comfortable", "spacious"} else "comfortable"

    def _clamp_ui_scale(self, value: float) -> float:
        return max(0.85, min(1.50, value))

    def _setup_ui_scale_controls(self) -> None:
        QApplication.instance().installEventFilter(self)

        self._zoom_in_shortcut = QShortcut(QKeySequence("Ctrl++"), self)
        self._zoom_in_shortcut.activated.connect(lambda: self._change_ui_scale(+0.05))

        self._zoom_in_alt_shortcut = QShortcut(QKeySequence("Ctrl+="), self)
        self._zoom_in_alt_shortcut.activated.connect(lambda: self._change_ui_scale(+0.05))

        self._zoom_out_shortcut = QShortcut(QKeySequence("Ctrl+-"), self)
        self._zoom_out_shortcut.activated.connect(lambda: self._change_ui_scale(-0.05))

        self._zoom_reset_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        self._zoom_reset_shortcut.activated.connect(self._reset_ui_scale)

    def eventFilter(self, watched: object, event: object) -> bool:
        if (
            isinstance(event, QEvent)
            and event.type() == QEvent.Wheel
            and QApplication.keyboardModifiers() & Qt.ControlModifier
        ):
            wheel_delta = event.angleDelta().y() if hasattr(event, "angleDelta") else 0
            if wheel_delta > 0:
                self._change_ui_scale(+0.05)
            elif wheel_delta < 0:
                self._change_ui_scale(-0.05)
            return True
        return super().eventFilter(watched, event)

    def _reset_ui_scale(self) -> None:
        self._ui_scale = 1.0
        self._apply_ui_scale(persist=True, show_status=True)

    def _change_ui_scale(self, delta: float) -> None:
        new_scale = self._clamp_ui_scale(self._ui_scale + delta)
        if abs(new_scale - self._ui_scale) < 0.001:
            return
        self._ui_scale = new_scale
        self._apply_ui_scale(persist=True, show_status=True)

    def _apply_ui_scale(self, persist: bool, show_status: bool) -> None:
        self._apply_styles()
        self._apply_layout_scale()
        if persist:
            self.app_controller.set_setting("ui_scale", f"{self._ui_scale:.2f}")
        if show_status:
            self.status_bar.showMessage(f"UI scale: {int(round(self._ui_scale * 100))}%", 2500)

    def _capture_layout_base_metrics(self) -> None:
        self._layout_base_metrics.clear()
        seen_layout_ids: set[int] = set()
        for widget in self.findChildren(QWidget):
            layout = widget.layout()
            if layout is None:
                continue
            stack = [layout]
            while stack:
                current_layout = stack.pop()
                layout_id = id(current_layout)
                if layout_id in seen_layout_ids:
                    continue
                seen_layout_ids.add(layout_id)

                margins = current_layout.contentsMargins()
                self._layout_base_metrics[layout_id] = (
                    (margins.left(), margins.top(), margins.right(), margins.bottom()),
                    current_layout.spacing(),
                )

                for item_index in range(current_layout.count()):
                    child_item = current_layout.itemAt(item_index)
                    child_layout = child_item.layout()
                    if child_layout is not None:
                        stack.append(child_layout)
                    child_widget = child_item.widget()
                    if child_widget is not None and child_widget.layout() is not None:
                        stack.append(child_widget.layout())

    def _density_scale(self) -> float:
        return {
            "compact": 0.88,
            "comfortable": 1.0,
            "spacious": 1.14,
        }.get(self._density_mode, 1.0)

    def _set_density_mode(self, mode: str, persist: bool = True, show_status: bool = True) -> None:
        normalized = mode.strip().lower()
        if normalized not in {"compact", "comfortable", "spacious"}:
            return
        if normalized == self._density_mode:
            self._refresh_density_actions()
            return

        self._density_mode = normalized
        self._apply_ui_scale(persist=False, show_status=False)
        if persist:
            self.app_controller.set_setting("ui_density", self._density_mode)
        self._refresh_density_actions()
        if show_status:
            self.status_bar.showMessage(f"Density: {self._density_mode.title()}", 2500)

    def _refresh_density_actions(self) -> None:
        for mode, action in self._density_actions.items():
            action.blockSignals(True)
            action.setChecked(mode == self._density_mode)
            action.blockSignals(False)

    def _apply_layout_scale(self) -> None:
        scale = self._ui_scale * self._density_scale()
        seen_layout_ids: set[int] = set()
        for widget in self.findChildren(QWidget):
            layout = widget.layout()
            if layout is None:
                continue
            stack = [layout]
            while stack:
                current_layout = stack.pop()
                layout_id = id(current_layout)
                if layout_id in seen_layout_ids:
                    continue
                seen_layout_ids.add(layout_id)

                base_metrics = self._layout_base_metrics.get(layout_id)
                if base_metrics is not None:
                    base_margins, base_spacing = base_metrics
                    current_layout.setContentsMargins(
                        max(0, int(round(base_margins[0] * scale))),
                        max(0, int(round(base_margins[1] * scale))),
                        max(0, int(round(base_margins[2] * scale))),
                        max(0, int(round(base_margins[3] * scale))),
                    )
                    if base_spacing >= 0:
                        current_layout.setSpacing(max(0, int(round(base_spacing * scale))))

                for item_index in range(current_layout.count()):
                    child_item = current_layout.itemAt(item_index)
                    child_layout = child_item.layout()
                    if child_layout is not None:
                        stack.append(child_layout)
                    child_widget = child_item.widget()
                    if child_widget is not None and child_widget.layout() is not None:
                        stack.append(child_widget.layout())

    def _set_widget_tone(self, widget: QWidget, tone: str) -> None:
        widget.setProperty("tone", tone)
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)

    def _apply_styles(self) -> None:
        scale = self._ui_scale
        density_scale = self._density_scale()
        spatial_scale = scale * density_scale
        font_size = max(9, int(round(10 * scale)))
        page_title_size = max(20, int(round(26 * scale)))
        subtitle_size = max(10, int(round(11 * scale)))
        section_title_size = max(12, int(round(15 * scale)))
        metric_value_size = max(16, int(round(22 * scale)))
        radius_large = max(10, int(round(18 * spatial_scale)))
        radius_medium = max(8, int(round(12 * spatial_scale)))
        tab_padding_y = max(8, int(round(12 * spatial_scale)))
        tab_padding_x = max(12, int(round(18 * spatial_scale)))
        control_padding = max(7, int(round(10 * spatial_scale)))
        button_padding_y = max(8, int(round(12 * spatial_scale)))
        button_padding_x = max(12, int(round(16 * spatial_scale)))
        header_padding = max(7, int(round(10 * spatial_scale)))
        scroll_handle_size = max(18, int(round(24 * spatial_scale)))
        tab_radius = max(8, int(round(10 * spatial_scale)))
        scroll_radius = max(4, int(round(6 * spatial_scale)))

        theme = {
            "bg_app": "#0a1018",
            "bg_surface": "#111a27",
            "bg_surface_alt": "#0d1520",
            "bg_surface_disabled": "#0b121c",
            "bg_surface_strong": "#09111a",
            "bg_tab": "#101826",
            "bg_tab_selected": "#172233",
            "bg_header": "#172233",
            "border": "#1e2b3f",
            "border_strong": "#233247",
            "border_grid": "#1f2d40",
            "text_primary": "#e7edf7",
            "text_heading": "#f5f8ff",
            "text_muted": "#90a4bf",
            "text_secondary": "#9fb0c7",
            "text_disabled": "#6f8098",
            "text_inverse": "#041012",
            "accent": "#2ec4b6",
            "accent_hover": "#58d4c8",
            "accent_pressed": "#25a99e",
            "accent_soft": "#163239",
            "success": "#8de59b",
            "warning": "#ffd166",
            "danger": "#ff8f8f",
            "warning_secondary": "#ffb347",
            "focus_ring": "#71e6db",
        }

        font = QFont("Segoe UI")
        font.setPointSize(font_size)

        app = QApplication.instance()
        app.setFont(font)

        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(theme["bg_app"]))
        palette.setColor(QPalette.WindowText, QColor(theme["text_primary"]))
        palette.setColor(QPalette.Base, QColor(theme["bg_surface_alt"]))
        palette.setColor(QPalette.AlternateBase, QColor(theme["bg_surface"]))
        palette.setColor(QPalette.ToolTipBase, QColor(theme["bg_tab_selected"]))
        palette.setColor(QPalette.ToolTipText, QColor(theme["text_heading"]))
        palette.setColor(QPalette.Text, QColor(theme["text_primary"]))
        palette.setColor(QPalette.Button, QColor(theme["bg_surface"]))
        palette.setColor(QPalette.ButtonText, QColor(theme["text_primary"]))
        palette.setColor(QPalette.BrightText, QColor(theme["text_heading"]))
        palette.setColor(QPalette.Highlight, QColor(theme["accent"]))
        palette.setColor(QPalette.HighlightedText, QColor(theme["text_inverse"]))
        app.setPalette(palette)

        style_values: dict[str, str | int] = {
            **theme,
            "font_size": font_size,
            "tab_padding_y": tab_padding_y,
            "tab_padding_x": tab_padding_x,
            "tab_radius": tab_radius,
            "page_title_size": page_title_size,
            "subtitle_size": subtitle_size,
            "section_title_size": section_title_size,
            "radius_large": radius_large,
            "metric_value_size": metric_value_size,
            "radius_medium": radius_medium,
            "control_padding": control_padding,
            "button_padding_y": button_padding_y,
            "button_padding_x": button_padding_x,
            "header_padding": header_padding,
            "scroll_handle_size": scroll_handle_size,
            "scroll_radius": scroll_radius,
        }

        self.setStyleSheet(
            """
            QWidget {
                color: %(text_primary)s;
                font-family: 'Segoe UI';
                font-size: %(font_size)dpt;
                background: %(bg_app)s;
            }
            QMainWindow {
                background: %(bg_app)s;
            }
            QTabWidget::pane {
                border: 0;
                background: %(bg_app)s;
                margin-top: 8px;
            }
            QTabBar::tab {
                background: %(bg_tab)s;
                color: %(text_secondary)s;
                padding: %(tab_padding_y)dpx %(tab_padding_x)dpx;
                margin-right: 6px;
                margin-top: 4px;
                border: 1px solid %(border)s;
                border-bottom: 3px solid transparent;
                border-top-left-radius: %(tab_radius)dpx;
                border-top-right-radius: %(tab_radius)dpx;
            }
            QTabBar::tab:hover {
                background: %(bg_tab_selected)s;
                color: %(text_heading)s;
            }
            QTabBar::tab:selected {
                background: %(bg_tab_selected)s;
                color: %(text_heading)s;
                border-color: %(border_strong)s;
                border-bottom: 3px solid %(accent)s;
                margin-top: 0;
            }
            QLabel#PageTitle {
                font-size: %(page_title_size)dpt;
                font-weight: 700;
                color: %(text_heading)s;
            }
            QLabel#PageSubtitle {
                font-size: %(subtitle_size)dpt;
                color: %(text_muted)s;
            }
            QLabel#SectionTitle {
                font-size: %(section_title_size)dpt;
                font-weight: 600;
                color: %(text_heading)s;
            }
            QLabel[tone='muted'] {
                color: %(text_muted)s;
            }
            QLabel[tone='success'] {
                color: %(success)s;
            }
            QLabel[tone='warning'] {
                color: %(warning_secondary)s;
            }
            QLabel[tone='danger'] {
                color: %(danger)s;
            }
            QFrame#Panel, QFrame#MetricCard {
                background: %(bg_surface)s;
                border: 1px solid %(border)s;
                border-radius: %(radius_large)dpx;
            }
            QLabel#MetricCardTitle {
                color: %(text_muted)s;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            QLabel#MetricCardValue {
                color: %(text_heading)s;
                font-size: %(metric_value_size)dpt;
                font-weight: 700;
            }
            QLabel#MetricCardValue[tone='warning'] {
                color: %(danger)s;
            }
            QLineEdit, QDoubleSpinBox, QDateEdit, QComboBox, QTextEdit, QTableWidget {
                background: %(bg_surface_alt)s;
                color: %(text_primary)s;
                border: 1px solid %(border_strong)s;
                border-radius: %(radius_medium)dpx;
                padding: %(control_padding)dpx;
                selection-background-color: %(accent)s;
            }
            QLineEdit:focus, QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus, QTextEdit:focus, QTableWidget:focus {
                border: 1px solid %(focus_ring)s;
                background: %(bg_surface)s;
            }
            QLineEdit:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled, QComboBox:disabled, QTextEdit:disabled {
                color: %(text_disabled)s;
                background: %(bg_surface_disabled)s;
            }
            QComboBox QAbstractItemView, QMenu, QMenuBar, QCalendarWidget {
                background: %(bg_surface)s;
                color: %(text_primary)s;
                selection-background-color: %(accent)s;
                selection-color: %(text_inverse)s;
            }
            QComboBox::drop-down {
                border: 0;
                width: 28px;
            }
            QComboBox QAbstractItemView::item, QCalendarWidget QToolButton, QCalendarWidget QSpinBox {
                background: %(bg_surface)s;
                color: %(text_primary)s;
            }
            QAbstractItemView {
                background: %(bg_surface_alt)s;
                color: %(text_primary)s;
                selection-background-color: %(accent)s;
                selection-color: %(text_inverse)s;
            }
            QPushButton {
                background: %(accent)s;
                color: %(text_inverse)s;
                border: none;
                border-radius: %(radius_medium)dpx;
                padding: %(button_padding_y)dpx %(button_padding_x)dpx;
                font-weight: 700;
            }
            QPushButton:hover {
                background: %(accent_hover)s;
            }
            QPushButton:pressed {
                background: %(accent_pressed)s;
            }
            QPushButton:focus {
                border: 1px solid %(focus_ring)s;
                background: %(accent_hover)s;
            }
            QHeaderView::section {
                background: %(bg_header)s;
                color: %(text_secondary)s;
                padding: %(header_padding)dpx;
                border: none;
            }
            QTableWidget {
                gridline-color: %(border_grid)s;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:selected {
                background: %(accent_soft)s;
                color: %(text_heading)s;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: %(bg_app)s;
                border: 0;
                margin: 0;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: %(border_strong)s;
                border-radius: %(scroll_radius)dpx;
                min-height: %(scroll_handle_size)dpx;
                min-width: %(scroll_handle_size)dpx;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                background: none;
                border: 0;
            }
            QStatusBar {
                background: %(bg_surface_strong)s;
                color: %(text_secondary)s;
            }
            QMenuBar::item {
                background: transparent;
                padding: 6px 10px;
                border-radius: %(radius_medium)dpx;
            }
            QMenuBar::item:selected {
                background: %(bg_tab_selected)s;
                color: %(text_heading)s;
            }
            QMessageBox {
                background: %(bg_app)s;
            }
            QTextEdit#ChatLog {
                background: %(bg_surface_strong)s;
            }
            """
            % style_values
        )

    def refresh_all(self) -> None:
        # Materialize due recurring entries once per full refresh cycle.
        self.app_controller.materialize_due_recurring_items()
        self.refresh_category_controls()
        self.refresh_recurring_category_controls()
        self.refresh_dashboard()
        self.refresh_ledger_tables()
        self.refresh_recurring_table()
        self.refresh_charts()
        self.refresh_budget()
        self.refresh_assets()

    def _populate_period_selectors(self, month_combo: QComboBox, year_combo: QComboBox) -> None:
        month_combo.clear()
        for month_index in range(1, 13):
            month_combo.addItem(calendar.month_name[month_index], month_index)
        month_combo.setCurrentIndex(self._selected_month - 1)

        year_combo.clear()
        current_year = date.today().year
        for year_value in range(current_year - 5, current_year + 6):
            year_combo.addItem(str(year_value), year_value)
        year_index = year_combo.findText(str(self._selected_year))
        if year_index >= 0:
            year_combo.setCurrentIndex(year_index)

    def _sync_period_controls(
        self,
        source_month: QComboBox,
        source_year: QComboBox,
        target_month: QComboBox,
        target_year: QComboBox,
    ) -> None:
        target_month.blockSignals(True)
        target_year.blockSignals(True)
        target_month.setCurrentIndex(source_month.currentIndex())
        target_year.setCurrentIndex(source_year.currentIndex())
        target_month.blockSignals(False)
        target_year.blockSignals(False)

    def refresh_category_controls(self) -> None:
        expense_categories = self.transaction_controller.list_categories("expense")
        income_categories = self.transaction_controller.list_categories("income")

        self.expense_category.clear()
        self.expense_category.addItems([category.name for category in expense_categories])

        self.income_category.clear()
        self.income_category.addItems([category.name for category in income_categories])

        if self.expense_category.count() == 0:
            self.expense_category.addItem("Other")
        if self.income_category.count() == 0:
            self.income_category.addItem("Salary")

    def refresh_recurring_category_controls(self, *_: object) -> None:
        current_kind = self.recurring_kind.currentText() if hasattr(self, "recurring_kind") else "expense"
        categories = self.recurring_controller.list_categories(current_kind)
        current_text = self.recurring_category.currentText() if hasattr(self, "recurring_category") else ""

        self.recurring_category.clear()
        self.recurring_category.addItems([category.name for category in categories])

        if self.recurring_category.count() == 0:
            self.recurring_category.addItem("Other" if current_kind == "expense" else "Salary")

        if current_text:
            index = self.recurring_category.findText(current_text)
            if index >= 0:
                self.recurring_category.setCurrentIndex(index)
            else:
                self.recurring_category.setCurrentIndex(0)

        is_expense = current_kind == "expense"
        if hasattr(self, "recurring_asset_link_combo"):
            self.recurring_asset_link_combo.setEnabled(is_expense)
        if hasattr(self, "recurring_asset_payment_kind_combo"):
            self.recurring_asset_payment_kind_combo.setEnabled(is_expense)

    def refresh_dashboard(self) -> None:
        snapshot = self.analytics_controller.snapshot_for_month(self._selected_year, self._selected_month)
        self._set_metric_value(self.income_card, snapshot.income_total)
        self._set_metric_value(self.expense_card, snapshot.expense_total)
        self._set_metric_value(self.net_card, snapshot.net_total)
        self.count_card.set_value(str(snapshot.transaction_count))

        summary_lines = [f"{category}: ${total:,.2f}" for category, total in snapshot.top_categories] or [
            "No expenses recorded yet."
        ]
        self.category_summary.setPlainText("\n".join(summary_lines))

    def refresh_ledger_tables(self) -> None:
        transactions = self.transaction_controller.list_transactions_for_month(self._selected_year, self._selected_month, limit=250)
        self._refresh_ledger_category_filter_options(transactions)

        selected_category = str(self.ledger_category_filter.currentData() or "").strip()
        if selected_category:
            filtered_transactions = [tx for tx in transactions if tx.category == selected_category]
        else:
            filtered_transactions = transactions

        self._populate_table(self.recent_table, filtered_transactions[:10])
        self._populate_table(self.full_ledger_table, filtered_transactions)

    def refresh_recurring_table(self) -> None:
        recurring_items = self.recurring_controller.list_recurring_items()
        self.recurring_table.setRowCount(len(recurring_items))
        for row_index, item in enumerate(recurring_items):
            cells = [
                item.kind.title(),
                f"${item.amount:,.2f}",
                item.category,
                item.description,
                item.cadence_label,
                item.next_run_on.isoformat(),
                item.last_run_on.isoformat() if item.last_run_on else "-",
                "Yes" if item.is_active else "No",
            ]
            for column_index, text in enumerate(cells):
                widget_item = QTableWidgetItem(text)
                widget_item.setData(Qt.UserRole, item.id)  # Store the ID
                if column_index == 1:
                    widget_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.recurring_table.setItem(row_index, column_index, widget_item)

    def refresh_charts(self) -> None:
        selected_view = str(self.charts_view_selector.currentData() or "cashflow")
        if selected_view == "position":
            payload = self.analytics_controller.get_position_charts_payload(
                self._selected_year,
                self._selected_month,
                months_history=12,
            )
            self._render_position_charts(payload)
            return

        payload = self.analytics_controller.get_cashflow_charts_payload(
            self._selected_year,
            self._selected_month,
            months_history=6,
        )
        self._render_cashflow_charts(payload)

    def _render_cashflow_charts(self, payload: CashflowChartsPayload) -> None:
        snapshot = payload.snapshot

        self.charts_summary.setText(
            f"{calendar.month_name[self._selected_month]} {self._selected_year}: "
            f"Income ${snapshot.income_total:,.2f} | Expenses ${snapshot.expense_total:,.2f} | "
            f"Net ${snapshot.net_total:,.2f} | Transactions {snapshot.transaction_count}"
        )

        self.analytics_figure.clear()
        axes = self.analytics_figure.subplots(2, 2)
        self.analytics_figure.patch.set_facecolor("#111a27")

        day_numbers = [point.occurred_on.day for point in payload.daily_points]
        income_values = [point.income for point in payload.daily_points]
        expense_values = [point.expense for point in payload.daily_points]
        net_values = [point.net for point in payload.daily_points]

        history_labels = [
            f"{calendar.month_abbr[point.month]} {str(point.year)[-2:]}"
            for point in payload.monthly_points
        ]
        history_income = [point.income for point in payload.monthly_points]
        history_expense = [point.expense for point in payload.monthly_points]
        history_net = [point.net for point in payload.monthly_points]

        category_labels = [point.category for point in payload.expense_breakdown[:8]]
        category_values = [point.amount for point in payload.expense_breakdown[:8]]

        ax_daily, ax_history, ax_categories, ax_share = axes[0][0], axes[0][1], axes[1][0], axes[1][1]
        for axis in (ax_daily, ax_history, ax_categories, ax_share):
            self._style_chart_axis(axis)

        ax_daily.plot(day_numbers, income_values, color="#2ec4b6", linewidth=2.2, label="Income")
        ax_daily.plot(day_numbers, expense_values, color="#ff7b72", linewidth=2.2, label="Expenses")
        ax_daily.plot(day_numbers, net_values, color="#f2c14e", linewidth=2.2, label="Net")
        ax_daily.set_title("Daily Cash Flow", color="#f5f8ff")
        ax_daily.set_xlabel("Day")
        ax_daily.set_ylabel("Amount")
        ax_daily.legend(facecolor="#111a27", edgecolor="#233247", labelcolor="#e7edf7")

        ax_history.plot(history_labels, history_income, marker="o", color="#2ec4b6", linewidth=2.0, label="Income")
        ax_history.plot(history_labels, history_expense, marker="o", color="#ff7b72", linewidth=2.0, label="Expenses")
        ax_history.plot(history_labels, history_net, marker="o", color="#f2c14e", linewidth=2.0, label="Net")
        ax_history.set_title("Six-Month Trend", color="#f5f8ff")
        ax_history.tick_params(axis="x", rotation=20)
        ax_history.legend(facecolor="#111a27", edgecolor="#233247", labelcolor="#e7edf7")

        if category_labels:
            ax_categories.barh(category_labels, category_values, color="#4cc9f0")
            ax_categories.invert_yaxis()
            ax_categories.set_title("Expenses by Category", color="#f5f8ff")
            ax_categories.set_xlabel("Amount")
        else:
            ax_categories.text(0.5, 0.5, "No expense data for this month.", color="#e7edf7", ha="center", va="center")
            ax_categories.set_title("Expenses by Category", color="#f5f8ff")

        if category_labels:
            pie_colors = ["#2ec4b6", "#4cc9f0", "#f2c14e", "#ff7b72", "#90be6d", "#577590", "#f9844a", "#43aa8b"]
            ax_share.pie(
                category_values,
                labels=category_labels,
                colors=pie_colors[: len(category_values)],
                autopct="%1.0f%%",
                textprops={"color": "#041012"},
            )
            ax_share.set_title("Expense Share", color="#f5f8ff")
        else:
            ax_share.text(0.5, 0.5, "No category mix yet.", color="#e7edf7", ha="center", va="center")
            ax_share.set_title("Expense Share", color="#f5f8ff")

        self.analytics_figure.tight_layout()
        self.analytics_canvas.draw_idle()

    def _render_position_charts(self, payload: PositionChartsPayload) -> None:
        debt_labels = ", ".join(point.label for point in payload.debt_composition[:3])
        debt_context = f" | Debt Drivers {debt_labels}" if debt_labels else ""
        self.charts_summary.setText(
            f"{calendar.month_name[self._selected_month]} {self._selected_year}: "
            f"Net Worth ${payload.total_net_worth:,.2f} | Debt ${payload.total_debt:,.2f} | "
            f"Assets ${payload.total_asset_value:,.2f} | Tracked Assets {len(payload.assets)}{debt_context}"
        )

        self.analytics_figure.clear()
        axes = self.analytics_figure.subplots(2, 2)
        self.analytics_figure.patch.set_facecolor("#111a27")

        ax_net_worth, ax_debt, ax_savings, ax_allocation = axes[0][0], axes[0][1], axes[1][0], axes[1][1]
        for axis in (ax_net_worth, ax_debt, ax_savings, ax_allocation):
            self._style_chart_axis(axis)

        if payload.monthly_points:
            labels = [f"{calendar.month_abbr[p.month]} {str(p.year)[-2:]}" for p in payload.monthly_points]
            net_worth_series = [p.estimated_net_worth for p in payload.monthly_points]
            debt_series = [p.estimated_total_debt for p in payload.monthly_points]
            savings_rate_series = [p.savings_rate * 100.0 for p in payload.monthly_points]

            ax_net_worth.plot(labels, net_worth_series, marker="o", color="#2ec4b6", linewidth=2.2)
            ax_net_worth.set_title("Estimated Net Worth Trend", color="#f5f8ff")
            ax_net_worth.tick_params(axis="x", rotation=20)
            ax_net_worth.set_ylabel("Amount")

            ax_debt.plot(labels, debt_series, marker="o", color="#ff7b72", linewidth=2.2)
            ax_debt.set_title("Estimated Total Debt Trend", color="#f5f8ff")
            ax_debt.tick_params(axis="x", rotation=20)
            ax_debt.set_ylabel("Amount")

            ax_savings.plot(labels, savings_rate_series, marker="o", color="#4cc9f0", linewidth=2.2)
            ax_savings.axhline(20.0, color="#f2c14e", linestyle="--", linewidth=1.4, label="20% target")
            ax_savings.set_title("Savings Rate Trend", color="#f5f8ff")
            ax_savings.tick_params(axis="x", rotation=20)
            ax_savings.set_ylabel("Percent")
            ax_savings.legend(facecolor="#111a27", edgecolor="#233247", labelcolor="#e7edf7")
        else:
            ax_net_worth.text(0.5, 0.5, "No monthly position history yet.", color="#e7edf7", ha="center", va="center")
            ax_net_worth.set_title("Estimated Net Worth Trend", color="#f5f8ff")
            ax_debt.text(0.5, 0.5, "No monthly debt history yet.", color="#e7edf7", ha="center", va="center")
            ax_debt.set_title("Estimated Total Debt Trend", color="#f5f8ff")
            ax_savings.text(0.5, 0.5, "No savings-rate history yet.", color="#e7edf7", ha="center", va="center")
            ax_savings.set_title("Savings Rate Trend", color="#f5f8ff")

        allocation_rows: list[tuple[str, float]] = []
        for asset in payload.assets:
            if asset.asset_type == "house":
                value = float(asset.house_value)
            else:
                value = float(asset.investment_worth)
            if value > 0:
                allocation_rows.append((asset.name, value))

        if allocation_rows:
            labels = [name for name, _ in allocation_rows]
            values = [amount for _, amount in allocation_rows]
            pie_colors = ["#2ec4b6", "#4cc9f0", "#f2c14e", "#90be6d", "#43aa8b", "#577590", "#f9844a", "#ff7b72"]
            ax_allocation.pie(
                values,
                labels=labels,
                colors=pie_colors[: len(values)],
                autopct="%1.0f%%",
                textprops={"color": "#041012"},
            )
            ax_allocation.set_title("Asset Allocation", color="#f5f8ff")
        else:
            ax_allocation.text(0.5, 0.5, "No asset allocation data.", color="#e7edf7", ha="center", va="center")
            ax_allocation.set_title("Asset Allocation", color="#f5f8ff")

        self.analytics_figure.tight_layout()
        self.analytics_canvas.draw_idle()

    def _style_chart_axis(self, axis: object) -> None:
        axis.set_facecolor("#111a27")
        axis.tick_params(colors="#cbd6e8")
        for spine in axis.spines.values():
            spine.set_color("#233247")
        axis.title.set_color("#f5f8ff")
        axis.xaxis.label.set_color("#9fb0c7")
        axis.yaxis.label.set_color("#9fb0c7")
        axis.grid(color="#1f2d40", alpha=0.45)

    def _populate_table(self, table: QTableWidget, transactions: list[Transaction]) -> None:
        table.setRowCount(len(transactions))
        for row_index, transaction in enumerate(transactions):
            cells = [
                transaction.occurred_on.isoformat(),
                transaction.kind.title(),
                transaction.category,
                transaction.description,
                f"${abs(transaction.amount):,.2f}",
            ]
            for column_index, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column_index == 0:
                    item.setData(Qt.UserRole, transaction.id)
                if column_index == 4:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(row_index, column_index, item)

    def _set_metric_value(self, card: MetricCard, amount: float, is_warning: bool = False) -> None:
        card.set_value(f"${amount:,.2f}", is_warning=is_warning)

    def _handle_period_changed(self) -> None:
        self.app_controller.materialize_due_recurring_items()
        self._selected_month = int(self.month_toggle.currentData())
        self._selected_year = int(self.year_toggle.currentData())
        self._sync_period_controls(self.month_toggle, self.year_toggle, self.charts_month_toggle, self.charts_year_toggle)
        self.refresh_dashboard()
        self.refresh_ledger_tables()
        self.refresh_charts()

        month_name = calendar.month_name[self._selected_month]
        self.status_bar.showMessage(f"Viewing {month_name} {self._selected_year}.", 3000)

    def _handle_chart_period_changed(self) -> None:
        self.app_controller.materialize_due_recurring_items()
        self._selected_month = int(self.charts_month_toggle.currentData())
        self._selected_year = int(self.charts_year_toggle.currentData())
        self._sync_period_controls(self.charts_month_toggle, self.charts_year_toggle, self.month_toggle, self.year_toggle)
        self.refresh_dashboard()
        self.refresh_ledger_tables()
        self.refresh_charts()

        month_name = calendar.month_name[self._selected_month]
        self.status_bar.showMessage(f"Viewing {month_name} {self._selected_year}.", 3000)

    def add_expense(self) -> None:
        self._add_transaction(
            kind="expense",
            amount=self.expense_amount.value(),
            category=self.expense_category.currentText(),
            description=self.expense_description.text(),
            occurred_on=self.expense_date.date(),
            payment_kind=self.expense_asset_payment_kind_combo.currentData(),
        )

    def add_income(self) -> None:
        self._add_transaction(
            kind="income",
            amount=self.income_amount.value(),
            category=self.income_category.currentText(),
            description=self.income_description.text(),
            occurred_on=self.income_date.date(),
        )

    def add_recurring_item(self) -> None:
        amount = self.recurring_amount.value()
        description = self.recurring_description.text().strip()
        category = self.recurring_category.currentText().strip()
        interval_count = int(self.recurring_interval_count.value())

        if amount <= 0:
            QMessageBox.warning(self, APP_NAME, "Enter a recurring amount greater than zero.")
            return
        if not description:
            QMessageBox.warning(self, APP_NAME, "Add a short description before saving.")
            return
        if not category:
            QMessageBox.warning(self, APP_NAME, "Choose or type a category before saving.")
            return

        start_on = self._qdate_to_date(self.recurring_start_date.date())
        recurring_id = self.recurring_controller.add_recurring_item(
            kind=self.recurring_kind.currentText(),
            amount=amount,
            category=category,
            description=description,
            interval_count=interval_count,
            interval_unit=self.recurring_interval_unit.currentText(),
            start_on=start_on,
        )

        if self.recurring_kind.currentText() == "expense":
            selected_asset_id = self.recurring_asset_link_combo.currentData()
            if selected_asset_id is not None:
                try:
                    self.recurring_controller.link_expense_to_asset(
                        int(selected_asset_id),
                        "recurring",
                        recurring_id,
                        payment_kind=str(self.recurring_asset_payment_kind_combo.currentData() or "mortgage"),
                    )
                except Exception:
                    QMessageBox.warning(self, APP_NAME, "Recurring item was saved, but could not be linked to the selected asset.")

        self.status_bar.showMessage("Saved recurring item.", 4000)
        self.refresh_all()
        self.recurring_amount.setValue(0.0)
        self.recurring_description.clear()
        self.recurring_asset_link_combo.setCurrentIndex(0)
        self.recurring_asset_payment_kind_combo.setCurrentIndex(0)

    def edit_selected_recurring(self) -> None:
        """Open edit dialog for selected recurring item."""
        current_row = self.recurring_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, APP_NAME, "Select a recurring item to edit.")
            return

        # Get the ID from the first column
        item = self.recurring_table.item(current_row, 0)
        recurring_id = item.data(Qt.UserRole)

        # Get the recurring item
        all_items = self.recurring_controller.list_recurring_items(active_only=False)
        recurring_item = next((item for item in all_items if item.id == recurring_id), None)

        if not recurring_item:
            QMessageBox.warning(self, APP_NAME, "Could not find recurring item.")
            return

        # Create edit dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit Recurring Item")
        dialog.setMinimumSize(460, 420)
        dialog.resize(560, 540)

        layout = QFormLayout(dialog)

        # Type
        kind_combo = QComboBox()
        kind_combo.addItems(["expense", "income"])
        kind_combo.setCurrentText(recurring_item.kind)
        layout.addRow("Type", kind_combo)

        # Amount
        amount_spin = QDoubleSpinBox()
        amount_spin.setMaximum(1_000_000)
        amount_spin.setDecimals(2)
        amount_spin.setPrefix("$")
        amount_spin.setValue(recurring_item.amount)
        layout.addRow("Amount", amount_spin)

        # Category dropdown
        category_combo = QComboBox()
        category_combo.setEditable(False)
        categories = self.recurring_controller.list_categories(kind=recurring_item.kind)
        for cat in categories:
            category_combo.addItem(cat.name, cat.name)
        category_combo.setCurrentText(recurring_item.category)
        layout.addRow("Category", category_combo)

        # Description
        description_edit = QLineEdit()
        description_edit.setText(recurring_item.description)
        layout.addRow("Description", description_edit)

        # Interval count
        interval_spin = QSpinBox()
        interval_spin.setMinimum(1)
        interval_spin.setMaximum(3650)
        interval_spin.setValue(recurring_item.interval_count)
        layout.addRow("Every N months", interval_spin)

        # Start date
        start_date_edit = QDateEdit()
        start_date_edit.setCalendarPopup(True)
        start_date_edit.setDate(QDate(recurring_item.start_on.year, recurring_item.start_on.month, recurring_item.start_on.day))
        layout.addRow("Start Date", start_date_edit)

        # Active status
        active_check = QCheckBox()
        active_check.setChecked(recurring_item.is_active)
        layout.addRow("Active", active_check)

        # Optional asset link for recurring expenses
        edit_asset_link_combo = QComboBox()
        edit_asset_link_combo.addItem("No asset link", None)
        for asset in self.recurring_controller.list_assets():
            edit_asset_link_combo.addItem(f"{asset.name} ({asset.asset_type.title()})", int(asset.id))
        current_link = self.recurring_controller.get_expense_asset_link("recurring", recurring_id)
        current_asset_id = current_link["asset_id"] if current_link else None
        current_payment_kind = str(current_link["payment_kind"] if current_link else "mortgage")
        current_asset_index = edit_asset_link_combo.findData(current_asset_id)
        edit_asset_link_combo.setCurrentIndex(current_asset_index if current_asset_index >= 0 else 0)
        edit_asset_link_combo.setEnabled(recurring_item.kind == "expense")
        layout.addRow("Link To Asset", edit_asset_link_combo)

        edit_payment_kind_combo = QComboBox()
        edit_payment_kind_combo.addItem("Mortgage", "mortgage")
        edit_payment_kind_combo.addItem("Principal", "principal")
        payment_index = edit_payment_kind_combo.findData(current_payment_kind)
        edit_payment_kind_combo.setCurrentIndex(payment_index if payment_index >= 0 else 0)
        edit_payment_kind_combo.setEnabled(recurring_item.kind == "expense")
        layout.addRow("Apply As", edit_payment_kind_combo)

        def on_kind_changed(new_kind: str) -> None:
            categories_local = self.recurring_controller.list_categories(kind=new_kind)
            category_combo.clear()
            for category in categories_local:
                category_combo.addItem(category.name, category.name)
            if recurring_item.kind == new_kind:
                category_combo.setCurrentText(recurring_item.category)
            elif category_combo.count() > 0:
                category_combo.setCurrentIndex(0)
            edit_asset_link_combo.setEnabled(new_kind == "expense")
            edit_payment_kind_combo.setEnabled(new_kind == "expense")

        kind_combo.currentTextChanged.connect(on_kind_changed)

        # Buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save Changes")
        cancel_button = QPushButton("Cancel")

        def save_changes():
            new_kind = kind_combo.currentText()
            new_amount = amount_spin.value()
            new_category = category_combo.currentText()
            new_description = description_edit.text().strip()
            new_interval = int(interval_spin.value())
            new_start = self._qdate_to_date(start_date_edit.date())
            new_active = active_check.isChecked()

            if new_amount <= 0:
                QMessageBox.warning(self, APP_NAME, "Amount must be greater than zero.")
                return
            if not new_description:
                QMessageBox.warning(self, APP_NAME, "Description is required.")
                return

            success = self.recurring_controller.update_recurring_item(
                recurring_id,
                kind=new_kind,
                amount=new_amount,
                category=new_category,
                description=new_description,
                interval_count=new_interval,
                start_on=new_start,
                is_active=new_active,
            )

            if success:
                try:
                    if new_kind == "expense":
                        self.recurring_controller.set_expense_asset_link(
                            edit_asset_link_combo.currentData(),
                            "recurring",
                            recurring_id,
                            payment_kind=str(edit_payment_kind_combo.currentData() or "mortgage"),
                        )
                    else:
                        self.recurring_controller.set_expense_asset_link(None, "recurring", recurring_id)
                except Exception:
                    QMessageBox.warning(self, APP_NAME, "Recurring item was updated, but the asset link could not be updated.")

                # If category changed, recategorize existing transactions from this recurring item
                if new_category != recurring_item.category:
                    self.recurring_controller.change_transaction_category(
                        from_category=recurring_item.category,
                        to_category=new_category,
                        description_filter=recurring_item.description,
                    )
                    self.status_bar.showMessage(
                        f"Recurring item and transactions updated (recategorized from {recurring_item.category} to {new_category}).",
                        4000,
                    )
                else:
                    self.status_bar.showMessage("Recurring item updated.", 4000)
                self.refresh_all()
                dialog.accept()
            else:
                QMessageBox.critical(self, APP_NAME, "Failed to update recurring item.")

        save_button.clicked.connect(save_changes)
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addRow(button_layout)

        dialog.exec_()

    def delete_selected_recurring(self) -> None:
        """Delete selected recurring item."""
        current_row = self.recurring_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, APP_NAME, "Select a recurring item to delete.")
            return

        item = self.recurring_table.item(current_row, 0)
        recurring_id = item.data(Qt.UserRole)
        description = self.recurring_table.item(current_row, 3).text()

        reply = QMessageBox.question(
            self,
            APP_NAME,
            f"Delete recurring item:\n{description}?\n\nThis will NOT remove past transactions.",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            success = self.recurring_controller.delete_recurring_item(recurring_id)
            if success:
                self.status_bar.showMessage(f"Deleted recurring item: {description}", 4000)
                self.refresh_all()
            else:
                QMessageBox.critical(self, APP_NAME, "Failed to delete recurring item.")

    def _qdate_to_date(self, value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    def _add_transaction(
        self,
        kind: str,
        amount: float,
        category: str,
        description: str,
        occurred_on: QDate,
        payment_kind: object | None = None,
    ) -> None:
        if amount <= 0:
            QMessageBox.warning(self, APP_NAME, "Enter an amount greater than zero.")
            return
        if not description.strip():
            QMessageBox.warning(self, APP_NAME, "Add a short description before saving.")
            return

        transaction_date = self._qdate_to_date(occurred_on)
        if kind == "expense":
            transaction_id = self.transaction_controller.add_expense(amount, category, description, transaction_date)
            selected_asset_id = self.expense_asset_link_combo.currentData()
            if selected_asset_id is not None:
                try:
                    self.transaction_controller.link_expense_to_asset(
                        int(selected_asset_id),
                        "transaction",
                        transaction_id,
                        payment_kind=str(payment_kind or self.expense_asset_payment_kind_combo.currentData() or "mortgage"),
                    )
                except Exception:
                    QMessageBox.warning(self, APP_NAME, "Expense was saved, but could not be linked to the selected asset.")
        else:
            self.transaction_controller.add_income(amount, category, description, transaction_date)

        self.status_bar.showMessage(f"Saved {kind} entry in {category}.", 4000)
        self.refresh_all()
        self._clear_entry_form(kind)

    def _clear_entry_form(self, kind: str) -> None:
        if kind == "expense":
            self.expense_amount.setValue(0.0)
            self.expense_description.clear()
            self.expense_asset_link_combo.setCurrentIndex(0)
            self.expense_asset_payment_kind_combo.setCurrentIndex(0)
        else:
            self.income_amount.setValue(0.0)
            self.income_description.clear()

    def edit_selected_recent_transaction(self) -> None:
        current_row = self.recent_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, APP_NAME, "Select a recent transaction to edit first.")
            return

        id_item = self.recent_table.item(current_row, 0)
        transaction_id = id_item.data(Qt.UserRole) if id_item is not None else None
        if transaction_id is None:
            QMessageBox.warning(self, APP_NAME, "Could not determine selected transaction ID.")
            return

        transaction = self.transaction_controller.get_transaction_by_id(int(transaction_id))
        if transaction is None:
            QMessageBox.warning(self, APP_NAME, "Selected transaction no longer exists.")
            self.refresh_all()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Recent Transaction")
        dialog.setMinimumSize(420, 340)
        dialog.resize(520, 420)
        form = QFormLayout(dialog)

        kind_label = QLabel(transaction.kind.title())
        form.addRow("Type", kind_label)

        amount_spin = QDoubleSpinBox()
        amount_spin.setMaximum(1_000_000)
        amount_spin.setDecimals(2)
        amount_spin.setPrefix("$")
        amount_spin.setValue(float(transaction.amount))
        form.addRow("Amount", amount_spin)

        category_combo = QComboBox()
        category_combo.setEditable(True)
        categories = self.transaction_controller.list_categories(transaction.kind)
        category_combo.addItems([c.name for c in categories])
        category_combo.setCurrentText(transaction.category)
        form.addRow("Category", category_combo)

        description_edit = QLineEdit()
        description_edit.setText(transaction.description)
        form.addRow("Description", description_edit)

        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDate(QDate(transaction.occurred_on.year, transaction.occurred_on.month, transaction.occurred_on.day))
        form.addRow("Date", date_edit)

        button_row = QHBoxLayout()
        save_button = QPushButton("Save Changes")
        cancel_button = QPushButton("Cancel")
        button_row.addWidget(save_button)
        button_row.addWidget(cancel_button)
        form.addRow(button_row)

        def save_changes() -> None:
            amount = amount_spin.value()
            category = category_combo.currentText().strip()
            description = description_edit.text().strip()
            occurred_on = self._qdate_to_date(date_edit.date())

            if amount <= 0:
                QMessageBox.warning(dialog, APP_NAME, "Amount must be greater than zero.")
                return
            if not category:
                QMessageBox.warning(dialog, APP_NAME, "Category is required.")
                return
            if not description:
                QMessageBox.warning(dialog, APP_NAME, "Description is required.")
                return

            updated = self.transaction_controller.update_transaction(
                transaction_id=int(transaction_id),
                amount=amount,
                category=category,
                description=description,
                occurred_on=occurred_on,
            )
            if not updated:
                QMessageBox.critical(dialog, APP_NAME, "Failed to update transaction.")
                return

            self.status_bar.showMessage("Recent transaction updated.", 4000)
            self.refresh_all()
            dialog.accept()

        save_button.clicked.connect(save_changes)
        cancel_button.clicked.connect(dialog.reject)
        dialog.exec_()

    def delete_selected_transaction(self, table: QTableWidget) -> None:
        selected_rows = sorted({index.row() for index in table.selectionModel().selectedRows()})
        if not selected_rows:
            QMessageBox.information(self, APP_NAME, "Select an income or expense to delete first.")
            return

        reply = QMessageBox.question(
            self,
            APP_NAME,
            f"Delete {len(selected_rows)} selected transaction(s)? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        deleted_count = 0
        for row_index in selected_rows:
            item = table.item(row_index, 0)
            transaction_id = item.data(Qt.UserRole) if item is not None else None
            if transaction_id is None:
                continue
            if self.transaction_controller.delete_transaction(int(transaction_id)):
                deleted_count += 1

        if deleted_count == 0:
            QMessageBox.warning(self, APP_NAME, "No selected transactions could be deleted.")
            return

        self.status_bar.showMessage(f"Deleted {deleted_count} transaction(s).", 4000)
        self.refresh_all()

    def send_prompt(self) -> None:
        prompt_text = self.chat_input.text().strip()
        if not prompt_text:
            return

        if self._ollama_warmup_worker is not None and self._ollama_warmup_worker.isRunning():
            QMessageBox.information(self, APP_NAME, "Ollama is still starting. Try again in a moment.")
            return

        readiness_error = self.assistant_service.client.readiness_error()
        if readiness_error:
            QMessageBox.warning(self, APP_NAME, readiness_error)
            self.status_bar.showMessage(readiness_error, 5000)
            return

        self.send_button.setEnabled(False)
        self.status_bar.showMessage("Checking Ollama before sending the question...", 0)
        self._ollama_warmup_worker = OllamaWarmupWorker(self.assistant_service)
        self._ollama_warmup_worker.ready.connect(lambda: self._send_prompt_after_warmup(prompt_text))
        self._ollama_warmup_worker.failed.connect(self._handle_ollama_failure)
        self._ollama_warmup_worker.start()

    def _warmup_ollama(self) -> None:
        if self._ollama_warmup_worker is not None and self._ollama_warmup_worker.isRunning():
            return

        self.status_bar.showMessage("Starting Ollama in the background...", 5000)
        self._ollama_warmup_worker = OllamaWarmupWorker(self.assistant_service)
        self._ollama_warmup_worker.ready.connect(self._handle_ollama_ready)
        self._ollama_warmup_worker.failed.connect(self._handle_ollama_failure)
        self._ollama_warmup_worker.start()

    def _send_prompt_after_warmup(self, prompt_text: str) -> None:
        self.chat_input.clear()
        self.chat_log.append(f"<b>You:</b> {prompt_text}")
        self.send_button.setEnabled(False)
        self.status_bar.showMessage("Thinking with the local assistant...", 0)

        self._assistant_worker = AssistantWorker(self.assistant_service, prompt_text)
        self._assistant_worker.result_ready.connect(self._handle_assistant_result)
        self._assistant_worker.failed.connect(self._handle_assistant_failure)
        self._assistant_worker.start()

    def _handle_ollama_ready(self) -> None:
        self.status_bar.showMessage("Ollama is ready.", 3000)
        self.send_button.setEnabled(True)

    def _handle_ollama_failure(self, error_text: str) -> None:
        self.status_bar.showMessage("Ollama is not responding.", 5000)
        self.send_button.setEnabled(True)
        QMessageBox.warning(
            self,
            APP_NAME,
            f"Ollama is not responding yet:\n\n{error_text}\n\nStart Ollama and try again.",
        )

    def _refresh_available_models(self) -> None:
        """Fetch available models from Ollama and populate the dropdown."""
        available_models = self.assistant_service.client.list_available_models()
        current_model = self.assistant_service.client.model
        
        self.model_selector.blockSignals(True)
        self.model_selector.clear()
        
        if available_models:
            self.model_selector.addItems(available_models)
            if current_model in available_models:
                self.model_selector.setCurrentText(current_model)
            else:
                self.model_selector.setCurrentIndex(0)
        else:
            self.model_selector.addItem("(No models found)")
            self.model_selector.setEnabled(False)
        
        self.model_selector.blockSignals(False)
        self.status_bar.showMessage(f"Found {len(available_models)} model(s).", 3000)

    def _handle_model_changed(self, model_name: str) -> None:
        """Handle model selection change."""
        if not model_name or model_name == "(No models found)":
            return
        
        self.assistant_service.client.set_model(model_name)
        self.app_controller.set_setting("selected_model", model_name)
        self.status_bar.showMessage(f"Switched to model: {model_name}", 3000)

    def _toggle_voice_listener(self) -> None:
        self._toggle_voice_listener_for_mode("assistant")

    def _toggle_voice_test_listener(self) -> None:
        self._toggle_voice_listener_for_mode("testing")

    def _toggle_voice_listener_for_mode(self, mode: str) -> None:
        if self.voice_enabled and self._voice_active_surface == mode:
            self.voice_coordinator.stop()
            self.voice_enabled = False
            self._voice_active_surface = None
            self._reset_voice_surfaces_after_stop()
            self.status_bar.showMessage("Voice listener stopped.", 3000)
            return

        if self.voice_enabled and self._voice_active_surface != mode:
            self.voice_coordinator.stop()
            self.voice_enabled = False

        self._voice_active_surface = mode
        self.voice_coordinator.start()
        self.voice_enabled = True
        self._reset_voice_surfaces_after_stop()
        self._set_voice_surface_button_text(mode, "Stop Voice")
        self._set_voice_surface_status_text(mode, "Voice: Listening for 'Hey Steven'...")
        self._set_voice_surface_partial_text(mode, "Live transcript: (waiting)")
        self.status_bar.showMessage("Voice listener started.", 3000)

    def _handle_voice_status(self, message: str) -> None:
        mode = self._voice_active_surface or "assistant"
        self._set_voice_surface_status_text(mode, f"Voice: {message}")
        self.status_bar.showMessage(message, 2500)

    def _handle_voice_error(self, message: str) -> None:
        mode = self._voice_active_surface or "assistant"
        self._set_voice_surface_status_text(mode, "Voice: Error")
        self.status_bar.showMessage(message, 6000)
        if mode == "assistant":
            self.chat_log.append(f"<i>Voice error:</i> {html.escape(message)}")
        else:
            output_box = self._voice_output_box(mode)
            if output_box is not None:
                output_box.append(f"[Voice error] {message}")
        self._set_voice_surface_last_command_text(mode, "Last voice command: (error - see output)")

    def _handle_voice_wake(self, source_id: str) -> None:
        mode = self._voice_active_surface or "assistant"
        if mode == "assistant":
            self.chat_log.append(f"<i>Wake detected from {html.escape(source_id)}. Listening...</i>")
        else:
            output_box = self._voice_output_box(mode)
            if output_box is not None:
                output_box.append(f"[Wake detected] {source_id}")
        self._set_voice_surface_partial_text(mode, "Live transcript: (listening)")

    def _handle_voice_partial(self, partial_text: str) -> None:
        mode = self._voice_active_surface or "assistant"
        text = partial_text.strip()
        if not text:
            self._set_voice_surface_partial_text(mode, "Live transcript: (waiting)")
            return
        self._set_voice_surface_partial_text(mode, f"Live transcript: {text}")

    def _handle_voice_diagnostic(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return

        mode = self._voice_active_surface or "assistant"
        widgets = self._voice_ui.get(mode)
        if widgets is None:
            return

        stage = str(payload.get("stage", "")).strip() or "-"
        provider = str(payload.get("provider", "")).strip() or "-"
        fallback_reason = str(payload.get("fallback_reason", "")).strip() or "-"
        endpoint_reason = str(payload.get("endpoint_reason", "")).strip() or "-"
        wake_mode = str(payload.get("wake_mode", "")).strip() or "-"

        confidence_raw = payload.get("confidence")
        confidence = "-"
        if isinstance(confidence_raw, (float, int)):
            confidence = f"{float(confidence_raw):.2f}"

        latency_raw = payload.get("latency_ms")
        latency = "-"
        if isinstance(latency_raw, (float, int)):
            latency = f"{int(latency_raw)} ms"

        speech_raw = payload.get("speech_ms")
        speech_ms = "-"
        if isinstance(speech_raw, (float, int)):
            speech_ms = f"{int(speech_raw)}"

        widgets["diag_stage"].setText(stage)  # type: ignore[call-arg]
        widgets["diag_provider"].setText(provider)  # type: ignore[call-arg]
        widgets["diag_confidence"].setText(confidence)  # type: ignore[call-arg]
        widgets["diag_latency"].setText(latency)  # type: ignore[call-arg]
        widgets["diag_fallback"].setText(fallback_reason)  # type: ignore[call-arg]
        widgets["diag_endpoint"].setText(endpoint_reason)  # type: ignore[call-arg]
        widgets["diag_speech_ms"].setText(speech_ms)  # type: ignore[call-arg]
        widgets["diag_wake_mode"].setText(wake_mode)  # type: ignore[call-arg]

    def _handle_voice_command(self, command_text: str) -> None:
        if not command_text.strip():
            return
        mode = self._voice_active_surface or "assistant"
        self._set_voice_surface_last_command_text(mode, f"Last voice command: {command_text}")
        self._set_voice_surface_partial_text(mode, "Live transcript: (sent)")

        if mode == "assistant":
            self.chat_input.setText(command_text)
            self.chat_log.append(f"<b>You (voice):</b> {html.escape(command_text)}")
            self.send_prompt()
            return

        output_box = self._voice_output_box(mode)
        if output_box is not None:
            output_box.append(command_text)

    def _load_wake_phrase_setting(self) -> str:
        raw_value = self.app_controller.get_setting("voice_wake_phrase", "hey steven") or "hey steven"
        normalized = " ".join(raw_value.strip().split())
        return normalized or "hey steven"

    def _bind_voice_coordinator_callbacks(self) -> None:
        self.voice_coordinator.on_status = self.voice_status_signal.emit
        self.voice_coordinator.on_error = self.voice_error_signal.emit
        self.voice_coordinator.on_wake = self.voice_wake_signal.emit
        self.voice_coordinator.on_command = self.voice_command_signal.emit
        self.voice_coordinator.on_partial = self.voice_partial_signal.emit
        self.voice_coordinator.on_diagnostic = self.voice_diagnostic_signal.emit

    def _voice_start_button_label(self) -> str:
        return f"Start Voice ({self._display_wake_phrase()})"

    def _display_wake_phrase(self) -> str:
        return self._wake_phrase.title()

    def _apply_wake_phrase_from_surface(self, mode: str) -> None:
        widgets = self._voice_ui.get(mode)
        if widgets is None:
            return

        wake_input = widgets.get("wake_input")
        if not isinstance(wake_input, QLineEdit):
            return

        new_phrase = " ".join(wake_input.text().strip().split())
        if not new_phrase:
            QMessageBox.warning(self, APP_NAME, "Wake phrase cannot be empty.")
            return

        was_running = self.voice_enabled
        active_surface = self._voice_active_surface
        if was_running:
            self.voice_coordinator.stop()
            self.voice_enabled = False

        self._wake_phrase = new_phrase
        self.app_controller.set_setting("voice_wake_phrase", new_phrase)
        self.voice_coordinator = VoiceCoordinator(wake_phrase=new_phrase)
        self._bind_voice_coordinator_callbacks()
        self._sync_wake_phrase_inputs()
        self._reset_voice_surfaces_after_stop()
        self.status_bar.showMessage(f"Wake phrase updated to '{self._display_wake_phrase()}'.", 4000)

        if was_running and active_surface is not None:
            self._voice_active_surface = active_surface
            self.voice_coordinator.start()
            self.voice_enabled = True
            self._set_voice_surface_button_text(active_surface, "Stop Voice")
            self._set_voice_surface_status_text(
                active_surface,
                f"Voice: Listening for '{self._display_wake_phrase()}'...",
            )
            self._set_voice_surface_partial_text(active_surface, "Live transcript: (waiting)")

    def _sync_wake_phrase_inputs(self) -> None:
        for widgets in self._voice_ui.values():
            wake_input = widgets.get("wake_input")
            if isinstance(wake_input, QLineEdit):
                wake_input.setText(self._wake_phrase)

    def _set_voice_surface_status_text(self, mode: str, text: str) -> None:
        widgets = self._voice_ui.get(mode)
        if widgets is not None:
            widgets["status"].setText(text)  # type: ignore[call-arg]

    def _set_voice_surface_last_command_text(self, mode: str, text: str) -> None:
        widgets = self._voice_ui.get(mode)
        if widgets is not None:
            widgets["last_command"].setText(text)  # type: ignore[call-arg]

    def _set_voice_surface_partial_text(self, mode: str, text: str) -> None:
        widgets = self._voice_ui.get(mode)
        if widgets is not None:
            widgets["partial"].setText(text)  # type: ignore[call-arg]

    def _set_voice_surface_button_text(self, mode: str, text: str) -> None:
        widgets = self._voice_ui.get(mode)
        if widgets is not None:
            widgets["button"].setText(text)  # type: ignore[call-arg]

    def _voice_output_box(self, mode: str) -> QTextEdit | None:
        widgets = self._voice_ui.get(mode)
        if widgets is None:
            return None
        output = widgets.get("output")
        return output if isinstance(output, QTextEdit) else None

    def _reset_voice_surfaces_after_stop(self) -> None:
        for mode in self._voice_ui:
            self._set_voice_surface_button_text(mode, self._voice_start_button_label())
            self._set_voice_surface_status_text(mode, "Voice: Off")
            self._set_voice_surface_partial_text(mode, "Live transcript: (off)")

    def _handle_assistant_result(self, result: AssistantResult) -> None:
        formatted_reply = self._format_assistant_reply_html(result.reply)
        response_lines = [f"<b>Assistant:</b> {formatted_reply}"]
        if result.applied_actions:
            response_lines.append("<i>Applied:</i> " + "; ".join(result.applied_actions))
        for table_payload in result.display_tables:
            response_lines.append(self._format_assistant_table_html(table_payload))
        self.chat_log.append("<br>".join(response_lines))
        self.status_bar.showMessage("Assistant response complete.", 4000)
        self.send_button.setEnabled(True)
        self.refresh_all()

    def _format_assistant_reply_html(self, reply_text: str) -> str:
        """Render assistant text as structured HTML while preserving all content."""
        if not reply_text:
            return ""

        lines = reply_text.splitlines()
        chunks: list[str] = []
        i = 0

        while i < len(lines):
            line = lines[i].rstrip("\n")
            stripped = line.strip()

            if not stripped:
                chunks.append("<br>")
                i += 1
                continue

            # Markdown heading support
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading_match:
                level = min(6, len(heading_match.group(1)) + 1)
                chunks.append(f"<h{level} style='margin:8px 0 4px 0; color:#f5f8ff;'>{html.escape(heading_match.group(2))}</h{level}>")
                i += 1
                continue

            # Section heading support (e.g., "Summary:" or "Recommendations")
            if self._looks_like_section_heading(stripped):
                chunks.append(f"<h4 style='margin:8px 0 4px 0; color:#f5f8ff;'>{html.escape(stripped.rstrip(':'))}</h4>")
                i += 1
                continue

            # Markdown/simple table support
            if "|" in stripped:
                table_html, consumed = self._parse_text_table(lines, i)
                if consumed > 0:
                    chunks.append(table_html)
                    i += consumed
                    continue

            # Numbered list support
            if re.match(r"^\s*\d+[\.)]\s+", line):
                list_items: list[str] = []
                while i < len(lines) and re.match(r"^\s*\d+[\.)]\s+", lines[i]):
                    item_text = re.sub(r"^\s*\d+[\.)]\s+", "", lines[i].strip())
                    list_items.append(f"<li>{html.escape(item_text)}</li>")
                    i += 1
                chunks.append("<ol style='margin:4px 0 8px 18px;'>" + "".join(list_items) + "</ol>")
                continue

            # Bullet list support
            if re.match(r"^\s*[-*]\s+", line):
                bullet_lines: list[str] = []
                while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                    item_text = re.sub(r"^\s*[-*]\s+", "", lines[i].strip())
                    bullet_lines.append(item_text)
                    i += 1

                # If bullets are numeric category lines, render a compact bar chart style.
                chart_html = self._build_inline_bar_chart_html(bullet_lines)
                if chart_html:
                    chunks.append(chart_html)
                else:
                    chunks.append(
                        "<ul style='margin:4px 0 8px 16px;'>"
                        + "".join(f"<li>{html.escape(item)}</li>" for item in bullet_lines)
                        + "</ul>"
                    )
                continue

            # Default paragraph
            chunks.append(f"<p style='margin:4px 0; white-space:pre-wrap;'>{html.escape(stripped)}</p>")
            i += 1

        return "".join(chunks)

    def _looks_like_section_heading(self, text: str) -> bool:
        if len(text) > 60:
            return False
        if text.endswith(":"):
            return True
        normalized = text.lower().strip()
        known_headings = {
            "summary",
            "recommendations",
            "overspending check",
            "where your money is going",
            "breakdown",
            "action plan",
            "next steps",
            "financial health assessment",
        }
        return normalized in known_headings

    def _parse_text_table(self, lines: list[str], start_index: int) -> tuple[str, int]:
        table_lines: list[str] = []
        i = start_index
        while i < len(lines):
            candidate = lines[i].strip()
            if not candidate or "|" not in candidate:
                break
            table_lines.append(candidate)
            i += 1

        if len(table_lines) < 2:
            return "", 0

        # Detect markdown separator row like |---|---|
        separator_idx = -1
        for idx, row in enumerate(table_lines):
            if re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", row):
                separator_idx = idx
                break

        # Header + body parsing
        header_cells = self._split_table_row(table_lines[0])
        if not header_cells:
            return "", 0

        body_start = separator_idx + 1 if separator_idx >= 0 else 1
        body_rows = [self._split_table_row(row) for row in table_lines[body_start:] if self._split_table_row(row)]

        header_html = "".join(
            f"<th style='text-align:left; padding:6px 8px; border-bottom:1px solid #314055;'>{html.escape(cell)}</th>"
            for cell in header_cells
        )
        body_html = "".join(
            "<tr>"
            + "".join(
                f"<td style='padding:6px 8px; border-bottom:1px solid #1d2736;'>{html.escape(cell)}</td>"
                for cell in row
            )
            + "</tr>"
            for row in body_rows
        )

        table_html = (
            "<table cellspacing='0' cellpadding='0' style='margin:6px 0; width:100%; border-collapse:collapse; background-color:#0f1722;'>"
            f"<thead><tr>{header_html}</tr></thead>"
            f"<tbody>{body_html}</tbody>"
            "</table>"
        )
        return table_html, len(table_lines)

    def _split_table_row(self, row: str) -> list[str]:
        trimmed = row.strip().strip("|")
        if not trimmed:
            return []
        return [cell.strip() for cell in trimmed.split("|")]

    def _build_inline_bar_chart_html(self, bullet_lines: list[str]) -> str:
        """Render bullet lines like 'Dining: $320.50' as an inline horizontal bar chart."""
        parsed: list[tuple[str, float]] = []
        for line in bullet_lines:
            match = re.search(r"^(.*?):\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?)", line)
            if not match:
                continue
            label = match.group(1).strip()
            value = float(match.group(2).replace(",", ""))
            parsed.append((label, value))

        if len(parsed) < 2:
            return ""

        max_value = max(value for _, value in parsed)
        if max_value <= 0:
            return ""

        rows_html = []
        for label, value in parsed:
            width_pct = max(2.0, (value / max_value) * 100.0)
            rows_html.append(
                "<div style='display:flex; align-items:center; gap:8px; margin:3px 0;'>"
                f"<div style='min-width:140px; color:#c9d7e8;'>{html.escape(label)}</div>"
                "<div style='flex:1; background:#182333; border-radius:4px; overflow:hidden; height:12px;'>"
                f"<div style='width:{width_pct:.1f}%; height:12px; background:#2ec4b6;'></div>"
                "</div>"
                f"<div style='min-width:88px; text-align:right; color:#e7edf7;'>${value:,.2f}</div>"
                "</div>"
            )

        return (
            "<div style='margin:6px 0 10px 0; padding:8px; background:#0f1722; border:1px solid #233247; border-radius:8px;'>"
            + "".join(rows_html)
            + "</div>"
        )

    def _format_assistant_table_html(self, table_payload: dict[str, object]) -> str:
        title = str(table_payload.get("title", "Table"))
        columns = table_payload.get("columns", [])
        rows = table_payload.get("rows", [])

        if not isinstance(columns, list) or not isinstance(rows, list):
            return ""

        header_html = "".join(
            f"<th style='text-align:left; padding:6px 8px; border-bottom:1px solid #314055;'>{str(column)}</th>"
            for column in columns
        )

        if rows:
            body_html = "".join(
                "<tr>"
                + "".join(
                    f"<td style='padding:6px 8px; border-bottom:1px solid #1d2736;'>{str(cell)}</td>"
                    for cell in row
                )
                + "</tr>"
                for row in rows
                if isinstance(row, list)
            )
        else:
            body_html = (
                f"<tr><td colspan='{max(1, len(columns))}' style='padding:8px; color:#9fb3c8;'>No rows matched this request.</td></tr>"
            )

        return (
            f"<br><b>{title}</b>"
            "<table cellspacing='0' cellpadding='0' style='margin-top:6px; width:100%; border-collapse:collapse; background-color:#0f1722;'>"
            f"<thead><tr>{header_html}</tr></thead>"
            f"<tbody>{body_html}</tbody>"
            "</table>"
        )

    def _handle_assistant_failure(self, error_text: str) -> None:
        self.chat_log.append(f"<b>Assistant error:</b> {error_text}")
        self.status_bar.showMessage("Assistant failed to respond.", 5000)
        self.send_button.setEnabled(True)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            self.voice_coordinator.stop()
        finally:
            super().closeEvent(event)


def run_application() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()
