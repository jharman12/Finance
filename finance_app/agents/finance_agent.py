from __future__ import annotations

from finance_app.agents.base_agent import AgentResponse, BaseAgent
from finance_app.services.llm_service import LLMRequest, LLMService

FINANCE_KEYWORDS = frozenset(
    {
        "budget",
        "budgets",
        "spend",
        "spent",
        "spending",
        "expense",
        "expenses",
        "income",
        "transaction",
        "transactions",
        "money",
        "cost",
        "paid",
        "pay",
        "payment",
        "savings",
        "save",
        "invest",
        "investment",
        "asset",
        "assets",
        "mortgage",
        "loan",
        "debt",
        "principal",
        "interest",
        "balance",
        "net",
        "cashflow",
        "afford",
        "reallocate",
        "category",
        "recurring",
        "bill",
        "bills",
        "dollars",
    }
)


class FinanceAgent(BaseAgent):
    """Proof-of-concept agent wrapping the existing finance assistant pipeline."""

    def __init__(self, llm_service: LLMService) -> None:
        self._llm_service = llm_service

    @property
    def name(self) -> str:
        return "finance"

    @property
    def description(self) -> str:
        return "Answers questions and makes changes to budgets, transactions, and assets."

    @property
    def keywords(self) -> frozenset[str]:
        return FINANCE_KEYWORDS

    def handle(self, request: LLMRequest) -> AgentResponse:
        result = self._llm_service.submit(request)
        outcome = getattr(self._llm_service, "last_outcome", None)
        metadata = {"cascade_tier": outcome.tier} if outcome is not None else {}
        return AgentResponse(result=result, agent_name=self.name, metadata=metadata)
