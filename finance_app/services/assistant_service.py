from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from finance_app.config import SYSTEM_PROMPT
from finance_app.models import AssistantResult
from finance_app.services.ollama_client import OllamaClient, OllamaMessage
from finance_app.storage import FinanceRepository


@dataclass(slots=True)
class AssistantContext:
    snapshot_text: str
    categories_text: str
    recurring_text: str


class AssistantService:
    def __init__(self, repository: FinanceRepository, client: OllamaClient | None = None) -> None:
        self.repository = repository
        self.client = client or OllamaClient()
        self.conversation_history: list[OllamaMessage] = []  # Maintain conversation memory

    def build_context(self) -> AssistantContext:
        snapshot = self.repository.snapshot()
        categories = self.repository.list_categories()
        recurring_items = self.repository.list_recurring_items()

        snapshot_text = (
            f"Income total: {snapshot.income_total:.2f}\n"
            f"Expense total: {snapshot.expense_total:.2f}\n"
            f"Net total: {snapshot.net_total:.2f}\n"
            f"Transaction count: {snapshot.transaction_count}\n"
            f"Top categories: {snapshot.top_categories}"
        )
        categories_text = ", ".join(f"{category.name} ({category.kind})" for category in categories)
        recurring_text = ", ".join(
            f"{item.description} [{item.kind}] in category {item.category} - {item.amount:.2f} {item.cadence_label} next {item.next_run_on.isoformat()}"
            for item in recurring_items
        )
        return AssistantContext(snapshot_text=snapshot_text, categories_text=categories_text, recurring_text=recurring_text)

    def handle_prompt(self, prompt_text: str) -> AssistantResult:
        context = self.build_context()
        
        # Build context message with current app state
        context_message = (
            "Current app state:\n"
            f"{context.snapshot_text}\n\n"
            f"Known categories: {context.categories_text or 'None'}\n\n"
            f"Recurring items: {context.recurring_text or 'None'}\n\n"
            f"User request: {prompt_text.strip()}"
        )
        
        # Build messages list with conversation history
        messages = [OllamaMessage(role="system", content=SYSTEM_PROMPT)]
        
        # Add all previous conversation turns (limited to last 10 to avoid token bloat)
        max_history = 10
        if len(self.conversation_history) > max_history:
            messages.extend(self.conversation_history[-max_history:])
        else:
            messages.extend(self.conversation_history)
        
        # Add current user message with context
        user_message = OllamaMessage(role="user", content=context_message)
        messages.append(user_message)

        raw_response = self.client.chat(messages, json_mode=True)
        payload = self._parse_payload(raw_response)

        if self._should_retry_for_actions(prompt_text, payload):
            repaired_raw, repaired_payload = self._retry_with_action_enforcement(
                messages=messages,
                original_response=raw_response,
            )
            if repaired_payload is not None:
                raw_response = repaired_raw
                payload = repaired_payload
        
        # Check if response appears incomplete (for analysis questions) and retry if needed
        reply_text = str(payload.get("reply", "")).strip()
        if self._is_analysis_question(prompt_text) and self._is_response_incomplete(reply_text):
            completion_result = self._retry_for_completion(
                messages=messages,
                original_response=raw_response,
                partial_reply=reply_text,
            )
            if completion_result is not None:
                raw_response, payload = completion_result
        
        result = AssistantResult(
            reply=str(payload.get("reply", "")) or raw_response,
            actions=list(payload.get("actions", [])) if isinstance(payload.get("actions", []), list) else [],
            raw_payload=payload,
        )

        result.applied_actions = self._apply_actions(result.actions)
        result.display_tables = self._build_display_tables(result.actions)
        
        # Store in conversation history for future context
        self.conversation_history.append(user_message)
        self.conversation_history.append(OllamaMessage(role="assistant", content=raw_response))
        
        return result

    def _parse_payload(self, raw_response: str) -> dict[str, Any]:
        candidate = raw_response.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
            candidate = re.sub(r"\s*```$", "", candidate)

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            json_text = self._extract_json_object(candidate)
            if json_text:
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    pass

        return {"reply": raw_response, "actions": []}

    def _extract_json_object(self, text: str) -> str | None:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start : end + 1]

    def _should_retry_for_actions(self, prompt_text: str, payload: dict[str, Any]) -> bool:
        if not self._is_mutation_request(prompt_text):
            return False
        actions = payload.get("actions", [])
        return not isinstance(actions, list) or len(actions) == 0

    def _is_mutation_request(self, prompt_text: str) -> bool:
        text = (prompt_text or "").lower()
        mutation_keywords = (
            "add ",
            "create",
            "edit",
            "update",
            "change",
            "reassign",
            "assign",
            "move",
            "rename",
            "delete",
            "remove",
        )
        return any(keyword in text for keyword in mutation_keywords)

    def _is_analysis_question(self, prompt_text: str) -> bool:
        """Check if this is an analysis/advice question (not a mutation)."""
        if self._is_mutation_request(prompt_text):
            return False
        text = (prompt_text or "").lower()
        analysis_keywords = (
            "how ",
            "what ",
            "should ",
            "analyze",
            "summary",
            "trend",
            "advice",
            "recommend",
            "budget",
            "spending",
            "overspend",
            "savings",
            "looking",
            "health",
            "pattern",
        )
        return any(keyword in text for keyword in analysis_keywords)

    def _is_response_incomplete(self, reply_text: str) -> bool:
        """Detect if a response appears to be cut off or incomplete."""
        if not reply_text:
            return True
        
        reply_lower = reply_text.lower().strip()
        lines = reply_text.strip().split('\n')
        last_line = lines[-1].strip() if lines else ""
        
        # Look for signs of incompleteness - setup text without actual content
        setup_indicators = (
            "let me",
            "here is a detailed",
            "here are",
            "based on",
            "looking at",
            "according to",
            "i've analyzed",
            "i can see",
            "let me provide",
            "let me analyze",
            "to give you",
            "to provide you",
        )
        
        # If response starts with setup/intro text
        if any(indicator in reply_lower[:80] for indicator in setup_indicators):
            # More precise check: need numbered list or specific dollar actions
            has_numbered_actions = any(marker in reply_text for marker in ["1)", "2)", "3)"])
            has_dollar_actions = ("$" in reply_text and any(
                word in reply_lower for word in ["reduce", "cut", "increase", "save", "to"]
            ))
            has_concrete_content = has_numbered_actions or has_dollar_actions
            
            # If it's pure setup without concrete numbered recommendations or money-specific actions
            if not has_concrete_content:
                return True
            
            # If it has some action content but is still quite short (maybe just one brief recommendation)
            if len(reply_text) < 200:
                return True
        
        # Check if it ends mid-sentence (no punctuation)
        if last_line and not any(last_line.endswith(p) for p in ['.', '!', '?', '"', "'"]):
            if len(last_line) > 20:
                return True
        
        return False

    def _retry_for_completion(
        self,
        messages: list[OllamaMessage],
        original_response: str,
        partial_reply: str,
    ) -> tuple[str, dict[str, Any]] | None:
        """Retry to complete an incomplete response."""
        continuation_prompt = (
            "Your previous response appears incomplete or cut off. "
            "Please provide the COMPLETE analysis and recommendations, continuing from where you left off or starting fresh. "
            "Include:\n"
            "1. Full financial health assessment\n"
            "2. Specific spending concerns with amounts\n"
            "3. Comparison to healthy spending benchmarks\n"
            "4. At least 3-5 specific, actionable recommendations\n"
            "5. Prioritized by impact and ease of implementation\n"
            "\n"
            "Return as strictly valid JSON: {\"reply\": \"complete analysis here\", \"actions\": []}\n"
            "Ensure the reply field contains the complete, untruncated analysis."
        )
        
        completion_messages = list(messages)
        completion_messages.append(OllamaMessage(role="assistant", content=original_response))
        completion_messages.append(OllamaMessage(role="user", content=continuation_prompt))
        
        try:
            completion_raw = self.client.chat(completion_messages, json_mode=True)
            completion_payload = self._parse_payload(completion_raw)
            
            # Only return if we got a better response
            completion_reply = str(completion_payload.get("reply", "")).strip()
            if len(completion_reply) > len(partial_reply):
                return completion_raw, completion_payload
        except Exception:
            pass
        
        return None

    def _retry_with_action_enforcement(
        self,
        messages: list[OllamaMessage],
        original_response: str,
    ) -> tuple[str, dict[str, Any] | None]:
        # Build a contextual retry prompt based on what we can detect
        repair_instruction = (
            "Your previous answer did not include any executable actions. "
            "Return ONLY strictly valid JSON with this exact shape: "
            '{"reply": "explanation here", "actions": [{"type": "action_name", "payload": {...}}]}. '
            "\n\n"
            "For REASSIGNING RECURRING ITEMS by description, use:\n"
            '{"type": "change_recurring_category", "payload": {"from_category": "CurrentCat", "to_category": "NewCat", "description_contains": "item description"}}\n'
            "\n"
            "For REASSIGNING TRANSACTIONS by description, use:\n"
            '{"type": "change_transaction_category", "payload": {"from_category": "CurrentCat", "to_category": "NewCat", "description_contains": "search term"}}\n'
            "\n"
            "For CREATING NEW CATEGORIES, use:\n"
            '{"type": "add_category", "payload": {"name": "CategoryName", "kind": "expense"}}\n'
            "\n"
            "For SHOWING DATA TABLES IN CHAT, use:\n"
            '{"type": "show_table", "payload": {"table": "upcoming_recurring", "kind": "expense", "status": "not_occurred_yet"}}\n'
            "\n"
            "KEY RULES:\n"
            "- Always include the from_category and to_category\n"
            "- Use description_contains to filter items by description\n"
            "- For read-only table requests, return show_table actions\n"
            "- Do NOT return a plan without actions\n"
            "- Return actions IMMEDIATELY in valid JSON\n"
            "\n"
            "Now provide the corrected JSON response:"
        )

        repair_messages = list(messages)
        repair_messages.append(OllamaMessage(role="assistant", content=original_response))
        repair_messages.append(OllamaMessage(role="user", content=repair_instruction))

        repaired_raw = self.client.chat(repair_messages, json_mode=True)
        repaired_payload = self._parse_payload(repaired_raw)
        actions = repaired_payload.get("actions", []) if isinstance(repaired_payload, dict) else []
        if isinstance(actions, list) and len(actions) > 0:
            return repaired_raw, repaired_payload
        return repaired_raw, None

    def _apply_actions(self, actions: list[dict[str, Any]]) -> list[str]:
        applied_messages: list[str] = []
        for action in actions:
            action_type = str(action.get("type", "")).strip()
            payload = action.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            if action_type == "add_expense":
                transaction_id = self.repository.add_expense(
                    amount=float(payload.get("amount", 0.0)),
                    category=str(payload.get("category", "Other")),
                    description=str(payload.get("description", "Assistant entry")),
                    occurred_on=self._parse_date(payload.get("occurred_on")),
                )
                applied_messages.append(f"Added expense #{transaction_id}")
            elif action_type == "add_income":
                transaction_id = self.repository.add_income(
                    amount=float(payload.get("amount", 0.0)),
                    category=str(payload.get("category", "Salary")),
                    description=str(payload.get("description", "Assistant entry")),
                    occurred_on=self._parse_date(payload.get("occurred_on")),
                )
                applied_messages.append(f"Added income #{transaction_id}")
            elif action_type == "add_category":
                category_name = str(payload.get("name", "")).strip()
                category_kind = str(payload.get("kind", "expense")).strip() or "expense"
                self.repository.ensure_category(category_name, category_kind)
                if category_name:
                    applied_messages.append(f"Added category {category_name}")
            elif action_type == "add_recurring_item":
                recurring_kind = str(payload.get("kind", "expense")).strip() or "expense"
                recurring_id = self.repository.add_recurring_item(
                    kind=recurring_kind,
                    amount=float(payload.get("amount", 0.0)),
                    category=str(payload.get("category", "Other")),
                    description=str(payload.get("description", "Recurring entry")),
                    interval_count=max(1, int(payload.get("interval_count", 1))),
                    interval_unit=str(payload.get("interval_unit", "months")),
                    start_on=self._parse_date(payload.get("start_on")),
                    is_active=bool(payload.get("is_active", True)),
                )
                applied_messages.append(f"Added recurring item #{recurring_id}")
            elif action_type == "change_transaction_category":
                from_category = str(payload.get("from_category", "")).strip()
                to_category = str(payload.get("to_category", "")).strip()
                desc_filter = str(payload.get("description_contains", "")).strip() or None
                if from_category and to_category:
                    count = self.repository.change_transaction_category(from_category, to_category, desc_filter)
                    if desc_filter:
                        applied_messages.append(f"Reassigned {count} transactions from {from_category} to {to_category} (description contains '{desc_filter}')")
                    else:
                        applied_messages.append(f"Reassigned {count} transactions from {from_category} to {to_category}")
            elif action_type == "change_recurring_category":
                from_category = str(payload.get("from_category", "")).strip()
                to_category = str(payload.get("to_category", "")).strip()
                desc_filter = str(payload.get("description_contains", "")).strip() or None
                if from_category and to_category:
                    recurring_count = self.repository.change_recurring_category(from_category, to_category, desc_filter)
                    # Also recategorize existing transactions from this recurring item
                    transaction_count = self.repository.change_transaction_category(from_category, to_category, desc_filter)
                    if desc_filter:
                        applied_messages.append(
                            f"Reassigned {recurring_count} recurring items from {from_category} to {to_category} (description contains '{desc_filter}')"
                        )
                        if transaction_count > 0:
                            applied_messages.append(
                                f"Also reassigned {transaction_count} existing transactions from {from_category} to {to_category}"
                            )
                    else:
                        applied_messages.append(f"Reassigned {recurring_count} recurring items from {from_category} to {to_category}")
                        if transaction_count > 0:
                            applied_messages.append(f"Also reassigned {transaction_count} existing transactions")
            elif action_type == "summarize":
                summary = self.repository.snapshot()
                applied_messages.append(
                    f"Income {summary.income_total:.2f}, expense {summary.expense_total:.2f}, net {summary.net_total:.2f}"
                )

        return applied_messages

    def _build_display_tables(self, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        for action in actions:
            action_type = str(action.get("type", "")).strip()
            payload = action.get("payload", {})
            if action_type != "show_table" or not isinstance(payload, dict):
                continue

            table_name = str(payload.get("table", "")).strip()
            if table_name == "upcoming_recurring":
                kind = str(payload.get("kind", "expense")).strip() or "expense"
                rows = self._get_upcoming_recurring_rows(kind=kind)
                tables.append(
                    {
                        "title": "Upcoming Recurring Items",
                        "columns": ["Description", "Category", "Kind", "Amount", "Next Run", "Active"],
                        "rows": rows,
                    }
                )
        return tables

    def _get_upcoming_recurring_rows(self, kind: str) -> list[list[str]]:
        items = self.repository.list_recurring_items(active_only=True)
        today = date.today()
        rows: list[list[str]] = []
        for item in items:
            if item.kind != kind:
                continue
            if item.next_run_on <= today:
                continue
            rows.append(
                [
                    item.description,
                    item.category,
                    item.kind,
                    f"${item.amount:,.2f}",
                    item.next_run_on.isoformat(),
                    "Yes" if item.is_active else "No",
                ]
            )
        rows.sort(key=lambda row: row[4])
        return rows

    def generate_budget_allocation(
        self, year: int, month: int, available_income: float, recurring_expenses_list: list | None = None
    ) -> dict[str, float]:
        """Use Ollama to intelligently allocate budget across expense categories.
        
        Args:
            year: Budget year
            month: Budget month
            available_income: Available discretionary budget (after recurring expenses)
            recurring_expenses_list: Optional list of RecurringItem objects that are already budgeted
        
        Returns a dict mapping category names to budgeted amounts.
        """
        # Get expense categories and their historical averages
        expense_categories = self.repository.list_categories(kind="expense")
        
        # Determine which categories are already allocated (recurring)
        recurring_categories = set()
        if recurring_expenses_list:
            recurring_categories = {item.category for item in recurring_expenses_list}
        
        # Calculate spending history for this month (excluding recurring categories)
        month_spending = {}
        for category in expense_categories:
            if category.name in recurring_categories:
                continue  # Skip recurring categories
            actual_spent = self.repository._get_actual_spent_for_category(year, month, category.name, "expense")
            if actual_spent > 0:
                month_spending[category.name] = actual_spent
        
        # Get last 3 months of spending patterns (excluding recurring categories)
        spending_history = {}
        for offset in range(1, 4):
            past_year, past_month = self.repository._shift_month(year, month, -offset)
            expense_breakdown = self.repository.expense_breakdown_for_month(past_year, past_month)
            
            for category, amount in expense_breakdown:
                if category in recurring_categories:
                    continue  # Skip recurring categories
                if category not in spending_history:
                    spending_history[category] = []
                spending_history[category].append(amount)
        
        # Build context for the AI (discretionary categories only)
        discretionary_categories = [cat.name for cat in expense_categories if cat.name not in recurring_categories]
        categories_list = ", ".join(discretionary_categories) if discretionary_categories else "None (all expenses are recurring)"
        
        spending_summary = ""
        for category, amounts in spending_history.items():
            avg_amount = sum(amounts) / len(amounts) if amounts else 0
            spending_summary += f"- {category}: ${avg_amount:.2f} average (last 3 months)\n"
        
        current_spending = ""
        total_current = 0.0
        for category, amount in sorted(month_spending.items()):
            current_spending += f"- {category}: ${amount:.2f}\n"
            total_current += amount
        
        categories_without_spending = [cat for cat in discretionary_categories if cat not in month_spending]
        
        recurring_note = ""
        if recurring_expenses_list:
            recurring_note = "\n\nNOTE: The following recurring items are ALREADY BUDGETED at their full amounts and should NOT be included in this allocation:\n"
            for item in recurring_expenses_list:
                recurring_note += f"- {item.category}: ${item.amount:.2f} (recurring)\n"
        
        prompt = f"""You are a professional financial advisor. Create a budget allocation for DISCRETIONARY spending this month.

AVAILABLE MONTHLY DISCRETIONARY BUDGET: ${available_income:.2f}
(This is after all recurring expenses have been allocated)

DISCRETIONARY EXPENSE CATEGORIES: {categories_list}
{recurring_note}

HISTORICAL DISCRETIONARY SPENDING PATTERNS (last 3 months, excluding recurring):
{spending_summary if spending_summary else "No data available"}

CURRENT MONTH DISCRETIONARY SPENDING TO DATE:
{current_spending if current_spending else "No spending yet this month"}
Total discretionary so far: ${total_current:.2f}

CATEGORIES WITHOUT RECENT DISCRETIONARY SPENDING: {', '.join(categories_without_spending) if categories_without_spending else 'None'}

Please analyze this data and create a professional discretionary budget that:
1. Does NOT exceed ${available_income:.2f} total
2. Allocates to discretionary/non-recurring categories only
3. Works with typical financial guidelines
4. Protects for unexpected discretionary expenses by including a buffer

Respond ONLY with a JSON object in this exact format (no markdown, no extra text):
{{
  "budgets": [
    {{"category": "Category Name", "amount": 0.00, "reasoning": "brief explanation"}},
    {{"category": "Another Category", "amount": 0.00, "reasoning": "brief explanation"}}
  ],
  "total_allocated": 0.00,
  "unused_buffer": 0.00,
  "summary": "brief overall budget summary"
}}"""

        try:
            raw_response = self.client.chat(
                [OllamaMessage(role="user", content=prompt)],
                json_mode=True
            )
            
            # Parse response
            candidate = raw_response.strip()
            if candidate.startswith("```"):
                candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
                candidate = re.sub(r"\s*```$", "", candidate)
            
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                json_text = self._extract_json_object(candidate)
                if json_text:
                    payload = json.loads(json_text)
                else:
                    return {}
            
            # Extract budgets into dict
            allocations = {}
            budgets_list = payload.get("budgets", [])
            if isinstance(budgets_list, list):
                for budget_entry in budgets_list:
                    if isinstance(budget_entry, dict):
                        category = str(budget_entry.get("category", "")).strip()
                        amount = float(budget_entry.get("amount", 0.0))
                        if category and amount > 0:
                            allocations[category] = amount
            
            return allocations
            
        except Exception:
            # Fallback: equal distribution across categories
            if expense_categories:
                per_category = available_income * 0.8 / len(expense_categories)  # Use 80% of income
                return {cat.name: per_category for cat in expense_categories if cat.name}
            return {}

    def clear_conversation_history(self) -> None:
        """Clear the conversation history. Use when starting a new session."""
        self.conversation_history = []

    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation history for display."""
        if not self.conversation_history:
            return "No conversation history yet. Start chatting with the financial advisor!"
        
        # Count user messages (every other message, starting at index 0)
        user_turns = len([m for m in self.conversation_history if m.role == "user"])
        return f"You've had {user_turns} exchanges with your financial advisor in this session."

    def _parse_date(self, value: Any) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None
