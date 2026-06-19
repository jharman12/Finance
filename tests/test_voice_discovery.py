from __future__ import annotations

import unittest

from finance_app.services.voice.discovery import (
    SERVICE_TYPE,
    build_service_name,
    build_service_properties,
    normalize_label,
)


class VoiceDiscoveryTests(unittest.TestCase):
    def test_normalize_label(self) -> None:
        self.assertEqual(normalize_label("Kitchen Node!"), "kitchen-node")
        self.assertEqual(normalize_label("   "), "finance-voice")

    def test_build_service_name(self) -> None:
        service_name = build_service_name("Kitchen Node", "remote-01")
        self.assertTrue(service_name.endswith(SERVICE_TYPE))
        self.assertIn("kitchen-node", service_name)
        self.assertIn("remote-01", service_name)

    def test_build_service_properties(self) -> None:
        properties = build_service_properties(
            source_id="remote-01",
            device_name="Kitchen Node",
            role="remote-sender",
            protocol_version="1",
        )

        self.assertEqual(properties["source_id"], b"remote-01")
        self.assertEqual(properties["device_name"], b"Kitchen Node")
        self.assertEqual(properties["role"], b"remote-sender")
        self.assertEqual(properties["protocol_version"], b"1")


if __name__ == "__main__":
    unittest.main()
