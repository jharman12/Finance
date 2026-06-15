# AI Month-over-Month Budget Reallocation Plan

Date: 2026-06-15

## Objective
Add an AI-assisted planning flow that reviews previous months of spending and recommends next-month category budget reallocations while keeping total discretionary spend within budget and preserving savings goals.

This feature must:
- Run only when sufficient history exists.
- Use MoM time-series logic to predict next month allocations.
- Keep recommendations within total discretionary budget.
- Provide per-category reasoning and confidence.
- Generate a curated coaching goal message for the user.

Example goal style:
"Last month, you overspent on Entertainment and Dining. Try staying under budget on these items this month to increase savings."

## Current Integration Points
- Budget AI trigger in UI: finance_app/ui/main_window.py
- Existing AI budget allocation entry point: finance_app/services/assistant_service.py
- Monthly history helper: finance_app/storage.py
- Monthly savings goal persistence: finance_app/storage.py
- Monthly budget upsert/list APIs: finance_app/storage.py

## Feature Architecture
Use a deterministic local forecasting engine for numbers and constraints. Use LLM only for explanation polish and goal sentence tone.

1. UI Layer
- Add new action: AI Reallocate Next Month.
- Show a review table before apply:
  - Category
  - Current Budget
  - Recommended Budget
  - Delta %
  - Confidence
  - Reason
- Allow apply all or selected rows.
- If insufficient history, show explanatory banner and disable apply.

2. Service Layer
- Assistant service orchestrates:
  - Build typed input contract from repository data.
  - Call deterministic reallocator service.
  - Optionally polish explanation text with LLM.
  - Return structured payload for UI preview.

3. Deterministic Reallocator (new module)
- File: finance_app/services/budget_reallocator.py
- Responsibilities:
  - History gate
  - Forecast category amounts
  - Apply safety rules
  - Solve constraints to exact discretionary total
  - Build explainability output
  - Generate one-line coaching goal

4. Storage Layer
- Add repository helpers for:
  - Category MoM spend series
  - Income series
  - Budget caps/floors
  - Reallocation audit log

## Minimum-History Gate
Default threshold: 3 complete months.

Rules:
- If available full months < 3:
  - Return status: insufficient_history
  - Do not generate reallocations
  - Provide guidance message in UI
  - Optional fallback suggestion: keep current split

## Forecasting Model (MVP)
For each discretionary category c with last k months (k=3):

1. Weighted moving average
WMA_c = sum(w_i * x_i), with weights [0.2, 0.3, 0.5]

2. Trend
Delta_c = (latest - oldest) / (k - 1)

3. Raw forecast
raw_c = WMA_c + alpha * Delta_c, alpha = 0.6

4. Volatility band
sigma_c = std(history)
lower_c = raw_c - beta * sigma_c
upper_c = raw_c + beta * sigma_c, beta = 0.75

5. Preliminary prediction
pred_c = clamp(raw_c, lower_c, upper_c)

## Discretionary Budget Target
Compute target discretionary pool for next month:

discretionary_target = max(0, predicted_income_next_month - fixed_recurring_expenses_next_month - savings_goal_next_month)

All recommended discretionary category budgets must sum to this target.

## Safety Rules
1. Preserve critical categories
- Do not reduce below floor unless plan is globally infeasible.

2. Overspend lock
- If non-critical category overspent in 2 of last 3 months, do not increase unless strong trend justification is met.

3. Strong-trend justification threshold
- Score from trend strength, improving adherence, and low volatility.
- Allow increase only when score >= configured threshold (e.g., 0.65).

4. Prevent runaway increases
- Cap maximum increase percentage per month for non-critical categories.

## Constraint Solver
Goal: exact sum of category recommendations equals discretionary_target.

Steps:
1. Start with preliminary predictions.
2. Clamp each category by floor/cap.
3. Compute residual:
   residual = discretionary_target - sum(clamped_values)
4. If residual > 0:
   - distribute to under-cap categories by priority weights
5. If residual < 0:
   - reduce from reducible categories in priority order
