# Graph Report - Finance  (2026-08-17)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1417 nodes · 2978 edges · 93 communities (62 shown, 31 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 194 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d6cc7bdb`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- VoiceCoordinator
- MainWindow
- DeviceTokenStore
- AnalyticsController
- AssistantResult
- .__init__
- PairedRemoteDevice
- FinanceRepository
- AssistantService
- .refresh_budget
- DevicePairingDialog
- budget_reallocator.py
- VoiceCommandEvent
- RemoteWakeStreamSender
- RemoteAudioServer
- storage.py
- ._connection
- TestPersistentRemoteConnection
- _ns
- voice_pipeline.py
- RemoteVoiceConfigManager
- BudgetController
- .refresh_all
- discovery.py
- TestRemoteVoicePairingManagerWithSessionId
- VoiceRemoteTransportTests
- AsrResult
- RemoteVoicePairingManager
- .generate
- assistant_service.py
- Transaction
- OllamaClient
- SessionResumption
- PairingState
- AssetsController
- remote_voice_sender.py
- ensure_remote_voice_receiver_rule
- PersistentRemoteConnection
- main_window.py
- RecurringRepository
- Asset
- date
- RecurringController
- VoicePipelineIntegrationTests
- network_transport.py
- test_phase2_pairing_protocol.py
- TransactionController
- assistant_sessions.py
- WakeWordCommandRouter
- VoiceActivityEndpoint
- ArchitectureBoundaryTests
- ReconnectConfig
- ._format_assistant_reply_html
- test_phase3_persistent_connection.py
- SettingsRepository
- VoiceTelemetryLogger
- VoskPhraseWakeDetector
- ._add_category_from_dialog
- test_phase0_baseline.py
- TestPhase2Protocol
- .__init__
- .__init__
- .list_asset_expense_links
- ControllerDelegationTests
- Phase0RecurringMaterializationTests
- ._heartbeat_loop
- TestPhase3Protocol
- SecureRemoteAudioConnection
- ._refresh_known_devices_table
- PairingDialog
- .__init__
- ._resolve_session_key
- .close
- ._get_remote_voice_enabled
- ._on_remote_voice_toggle
- _FakePairingState
- finance_app/__init__.py
- services/__init__.py
- ui/__init__.py
- Vosk Model English US 0.22 LGraph Words
- .test_calculate_backoff_delay_initial
- .test_calculate_backoff_delay_capped_at_max
- .test_calculate_backoff_includes_jitter
- .test_pairing_code_included_in_hello
- .test_callbacks_invoked
- RemoteVoiceDiscoveryBrowser

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 207 edges
2. `FinanceRepository` - 132 edges
3. `VoiceCoordinator` - 65 edges
4. `AssistantService` - 44 edges
5. `RemoteWakeStreamSender` - 38 edges
6. `RemoteAudioServer` - 38 edges
7. `DeviceTokenStore` - 32 edges
8. `PersistentRemoteConnection` - 28 edges
9. `DevicePairingDialog` - 27 edges
10. `VoiceCommandEvent` - 26 edges

## Surprising Connections (you probably didn't know these)
- `VoicePipelineIntegrationTests` --uses--> `VoiceCoordinator`  [INFERRED]
  tests/test_voice_pipeline_integration.py → finance_app/services/voice_pipeline.py
- `RemoteWakeStreamSender` --uses--> `OpenWakeWordDetector`  [INFERRED]
  remote_voice_sender.py → finance_app/services/voice/wake_detector.py
- `RemoteWakeStreamSender` --uses--> `VoskPhraseWakeDetector`  [INFERRED]
  remote_voice_sender.py → finance_app/services/voice/wake_detector.py
- `VoiceAssistantConfirmationTests` --uses--> `MainWindow`  [INFERRED]
  tests/test_voice_assistant_confirmation.py → finance_app/ui/main_window.py
- `VoiceAssistantTelemetryTests` --uses--> `MainWindow`  [INFERRED]
  tests/test_voice_assistant_telemetry.py → finance_app/ui/main_window.py

