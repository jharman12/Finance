from __future__ import annotations

from statistics import mean, pstdev
from typing import Any


def generate_reallocation_plan(input_contract: dict) -> dict:
    """Generate a deterministic next-month reallocation plan from historical data."""
    reference_year = int(input_contract.get("reference_year", 0) or 0)
    reference_month = int(input_contract.get("reference_month", 0) or 0)
    target_year = int(input_contract.get("target_year", 0) or 0)
    target_month = int(input_contract.get("target_month", 0) or 0)

    min_history_months = int(input_contract.get("min_history_months", 3) or 3)
    history_available = int(input_contract.get("history_available_months", 0) or 0)

    if history_available < min_history_months:
        return {
            "reference_year": reference_year,
            "reference_month": reference_month,
            "target_year": target_year,
            "target_month": target_month,
            "status": "insufficient_history",
            "min_history_months": min_history_months,
            "history_available_months": history_available,
            "recommendations": [],
            "discretionary_target_budget": 0.0,
            "total_recommended_discretionary": 0.0,
            "goal_message": "Add more monthly history before AI reallocation can run.",
            "guardrail_flags": ["insufficient_history"],
        }

    inputs = input_contract.get("inputs", {})
    if not isinstance(inputs, dict):
        inputs = {}

    income_series = [float(value) for value in inputs.get("income_series", []) if _is_number(value)]
    predicted_income = _predict_next_income(income_series)

    recurring_fixed_expenses = inputs.get("recurring_fixed_expenses", [])
    if not isinstance(recurring_fixed_expenses, list):
        recurring_fixed_expenses = []
    fixed_total = sum(float(entry.get("amount", 0.0) or 0.0) for entry in recurring_fixed_expenses if isinstance(entry, dict))

    savings_goal = float(inputs.get("savings_goal", 0.0) or 0.0)
    discretionary_target_budget = max(0.0, predicted_income - fixed_total - savings_goal)

    category_history = inputs.get("category_history", [])
    if not isinstance(category_history, list):
        category_history = []

    if not category_history:
        return {
            "reference_year": reference_year,
            "reference_month": reference_month,
            "target_year": target_year,
            "target_month": target_month,
            "status": "insufficient_history",
            "min_history_months": min_history_months,
            "history_available_months": history_available,
            "recommendations": [],
            "discretionary_target_budget": discretionary_target_budget,
            "total_recommended_discretionary": 0.0,
            "goal_message": "No category history found to forecast from.",
            "guardrail_flags": ["missing_category_history"],
        }

    config = inputs.get("forecast_config", {})
    if not isinstance(config, dict):
        config = {}

    preliminary = forecast_category_amounts(category_history, config)
    safety_context = {
        "category_history": category_history,
        "increase_gate_threshold": float(config.get("increase_gate_threshold", 0.65) or 0.65),
    }
    post_safety, safety_flags = apply_safety_rules(preliminary, safety_context)

    caps_floors = inputs.get("category_caps_floors", {})
    if not isinstance(caps_floors, dict):
        caps_floors = {}

    solved, solve_flags = solve_budget_constraints(post_safety, discretionary_target_budget, caps_floors, safety_context)

    old_budgets: dict[str, float] = {}
    diagnostics: dict[str, dict[str, Any]] = {}
    for entry in category_history:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category", "")).strip()
        if not category:
            continue
        old_budgets[category] = float(entry.get("current_budget", 0.0) or 0.0)
        monthly_spend = entry.get("monthly_spend", [])
        history = [float(value) for value in monthly_spend if _is_number(value)]
        diagnostics[category] = {
            "history": history,
            "is_critical": bool(entry.get("is_critical", False)),
            "overspent_recently": bool(entry.get("overspent_recently", False)),
            "post_safety_amount": float(post_safety.get(category, 0.0)),
        }

    recommendations = build_explainability_output(old_budgets, solved, diagnostics)
    goal_message = generate_goal_message(recommendations, {
        "savings_goal": savings_goal,
        "discretionary_target_budget": discretionary_target_budget,
    })

    return {
        "reference_year": reference_year,
        "reference_month": reference_month,
        "target_year": target_year,
        "target_month": target_month,
        "status": "ready",
        "min_history_months": min_history_months,
        "history_available_months": history_available,
        "predicted_income": round(predicted_income, 2),
        "fixed_recurring_expenses": round(fixed_total, 2),
        "savings_goal": round(savings_goal, 2),
        "discretionary_target_budget": round(discretionary_target_budget, 2),
        "total_recommended_discretionary": round(sum(solved.values()), 2),
        "guardrail_flags": sorted(set(safety_flags + solve_flags)),
        "recommendations": recommendations,
        "goal_message": goal_message,
    }


