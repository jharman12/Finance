# Charts Tab Overhaul Plan (Personal Finance Focus)

Date: 2026-06-15

## 1) Objective

Transform the Charts tab from a business-style monthly expense dashboard into a personal finance analysis workspace that answers:

- Is my net worth growing?
- How is my debt trending?
- What is my savings rate and burn rate?
- Which assets are improving or underperforming?
- How much equity am I building in my home?
- How are contributions translating into investment value?

This plan preserves the architecture boundary where UI calls controllers, and controllers call repository/facade methods.

## 2) Current State Summary

Current implementation is concentrated in:

- finance_app/ui/main_window.py: _build_charts_tab and refresh_charts
- finance_app/ui/controllers/analytics_controller.py: monthly snapshot/history delegates
- finance_app/infrastructure/db/analytics_repository.py: tuple-based chart data
- finance_app/storage.py: compatibility facade plus assets overview and linked expense access

Current charts are a 2x2 grid focused on:

- daily cash flow
- six-month income/expense/net trend
- expense category bar
- expense share pie

## 3) Target Information Architecture (Charts Tab)

Keep one Charts top-level tab, but add internal sections:

1. Overview
2. Cash Flow
3. Net Worth
4. Assets
5. Debt and Housing
6. Investments

Shared controls at top of Charts tab:

1. Period presets: 1M, 3M, 6M, 12M, YTD, All
2. Month and year selectors (kept for backward compatibility)
3. Granularity: monthly, weekly (weekly only for short windows)
4. Asset filter: all assets, houses only, investments only, single asset
5. Compare toggle: compare to previous period

## 4) Personal Finance Chart Catalog

Minimum chart set for rollout (12 charts):

1. Income, expense, net income trend (line)
2. Daily income vs daily expense vs daily net (line)
3. Savings rate trend (line, percent)
4. Net worth trend (line/area)
5. Net worth composition over time (stacked area)
6. Total debt trend (line)
7. Debt composition by asset/type (stacked bar or donut)
8. Asset allocation current mix (donut)
9. Per-asset value history (multi-line)
10. Housing equity progression: house value vs principal with equity band (dual-line + fill)
11. Investment contributions vs investment value (dual-line)
12. Burn rate and runway estimate (bar + line)

Recommended additional charts after MVP:

1. Expense category trend over time (stacked columns)
2. Essential vs discretionary spending split (stacked bars)
3. Debt-to-income ratio trend (line)
4. Housing payment split: principal vs mortgage/interest-linked outflow (stacked bars)

## 5) Architecture Integration Plan (Codebase Architect)

### 5.1 Controller Surface

Extend finance_app/ui/controllers/analytics_controller.py with composed payload methods:

- get_cashflow_charts_payload(year: int, month: int, months_history: int = 12)
- get_position_charts_payload(year: int, month: int, months_history: int = 24, asset_ids: list[int] | None = None)
- get_asset_chart_payload(asset_id: int, year: int, month: int, months_history: int = 24)

These methods should aggregate repository outputs into chart-ready view models and remove tuple-index coupling from UI.

### 5.2 Repository/Facade Additions

Add facade methods in finance_app/storage.py that delegate to analytics/data mappers:

- net_worth_history(reference_year, reference_month, months=24)
- debt_history(reference_year, reference_month, months=24)
- debt_composition_for_month(year, month)
- asset_position_history(asset_id, reference_year, reference_month, months=24)
- expense_by_asset_for_month(year, month)
- savings_rate_history(reference_year, reference_month, months=24)
- runway_series(reference_year, reference_month, months=12)

Add SQL/support methods in finance_app/infrastructure/db/analytics_repository.py for the same data families.

### 5.3 Chart Payload Models

Add a dedicated chart model module:

- finance_app/models/chart_models.py

Suggested data classes:

- MonthValue(year, month, value)
- CategoryValue(label, value)
- AssetValue(asset_id, asset_name, value)
- PositionSnapshot(total_assets, total_debt, net_worth, monthly_income, monthly_expenses, monthly_net_income, savings_rate)
- AssetPositionHistory(asset_id, asset_name, asset_type, value_series, debt_series, equity_series, linked_expense_series)
- CashflowChartsPayload(...)
- PositionChartsPayload(...)

Contract rules:

- UI receives structured objects, not tuple-indexed arrays.
- Series are sorted ascending by year/month.
- Empty states return empty lists, never None.

### 5.4 UI Rendering Split

Introduce chart renderer helpers to keep main_window slim:

- finance_app/ui/charts/chart_renderer.py
- finance_app/ui/charts/chart_specs.py

MainWindow responsibilities remain:

- control wiring
- filter state
- calling controller
- selecting renderer method

Renderer responsibilities:

- plotting only
- shared axis styling
- empty-state placeholders

## 6) UX Integration Plan (Gui Handler)

