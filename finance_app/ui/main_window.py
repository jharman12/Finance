from __future__ import annotations

from datetime import date
import calendar

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtCore import QDate, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
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
from finance_app.models import AssistantResult, Transaction
from finance_app.services.assistant_service import AssistantService
from finance_app.storage import FinanceRepository


class AssistantWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, assistant_service: AssistantService, prompt_text: str) -> None:
        super().__init__()
        self.assistant_service = assistant_service
        self.prompt_text = prompt_text

    def run(self) -> None:
        try:
            result = self.assistant_service.handle_prompt(self.prompt_text)
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str, is_warning: bool = False) -> None:
        self.value_label.setText(value)
        if is_warning:
            self.value_label.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        else:
            self.value_label.setStyleSheet("")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.repository = FinanceRepository()
        self.assistant_service = AssistantService(self.repository)
        self._assistant_worker: AssistantWorker | None = None
        self._ollama_warmup_worker: OllamaWarmupWorker | None = None
        self._selected_year = date.today().year
        self._selected_month = date.today().month

        self.setWindowTitle(APP_NAME)
        self.resize(1400, 880)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.dashboard_tab = QWidget()
        self.charts_tab = QWidget()
        self.ledger_tab = QWidget()
        self.recurring_tab = QWidget()
        self.budget_tab = QWidget()
        self.assistant_tab = QWidget()

        self.tabs.addTab(self.dashboard_tab, "Overview")
        self.tabs.addTab(self.charts_tab, "Charts")
        self.tabs.addTab(self.ledger_tab, "Ledger")
        self.tabs.addTab(self.recurring_tab, "Recurring")
        self.tabs.addTab(self.budget_tab, "Budget")
        self.tabs.addTab(self.assistant_tab, "Assistant")

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Syncing recurring items with transactions...", 0)

        self._build_dashboard_tab()
        self._build_charts_tab()
        self._build_ledger_tab()
        self._build_recurring_tab()
        self._build_budget_tab()
        self._build_assistant_tab()
        self._apply_styles()
        
        # Sync all recurring items with their transactions to fix any category mismatches
        sync_result = self.repository.sync_recurring_with_transactions()
        if sync_result["total_synced"] > 0:
            self.status_bar.showMessage(
                f"Fixed {sync_result['total_synced']} transaction categories to match recurring items.",
                5000
            )
        else:
            self.status_bar.showMessage("", 0)
        
        self.refresh_all()
        self._warmup_ollama()

    def _build_dashboard_tab(self) -> None:
        layout = QVBoxLayout(self.dashboard_tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

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
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        dashboard_actions = QHBoxLayout()
        self.delete_recent_button = QPushButton("Delete Selected Recent Entry")
        self.delete_recent_button.clicked.connect(lambda: self.delete_selected_transaction(self.recent_table))
        dashboard_actions.addWidget(self.delete_recent_button)
        dashboard_actions.addStretch(1)
        layout.addLayout(dashboard_actions)

    def _build_charts_tab(self) -> None:
        layout = QVBoxLayout(self.charts_tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        title = QLabel("Monthly Charts")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Visualize cash flow, category mix, and recent monthly trends for the selected period.")
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
        expense_form.addRow("Amount", self.expense_amount)
        expense_form.addRow("Category", self.expense_category)
        expense_form.addRow("Description", self.expense_description)
        expense_form.addRow("Date", self.expense_date)
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
        layout = QVBoxLayout(self.recurring_tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

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
        layout = QVBoxLayout(self.ledger_tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        title = QLabel("Ledger")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Everything is stored locally in SQLite as soon as you add it.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

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
        self.budget_net_on_target = MetricCard("Net If On Budget", "$0.00")

        insight_layout.addWidget(self.budget_income_insight, 0, 0)
        insight_layout.addWidget(self.budget_total_spend_insight, 0, 1)
        insight_layout.addWidget(self.budget_net_on_target, 0, 2)

        # Bottom row: Savings goal, remaining to spend budget
        self.budget_savings_goal_card = MetricCard("Savings Goal", "$0.00")
        self.budget_expected_net = MetricCard("Expected Net This Month", "$0.00")
        self.budget_remaining_to_spend = MetricCard("Remaining Budget", "$0.00")

        insight_layout.addWidget(self.budget_savings_goal_card, 1, 0)
        insight_layout.addWidget(self.budget_expected_net, 1, 1)
        insight_layout.addWidget(self.budget_remaining_to_spend, 1, 2)
        insight_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout.addWidget(insight_panel)

        # Goal savings input section
        goal_panel = QFrame()
        goal_panel.setObjectName("Panel")
        goal_layout = QHBoxLayout(goal_panel)
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

        goal_layout.addWidget(goal_label)
        goal_layout.addWidget(self.savings_goal_input)
        goal_layout.addStretch(1)
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
        self.budget_table.setMinimumHeight(420)
        self.budget_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        budget_layout.addWidget(self.budget_table)

        # Controls
        button_row = QHBoxLayout()
        self.budget_ai_suggest_button = QPushButton("AI Suggest Budget")
        self.budget_ai_suggest_button.clicked.connect(self._suggest_budget_with_ai)
        self.budget_save_button = QPushButton("Save Changes")
        self.budget_save_button.clicked.connect(self._save_budget)
        self.budget_delete_button = QPushButton("Delete Selected")
        self.budget_delete_button.clicked.connect(self._delete_budget_entry)

        button_row.addWidget(self.budget_ai_suggest_button)
        button_row.addWidget(self.budget_save_button)
        button_row.addWidget(self.budget_delete_button)
        button_row.addStretch(1)
        budget_layout.addLayout(button_row)

        layout.addWidget(budget_panel, 1)

        # Add new budget category section
        add_panel = QFrame()
        add_panel.setObjectName("Panel")
        add_layout = QHBoxLayout(add_panel)
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

        add_layout.addWidget(add_label)
        add_layout.addWidget(QLabel("Category:"))
        add_layout.addWidget(self.new_budget_category, 1)
        add_layout.addWidget(QLabel("Amount:"))
        add_layout.addWidget(self.new_budget_amount)
        add_layout.addWidget(QLabel("Notes:"))
        add_layout.addWidget(self.new_budget_notes, 2)
        add_layout.addWidget(add_button)
        add_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(add_panel)
        layout.setStretch(0, 0)
        layout.setStretch(1, 0)
        layout.setStretch(2, 1)
        layout.setStretch(3, 0)

    def _handle_budget_period_changed(self) -> None:
        """Update budget display when period changes."""
        self.refresh_budget()
        month_name = calendar.month_name[int(self.budget_month_toggle.currentData())]
        year = int(self.budget_year_toggle.currentData())
        self.status_bar.showMessage(f"Viewing budget for {month_name} {year}.", 3000)

    def _handle_savings_goal_changed(self) -> None:
        """Update insights when savings goal changes."""
        self.refresh_budget()

    def refresh_budget(self) -> None:
        """Refresh the budget tab with current data and calculate insights."""
        if not hasattr(self, 'budget_table'):
            return

        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())

        # Get projected recurring totals
        total_income, recurring_expenses = self.repository.get_projected_recurring_totals_for_month(selected_year, selected_month)

        # Split budget rows so recurring auto-allocations are not counted twice in summary insights.
        budgets = self.repository.list_budgets_for_month(selected_year, selected_month, kind="expense")
        recurring_budget_rows = [b for b in budgets if b.notes == "Recurring item (auto-allocated)"]
        discretionary_budget_rows = [b for b in budgets if b.notes != "Recurring item (auto-allocated)"]
        budgeted_discretionary = sum(b.budgeted_amount for b in discretionary_budget_rows)
        actual_discretionary = sum(b.actual_spent for b in discretionary_budget_rows)

        # Calculate key metrics
        total_expected_spend = recurring_expenses + budgeted_discretionary
        net_if_on_target = total_income - total_expected_spend
        
        savings_goal = self.savings_goal_input.value()
        
        # Expected net this month = income - savings goal - expected spend
        # But if savings goal > income, remaining should show negative
        discretionary_after_savings = total_income - savings_goal - recurring_expenses
        
        # Remaining to spend = what's left in discretionary budget after expenses so far
        remaining_to_spend = discretionary_after_savings - actual_discretionary

        # Update insight cards
        self._set_metric_value(self.budget_income_insight, total_income)
        self._set_metric_value(self.budget_total_spend_insight, total_expected_spend)
        self._set_metric_value(self.budget_net_on_target, max(0, net_if_on_target))
        self._set_metric_value(self.budget_savings_goal_card, savings_goal)
        
        # Expected net = income - recurring expenses - discretionary budget - savings goal.
        expected_net = total_income - recurring_expenses - budgeted_discretionary
        if expected_net < 0:
            # Show in red/warning color
            self._set_metric_value(self.budget_expected_net, expected_net, is_warning=True)
        else:
            self._set_metric_value(self.budget_expected_net, expected_net)
        
        # Remaining to spend in budget
        self._set_metric_value(self.budget_remaining_to_spend, max(0, remaining_to_spend))

        # Populate budget table
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
                if column_index > 0:  # Align numbers to right
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if column_index in [1, 2, 3, 4]:  # Color number columns
                    item.setBackground(QColor(color))
                self.budget_table.setItem(row_index, column_index, item)

        # Update category dropdown for new entries
        self._refresh_budget_category_dropdown(selected_month, selected_year)

    def _refresh_budget_category_dropdown(self, year: int, month: int) -> None:
        """Populate the category dropdown with unbudgeted expense categories."""
        self.new_budget_category.blockSignals(True)
        self.new_budget_category.clear()

        # Get all expense categories
        all_categories = self.repository.list_categories(kind="expense")

        # Get already-budgeted categories
        existing_budgets = self.repository.list_budgets_for_month(year, month, kind="expense")
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

        self.repository.add_or_update_budget(
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
            self.repository.delete_budget(budget_id)
            self.status_bar.showMessage(f"Deleted budget for {category_name}.", 3000)
            self.refresh_budget()

    def _suggest_budget_with_ai(self) -> None:
        """Request AI budget suggestions."""
        selected_month = int(self.budget_month_toggle.currentData())
        selected_year = int(self.budget_year_toggle.currentData())

        income_total, expense_total = self.repository.get_projected_recurring_totals_for_month(selected_year, selected_month)
        available_budget = income_total - expense_total

        if available_budget <= 0:
            QMessageBox.warning(
                self, APP_NAME, "Available budget must be positive.\n\nEnsure recurring income exceeds recurring expenses."
            )
            return

        # First, create budget entries for all recurring expenses at their full amounts
        recurring_expenses = self.repository.get_active_recurring_items_for_month(selected_year, selected_month, kind="expense")
        discretionary_budget = available_budget
        
        for recurring_item in recurring_expenses:
            # Add budget for this recurring expense
            self.repository.add_or_update_budget(
                year=selected_year,
                month=selected_month,
                category=recurring_item.category,
                kind="expense",
                budgeted_amount=recurring_item.amount,
                notes="Recurring item (auto-allocated)",
            )
            # Deduct from discretionary budget
            discretionary_budget -= recurring_item.amount
        
        if discretionary_budget <= 0:
            # No room for additional discretionary spending
            self.status_bar.showMessage(f"Budgets set for {len(recurring_expenses)} recurring items. No discretionary budget remaining.", 3000)
            self.refresh_budget()
            return

        self.budget_ai_suggest_button.setEnabled(False)
        self.budget_ai_suggest_button.setText("Generating suggestions...")

        try:
            # Ask AI to allocate only the discretionary budget
            allocations = self.assistant_service.generate_budget_allocation(
                selected_year, selected_month, discretionary_budget, recurring_expenses_list=recurring_expenses
            )

            if not allocations:
                QMessageBox.warning(self, APP_NAME, "Could not generate discretionary budget suggestions. Recurring items have been budgeted.")
                self.budget_ai_suggest_button.setEnabled(True)
                self.budget_ai_suggest_button.setText("AI Suggest Budget")
                self.refresh_budget()
                return

            # Apply allocations to budget (for discretionary categories)
            for category, amount in allocations.items():
                if amount > 0:
                    self.repository.add_or_update_budget(
                        year=selected_year,
                        month=selected_month,
                        category=category,
                        kind="expense",
                        budgeted_amount=amount,
                        notes="AI-suggested discretionary allocation",
                    )

            self.status_bar.showMessage(
                f"Budgeted {len(recurring_expenses)} recurring items + {len(allocations)} discretionary categories.", 3000
            )
            self.refresh_budget()

        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Error generating suggestions: {str(e)}")
        finally:
            self.budget_ai_suggest_button.setEnabled(True)
            self.budget_ai_suggest_button.setText("AI Suggest Budget")

    def _open_category_manager(self) -> None:
        """Open the category management dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Categories")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)

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
        expense_categories = self.repository.list_categories(kind="expense")
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
        income_categories = self.repository.list_categories(kind="income")
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
        existing = self.repository.list_categories(kind=kind)
        if any(cat.name.lower() == category_name.lower() for cat in existing):
            QMessageBox.warning(self, APP_NAME, f"Category '{category_name}' already exists.")
            return

        # Add the category
        self.repository.ensure_category(category_name, kind)
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
            success = self.repository.delete_category(category_name, kind)
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

    def _build_assistant_tab(self) -> None:
        layout = QVBoxLayout(self.assistant_tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        title = QLabel("Local AI Assistant")
        title.setObjectName("PageTitle")
        subtitle = QLabel("The assistant can answer questions, start Ollama if needed, and write directly to the ledger.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

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

    def _apply_styles(self) -> None:
        font = QFont("Segoe UI")
        font.setPointSize(10)

        app = QApplication.instance()
        app.setFont(font)

        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#0a1018"))
        palette.setColor(QPalette.WindowText, QColor("#e7edf7"))
        palette.setColor(QPalette.Base, QColor("#0d1520"))
        palette.setColor(QPalette.AlternateBase, QColor("#111a27"))
        palette.setColor(QPalette.ToolTipBase, QColor("#172233"))
        palette.setColor(QPalette.ToolTipText, QColor("#f5f8ff"))
        palette.setColor(QPalette.Text, QColor("#e7edf7"))
        palette.setColor(QPalette.Button, QColor("#111a27"))
        palette.setColor(QPalette.ButtonText, QColor("#e7edf7"))
        palette.setColor(QPalette.BrightText, QColor("#ffffff"))
        palette.setColor(QPalette.Highlight, QColor("#2ec4b6"))
        palette.setColor(QPalette.HighlightedText, QColor("#041012"))
        app.setPalette(palette)

        self.setStyleSheet(
            """
            QWidget {
                color: #e7edf7;
                font-family: 'Segoe UI';
                font-size: 10pt;
                background: #0a1018;
            }
            QMainWindow {
                background: #0a1018;
            }
            QTabWidget::pane {
                border: 0;
                background: #0a1018;
            }
            QTabBar::tab {
                background: #101826;
                color: #9fb0c7;
                padding: 12px 18px;
                margin-right: 6px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background: #172233;
                color: #ffffff;
            }
            QLabel#PageTitle {
                font-size: 26pt;
                font-weight: 700;
                color: #f5f8ff;
            }
            QLabel#PageSubtitle {
                font-size: 11pt;
                color: #90a4bf;
            }
            QLabel#SectionTitle {
                font-size: 15pt;
                font-weight: 600;
                color: #f5f8ff;
            }
            QFrame#Panel, QFrame#MetricCard {
                background: #111a27;
                border: 1px solid #1e2b3f;
                border-radius: 18px;
            }
            QLabel#MetricCardTitle {
                color: #90a4bf;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            QLabel#MetricCardValue {
                color: #ffffff;
                font-size: 22pt;
                font-weight: 700;
            }
            QLineEdit, QDoubleSpinBox, QDateEdit, QComboBox, QTextEdit, QTableWidget {
                background: #0d1520;
                color: #e7edf7;
                border: 1px solid #233247;
                border-radius: 12px;
                padding: 10px;
                selection-background-color: #2ec4b6;
            }
            QLineEdit:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled, QComboBox:disabled, QTextEdit:disabled {
                color: #6f8098;
                background: #0b121c;
            }
            QComboBox QAbstractItemView, QMenu, QMenuBar, QCalendarWidget {
                background: #111a27;
                color: #e7edf7;
                selection-background-color: #2ec4b6;
                selection-color: #041012;
            }
            QComboBox::drop-down {
                border: 0;
                width: 28px;
            }
            QComboBox QAbstractItemView::item, QCalendarWidget QToolButton, QCalendarWidget QSpinBox {
                background: #111a27;
                color: #e7edf7;
            }
            QAbstractItemView {
                background: #0d1520;
                color: #e7edf7;
                selection-background-color: #2ec4b6;
                selection-color: #041012;
            }
            QPushButton {
                background: #2ec4b6;
                color: #041012;
                border: none;
                border-radius: 12px;
                padding: 12px 16px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #58d4c8;
            }
            QPushButton:pressed {
                background: #25a99e;
            }
            QHeaderView::section {
                background: #172233;
                color: #cbd6e8;
                padding: 10px;
                border: none;
            }
            QTableWidget {
                gridline-color: #1f2d40;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: #0a1018;
                border: 0;
                margin: 0;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #233247;
                border-radius: 6px;
                min-height: 24px;
                min-width: 24px;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                background: none;
                border: 0;
            }
            QStatusBar {
                background: #09111a;
                color: #9fb0c7;
            }
            QMessageBox {
                background: #0a1018;
            }
            QTextEdit#ChatLog {
                background: #09111a;
            }
            """
        )

    def refresh_all(self) -> None:
        self.refresh_category_controls()
        self.refresh_recurring_category_controls()
        self.refresh_dashboard()
        self.refresh_ledger_tables()
        self.refresh_recurring_table()
        self.refresh_charts()
        self.refresh_budget()

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
        expense_categories = self.repository.list_categories("expense")
        income_categories = self.repository.list_categories("income")

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
        categories = self.repository.list_categories(current_kind)
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

    def refresh_dashboard(self) -> None:
        snapshot = self.repository.snapshot_for_month(self._selected_year, self._selected_month)
        self._set_metric_value(self.income_card, snapshot.income_total)
        self._set_metric_value(self.expense_card, snapshot.expense_total)
        self._set_metric_value(self.net_card, snapshot.net_total)
        self.count_card.set_value(str(snapshot.transaction_count))

        summary_lines = [f"{category}: ${total:,.2f}" for category, total in snapshot.top_categories] or [
            "No expenses recorded yet."
        ]
        self.category_summary.setPlainText("\n".join(summary_lines))

    def refresh_ledger_tables(self) -> None:
        transactions = self.repository.list_transactions_for_month(self._selected_year, self._selected_month, limit=250)
        self._populate_table(self.recent_table, transactions[:10])
        self._populate_table(self.full_ledger_table, transactions)

    def refresh_recurring_table(self) -> None:
        recurring_items = self.repository.list_recurring_items()
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
        daily_totals = self.repository.daily_totals_for_month(self._selected_year, self._selected_month)
        expense_breakdown = self.repository.expense_breakdown_for_month(self._selected_year, self._selected_month)
        monthly_history = self.repository.monthly_history(self._selected_year, self._selected_month, months=6)
        snapshot = self.repository.snapshot_for_month(self._selected_year, self._selected_month)

        self.charts_summary.setText(
            f"{calendar.month_name[self._selected_month]} {self._selected_year}: "
            f"Income ${snapshot.income_total:,.2f} | Expenses ${snapshot.expense_total:,.2f} | "
            f"Net ${snapshot.net_total:,.2f} | Transactions {snapshot.transaction_count}"
        )

        self.analytics_figure.clear()
        axes = self.analytics_figure.subplots(2, 2)
        self.analytics_figure.patch.set_facecolor("#111a27")

        day_numbers = [entry[0].day for entry in daily_totals]
        income_values = [entry[1] for entry in daily_totals]
        expense_values = [entry[2] for entry in daily_totals]
        net_values = [entry[3] for entry in daily_totals]

        history_labels = [f"{calendar.month_abbr[month]} {str(year)[-2:]}" for year, month, *_ in monthly_history]
        history_income = [entry[2] for entry in monthly_history]
        history_expense = [entry[3] for entry in monthly_history]
        history_net = [entry[4] for entry in monthly_history]

        category_labels = [label for label, _ in expense_breakdown[:8]]
        category_values = [value for _, value in expense_breakdown[:8]]

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
        self._selected_month = int(self.month_toggle.currentData())
        self._selected_year = int(self.year_toggle.currentData())
        self._sync_period_controls(self.month_toggle, self.year_toggle, self.charts_month_toggle, self.charts_year_toggle)
        self.refresh_dashboard()
        self.refresh_ledger_tables()
        self.refresh_charts()

        month_name = calendar.month_name[self._selected_month]
        self.status_bar.showMessage(f"Viewing {month_name} {self._selected_year}.", 3000)

    def _handle_chart_period_changed(self) -> None:
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
        self.repository.add_recurring_item(
            kind=self.recurring_kind.currentText(),
            amount=amount,
            category=category,
            description=description,
            interval_count=interval_count,
            interval_unit=self.recurring_interval_unit.currentText(),
            start_on=start_on,
        )

        self.status_bar.showMessage("Saved recurring item.", 4000)
        self.refresh_all()
        self.recurring_amount.setValue(0.0)
        self.recurring_description.clear()

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
        all_items = self.repository.list_recurring_items(active_only=False)
        recurring_item = next((item for item in all_items if item.id == recurring_id), None)

        if not recurring_item:
            QMessageBox.warning(self, APP_NAME, "Could not find recurring item.")
            return

        # Create edit dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit Recurring Item")
        dialog.setMinimumWidth(500)

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
        categories = self.repository.list_categories(kind=recurring_item.kind)
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

            success = self.repository.update_recurring_item(
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
                # If category changed, recategorize existing transactions from this recurring item
                if new_category != recurring_item.category:
                    self.repository.change_transaction_category(
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
            success = self.repository.delete_recurring_item(recurring_id)
            if success:
                self.status_bar.showMessage(f"Deleted recurring item: {description}", 4000)
                self.refresh_all()
            else:
                QMessageBox.critical(self, APP_NAME, "Failed to delete recurring item.")

    def _qdate_to_date(self, value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    def _add_transaction(self, kind: str, amount: float, category: str, description: str, occurred_on: QDate) -> None:
        if amount <= 0:
            QMessageBox.warning(self, APP_NAME, "Enter an amount greater than zero.")
            return
        if not description.strip():
            QMessageBox.warning(self, APP_NAME, "Add a short description before saving.")
            return

        transaction_date = self._qdate_to_date(occurred_on)
        if kind == "expense":
            self.repository.add_expense(amount, category, description, transaction_date)
        else:
            self.repository.add_income(amount, category, description, transaction_date)

        self.status_bar.showMessage(f"Saved {kind} entry in {category}.", 4000)
        self.refresh_all()
        self._clear_entry_form(kind)

    def _clear_entry_form(self, kind: str) -> None:
        if kind == "expense":
            self.expense_amount.setValue(0.0)
            self.expense_description.clear()
        else:
            self.income_amount.setValue(0.0)
            self.income_description.clear()

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
            if self.repository.delete_transaction(int(transaction_id)):
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

    def _handle_assistant_result(self, result: AssistantResult) -> None:
        response_lines = [f"<b>Assistant:</b> {result.reply}"]
        if result.applied_actions:
            response_lines.append("<i>Applied:</i> " + "; ".join(result.applied_actions))
        for table_payload in result.display_tables:
            response_lines.append(self._format_assistant_table_html(table_payload))
        self.chat_log.append("<br>".join(response_lines))
        self.status_bar.showMessage("Assistant response complete.", 4000)
        self.send_button.setEnabled(True)
        self.refresh_all()

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


def run_application() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()
