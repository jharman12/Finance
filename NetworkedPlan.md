Phase 1: Fix the immediate code mismatch bug

Make the running receiver server the single source of truth for pairing token.
In pairing UI flow, pull token from active remote stream server auth token, not from a fresh config-manager read.
If receiver is not active or token unavailable, block pairing with a clear error.
Add one diagnostic event containing token fingerprint (first 6 chars of SHA-256) on both sides, never the full token.
Expected result: both devices display identical pairing code and pairing succeeds.

Phase 2: Make pairing protocol robust

Add pairing_session_id generated when user clicks Pair Selected Device.
Include pairing_session_id in pairing state and in hello payload.
Compute code as HMAC(token, source_id + pairing_session_id), truncated to 6-8 chars for display.
Expire session after 30-60 seconds.
Reject stale or missing session_id immediately and log reason.
Expected result: no accidental cross-session pairing and less race-prone behavior.

Phase 3: Implement AirPlay-style lasting TLS connection

Move from per-utterance connect/close to persistent TLS socket per paired device.
Keep connection alive with heartbeat ping/pong.
Add reconnect with exponential backoff + jitter.
Keep audio streaming as framed messages on same channel.
Add session resumption metadata (source_id, connection_id, last_seq_no).
Expected result: lower latency, fewer reconnect failures, more seamless “always available” remote mic behavior.

Phase 4: Harden LAN security

Stop advertising auth_token in mDNS.
Keep mDNS to discovery metadata only: source_id, role, protocol_version, endpoint.
Prefer per-device keys after pairing; medium-term move to mTLS (device cert enrollment during pairing).
Keep TLS 1.2+ now; prefer TLS 1.3 where available.
Expected result: significantly reduced LAN attack surface.