def forecast_category_amounts(category_history: list[dict], config: dict) -> dict[str, float]:
    """Forecast category budgets from weighted moving average + trend."""
    alpha = float(config.get("alpha", 0.6) or 0.6)
    beta = float(config.get("beta", 0.75) or 0.75)
    weights = config.get("weights", [0.2, 0.3, 0.5])
    if not isinstance(weights, list) or len(weights) == 0:
        weights = [0.2, 0.3, 0.5]
    weights = [float(w) for w in weights if _is_number(w)]
    if not weights:
        weights = [0.2, 0.3, 0.5]

    forecast: dict[str, float] = {}
    for entry in category_history:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category", "")).strip()
        if not category:
            continue

        history = [float(value) for value in entry.get("monthly_spend", []) if _is_number(value)]
        if not history:
            current_budget = float(entry.get("current_budget", 0.0) or 0.0)
            forecast[category] = max(0.0, current_budget)
            continue

        if len(history) == 1:
            raw_forecast = history[-1]
            sigma = 0.0
        else:
            k = min(len(weights), len(history))
            recent_values = history[-k:]
            recent_weights = weights[-k:]
            weight_sum = sum(recent_weights) or 1.0
            normalized_weights = [w / weight_sum for w in recent_weights]
            wma = sum(value * weight for value, weight in zip(recent_values, normalized_weights))
            trend = (history[-1] - history[-k]) / max(1, (k - 1))
            raw_forecast = wma + alpha * trend
            sigma = pstdev(history) if len(history) > 1 else 0.0

        lower = raw_forecast - beta * sigma
        upper = raw_forecast + beta * sigma
        clamped = _clamp(raw_forecast, lower, upper)
        forecast[category] = max(0.0, float(clamped))

    return forecast


def apply_safety_rules(preliminary: dict, context: dict) -> tuple[dict, list[str]]:
    """Apply overspend and critical-category guardrails to preliminary allocations."""
    category_history = context.get("category_history", [])
    if not isinstance(category_history, list):
        category_history = []

    threshold = float(context.get("increase_gate_threshold", 0.65) or 0.65)
    history_by_category: dict[str, dict[str, Any]] = {}
    for entry in category_history:
        if isinstance(entry, dict):
            category = str(entry.get("category", "")).strip()
            if category:
                history_by_category[category] = entry

    adjusted = {str(category): float(amount) for category, amount in preliminary.items()}
    flags: list[str] = []

    for category, amount in list(adjusted.items()):
        entry = history_by_category.get(category, {})
        current_budget = float(entry.get("current_budget", 0.0) or 0.0)
        is_critical = bool(entry.get("is_critical", False))
        overspent_recently = bool(entry.get("overspent_recently", False))

        if is_critical and amount < current_budget:
            adjusted[category] = current_budget
            flags.append("critical_floor_protected")
            continue

        if not is_critical and overspent_recently and amount > current_budget:
            history = [float(value) for value in entry.get("monthly_spend", []) if _is_number(value)]
            score = _strong_trend_score(history)
            if score < threshold:
                adjusted[category] = current_budget
                flags.append("overspend_lock_applied")

    return adjusted, sorted(set(flags))


