from __future__ import annotations

from finance_app.models import PairedRemoteDevice
from finance_app.storage import FinanceRepository


class AppController:
    def __init__(self, repository: FinanceRepository) -> None:
        self._repository = repository

    def get_setting(self, key: str, default: str | None = None):
        return self._repository.get_setting(key, default)

    def set_setting(self, key: str, value: str) -> None:
        self._repository.set_setting(key, value)

    def export_to_csv(self, directory: str):
        return self._repository.export_to_csv(directory)

    def import_from_csv(self, directory: str, clear_first: bool = False):
        return self._repository.import_from_csv(directory, clear_first=clear_first)

    def sync_recurring_with_transactions(self):
        return self._repository.sync_recurring_with_transactions()

    def materialize_due_recurring_items(self) -> None:
        self._repository.materialize_due_recurring_items()

    def save_paired_remote_device(self, device: PairedRemoteDevice) -> PairedRemoteDevice:
        return self._repository.save_paired_remote_device(device)

    def list_paired_remote_devices(self, active_only: bool = True) -> list[PairedRemoteDevice]:
        return self._repository.list_paired_remote_devices(active_only=active_only)

    def get_paired_remote_device(self, source_id: str) -> PairedRemoteDevice | None:
        return self._repository.get_paired_remote_device(source_id)

    def update_paired_device_connection_time(self, source_id: str) -> None:
        self._repository.update_paired_device_connection_time(source_id)

    def remove_paired_remote_device(self, source_id: str) -> None:
        self._repository.remove_paired_remote_device(source_id)
