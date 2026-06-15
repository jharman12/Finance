# Finance App Restructure Plan

## Status Update (2026-06-15)
- Core architecture goals are complete for the current codebase scope.
- `MainWindow` no longer performs direct repository calls; all persistence/query interactions route through UI controllers.
- Controller boundaries are guarded by architecture tests in `tests/test_architecture_boundaries.py`.
- Added controller delegation tests for all introduced UI controllers in `tests/test_controller_delegation.py`.
- Added low-risk UI structure split by extracting worker/widget helper classes from `ui/main_window.py` into `ui/support.py`.
- Regression suite remains green after each refactor slice.

### Remaining Optional Improvements
- Continue reducing `ui/main_window.py` line count by splitting tab construction methods into `ui/tabs/*` modules.
- Add broader integration tests for assistant and assets workflows.
- Add CI gate for file-size thresholds and architecture boundary checks.

## Goals
- Reduce bug rate by isolating side effects and shrinking class/file responsibilities.
- Reduce implementation time by creating predictable module boundaries.
- Keep UI responsive by removing heavy DB and business logic from UI classes.
- Improve testability with deterministic service and repository layers.

## Current Hotspots (Measured)
- `finance_app/ui/main_window.py` is a monolith (~4,444 lines) with UI build code, business logic, formatting, model operations, voice orchestration, and assistant flow.
- `finance_app/storage.py` is a monolith (~2,000+ lines) owning schema setup, migrations, multiple repository concerns, CSV import/export, and business-side computations.
- `finance_app/services/assistant_service.py` is large (~870+ lines) and mixes prompt orchestration, JSON parsing/repair, domain actions, budget allocation logic, and reallocation orchestration.
- Test coverage is narrowly focused (`tests/test_budget_reallocator.py`) with no repository, assistant action pipeline, or UI controller tests.

## Architectural Risks To Address First
1. Read operations in storage trigger writes (recurring materialization), coupling query paths to mutation paths.
2. `MainWindow` has too many responsibilities, increasing regression risk and merge conflicts.
3. Repository internal/private helpers are called by service layer, leaking persistence internals into application logic.
4. Asset/recurring linking logic includes expensive iterative expansion and repeated cross-calls in one method.

## Target Architecture

### 1) Package Structure
- `finance_app/domain/`
  - `entities.py` (existing dataclasses)
  - `value_objects.py` (optional, e.g., `Money`, `YearMonth`)
  - `policies/` (budget and recurring rules)
- `finance_app/infrastructure/db/`
  - `connection.py`
  - `schema.py`
  - `migrations.py`
  - `repositories/`
    - `transaction_repository.py`
    - `recurring_repository.py`
    - `budget_repository.py`
    - `asset_repository.py`
    - `settings_repository.py`
  - `csv_io.py`
- `finance_app/application/`
  - `use_cases/`
    - `add_transaction.py`
    - `manage_recurring.py`
    - `compute_dashboard_snapshot.py`
    - `generate_budget_reallocation.py`
    - `apply_budget_reallocation.py`
  - `dto.py`
- `finance_app/services/assistant/`
  - `assistant_orchestrator.py`
  - `context_builder.py`
  - `response_parser.py`
  - `action_executor.py`
  - `table_builders.py`
- `finance_app/ui/`
  - `main_window.py` (shell and tab wiring only)
  - `tabs/`
    - `dashboard_tab.py`
    - `ledger_tab.py`
    - `recurring_tab.py`
    - `budget_tab.py`
    - `assets_tab.py`
    - `assistant_tab.py`
  - `controllers/`
    - `dashboard_controller.py`
    - `budget_controller.py`
    - `assistant_controller.py`
  - `widgets/` (shared UI components)
  - `formatters/` (assistant HTML/table rendering)

### 2) File and Class Size Constraints
- Soft file limit: 350 lines.
- Hard file limit: 500 lines (requires split ticket).
- Class method target: 12-15 methods max per class.
- UI class rule: no direct SQL-like or persistence logic in tab widgets.
- Service rule: no calls to private methods from other classes/modules.

