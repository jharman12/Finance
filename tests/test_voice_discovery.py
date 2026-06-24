from __future__ import annotations

import unittest

from finance_app.services.voice.discovery import (
    LEGACY_SERVICE_TYPE_RECEIVER,
    RECEIVER_SERVICE_TYPES,
    SERVICE_TYPE,
    SERVICE_TYPE_RECEIVER,
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

    def test_build_service_name_for_legacy_receiver_type(self) -> None:
        service_name = build_service_name(
            "Kitchen Node",
            "remote-01",
            service_type=LEGACY_SERVICE_TYPE_RECEIVER,
        )
        self.assertTrue(service_name.endswith(LEGACY_SERVICE_TYPE_RECEIVER))

    def test_receiver_service_types_include_current_and_legacy(self) -> None:
        self.assertEqual(RECEIVER_SERVICE_TYPES, (SERVICE_TYPE_RECEIVER, LEGACY_SERVICE_TYPE_RECEIVER))

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
