from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class DeviceTokenRecord:
    source_id: str
    token_hash: str
    device_name: str = ""
    paired_at: str = ""
    last_used_at: str = ""
    revoked_at: str = ""
    schema_version: int = 1

    def is_active(self) -> bool:
        return not self.revoked_at


class DeviceTokenStore:
    """Persist paired remote voice device tokens using a versioned JSON schema."""

    def __init__(self, config_dir: str | Path | None = None) -> None:
        base_dir = Path(config_dir) if config_dir is not None else Path.home() / ".finance-voice"
        self.config_dir = base_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.config_dir / "paired-device-tokens.json"

    def issue_token(self, source_id: str, device_name: str = "") -> str:
        token = secrets.token_urlsafe(32)
        record = DeviceTokenRecord(
            source_id=self._clean_source_id(source_id),
            token_hash=self._hash_token(token),
            device_name=device_name.strip(),
            paired_at=self._now_iso(),
            last_used_at="",
            revoked_at="",
        )
        records = self._load_records()
        records[record.source_id] = record
        self._save_records(records)
        return token

    def load_token(self, source_id: str) -> DeviceTokenRecord | None:
        record = self._load_records().get(self._clean_source_id(source_id))
        if record is None or not record.is_active():
            return None
        return record

    def verify_token(self, source_id: str, token: str) -> bool:
        record = self.load_token(source_id)
        if record is None:
            return False
        candidate_hash = self._hash_token(token)
        if not hmac.compare_digest(candidate_hash, record.token_hash):
            return False
        self._touch_last_used(record.source_id)
        return True

    def revoke_token(self, source_id: str) -> bool:
        records = self._load_records()
        record = records.get(self._clean_source_id(source_id))
        if record is None:
            return False
        if record.revoked_at:
            return True
        record.revoked_at = self._now_iso()
        records[record.source_id] = record
        self._save_records(records)
        return True

    def list_tokens(self, active_only: bool = True) -> list[DeviceTokenRecord]:
        records = list(self._load_records().values())
        if active_only:
            records = [record for record in records if record.is_active()]
        return sorted(records, key=lambda record: record.paired_at or "", reverse=True)

    def _touch_last_used(self, source_id: str) -> None:
        records = self._load_records()
        record = records.get(self._clean_source_id(source_id))
        if record is None:
            return
        record.last_used_at = self._now_iso()
        records[record.source_id] = record
        self._save_records(records)

    def _load_records(self) -> dict[str, DeviceTokenRecord]:
        path = self.path
        if not path.exists():
            return {}

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        records: dict[str, DeviceTokenRecord] = {}
        if isinstance(payload, dict) and payload.get("schema_version") == 1 and isinstance(payload.get("records"), list):
            for entry in payload.get("records", []):
                record = self._decode_record(entry)
                if record is not None:
                    records[record.source_id] = record
            return records

        if isinstance(payload, dict):
            for key, value in payload.items():
                source_id = self._clean_source_id(str(key))
                token = str(value).strip()
                if not source_id or len(token) < 16:
                    continue
                records[source_id] = DeviceTokenRecord(
                    source_id=source_id,
                    token_hash=self._hash_token(token),
                    device_name="",
                    paired_at=self._now_iso(),
                    last_used_at="",
                    revoked_at="",
                    schema_version=1,
                )
            if records:
                self._save_records(records)
            return records

        return {}

    def _save_records(self, records: dict[str, DeviceTokenRecord]) -> None:
        payload = {
            "schema_version": 1,
            "records": [self._encode_record(record) for record in records.values()],
        }
        data = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(self.config_dir)) as handle:
                handle.write(data)
                tmp_path = Path(handle.name)
            if tmp_path is not None:
                tmp_path.replace(self.path)
            self.path.chmod(0o600)
        except Exception:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _encode_record(self, record: DeviceTokenRecord) -> dict[str, str | int]:
        return {
            "source_id": record.source_id,
            "token_hash": record.token_hash,
            "device_name": record.device_name,
            "paired_at": record.paired_at,
            "last_used_at": record.last_used_at,
            "revoked_at": record.revoked_at,
            "schema_version": record.schema_version,
        }

    def _decode_record(self, payload: object) -> DeviceTokenRecord | None:
        if not isinstance(payload, dict):
            return None
        source_id = self._clean_source_id(str(payload.get("source_id", "")))
        token_hash = str(payload.get("token_hash", "")).strip()
        if not source_id or not token_hash:
            return None
        return DeviceTokenRecord(
            source_id=source_id,
            token_hash=token_hash,
            device_name=str(payload.get("device_name", "")).strip(),
            paired_at=str(payload.get("paired_at", "")).strip(),
            last_used_at=str(payload.get("last_used_at", "")).strip(),
            revoked_at=str(payload.get("revoked_at", "")).strip(),
            schema_version=int(payload.get("schema_version", 1)),
        )

    def _hash_token(self, token: str) -> str:
        cleaned = str(token).strip().encode("utf-8")
        return hashlib.sha256(cleaned).hexdigest()

    def _clean_source_id(self, source_id: str) -> str:
        return str(source_id).strip()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()