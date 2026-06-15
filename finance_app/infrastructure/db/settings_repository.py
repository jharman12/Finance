from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
import sqlite3


ConnectionFactory = Callable[[], AbstractContextManager[sqlite3.Connection] | Iterator[sqlite3.Connection]]


class SettingsRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connection_factory() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        cleaned_key = key.strip()
        if not cleaned_key:
            return

        with self._connection_factory() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (cleaned_key, value),
            )

    def get_category_budget_caps_floors(self) -> dict[str, dict[str, float]]:
        raw_value = self.get_setting("category_budget_caps_floors", "{}") or "{}"
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}

        if not isinstance(payload, dict):
            return {}

        normalized: dict[str, dict[str, float]] = {}
        for category, config in payload.items():
            if not isinstance(category, str) or not isinstance(config, dict):
                continue

            entry: dict[str, float] = {}
            floor_value = config.get("floor")
            cap_value = config.get("cap")
            try:
                if floor_value is not None:
                    entry["floor"] = max(0.0, float(floor_value))
                if cap_value is not None:
                    entry["cap"] = max(0.0, float(cap_value))
            except (TypeError, ValueError):
                continue

            if entry:
                normalized[category.strip()] = entry

        return normalized

    def set_category_budget_caps_floors(self, caps_floors: dict[str, dict[str, float]]) -> None:
        normalized: dict[str, dict[str, float]] = {}
        for category, config in caps_floors.items():
            if not isinstance(category, str) or not isinstance(config, dict):
                continue
            cleaned_category = category.strip()
            if not cleaned_category:
                continue

            entry: dict[str, float] = {}
            floor_value = config.get("floor")
            cap_value = config.get("cap")

            try:
                if floor_value is not None:
                    entry["floor"] = max(0.0, float(floor_value))
                if cap_value is not None:
                    entry["cap"] = max(0.0, float(cap_value))
            except (TypeError, ValueError):
                continue

            if entry:
                normalized[cleaned_category] = entry

        self.set_setting("category_budget_caps_floors", json.dumps(normalized, sort_keys=True))

    def get_monthly_savings_goal(self, year: int, month: int, default: float = 0.0) -> float:
        if month < 1 or month > 12:
            return float(default)

        key = f"savings_goal:{int(year):04d}-{int(month):02d}"
        raw_value = self.get_setting(key)
        if raw_value is None:
            return float(default)

        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return float(default)

    def set_monthly_savings_goal(self, year: int, month: int, value: float) -> None:
        if month < 1 or month > 12:
            return

        key = f"savings_goal:{int(year):04d}-{int(month):02d}"
        normalized_value = max(0.0, float(value))
        self.set_setting(key, f"{normalized_value:.2f}")