## Import Cycles
- None detected.

## Communities (93 total, 31 thin omitted)

### Community 0 - "VoiceCoordinator"
Cohesion: 0.09
Nodes (10): Any, Coordinates voice input nodes and wake-word routing. Future nodes can be added…, Enable or disable remote audio receiver availability., Ensure the remote receiver server is running so pairing callbacks can arrive., VoiceCoordinator, patch, VoiceAsrConfigTests, VoiceCooldownTests (+2 more)

### Community 1 - "MainWindow"
Cohesion: 0.06
Nodes (8): MainWindow, Save all edits to budget entries., Enable or disable all asset detail inputs and toggle edit/save/cancel button…, Handle device pairing cancelled., Handle model selection change., Export current month budget rows to a CSV file., QMainWindow, WakePhraseSettingTests

### Community 2 - "DeviceTokenStore"
Cohesion: 0.11
Nodes (23): DeviceTokenRecord, DeviceTokenStore, Path, Persist paired remote voice device tokens using a versioned JSON schema., Revoke a paired remote device token so it can no longer auto-authenticate., cmd_export(), cmd_import(), cmd_list_devices() (+15 more)

### Community 3 - "AnalyticsController"
Cohesion: 0.11
Nodes (15): CashflowChartsPayload, ChartCategoryPoint, ChartDailyPoint, ChartMonthlyPoint, DebtCompositionPoint, PositionChartsPayload, PositionMonthlyPoint, AnalyticsRepository (+7 more)

### Community 4 - "AssistantResult"
Cohesion: 0.09
Nodes (11): AssistantResult, AssistantLLMService, Week 2 abstraction layer over AssistantService for unified local/remote…, LLMRequest, LLMService, Protocol, AssistantWorker, OllamaWarmupWorker (+3 more)

### Community 5 - ".__init__"
Cohesion: 0.14
Nodes (13): Display saved AI reallocation plans with filters, export, and rich detail view., Build the Remote Voice enable/disable settings panel., Open edit dialog for selected recurring item., Fetch available models from Ollama and populate the dropdown., MetricCard, QComboBox, QDate, QFrame (+5 more)

### Community 6 - "PairedRemoteDevice"
Cohesion: 0.07
Nodes (15): PairedRemoteDeviceRepository, Connection, Manage paired remote voice devices in persistent storage., Update the last connected timestamp for a device., Soft delete (deactivate) a paired device., Get all paired devices, active or not., Get only active paired devices., Get a paired device by its source ID. (+7 more)

### Community 7 - "FinanceRepository"
Cohesion: 0.06
Nodes (7): FinanceRepository, Return the monthly budgeted amount map keyed by category., List paired remote voice devices., Get a paired remote device by source ID., Save or update a paired remote device., Update the last connected timestamp for a device., Soft delete (deactivate) a paired remote device.

### Community 8 - "AssistantService"
Cohesion: 0.12
Nodes (13): AssistantContext, AssistantService, Any, date, Check if this is an analysis/advice question (not a mutation)., Detect if a response appears to be cut off or incomplete., Retry to complete an incomplete response., Generate a complete budget analysis directly from local data. (+5 more)

### Community 9 - ".refresh_budget"
Cohesion: 0.06
Nodes (14): Import budget rows into the currently selected month from a CSV file., Persist inline budget amount edits and refresh dependent insights., Populate the category dropdown with unbudgeted expense categories., Add a new budget entry., Delete selected budget entry., Generate and optionally apply AI reallocation for next month., Show review table and return selected category amounts to apply., Apply selected recommendation rows to target month budgets. (+6 more)

### Community 10 - "DevicePairingDialog"
Cohesion: 0.08
Nodes (16): DevicePairingDialog, Any, QDialog, Handle a newly discovered remote device., Handle diagnostic messages from discovery., Handle pair button clicked., Show pairing code and wait for confirmation., Get the current pairing session ID (Phase 2). (+8 more)