### 3) Dependency Direction
- UI -> Application use cases -> Repository interfaces -> DB implementations.
- Assistant orchestrator -> action executor/use cases -> repositories.
- Domain layer must not depend on PyQt5 or requests.

## Phased Execution Plan

### Phase 0: Stabilize and Baseline (1-2 days)
- Add tests around existing behavior before moving code:
  - recurring materialization behavior for list/snapshot operations
  - assistant action application paths (`add_*`, `change_*`, `show_table`)
  - budget tab import/export and inline edit behavior
- Add a lightweight architecture test that fails if `ui/` imports `storage.py` directly (except through controller facade).

### Phase 1: Split Persistence by Concern (2-3 days)
- Extract `FinanceRepository` into focused repositories:
  - transaction + recurring
  - budgets + settings
  - assets + links + snapshots
  - CSV import/export
- Keep a temporary compatibility facade (`FinanceRepositoryFacade`) to avoid big-bang UI breakage.
- Move schema/migration code out of repository runtime path into dedicated module.

### Phase 2: Remove Side Effects From Read Paths (1-2 days)
- Introduce explicit recurring materialization use case:
  - `materialize_due_recurring(as_of)`
- Stop calling recurring materialization from read methods (`snapshot`, `list_transactions_for_month`, `expense_breakdown_for_month`, etc.).
- Trigger materialization from deterministic points:
  - app startup
  - before dashboard refresh cycle (single call)
  - optional scheduled timer

### Phase 3: Decompose UI Monolith (3-5 days)
- Convert `MainWindow` to shell/composition root only.
- Move each tab to its own module with focused controller.
- Extract assistant rendering helpers to `ui/formatters/assistant_html.py`.
- Extract shared table fill + metric-card logic into `ui/widgets/` and `ui/helpers/`.

### Phase 4: Split Assistant Service (2-3 days)
- Break into:
  - context builder
  - response parser/repair
  - action executor
  - table response builder
- Replace direct repository private-method usage with public query APIs/use cases.
- Keep deterministic budget reallocator separate from LLM orchestration.

### Phase 5: Hardening and Performance (1-2 days)
- Add query-count and latency checks for assets and recurring-link views.
- Optimize asset-link expansion by pre-fetching recurring items once and avoiding repeated full-list calls.
- Add indexes where needed for recurring and link lookups.

## Testing Strategy During Migration
- Unit tests:
  - `tests/unit/repositories/*`
  - `tests/unit/services/assistant/*`
  - `tests/unit/use_cases/*`
- Contract tests:
  - Verify old facade and new repositories return equivalent results for key workflows.
- Integration tests (sqlite temp DB):
  - add/edit/delete transaction
  - recurring roll-forward and snapshot consistency
  - budget import/export and reallocation apply flow

## Refactor Safety Rules
- No feature changes during extraction commits.
- One module move per PR when possible.
- Keep old names as thin wrappers temporarily, then delete wrappers after callers migrate.
- Enforce no new file >500 lines in CI.

## Immediate First 10 Tasks
1. Add tests for recurring materialization side effects and snapshot consistency.
2. Create `infrastructure/db/connection.py` and move `_connection` there.
3. Extract `settings` + budget cap/floor methods into `settings_repository.py`.
4. Extract budget CRUD/query methods into `budget_repository.py`.
5. Introduce explicit recurring materializer use case and stop auto-materialization in one read method first.
6. Split assistant parsing/repair into `response_parser.py`.
7. Move assistant action application into `action_executor.py`.
8. Extract assistant HTML formatting from UI into `ui/formatters/assistant_html.py`.
9. Move budget tab build/refresh methods into `ui/tabs/budget_tab.py` + controller.
10. Add CI check for file line-count threshold and architecture import boundaries.

## Definition of Done
- No single production file above 500 lines.
- `MainWindow` reduced to orchestration shell (<300 lines).
- Persistence concerns split by bounded context.
- Read queries no longer trigger writes.
- Assistant pipeline modules independently unit-tested.
- Regression suite covers core CRUD, recurring, budget, asset links, and assistant actions.