def solve_budget_constraints(
    preliminary: dict,
    target_budget: float,
    caps_floors: dict,
    safety_context: dict,
) -> tuple[dict, list[str]]:
    """Clamp and rebalance category amounts to match target budget exactly."""
    solved: dict[str, float] = {}
    floors: dict[str, float] = {}
    caps: dict[str, float] = {}

    for category, amount in preliminary.items():
        category_key = str(category)
        config = caps_floors.get(category_key, {}) if isinstance(caps_floors, dict) else {}
        floor_value = float(config.get("floor", 0.0) or 0.0) if isinstance(config, dict) else 0.0
        cap_value = float(config.get("cap", max(float(amount), floor_value)) or max(float(amount), floor_value))
        if cap_value < floor_value:
            cap_value = floor_value

        floors[category_key] = max(0.0, floor_value)
        caps[category_key] = max(floors[category_key], cap_value)
        solved[category_key] = _clamp(float(amount), floors[category_key], caps[category_key])

    flags: list[str] = []
    target = max(0.0, float(target_budget))
    total = sum(solved.values())
    residual = target - total

    if abs(residual) < 0.005:
        return _round_and_reconcile(solved, target), flags

    category_history = safety_context.get("category_history", [])
    history_map: dict[str, dict[str, Any]] = {}
    if isinstance(category_history, list):
        for entry in category_history:
            if isinstance(entry, dict):
                category = str(entry.get("category", "")).strip()
                if category:
                    history_map[category] = entry

    if residual > 0:
        remaining = residual
        while remaining > 0.005:
            candidates = [
                category for category, amount in solved.items() if amount < caps.get(category, amount)
            ]
            if not candidates:
                flags.append("under_allocated_no_capacity")
                break

            weights = {category: _increase_priority(history_map.get(category, {})) for category in candidates}
            weight_sum = sum(weights.values()) or 1.0
            progressed = False
            for category in candidates:
                share = remaining * (weights[category] / weight_sum)
                capacity = caps[category] - solved[category]
                delta = min(capacity, share)
                if delta > 0:
                    solved[category] += delta
                    remaining -= delta
                    progressed = True
            if not progressed:
                break
    else:
        remaining = abs(residual)
        while remaining > 0.005:
            candidates = [
                category for category, amount in solved.items() if amount > floors.get(category, 0.0)
            ]
            if not candidates:
                flags.append("infeasible_floor_constraints")
                break

            candidates = sorted(candidates, key=lambda c: _reduction_priority(history_map.get(c, {})))
            progressed = False
            for category in candidates:
                reducible = solved[category] - floors[category]
                if reducible <= 0:
                    continue
                delta = min(reducible, remaining)
                solved[category] -= delta
                remaining -= delta
                progressed = True
                if remaining <= 0.005:
                    break
            if not progressed:
                break

    return _round_and_reconcile(solved, target), sorted(set(flags))


def build_explainability_output(old_budgets: dict, new_budgets: dict, diagnostics: dict) -> list[dict]:
    """Build explainability rows for UI preview and user review."""
    rows: list[dict] = []
    all_categories = sorted(set(old_budgets.keys()) | set(new_budgets.keys()))

    for category in all_categories:
        old_amount = float(old_budgets.get(category, 0.0) or 0.0)
        new_amount = float(new_budgets.get(category, 0.0) or 0.0)
        if abs(new_amount - old_amount) < 0.01:
            continue

        delta = new_amount - old_amount
        change_percent = 0.0 if old_amount == 0 else (delta / old_amount) * 100.0

        detail = diagnostics.get(category, {}) if isinstance(diagnostics, dict) else {}
        history = detail.get("history", [])
        if not isinstance(history, list):
            history = []

        reason_tags: list[str] = []
        if delta > 0:
            reason_tags.append("trend_up")
        else:
            reason_tags.append("cost_control")
        if bool(detail.get("is_critical", False)):
            reason_tags.append("critical_preserved")
        if bool(detail.get("overspent_recently", False)):
            reason_tags.append("overspent_recently")

        confidence = compute_confidence([float(v) for v in history if _is_number(v)], detail)
        explanation = _build_explanation_sentence(category, delta, old_amount, new_amount, reason_tags)

        rows.append(
            {
                "category": category,
                "old_amount": round(old_amount, 2),
                "new_amount": round(new_amount, 2),
                "change_percent": round(change_percent, 2),
                "reason_tags": reason_tags,
                "confidence": round(confidence, 3),
                "explanation": explanation,
            }
        )

    rows.sort(key=lambda row: abs(float(row["change_percent"])), reverse=True)
    return rows


