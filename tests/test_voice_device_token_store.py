from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from finance_app.services.voice.device_token_store import DeviceTokenStore


class DeviceTokenStoreTests(TestCase):
    def test_issue_verify_and_revoke_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DeviceTokenStore(temp_dir)
            token = store.issue_token("remote-01", device_name="Kitchen Node")

            self.assertTrue(store.verify_token("remote-01", token))

            record = store.load_token("remote-01")
            self.assertIsNotNone(record)
            self.assertEqual(record.source_id, "remote-01")
            self.assertEqual(record.device_name, "Kitchen Node")
            self.assertTrue(record.token_hash)

            self.assertTrue(store.revoke_token("remote-01"))
            self.assertIsNone(store.load_token("remote-01"))

    def test_migrates_legacy_token_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            legacy_path = config_dir / "paired-device-tokens.json"
            legacy_path.write_text(json.dumps({"remote-legacy": "legacy-token-value"}), encoding="utf-8")

            store = DeviceTokenStore(config_dir)
            record = store.load_token("remote-legacy")

            self.assertIsNotNone(record)
            self.assertEqual(record.source_id, "remote-legacy")
            self.assertNotEqual(record.token_hash, "legacy-token-value")

            migrated_payload = json.loads(legacy_path.read_text(encoding="utf-8"))
            self.assertEqual(migrated_payload["schema_version"], 1)
            self.assertEqual(migrated_payload["records"][0]["source_id"], "remote-legacy")