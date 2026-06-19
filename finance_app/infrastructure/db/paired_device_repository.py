from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Callable, Iterator

from finance_app.models import PairedRemoteDevice


class PairedRemoteDeviceRepository:
    """Manage paired remote voice devices in persistent storage."""

    def __init__(self, connection_factory: Callable[[], Iterator[sqlite3.Connection]]) -> None:
        self.connection_factory = connection_factory

    def list_all(self) -> list[PairedRemoteDevice]:
        """Get all paired devices, active or not."""
        with self.connection_factory() as conn:
            rows = conn.execute(
                """
                SELECT id, source_id, device_name, host_ip, port, role, protocol_version,
                       paired_at, last_connected_at, is_active
                FROM paired_remote_devices
                ORDER BY paired_at DESC
                """
            ).fetchall()

            return [self._row_to_model(row) for row in rows]

    def list_active(self) -> list[PairedRemoteDevice]:
        """Get only active paired devices."""
        with self.connection_factory() as conn:
            rows = conn.execute(
                """
                SELECT id, source_id, device_name, host_ip, port, role, protocol_version,
                       paired_at, last_connected_at, is_active
                FROM paired_remote_devices
                WHERE is_active = 1
                ORDER BY paired_at DESC
                """
            ).fetchall()

            return [self._row_to_model(row) for row in rows]

    def get_by_source_id(self, source_id: str) -> PairedRemoteDevice | None:
        """Get a paired device by its source ID."""
        with self.connection_factory() as conn:
            row = conn.execute(
                """
                SELECT id, source_id, device_name, host_ip, port, role, protocol_version,
                       paired_at, last_connected_at, is_active
                FROM paired_remote_devices
                WHERE source_id = ?
                """,
                (source_id,),
            ).fetchone()

            return self._row_to_model(row) if row else None

    def save(self, device: PairedRemoteDevice) -> PairedRemoteDevice:
        """Save or update a paired device."""
        with self.connection_factory() as conn:
            if device.id is None:
                cursor = conn.execute(
                    """
                    INSERT INTO paired_remote_devices
                    (source_id, device_name, host_ip, port, role, protocol_version, paired_at, last_connected_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device.source_id,
                        device.device_name,
                        device.host_ip,
                        device.port,
                        device.role,
                        device.protocol_version,
                        device.paired_at.isoformat() if isinstance(device.paired_at, datetime) else device.paired_at,
                        device.last_connected_at.isoformat()
                        if device.last_connected_at and isinstance(device.last_connected_at, datetime)
                        else device.last_connected_at,
                        1 if device.is_active else 0,
                    ),
                )
                device.id = cursor.lastrowid
            else:
                conn.execute(
                    """
                    UPDATE paired_remote_devices
                    SET device_name = ?, host_ip = ?, port = ?, role = ?, protocol_version = ?,
                        paired_at = ?, last_connected_at = ?, is_active = ?
                    WHERE id = ?
                    """,
                    (
                        device.device_name,
                        device.host_ip,
                        device.port,
                        device.role,
                        device.protocol_version,
                        device.paired_at.isoformat() if isinstance(device.paired_at, datetime) else device.paired_at,
                        device.last_connected_at.isoformat()
                        if device.last_connected_at and isinstance(device.last_connected_at, datetime)
                        else device.last_connected_at,
                        1 if device.is_active else 0,
                        device.id,
                    ),
                )

            return device

    def update_last_connected(self, source_id: str) -> None:
        """Update the last connected timestamp for a device."""
        with self.connection_factory() as conn:
            conn.execute(
                """
                UPDATE paired_remote_devices
                SET last_connected_at = CURRENT_TIMESTAMP
                WHERE source_id = ?
                """,
                (source_id,),
            )

    def delete(self, source_id: str) -> None:
        """Soft delete (deactivate) a paired device."""
        with self.connection_factory() as conn:
            conn.execute(
                """
                UPDATE paired_remote_devices
                SET is_active = 0
                WHERE source_id = ?
                """,
                (source_id,),
            )

    def _row_to_model(self, row: sqlite3.Row | None) -> PairedRemoteDevice | None:
        if row is None:
            return None

        paired_at_str = row["paired_at"]
        paired_at = datetime.fromisoformat(paired_at_str) if isinstance(paired_at_str, str) else paired_at_str

        last_connected_str = row["last_connected_at"]
        last_connected_at = (
            datetime.fromisoformat(last_connected_str) if isinstance(last_connected_str, str) else last_connected_str
        )

        return PairedRemoteDevice(
            id=row["id"],
            source_id=row["source_id"],
            device_name=row["device_name"],
            host_ip=row["host_ip"],
            port=row["port"],
            role=row["role"],
            protocol_version=row["protocol_version"],
            paired_at=paired_at,
            last_connected_at=last_connected_at,
            is_active=bool(row["is_active"]),
        )
