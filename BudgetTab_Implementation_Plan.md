# Budget Tab Comprehensive Review and Implementation Plan

Date: 2026-06-15
Scope: finance_app/ui/main_window.py + finance_app/storage.py + finance_app/services/assistant_service.py
Goal: upgrade the Budget tab to spreadsheet-grade monthly planning/tracking for overspend, under-budget performance, and remaining spend under both break-even and goal targets.

## 1) Current-State Review (Findings)

### Critical

1. Budget category dropdown refresh is called with year/month reversed.
- Call site currently passes selected_month, selected_year.
- Function signature expects year, month.
- Impact: wrong set of budgeted categories can appear in dropdown, allowing duplicate/additional inconsistencies by month.

2. Negative budget health is hidden in KPI cards.
- Net and remaining cards clamp negative values to 0.
- Impact: users cannot see deficit magnitude, which hides overspending severity and weakens decision-making.

### High

3. Expected net metric does not include savings goal despite label/context implying goal-aware planning.
- Expected net currently uses income - recurring - discretionary budgeted; goal value is shown separately but not integrated into expected result.
- Impact: mismatch between displayed insights and true goal attainment.

4. Budget tab behaves as a single-entry editor, not spreadsheet-like planner.
- No pacing-to-date, no month-end forecast, no variance columns, no drilldown-by-cell, no filters/grouping/sort state.
- Impact: users cannot answer common monthly control questions quickly.

5. Monthly savings goal is UI-state only (not persisted by month/version).
- Impact: switching periods loses target continuity and historical accountability.

### Medium

6. Budget storage model is single-version per month/category/kind.
- No plan versions/scenarios (Base/Conservative/Stretch), no rollovers, no allocation modes.
- Impact: cannot compare options the way spreadsheet users do.

7. AI suggest fallback allocates across all categories and can ignore recurring exclusions in fallback path.
- Impact: confusing allocations in failure paths and potential double-allocation patterns.

8. Save button is mostly confirmational and does not provide explicit dirty-state lifecycle.
- Impact: editing model is unclear for users expecting spreadsheet semantics.

## 2) Spreadsheet Parity Targets (What to Add)

### Core outcomes to support each month
- Where am I overspent?
- Where am I under budget?
- How much can I still spend and stay break-even?
- How much can I still spend and still hit my savings goal?
- Which categories are on pace to overspend by month-end?

### Budget Planner Grid (target columns)
- Category
- Kind (Income/Expense)
- Budgeted
- Actual
- Remaining
- % Used
- Days Elapsed
- Days in Month
- Pacing Target To Date
- Variance vs Pacing
- Forecast Month-End
- Forecast Variance vs Budget
- Break-even Left to Spend
- Goal-adjusted Budget
- Goal Left to Spend
- Rollover In
- Rollover Out
- Notes
- Status

### Formula definitions (plain language)
- Remaining = Budgeted - Actual
- % Used = Actual / Budgeted (N/A if budgeted is 0)
- Pacing Target To Date = Budgeted * (Days Elapsed / Days in Month)
- Variance vs Pacing = Actual - Pacing Target To Date
- Forecast Month-End = (Actual / Days Elapsed) * Days in Month (if days elapsed > 0)
- Forecast Variance vs Budget = Forecast Month-End - Budgeted
- Break-even Left to Spend (category) = max(0, Budgeted - Actual) for expenses
- Goal Left to Spend (category) = Goal-adjusted Budget - Actual

## 3) Proposed Budget Tab Information Architecture

1. Top Controls Row
- Month selector (existing)
- Year selector (existing)
- Budget version selector (new)
- Monthly savings goal input (persisted, month/version aware)
- Actions: Save, Duplicate Version, Import CSV, Export CSV

2. KPI Strip (always visible)
- Income (month)
- Planned Spend
- Actual Spend
- Break-even Left to Spend
- Goal Left to Spend
- Overspent Categories / Under-budget Categories counts

3. Main Workspace (split)
- Left: Budget Planner Grid (QTableView + model)
- Right: Category Inspector
  - selected category notes
  - month trend mini-chart (planned vs actual)
  - transaction drilldown list for selected category

4. Bottom Alerts Panel
- Critical: currently overspent
- Warning: pacing/forecast overspend risk
- Positive: under-budget opportunities to reallocate toward goal

## 4) Data Model and Storage Upgrades