6. If infeasible due to floors:
   - return infeasible flag and guidance
7. Round to cents and reconcile final penny-drift to hit exact target.

## Explainability Output Contract
Return a structured payload to UI.

Top-level:
- status: ready | insufficient_history | infeasible
- target_month
- discretionary_target
- total_recommended
- guardrail_flags
- goal_message
- recommendations: list

Per recommendation row:
- category
- old_amount
- new_amount
- change_percent
- reason_tags
- confidence
- explanation

## Goal Message Generation
Create one concise coaching sentence using strongest 1-2 behavioral findings:
- Overspend categories in last month
- Categories with largest negative variance
- Savings-goal impact

Pattern:
- Last month behavior + this month action + outcome target

Example:
- Last month, you overspent on Entertainment and Dining. Try staying under budget on these items this month to improve your savings result.

## API Plan
### New storage methods (finance_app/storage.py)
- list_monthly_category_spend(start_year, start_month, end_year, end_month, kind="expense")
- count_full_history_months(reference_year, reference_month, kind="expense")
- compute_income_series(reference_year, reference_month, months=6)
- get_current_month_budget_map(year, month, kind="expense")
- get_category_budget_caps_floors()
- set_category_budget_caps_floors(caps_floors)
- save_budget_reallocation_audit(payload)
- list_budget_reallocation_audits(limit=50)

### New service module (finance_app/services/budget_reallocator.py)
- generate_reallocation_plan(input_contract)
- forecast_category_amounts(category_history, config)
- apply_safety_rules(preliminary, context)
- solve_budget_constraints(preliminary, target_budget, caps_floors, safety_context)
- build_explainability_output(old_budgets, new_budgets, diagnostics)
- generate_goal_message(recommendations, global_context)
- compute_confidence(history, diagnostics)

### assistant_service additions (finance_app/services/assistant_service.py)
- generate_next_month_reallocation(reference_year, reference_month, min_history_months=3)
- _build_reallocation_input_contract(reference_year, reference_month, min_history_months)
- _polish_reallocation_explanations_with_llm(payload)
- apply_reallocation_plan(target_year, target_month, category_amounts, note_prefix="AI-reallocated")

### UI additions (finance_app/ui/main_window.py)
- Replace or extend AI suggestion flow with next-month reallocation mode
- _open_reallocation_review_dialog(payload)
- _apply_selected_reallocation_rows(target_year, target_month, rows)
- _show_insufficient_history_state(payload)

## Phased Delivery
### MVP
- Deterministic local engine
- 3-month history gate
- Next-month reallocation preview dialog
- Apply selected/all recommendations
- Explanation + confidence + goal sentence
- Audit log persistence
- Unit tests for gate + constraints + sum-equality invariants

### V2
- Seasonality support when >= 12 months history
- Personalization from user acceptance behavior
- Better uncertainty intervals
- Rollback/comparison UX between AI plans

## Metrics and Evaluation
Track these after rollout:
1. Projection error (MAPE) per category/month
2. Budget adherence rate: categories with actual <= recommended budget
3. User acceptance rate: accepted recommendations / total recommendations
4. Guardrail trigger frequency (overspend locks, infeasible floors)

## Risks and Mitigations
1. Sparse data instability
- Mitigation: strict history gate + conservative fallback

2. Exceeding discretionary total
- Mitigation: hard constraint solver and exact total reconciliation

3. Opaque recommendations
- Mitigation: required reason tags, confidence, old/new deltas

4. Unsafe growth in problematic categories
- Mitigation: overspend lock + trend-justification threshold

5. LLM hallucinated numbers
- Mitigation: deterministic numbers only; LLM can only polish text

## Build Sequence (Recommended)
1. Implement storage read APIs and audit table support
2. Implement budget_reallocator deterministic module
3. Add assistant_service orchestration methods
4. Add UI review/apply flow and insufficient-history state
5. Add tests and metrics logging
6. Run dry tests on seeded history data and verify budget-sum invariants