### Community 11 - "budget_reallocator.py"
Cohesion: 0.14
Nodes (24): apply_safety_rules(), build_explainability_output(), _build_explanation_sentence(), _clamp(), compute_confidence(), forecast_category_amounts(), generate_goal_message(), generate_reallocation_plan() (+16 more)

### Community 12 - "VoiceCommandEvent"
Cohesion: 0.15
Nodes (11): evaluate_voice_command_event(), is_confirmation_phrase(), _is_mutation_request(), is_rejection_phrase(), _normalize_text(), Classify how a spoken command should be handled before assistant execution., VoiceExecutionDecision, VoiceCommandEvent (+3 more)

### Community 14 - "RemoteWakeStreamSender"
Cohesion: 0.18
Nodes (6): Exception, RemoteVoiceDiscoveryDevice, _debug(), _log(), Reset detector session state between streams to prevent stale matches., RemoteWakeStreamSender

### Community 15 - "RemoteAudioServer"
Cohesion: 0.10
Nodes (8): Update session last activity time and seq_no (Phase 3)., Remove sessions that haven't had activity (Phase 3)., Revoke a paired per-device token so future auth is rejected., Check whether a non-revoked per-device token exists., Build discovery metadata (Phase 4): endpoint-only, no secrets., Authenticated LAN audio ingest server with persistent connections (Phase 3).…, RemoteAudioServer, _ThreadingTcpServer

### Community 16 - "storage.py"
Cohesion: 0.20
Nodes (6): datetime, BudgetRepository, Budget, Category, RecurringItem, BudgetMonthView

### Community 17 - "._connection"
Cohesion: 0.10
Nodes (6): Connection, Delete a category. Returns True if successful. Note: Safe to call even if the…, Change category on existing transactions. Args: from_category: Current category…, Change category on existing recurring items. Args: from_category: Current…, Persist a generated reallocation plan/audit payload., List recent reallocation audits.

### Community 18 - "TestPersistentRemoteConnection"
Cohesion: 0.09
Nodes (12): Test connection object initialization., Test exponential backoff growth., Test that connection_id is generated and stored., Test session resumption carries last_seq_no., Test default heartbeat interval., Test custom heartbeat interval., Test that audio messages include connection_id (Phase 3)., Handshake should send hello directly and then mark connected on ack. (+4 more)

### Community 19 - "_ns"
Cohesion: 0.16
Nodes (14): _make_token(), _ns(), Namespace, patch, list-devices shows one active and one revoked device with correct token status., unpair calls delete() on the repo and revoke_token() on the token store., unpair exits with code 1 when the device is not in the DB., rotate-token revokes the current token, issues a new one, and prints it. (+6 more)

### Community 20 - "voice_pipeline.py"
Cohesion: 0.20
Nodes (7): Enum, normalize_command_text(), Normalize transcript text before assistant dispatch., VoiceSessionState, MicStreamSource, Captures chunks of PCM16 audio from default input device., str

### Community 21 - "RemoteVoiceConfigManager"
Cohesion: 0.12
Nodes (12): Path, Generate a random 32-byte auth token., TLS certificate, key, and shared token for remote audio connection., Auto-generates and persists TLS certificates and auth tokens., Get or auto-generate credentials., Get or generate auth token., Persist a provided auth token (for enrolled per-device credentials)., Generate self-signed TLS certificate using OpenSSL or Python. (+4 more)

### Community 22 - "BudgetController"
Cohesion: 0.10
Nodes (3): BudgetController, Any, BudgetControllerCsvTests

### Community 23 - ".refresh_all"
Cohesion: 0.14
Nodes (5): Delete selected recurring item., Jump to ledger with month/category context when users inspect actual spend., Set ledger category filter and refresh the table., Clear ledger filters and show all rows for the selected month., Refresh filter options while preserving current selection where possible.

### Community 24 - "discovery.py"
Cohesion: 0.17
Nodes (8): build_service_name(), build_service_properties(), decode_service_properties(), normalize_label(), Any, RemoteVoiceDiscoveryPublisher, resolve_local_ipv4(), VoiceDiscoveryTests