def generate_goal_message(recommendations: list[dict], global_context: dict) -> str:
    """Generate a concise coaching goal sentence from top recommendation signals."""
    if not recommendations:
        savings_goal = float(global_context.get("savings_goal", 0.0) or 0.0)
        if savings_goal > 0:
            return f"Keep spending steady this month and protect your ${savings_goal:,.2f} savings target."
        return "No major reallocation changes were needed this month."

    reductions = [row for row in recommendations if float(row.get("change_percent", 0.0)) < 0]
    target_rows = reductions[:2] if reductions else recommendations[:2]
    target_categories = [str(row.get("category", "")).strip() for row in target_rows if str(row.get("category", "")).strip()]

    if len(target_categories) >= 2:
        joined = " and ".join(target_categories[:2])
        return (
            f"Last month, you over spent on targeted budget for both {joined}. "
            "Try staying under budget on these items this month to increase savings goals!"
        )
    if len(target_categories) == 1:
        return (
            f"Last month, you over spent on targeted budget for {target_categories[0]}. "
            "Try staying under budget on this item this month to increase savings goals!"
        )

    return "Focus on the adjusted categories this month to improve savings performance."


def compute_confidence(history: list[float], diagnostics: dict) -> float:
    """Compute a bounded confidence score using history stability and availability."""
    if not history:
        return 0.35

    avg_value = abs(mean(history))
    volatility = pstdev(history) if len(history) > 1 else 0.0
    stability = 1.0 - (volatility / (avg_value + 1.0))
    stability = _clamp(stability, 0.0, 1.0)

    history_factor = _clamp(len(history) / 6.0, 0.3, 1.0)
    overspend_penalty = 0.05 if bool(diagnostics.get("overspent_recently", False)) else 0.0

    confidence = 0.35 + 0.5 * stability + 0.15 * history_factor - overspend_penalty
    return _clamp(confidence, 0.3, 0.95)


def _predict_next_income(income_series: list[float]) -> float:
    if not income_series:
        return 0.0
    if len(income_series) == 1:
        return max(0.0, income_series[-1])

    k = min(3, len(income_series))
    weights = [0.2, 0.3, 0.5][-k:]
    values = income_series[-k:]
    weight_sum = sum(weights) or 1.0
    normalized = [weight / weight_sum for weight in weights]
    baseline = sum(value * weight for value, weight in zip(values, normalized))
    trend = (values[-1] - values[0]) / max(1, (k - 1))
    return max(0.0, baseline + 0.5 * trend)


def _strong_trend_score(history: list[float]) -> float:
    if len(history) < 2:
        return 0.0

    latest = history[-1]
    oldest = history[0]
    trend = latest - oldest
    avg = abs(mean(history)) + 1.0
    trend_component = _clamp((trend / avg + 1.0) / 2.0, 0.0, 1.0)

    volatility = pstdev(history) if len(history) > 1 else 0.0
    volatility_component = _clamp(1.0 - (volatility / avg), 0.0, 1.0)

    return 0.65 * trend_component + 0.35 * volatility_component


def _increase_priority(entry: dict[str, Any]) -> float:
    is_critical = bool(entry.get("is_critical", False))
    overspent_recently = bool(entry.get("overspent_recently", False))
    score = 1.0
    if is_critical:
        score += 0.35
    if overspent_recently:
        score -= 0.2
    return max(0.2, score)


def _reduction_priority(entry: dict[str, Any]) -> float:
    is_critical = bool(entry.get("is_critical", False))
    overspent_recently = bool(entry.get("overspent_recently", False))

    # Lower score means reduce earlier.
    score = 1.0
    if not is_critical:
        score -= 0.4
    if overspent_recently:
        score -= 0.3
    return score


def _build_explanation_sentence(
    category: str,
    delta: float,
    old_amount: float,
    new_amount: float,
    reason_tags: list[str],
) -> str:
    if delta > 0:
        direction = "increased"
    else:
        direction = "reduced"

    tag_text = ", ".join(reason_tags)
    return (
        f"{category} was {direction} from ${old_amount:,.2f} to ${new_amount:,.2f} "
        f"based on observed trend and controls ({tag_text})."
    )


def _round_and_reconcile(values: dict[str, float], target: float) -> dict[str, float]:
    rounded = {category: round(amount, 2) for category, amount in values.items()}
    drift = round(target - sum(rounded.values()), 2)

    if abs(drift) < 0.01 or not rounded:
        return rounded

    # Apply residual pennies to the largest bucket to preserve exact total.
    largest_category = max(rounded.keys(), key=lambda key: rounded[key])
    rounded[largest_category] = round(rounded[largest_category] + drift, 2)
    return rounded


def _clamp(value: float, lower: float, upper: float) -> float:
    if lower > upper:
        lower, upper = upper, lower
    return max(lower, min(upper, value))


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