### 6.1 Layout

In Charts tab:

1. Header + shared controls
2. Section selector (internal tabs)
3. Splitter area:
- left: matplotlib canvas
- right: insight panel with key metrics and point-in-time details

On narrow width, stack insights below chart.

### 6.2 Interactions

1. Click chart point to update insight panel for that month/day.
2. Click category/asset segments to open filtered ledger view.
3. Toggle compare to overlay prior period.
4. Keep last selected section/filter when month/year changes.

### 6.3 Data States

1. Empty: clear explanation plus action hint (for example, add asset value snapshots in Assets tab).
2. Loading: temporary label in chart panel while payload is computed.
3. Error: non-blocking banner with retry, keep prior successful render if possible.
4. Partial history: show insufficient-history annotation rather than hiding chart.

### 6.4 Accessibility

1. Consistent semantic colors:
- income: green
- expenses: red/orange
- net worth/equity: blue
- debt: amber/red
2. Do not rely on color alone; pair with line style and markers.
3. Keep readable axis fonts and high contrast.
4. Label latest point values directly for fast interpretation.

## 7) Phased Delivery Roadmap

### Phase 0: Preparation and Safety (0.5-1 day)

1. Add chart payload models and no-op controller method stubs.
2. Add unit tests for payload shape contracts.
3. Keep existing charts untouched.

### Phase 1: Contract-First Migration (1-2 days)

1. Refactor refresh_charts to consume payload objects while preserving current 2x2 visuals.
2. Ensure no new direct repository calls from MainWindow.
3. Add architecture boundary test coverage for chart methods.

### Phase 2: New Sections and Metrics (2-4 days)

1. Add Net Worth section (net worth trend + composition).
2. Add Debt and Housing section (debt trend + debt composition + equity progression).
3. Add Assets section (allocation + per-asset history).
4. Add Investments section (contributions vs value).

### Phase 3: Interaction and Drilldowns (1-2 days)

1. Add clickable drilldowns to ledger filters.
2. Add right-side insight panel updates from selection.
3. Add compare-period overlays.

### Phase 4: Performance and Hardening (1-2 days)

1. Add payload caching by filter key.
2. Add windowed aggregation for long ranges.
3. Add performance tests for 24-month and high-row datasets.
4. Add/verify indexes for date-heavy and link-heavy queries.

## 8) Testing Plan

1. Architecture boundary tests in tests/test_architecture_boundaries.py:
- charts refresh paths only call analytics controller and renderer
- no direct repository calls in chart handlers

2. Controller delegation tests in tests/test_controller_delegation.py:
- new analytics methods delegate correctly

3. Analytics repository tests (new file tests/test_analytics_position_repository.py):
- net worth history correctness
- debt history and composition correctness
- asset position history correctness
- expense-by-asset aggregation correctness

4. Payload shape tests (new file tests/test_chart_payload_shapes.py):
- sorted month series
- numeric values
- empty lists for missing data

5. UI behavior smoke tests (new file tests/test_charts_tab_sections.py):
- section switching
- period sync
- empty-state rendering without crash

## 9) Performance Risks and Mitigations

Risk 1: asset-linked recurring expansions can be expensive and double-counted.

Mitigation:

- treat repository returned link events as already expanded
- do not re-expand in UI or renderer
- aggregate by time window once per payload

Risk 2: too many charts redrawing on period/filter changes.

Mitigation:

- render active section only
- use draw_idle and reuse figure where possible
- debounce rapid control changes

Risk 3: long-range history query overhead.

Mitigation:

- default to 12-24 month windows
- aggregate for All range
- ensure indexes on occurred_on, link keys, snapshot date

## 10) Definition of Done

Charts overhaul is done when:

1. Charts tab includes at least 10 personal finance charts from this plan.
2. Net worth, total debt, and per-asset charts are available and accurate.
3. UI remains architecture-compliant (controller boundary preserved).
4. Empty/loading/error states are user-friendly and stable.
5. Existing chart behavior remains available during migration and then cleanly replaced.
6. Automated tests cover data correctness, boundaries, and chart-section stability.

## 11) Initial Task Breakdown (Ready To Implement)

1. Create finance_app/models/chart_models.py with payload dataclasses.
2. Extend finance_app/ui/controllers/analytics_controller.py with payload methods.
3. Add delegating facade methods in finance_app/storage.py.
4. Add analytics SQL/query methods in finance_app/infrastructure/db/analytics_repository.py.
5. Add finance_app/ui/charts/chart_renderer.py and migrate current 2x2 plotting into renderer.
6. Replace refresh_charts internals to use payload+renderer while preserving current output.
7. Add Net Worth and Debt/Housing sections.
8. Add Assets and Investments sections.
9. Add chart drilldown interactions to ledger filters.
10. Add test coverage files listed above.
