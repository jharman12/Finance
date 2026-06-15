from __future__ import annotations

from finance_app.storage import FinanceRepository


class CategoryController:
    def __init__(self, repository: FinanceRepository) -> None:
        self._repository = repository

    def list_categories(self, kind: str):
        return self._repository.list_categories(kind=kind)

    def category_exists(self, kind: str, category_name: str) -> bool:
        normalized = category_name.strip().lower()
        if not normalized:
            return False
        return any(category.name.lower() == normalized for category in self._repository.list_categories(kind=kind))

    def ensure_category(self, category_name: str, kind: str) -> None:
        self._repository.ensure_category(category_name, kind)

    def delete_category(self, category_name: str, kind: str) -> bool:
        return self._repository.delete_category(category_name, kind)