### New/changed tables
1. budget_goals
- id, year, month, version_id, savings_goal, break_even_mode(optional), created_at, updated_at

2. budget_versions
- id, year, month, name, is_active, created_at
- unique(year, month, name)

3. budgets table enhancement
- add version_id (FK -> budget_versions.id)
- add rollover_in, rollover_rule
- unique(year, month, version_id, category, kind)

### Service/repository additions
- list_budget_versions(year, month)
- create_budget_version(year, month, name)
- clone_budget_version(source_version_id, target_name)
- get_budget_goal(year, month, version_id)
- set_budget_goal(year, month, version_id, savings_goal)
- list_budget_rows_with_metrics(year, month, version_id, as_of_date)
- get_budget_alerts(year, month, version_id)

## 5) GUI Coordination Plan (with GUI Handler guidance)

### Phase 1: MVP (2-3 days)
Objective: truthful monthly control with break-even and goal visibility.

Implementation
- Fix year/month parameter mismatch for budget dropdown refresh.
- Remove KPI clamping of negative values so deficits are visible.
- Persist monthly savings goal by period (and default version).
- Add KPI cards:
  - Break-even Left to Spend
  - Goal Left to Spend
  - Overspent Count / Under-budget Count
- Expand budget grid with:
  - Remaining, % Used, Status (if not already computed, normalize)
- Add click-to-drilldown for Actual cell -> filtered ledger view.

Acceptance criteria
- Overspent categories always display negative remaining and red status.
- Under-budget categories show positive remaining and green status.
- Break-even and goal-left KPIs are visible simultaneously and preserve sign.
- Switching month/year restores saved goal and budgets correctly.

### Phase 2: Enhanced (3-5 days)
Objective: pacing and forecast intelligence.

Implementation
- Add pacing columns and forecast columns.
- Add alert panel (critical/warning/info buckets).
- Add table filters (All, Overspent, Pacing Risk, Under-budget).
- Add AI suggestion preview dialog (diff/apply selected rows).

Acceptance criteria
- Mid-month pacing values update correctly from current date.
- Forecast identifies likely overspends before month-end.
- User can filter and export filtered budget view.

### Phase 3: Power User (5-8 days)
Objective: spreadsheet-style planning workflows.

Implementation
- Add month/version scenarios (Base, Conservative, Stretch).
- Add rollover support and next-month carry logic.
- Add bulk paste + undo/redo transaction-safe edits.
- Optional formula columns with safe parser (restricted expressions).

Acceptance criteria
- User can compare at least 3 versions for a month.
- Rollover behavior carries deterministically month-to-month.
- Bulk operations remain responsive and reversible.

## 6) Engineering Notes and Risk Controls

1. Move budget table to QTableView + QAbstractTableModel for performance and cleaner formula recomputation.
2. Cache monthly transaction aggregates per category to avoid repeated SQL per row.
3. Debounce recompute on edit events to prevent UI churn.
4. Keep color + text/icon status (not color-only) for accessibility.
5. Keep negative values visible in all deficit metrics.

## 7) Immediate Next Implementation Tickets

1. Fix refresh parameter order and negative clamping defects.
2. Add persisted monthly goal storage and wiring in budget tab.
3. Introduce BudgetMetrics service that computes all KPI and row formulas in one pass.
4. Replace item-based table handling with model-based budget grid.
5. Add drilldown interaction from grid rows to ledger filter.

## 8) Coordination Hand-off Checklist for GUI Handler

- Build UI components in finance_app/ui/main_window.py budget section:
  - top controls row, KPI strip, splitter workspace, alerts panel.
- Introduce BudgetTableModel class (new file under finance_app/ui/models/ if preferred).
- Wire signals:
  - period/version/goal changes -> recompute + redraw
  - row edit -> repository update + dirty state
  - cell click on Actual -> ledger filter event
- Apply status color semantics:
  - Overspent: red
  - Pacing Risk: amber
  - Under-budget: green
- Keep existing style language while adding planner-specific table affordances.

## 9) Definition of Done

The budget tab is considered complete for this roadmap when a user can, for any selected month:
- see true deficit/surplus without clamping,
- identify overspent and under-budget categories instantly,
- see both break-even and goal-constrained remaining spend,
- understand pacing risk before month-end,
- adjust plan inline with spreadsheet-like interactions,
- and persist/reload the plan with confidence.