### Community 25 - "TestRemoteVoicePairingManagerWithSessionId"
Cohesion: 0.11
Nodes (10): Test pairing manager with session ID validation (Phase 2)., Test starting pairing with session_id., Test that verification rejects expired sessions., Test that verification rejects mismatched session_id., Test that verification accepts matching session_id., Test that verification works without session_id (backward compatibility)., Test that callback is fired on successful verification with session_id., Token-authenticated existing device should confirm active pairing UI session. (+2 more)

### Community 27 - "AsrResult"
Cohesion: 0.22
Nodes (7): AsrProvider, AsrResult, Protocol, Provider contract for one-shot utterance transcription., AsrRouter, AsrRouterTests, _FakeProvider

### Community 28 - "RemoteVoicePairingManager"
Cohesion: 0.12
Nodes (9): Confirm pairing for an already enrolled device token during an active pairing…, Get current pairing state., Manages pairing state for incoming remote voice connections., Set callback functions., Start waiting for a pairing connection. Args: source_id: ID of the remote…, Cancel the active pairing session., Check if currently waiting for a pairing connection., Verify incoming pairing code and session ID. Returns True if pairing is… (+1 more)

### Community 29 - ".generate"
Cohesion: 0.15
Nodes (10): Generate a deterministic pairing code from token and source ID. Phase 2: Code…, Verify that a pairing code matches expected value. Phase 2: Code is…, Confirm pairing (called when connection from sender received)., Test deterministic pairing code generation with session-based validation (Phase…, Test that code is deterministic and NOT affected by session_id. Phase 2: Remote…, Test that code is deterministic so remote device can independently compute it., Test that pairing codes expire after 60 seconds., Test that code verification works without session_id knowledge. (+2 more)

### Community 30 - "assistant_service.py"
Cohesion: 0.18
Nodes (6): AssistantSessionIsolationTests, _FakeCategory, _FakeClient, _FakeRecurring, _FakeRepository, _FakeSnapshot

### Community 31 - "Transaction"
Cohesion: 0.15
Nodes (5): ConnectionFactory, date, EnsureCategoryProvider, TransactionsRepository, Transaction

### Community 32 - "OllamaClient"
Cohesion: 0.24
Nodes (4): OllamaClient, OllamaMessage, Any, Change the active model.

### Community 33 - "SessionResumption"
Cohesion: 0.15
Nodes (10): Create and register a new session (Phase 3)., Retrieve session by connection_id (Phase 3)., Metadata for persistent connection session resumption (Phase 3). Allows client…, Check if session hasn't had activity for too long., SessionResumption, Test session resumption data structure (Phase 3)., Test creating a session resumption record., Test that recent session is not marked as stale. (+2 more)

### Community 34 - "PairingState"
Cohesion: 0.16
Nodes (10): PairingState, State of an active pairing session., Check if pairing session has expired., Get age of pairing session in seconds., Test that session expires after configured timeout., Test that session is valid before timeout., Test session age calculation., Test pairing state management with session IDs and expiration (Phase 2). (+2 more)

### Community 36 - "remote_voice_sender.py"
Cohesion: 0.31
Nodes (8): ArgumentParser, _bool_env(), build_config(), build_parser(), _debug_enabled(), _env(), main(), Namespace

### Community 37 - "ensure_remote_voice_receiver_rule"
Cohesion: 0.23
Nodes (6): ensure_remote_voice_receiver_rule(), FirewallAutomationResult, Windows-only netsh helper for inbound remote voice receiver rules., Ensure an inbound TCP rule exists for the remote voice receiver port., WindowsFirewallAutomation, WindowsFirewallAutomationTests

### Community 38 - "PersistentRemoteConnection"
Cohesion: 0.22
Nodes (7): PersistentRemoteConnection, Establish initial TLS connection and send hello., Maintains a persistent TLS connection with heartbeat and auto-reconnect (Phase…, Monitor connection and reconnect with exponential backoff., Calculate exponential backoff delay with jitter., Persist peer certificate for subsequent verified TLS connections., Start the persistent connection and heartbeat.

### Community 40 - "RecurringRepository"
Cohesion: 0.21
Nodes (5): ConnectionFactory, date, EnsureCategoryProvider, MonthBoundsProvider, RecurringRepository

### Community 41 - "Asset"
Cohesion: 0.22
Nodes (4): Asset, date, Reverse-linked payment events to estimate principal at tracking start., Estimate monthly payment using linked events; fallback to amortized term…

### Community 44 - "VoicePipelineIntegrationTests"
Cohesion: 0.13
Nodes (5): EndpointDecision, _FakeAsrRouter, _FakeEndpoint, _FakeWakeDetector, VoicePipelineIntegrationTests

### Community 45 - "network_transport.py"
Cohesion: 0.19
Nodes (3): RemoteAudioPacket, Bridges authenticated network audio packets into the voice coordinator., RemoteStreamSource

### Community 46 - "test_phase2_pairing_protocol.py"
Cohesion: 0.22
Nodes (7): Manage pairing state for remote voice connections., PairingCode, PairingCodeGenerator, Short code for user verification during pairing., Generate and verify human-readable pairing codes., Device pairing dialog for remote voice senders., Tests for Phase 2: Robust pairing protocol with session-based validation.

### Community 48 - "assistant_sessions.py"
Cohesion: 0.32
Nodes (5): normalize_source_id(), typed_assistant_session_key(), voice_assistant_session_key(), voice_confirmation_session_key(), AssistantSessionKeyTests

### Community 49 - "WakeWordCommandRouter"
Cohesion: 0.27
Nodes (4): Future expansion point for remote Alexa-like devices., Turns streaming transcripts into wake + command events. This router is input-…, VoiceTextEvent, WakeWordCommandRouter

### Community 50 - "VoiceActivityEndpoint"
Cohesion: 0.29
Nodes (5): Simple energy-based endpointing for command utterances., VoiceActivityEndpoint, _silence_chunk(), _speech_chunk(), VoiceActivityEndpointTests

### Community 52 - "ReconnectConfig"
Cohesion: 0.22
Nodes (7): Persistent TLS connection manager with heartbeat and exponential backoff (Phase…, Configuration for exponential backoff reconnection., ReconnectConfig, Test exponential backoff configuration (Phase 3)., Test default reconnect configuration., Test custom reconnect configuration., TestReconnectConfig

### Community 54 - "test_phase3_persistent_connection.py"
Cohesion: 0.27
Nodes (6): SenderConfig, Tests for Phase 3: Persistent TLS connections with heartbeat and session…, Test that the sender wires streams through the persistent transport., Test that pairing confirmation does not eagerly start persistent TLS., Wake-triggered connection failures should not crash sender loop., TestRemoteWakeStreamSenderPersistentWiring

### Community 56 - "VoiceTelemetryLogger"
Cohesion: 0.27
Nodes (5): Any, Path, Appends structured voice events for tuning and debugging., VoiceTelemetryLogger, VoiceTelemetryTests

### Community 57 - "VoskPhraseWakeDetector"
Cohesion: 0.13
Nodes (6): OpenWakeWordDetector, Optional wake detector using openWakeWord model. This detector is best-effort…, Reset recognizer state without reloading the model., Wake detector using Vosk partial/final text and phrase matching., VoskPhraseWakeDetector, WakeDetectorSanityTests

### Community 58 - "._add_category_from_dialog"
Cohesion: 0.29
Nodes (4): Open the category management dialog., Add a category from the category manager dialog., Delete a category from the category manager dialog., QListWidget

### Community 60 - "TestPhase2Protocol"
Cohesion: 0.20
Nodes (6): Integration tests for Phase 2 pairing protocol with session-based validation., Test complete Phase 2 pairing flow with session IDs for validation only., Test that session_id ensures pairing happens in current window., Test that 60-second session timeout prevents replay attacks., Test that remote device can independently compute and display pairing code., TestPhase2Protocol

### Community 62 - ".__init__"
Cohesion: 0.22
Nodes (3): Path, Export all data to CSV files in the given directory. Returns a dict mapping…, Import data from CSV files in the given directory. Args: directory: Path…

### Community 66 - "._heartbeat_loop"
Cohesion: 0.25
Nodes (4): Send an audio frame on the persistent connection. Accepts either raw PCM bytes…, Send periodic heartbeats to keep connection alive., Send JSON message on socket., Receive one line from socket.

### Community 67 - "TestPhase3Protocol"
Cohesion: 0.25
Nodes (5): Integration tests for Phase 3 persistent connection protocol., Test conceptual difference between Phase 2 (per-utterance) and Phase 3…, Test that heartbeat keeps connection from timing out., Test that session resumption reduces reconnection latency., TestPhase3Protocol

### Community 70 - "PairingDialog"
Cohesion: 0.33
Nodes (3): PairingDialog, QDialog, Dialog for pairing a remote voice device.

### Community 71 - ".__init__"
Cohesion: 0.40
Nodes (4): AdvanceMonthsProvider, ConnectionFactory, EnsureCategoryProvider, MonthBoundsProvider

## Knowledge Gaps
- **3 isolated node(s):** `_FakeRecurring`, `Vosk Model English US 0.22 LGraph Words`, `Finance App Seeds README`
  These have ≤1 connection - possible missing edges or undocumented components.
- **31 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `MainWindow` to `VoiceCoordinator`, `AnalyticsController`, `AssistantResult`, `.__init__`, `PairedRemoteDevice`, `FinanceRepository`, `AssistantService`, `.refresh_budget`, `DevicePairingDialog`, `VoiceCommandEvent`, `._handle_voice_command`, `BudgetController`, `.refresh_all`, `Transaction`, `AssetsController`, `main_window.py`, `Asset`, `RecurringController`, `TransactionController`, `._format_assistant_reply_html`, `._add_category_from_dialog`, `._refresh_known_devices_table`, `._get_remote_voice_enabled`, `._on_remote_voice_toggle`?**
  _High betweenness centrality (0.386) - this node is a cross-community bridge._
- **Why does `VoiceCoordinator` connect `VoiceCoordinator` to `MainWindow`, `DeviceTokenStore`, `.__init__`, `main_window.py`, `VoiceCommandEvent`, `network_transport.py`, `._handle_voice_command`, `VoicePipelineIntegrationTests`, `WakeWordCommandRouter`, `VoiceActivityEndpoint`, `voice_pipeline.py`, `RemoteVoiceConfigManager`, `VoiceTelemetryLogger`, `VoskPhraseWakeDetector`, `AsrResult`, `RemoteVoicePairingManager`, `.__init__`?**
  _High betweenness centrality (0.273) - this node is a cross-community bridge._
- **Why does `FinanceRepository` connect `FinanceRepository` to `MainWindow`, `DeviceTokenStore`, `AnalyticsController`, `.__init__`, `PairedRemoteDevice`, `AssistantService`, `storage.py`, `._connection`, `BudgetController`, `assistant_service.py`, `Transaction`, `AssetsController`, `main_window.py`, `RecurringRepository`, `Asset`, `date`, `RecurringController`, `TransactionController`, `assistant_sessions.py`, `SettingsRepository`, `test_phase0_baseline.py`, `.__init__`, `.list_asset_expense_links`, `Phase0RecurringMaterializationTests`?**
  _High betweenness centrality (0.245) - this node is a cross-community bridge._
- **Are the 27 inferred relationships involving `MainWindow` (e.g. with `CashflowChartsPayload` and `PositionChartsPayload`) actually correct?**
  _`MainWindow` has 27 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `FinanceRepository` (e.g. with `AssistantService` and `AnalyticsRepository`) actually correct?**
  _`FinanceRepository` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `VoiceCoordinator` (e.g. with `FasterWhisperAsrProvider` and `AsrRouter`) actually correct?**
  _`VoiceCoordinator` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `AssistantService` (e.g. with `AssistantLLMService` and `AssistantResult`) actually correct?**
  _`AssistantService` has 8 INFERRED edges - model-reasoned connections that need verification._