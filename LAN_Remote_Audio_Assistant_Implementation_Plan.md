# LAN Remote Audio Assistant Implementation Plan

## Objective
Enable a separate device on the same local network to capture voice audio and stream it to the main PC, where the app performs ASR and sends text to the local LLM assistant.

This plan validates your proposed approach, improves it for security and reliability, and provides phased delivery with clear acceptance criteria.

## Architecture Decision

### Is your proposed process the best way?
Yes, with conditions.

- Your core direction is correct: keep ASR and LLM centralized on the main PC, and use remote devices as thin audio capture clients.
- This is better than distributing ASR/LLM across devices for your current app because it preserves model consistency, keeps data local to one trusted host, and reduces client complexity.
- However, it is not safe enough if implemented as unauthenticated/plain LAN audio streaming.

### Recommended target design
Use a hub-and-spoke architecture:

- Main PC (hub): secure receiver, ASR, assistant, action gating, telemetry.
- Remote device (spoke): capture mic audio, optional wake/VAD hinting, stream encrypted audio.
- Transport: authenticated encrypted bidirectional streaming with strong identity.

Recommended initial protocol choice:
- `gRPC bidirectional streaming over TLS 1.3 with mTLS` (preferred for typed contracts and policy controls),
- or `binary WebSocket over TLS` for faster initial delivery, provided equivalent security controls are enforced.

## Security-First Requirements (Mandatory)

### Threat model coverage
Defend against:
- unauthorized device joining on LAN,
- man-in-the-middle and replay,
- compromised IoT/guest devices on Wi-Fi,
- packet flooding/DoS,
- transcript/audio privacy leakage.

### Hard requirements before production use
1. Mutual authentication
- Per-device identity with mTLS client certificates.
- Pairing flow from main PC UI (one-time code or QR).

2. Encryption in transit
- TLS 1.3 only.
- Certificate pinning on sender where practical.

3. Replay and injection resistance
- Session nonce plus monotonic sequence numbers.
- Reject duplicate/out-of-window packets.

4. Authorization
- Per-device role limited to `stream_audio`.
- Deny unknown/unpaired devices by default.

5. DoS controls
- Max frame size/rate.
- Max concurrent streams.
- Bounded queues with backpressure and drop policy.

6. Privacy defaults
- No raw audio persistence by default.
- Transcript logging disabled by default (explicit opt-in).
- Retention limits and redaction controls.

If these controls are not ready, ship remote typed input first and defer remote raw audio.

## Recommended End-to-End Flow

1. Remote sender captures audio in fixed 20 ms frames.
2. Sender attaches metadata: `session_id`, `sender_id`, `room_id`, `seq_no`, `timestamp_ms`, `sample_rate`, `codec`.
3. Sender streams audio to main PC over authenticated encrypted channel.
4. Main PC receiver applies jitter buffer, reorder, and gap handling.
5. Main PC endpointing is authoritative for utterance start/end.
6. ASR produces partial and final transcripts.
7. Final transcript is passed to assistant with confidence metadata.
8. Safety tier policy decides execute vs confirm vs reject/clarify.
9. Actions execute with idempotency token and audit event.

## Audio and STT Technical Profile

### Defaults
- Audio format: `PCM16 mono`, 16 kHz.
- Frame size: 20 ms.
- Jitter buffer target: 80 ms baseline, adaptive upward under jitter.
- Endpointing:
  - speech start: 120-200 ms voiced,
  - speech end: 500-800 ms silence,
  - pre-roll buffer: 200-300 ms,
  - max utterance: 10-15 s.

### Wake and VAD strategy
- Sender-side wake/VAD can provide hints and reduce bandwidth.
- Main PC remains authoritative for endpointing and final commit.
- Optional two-stage wake verification on PC to reduce false activations.

### Partial vs final transcript behavior
- Partial transcript updates every 100-250 ms for UI only.
- Final transcript triggers assistant execution path.
- Optional speculative assistant pre-warm on stable partials; commit only on final.

## AI/Assistant Safety and Quality Controls

### Confidence and clarification policy
- Auto-execute: confidence >= 0.80 and low no-speech probability.
- Confirm-required: 0.60 <= confidence < 0.80 or ambiguous entities.
- Clarify/retry: confidence < 0.60 or high no-speech probability.

### Command safety tiers
- Tier 0 (read-only): execute immediately.
- Tier 1 (reversible edits): auto-execute only at high confidence.
- Tier 2 (bulk/destructive): always require confirmation with preview.
- Tier 3 (sensitive/system): explicit confirmation phrase and optional PIN.

### Multi-room/session isolation
- Session key: `room_id + sender_id + active_surface`.
- Keep per-session memory and pending confirmations.
- Enforce TTL expiry and summarization to avoid cross-room leakage.

## Integration Plan for Current Codebase

### New modules to add
- `finance_app/services/voice/network_transport.py`
  - Secure server, pairing, stream session lifecycle.
- `finance_app/services/voice/remote_stream_source.py`
  - Receiver-side stream source adapter for remote audio.
- `finance_app/services/voice/command_event.py`
  - Structured event model with text + confidence + session metadata.
- `finance_app/services/voice/action_safety.py`
  - Tier classification and confirmation gate.

### Existing modules to update
- `finance_app/services/voice_pipeline.py`
  - Accept both local mic and remote stream source.
- `finance_app/services/voice/stream_source.py`
  - Abstract source contract to support remote stream.
- `finance_app/services/assistant_service.py`
  - Move from global conversation state to session-scoped state.
  - Add safety gate before action application.
- `finance_app/ui/main_window.py`
  - Show sender/room, confidence, confirm/clarify prompts.
- `finance_app/services/voice/telemetry.py`
  - Add transport and safety funnel metrics.

## Phased Delivery Plan

## Phase 0: Design and security baseline
Deliverables:
- protocol schema,
- pairing UX,
- certificate/key strategy,
- threat model and abuse cases.

Acceptance criteria:
- architecture review approved,
- security controls list signed off,
- feature flag defaults set to off.

## Phase 1: Remote ingest foundation (no action execution)
Deliverables:
- secure stream receiver,
- sender heartbeat/timeout,
- jitter buffer and packet sequencing,
- transcript display only path.

Acceptance criteria:
- 3 simultaneous senders for 30 minutes,
- no crashes,
- no cross-session transcript mixing.

## Phase 2: Structured voice event model
Deliverables:
- replace plain text callbacks with `CommandEvent` carrying confidence/provider/session metadata.

Acceptance criteria:
- 100% assistant-bound commands include metadata,
- local mic mode remains compatible.

## Phase 3: Safety policy and confirmation flow
Deliverables:
- confidence threshold engine,
- tiered action gating,
- pending-confirmation state machine.

Acceptance criteria:
- low-confidence commands never mutate without confirmation,
- destructive actions always require explicit confirm.

## Phase 4: Session isolation and reliability hardening
Deliverables:
- per-room/sender assistant context,
- idempotent action IDs,
- reconnect and degradation states,
- dead-letter path for failed mutations.

Acceptance criteria:
- cross-room contamination tests pass,
- duplicate action prevention verified,
- controlled recovery from disconnects.

## Phase 5: Production hardening and security validation
Deliverables:
- replay/MITM/flood tests,
- operational revocation/rotate controls,
- retention and privacy controls in UI.

Acceptance criteria:
- security test suite passes,
- alerting and audit trail complete,
- rollout checklist approved.

## Telemetry and SLOs

Track per `session_id` and `action_id`:
- transport: loss, reorder, jitter, reconnect count,
- ASR: provider, confidence, no-speech, latency, fallback usage,
- assistant: response latency, parse success, action count,
- safety: tier, confirmation required/outcome,
- execution: success/failure, rows affected, rollback usage.

Initial SLO targets:
- p95 voice-to-final-transcript latency: <= 1.5 s on LAN,
- false execution rate: < 1%,
- reconnect recovery time: <= 5 s in common Wi-Fi interruption cases.

## Testing Strategy

### Unit tests
- transport packet ordering and replay rejection,
- confidence threshold classification,
- safety tier enforcement,
- session context isolation.

### Integration tests
- remote sender disconnect/reconnect,
- jitter and packet-drop simulation,
- ASR fallback behavior,
- confirm/clarify execution flows.

### Security tests
- unauthorized sender denied,
- MITM/cert substitution blocked,
- replay attempt blocked,
- flooding triggers rate limits.

## Rollout and Operations

Rollout sequence:
1. internal feature flag test,
2. one-device pilot,
3. limited multi-room beta,
4. production enablement.

Operational controls:
- one-click disable remote audio,
- one-click revoke/unpair device,
- rotate trust material and re-pair flow,
- incident playbook for suspected compromise.

## Final Recommendation
Proceed with your proposed architecture (remote device streams audio, main PC performs ASR then LLM), but only with mandatory pairing + mTLS + replay protection + strict action safety gating.

This is the best overall balance of privacy, security, quality, and maintainability for your current application design.