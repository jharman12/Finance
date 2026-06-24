# LAN Remote Audio Security Hardening Checklist

**Status:** Pre-launch security validation  
**Scope:** Single-LAN deployment, home use  
**References:** NETWORK_ARCHITECTURE_GUIDE.md, Phase 4-5 planning

---

## I. Threat Model

### In-Scope Threats (LAN)
- **Unauthorized pairing:** Neighbor on Wi-Fi attempts to pair device
- **MITM on audio stream:** Attacker intercepts microphone traffic (to spoof commands)
- **Replay attacks:** Attacker replays previous "transfer $1000" command
- **Session hijacking:** Attacker steals session ID, sends audio as legitimate device
- **DoS:** Attacker floods server with malformed packets
- **Packet sniffing:** Guest device sniffs audio transcripts on unencrypted traffic

### Out-of-Scope (Assume secure)
- **Rogue main PC:** Attacker replaces main PC with malicious device (requires physical access; not LAN-only)
- **WAN compromise:** Cloud service compromise (you're LAN-only by default)
- **WiFi WPA2 crack:** Attacker breaks Wi-Fi encryption (assume Wi-Fi is trustworthy)

---

## II. Security Controls Checklist

### A. Authentication & Pairing ✓ (Mostly Done)

- [ ] **✓ Mandatory pairing before audio**
  - [ ] Device cannot send audio without valid pairing token
  - [ ] Unpaired device receives error on first message
  - [ ] Test: Send hello without valid token → verify rejection + log

- [ ] **✓ One-time pairing code (6-8 digits)**
  - [ ] Code expires after 30-60 seconds
  - [ ] Code not reusable (HMAC session ID prevents replay)
  - [ ] Code displayed on main PC UI only (not logged)
  - [ ] Test: Enter expired code → verify rejection

- [ ] **TODO: Per-device token storage**
  - [ ] Token persisted to `~/.finance-voice/paired-device-tokens.json`
  - [ ] Tokens not readable by other users (file perms: 0600)
  - [ ] Tokens not printed in logs
  - [ ] Test: Unplug app, restart → verify device auto-connects

- [ ] **TODO: Token rotation capability**
  - [ ] CLI command: `device rotate-token`
  - [ ] Old token invalidated immediately after rotation
  - [ ] Devices must re-pair with new token
  - [ ] Audit log: who rotated, when, reason
  - [ ] Test: Rotate token, verify old device rejected

- [ ] **TODO: Device unpair (revocation)**
  - [ ] CLI command: `device unpair <source_id>`
  - [ ] Revoked device cannot re-connect (even with old session_id)
  - [ ] Unpair logs: source_id, reason, timestamp
  - [ ] Test: Unpair device, verify connection refused

- [ ] **TODO: Max pairing limit**
  - [ ] Limit: 16 devices (prevents brute-force pair flooding)
  - [ ] Error message if limit exceeded
  - [ ] Test: Try to pair 17th device → verify rejection

---

### B. Transport Layer ✓ (Implemented)

- [ ] **✓ TLS 1.3+ required**
  - [ ] No plaintext audio on LAN
  - [ ] TLS version: 1.3 preferred, 1.2 fallback
  - [ ] Test: `openssl s_client -connect <ip>:9876` → verify TLS version
  - [ ] Code: `context.minimum_version = ssl.TLSVersion.TLSv1_3`

- [ ] **✓ TLS certificate generation**
  - [ ] Self-signed cert generated on first run
  - [ ] Cert stored in `~/.finance-voice/server.crt` (readable by app only)
  - [ ] Key stored in `~/.finance-voice/server.key` (NEVER transmitted)
  - [ ] Cert validity: >= 1 year (or app's lifetime)
  - [ ] Test: Cert exists and loads without error

- [ ] **TODO: Certificate pinning (optional for Phase 4)**
  - [ ] Remote devices store main PC cert fingerprint
  - [ ] On reconnect, verify cert matches pinned fingerprint
  - [ ] Prevents MITM via certificate substitution
  - [ ] Test: Replace cert with different cert → verify rejection

- [ ] **✓ No plaintext token in TLS negotiation**
  - [ ] Token sent AFTER TLS handshake (inside encrypted channel)
  - [ ] Test: Tcpdump during pairing → verify no token in plaintext

- [ ] **✓ Packet framing (newline-delimited JSON)**
  - [ ] No length prefix attack (length-prefix injection)
  - [ ] JSON parsing validates structure before processing
  - [ ] Malformed JSON logged but doesn't crash server
  - [ ] Test: Send malformed JSON → verify graceful error

---

### C. Message Integrity ✓ (Mostly Done)

- [ ] **✓ Sequence numbers per stream**
  - [ ] Each device has independent `seq_no` counter (0-65535, wraps)
  - [ ] Duplicate packets rejected (`seq_no` already seen)
  - [ ] Out-of-order packets handled (jitter buffer reorders)
  - [ ] Gap detection: if seq_no jumps > 100, log warning (possible loss)
  - [ ] Test: Send seq_no 1,3,2,4 → verify reordered or gap logged

- [ ] **TODO: Idempotency token for actions**
  - [ ] Each action (budget update, etc.) gets unique `action_id`
  - [ ] Action stored in deduplication log (24h TTL)
  - [ ] Duplicate action_id → return cached result (don't re-execute)
  - [ ] Prevents duplicate execution if ACK lost
  - [ ] Test: Send same action twice → verify only executes once

- [ ] **✓ No HMAC in payload (already verified)**
  - [ ] Pairing code uses HMAC(token, source_id + session_id)
  - [ ] HMAC only used for pairing, not per-packet (TLS provides integrity)
  - [ ] Test: Verify pairing code format in logs

---

### D. Authorization & Access Control

- [ ] **✓ Per-device role enforcement**
  - [ ] Remote device role: "stream_audio_only"
  - [ ] Cannot execute arbitrary commands on main PC
  - [ ] Only allowed actions: send audio, receive transcript, get TTS response
  - [ ] Test: Send unauthorized action (e.g., "rm -rf /") → verify rejection

- [ ] **TODO: Session-scoped permissions**
  - [ ] Each session has (room_id, user_id, source_id)
  - [ ] Session cannot modify other sessions' data
  - [ ] E.g., kitchen device cannot access living-room budget
  - [ ] Test: Send command as kitchen_id, verify cannot modify living_room data

- [ ] **TODO: Rate limiting per device**
  - [ ] Max messages per second: 120 (10ms frames → 100 pps)
  - [ ] Burst capacity: 200 msgs in 2-second window
  - [ ] Exceeding limit: drop packets + log rate_limit_hit
  - [ ] Test: Send 1000 messages in 1 second → verify limiting

- [ ] **TODO: Command safety tiers**
  - [ ] Tier 0 (read-only): auto-execute (e.g., "what's my balance?")
  - [ ] Tier 1 (reversible): auto-execute high-confidence, confirm low-confidence (e.g., "add transaction")
  - [ ] Tier 2 (destructive): always require confirmation (e.g., "delete all transactions")
  - [ ] Tier 3 (sensitive): require confirmation phrase + PIN (e.g., "reset account")
  - [ ] Test: Verify tier classification in logs

---

### E. Denial-of-Service Protection

- [ ] **✓ Max frame size limit**
  - [ ] Max audio frame: 32 KB (way larger than 20ms @ 256kbps)
  - [ ] Frames larger than limit: drop + log
  - [ ] Code: `max_chunk_bytes = 32768`
  - [ ] Test: Send 1 MB frame → verify dropped

- [ ] **✓ Connection-level rate limiting**
  - [ ] Max 120 messages per second per device
  - [ ] Code: `max_messages_per_second = 120`
  - [ ] Test: Send 1000 pings/sec → verify throttled

- [ ] **✓ Max concurrent connections**
  - [ ] Limit: 4-8 devices (configurable)
  - [ ] Reject new connections when limit reached
  - [ ] Code: `MAX_CONCURRENT_CONNECTIONS = 4`
  - [ ] Test: Open 5 connections → verify 5th rejected

- [ ] **TODO: Backpressure + queue depth**
  - [ ] Audio queue per device: max 1000 frames (20 seconds)
  - [ ] If queue fills, drop oldest frames (not newest)
  - [ ] Log: "audio_queue_overflow" for telemetry
  - [ ] Test: Starve receiver, verify queue fills then drops

- [ ] **TODO: Connection timeout**
  - [ ] Idle connection (no packets for 5 min): close
  - [ ] Prevents zombie connections + resource exhaustion
  - [ ] Test: Open connection, wait 5+ min, verify closed

---

### F. Privacy & Data Minimization

- [ ] **✓ No auth token in mDNS**
  - [ ] mDNS properties: source_id, device_name, role, protocol_version
  - [ ] NOT advertised: token, credentials, IP address
  - [ ] Test: Query mDNS → verify no token in properties

- [ ] **TODO: No sensitive data in logs**
  - [ ] Logs omit: tokens, audio frames, transcripts, user commands
  - [ ] Logs include: anonymized source_id, timing, error codes
  - [ ] Test: Run with debug enabled, grep for token → verify absent

- [ ] **TODO: Audio not persisted by default**
  - [ ] Audio frames not written to disk (unless transcription enabled)
  - [ ] Transcripts stored only if user explicitly enables "Save history"
  - [ ] Default: no audio / transcript logging
  - [ ] Test: Verify no audio files in ~/.finance-voice/ after session

- [ ] **TODO: Encryption for persisted tokens**
  - [ ] Pairing tokens stored in `~/.finance-voice/paired-device-tokens.json`
  - [ ] File permission: 0600 (readable by owner only)
  - [ ] Consider: encryption at rest (optional; home app may be overkill)
  - [ ] Test: Check file perms are 0600

- [ ] **TODO: Retention limits for audit logs**
  - [ ] Pairing events: keep 30 days
  - [ ] Audio metadata (not audio): keep 7 days
  - [ ] Errors: keep 90 days
  - [ ] Auto-delete old records
  - [ ] Test: Verify auto-cleanup works

---

### G. Network Isolation & Firewall

- [ ] **✓ LAN binding (not WAN)**
  - [ ] Server binds to local IP (192.168.x.x), NOT 0.0.0.0:9876
  - [ ] Code: `host = resolve_local_ipv4()`
  - [ ] Test: `netstat -an | grep 9876` → verify local IP binding

- [ ] **TODO: Firewall allow-listing**
  - [ ] Windows: Add netsh rule (TCP inbound port 9876)
  - [ ] macOS: Add to System Preferences > Firewall
  - [ ] Linux: `ufw allow 9876/tcp`
  - [ ] Test: Connect from remote device → verify success with rule, failure without

- [ ] **TODO: No port forwarding docs**
  - [ ] User manual explicitly warns: "DO NOT port-forward to WAN"
  - [ ] Recommend: VPN (WireGuard, Tailscale) for remote access
  - [ ] Test: Read user docs, verify warning present

- [ ] **✓ mDNS multicast binding**
  - [ ] mDNS uses UDP 5353 multicast (224.0.0.251)
  - [ ] Not forwarded to WAN by default
  - [ ] Test: Verify multicast scope limited to local subnet

---

### H. Error Handling & Logging

- [ ] **TODO: No exception leakage**
  - [ ] Exception messages logged but not sent to client (prevents info disclosure)
  - [ ] Client receives generic error: "Internal server error"
  - [ ] Detailed error logged on server side only
  - [ ] Test: Send malformed command → verify generic error to client, detailed error in logs

- [ ] **TODO: Security event logging**
  - [ ] All pairing attempts logged: source_id, timestamp, success/failure, reason
  - [ ] All rejected connections: source_id, IP, reason (e.g., "rate_limit_exceeded")
  - [ ] All auth failures: token_hash (first 6 chars), source_id, timestamp
  - [ ] All data mutations: action_id, source_id, command, timestamp
  - [ ] Test: Grep logs for "SECURITY:" events

- [ ] **TODO: Alerting for anomalies**
  - [ ] Alert: 5+ failed pairing attempts in 1 minute
  - [ ] Alert: rate limiting triggered
  - [ ] Alert: revoked device attempted connection
  - [ ] Alert: certificate expiry warning (10 days before)
  - [ ] Test: Manually trigger alert condition, verify notification

---

### I. Cryptography & Key Management

- [ ] **✓ TLS 1.3 (no weak ciphers)**
  - [ ] Python ssl module enforces strong ciphers by default
  - [ ] No SSLv3, TLSv1.0, TLSv1.1 support
  - [ ] Test: `openssl s_client -connect <ip>:9876 -tls1` → should fail

- [ ] **✓ Self-signed certificate (acceptable for LAN)**
  - [ ] Certificate generated on first run
  - [ ] Stored in `~/.finance-voice/`
  - [ ] Regenerated if missing (normal recovery)
  - [ ] Test: Delete cert, restart app → verify regenerated

- [ ] **TODO: Random token generation**
  - [ ] Use `secrets.token_urlsafe(32)` (cryptographically strong)
  - [ ] NOT `random.choice(alphabet)` (weak)
  - [ ] Token entropy: >= 256 bits
  - [ ] Test: Generate 100 tokens, verify all unique (no collisions)

- [ ] **TODO: Secure random for HMAC nonce**
  - [ ] Session ID generated with `uuid.uuid4()` or `secrets.token_hex()`
  - [ ] Prevents predictable session IDs
  - [ ] Test: Inspect pairing_session_id format in logs

---

### J. Testing & Validation

- [ ] **Unit tests for security:**
  - [ ] Test: Invalid token rejected
  - [ ] Test: Expired pairing code rejected
  - [ ] Test: Duplicate seq_no rejected
  - [ ] Test: Rate limit enforced
  - [ ] Test: Oversized frame dropped
  - [ ] Test: Out-of-order packets handled

- [ ] **Integration tests for security:**
  - [ ] Test: Unauthorized device cannot execute actions
  - [ ] Test: Device 1 cannot access device 2's session
  - [ ] Test: Connection persists across network hiccups
  - [ ] Test: Malformed JSON doesn't crash server
  - [ ] Test: Certificate pinning (if implemented) blocks MITM

- [ ] **Security audit checklist:**
  - [ ] Code review: pairing logic (HMAC validation)
  - [ ] Code review: TLS setup (version, cipher suite)
  - [ ] Code review: token storage (file perms, no logging)
  - [ ] Manual test: Wireshark capture of pairing flow (verify encrypted)
  - [ ] Manual test: mDNS query (verify no token advertised)

---

## III. Phase-Gate Checklist (Pre-Launch)

### Phase 0: Design ✓
- [ ] Threat model documented
- [ ] Architecture reviewed (hub-and-spoke, TLS, mDNS)
- [ ] Security controls list (this document)

### Phase 1: Remote Ingest Foundation (Current)
- [ ] Secure stream receiver: TLS 1.3, mDNS discovery ✓
- [ ] Jitter buffer + seq_no deduplication ✓
- [ ] Transcript display only (no action execution)
- [ ] 3 simultaneous senders: 30 min test (in progress)

### Phase 2: Structured Voice Event Model
- [ ] CommandEvent with metadata (confidence, provider, session_id)
- [ ] Per-device CommandEvent (not global conversation state)
- [ ] Local mic + remote mic modes coexist
- [ ] **Security gates:** All pairing checks pass

### Phase 3: Persistent Connections + Session Resumption
- [ ] Heartbeat keep-alive (ping/pong)
- [ ] Reconnect with exponential backoff
- [ ] Session resumption by connection_id + last_seq_no
- [ ] **Security gates:** Device token persistence, unpair capability

### Phase 4: Safety Policy + Action Gating
- [ ] Confidence threshold enforcement
- [ ] Tiered action gating (read-only, reversible, destructive, sensitive)
- [ ] Confirmation UI + pending state machine
- [ ] **Security gates:** Idempotency token, rate limiting, auth failure logging

### Phase 5: Production Hardening
- [ ] Replay attack tests (seq_no + idempotency_id)
- [ ] MITM test (certificate substitution blocked)
- [ ] Flood DoS test (rate limit + connection limit)
- [ ] Security audit completed
- [ ] Privacy policy finalized
- [ ] Incident response playbook written
- [ ] **Security gates:** All above tests pass

---

## IV. Operational Security

### Pre-Launch Checklist

- [ ] **User documentation**
  - [ ] "Don't port-forward to WAN"
  - [ ] "Pairing code is one-time; don't screenshot"
  - [ ] "Tokens stored in ~/.finance-voice/; don't share"

- [ ] **Incident response**
  - [ ] Procedure: Revoke compromised device
  - [ ] Procedure: Rotate all tokens
  - [ ] Procedure: Check audit logs for suspicious activity
  - [ ] Procedure: Reset to factory defaults

- [ ] **Monitoring**
  - [ ] Alert on: 5+ failed pairing attempts in 1 min
  - [ ] Alert on: rate_limit_exceeded per device
  - [ ] Alert on: revoked device attempting connection
  - [ ] Alert on: certificate expiring in 10 days

---

## V. Score & Recommendation

| Category | Score | Comments |
|----------|-------|----------|
| Authentication | 8/10 | ✓ Pairing + token, TODO: persist + unpair CLI |
| Transport | 10/10 | ✓ TLS 1.3 + mDNS (fix service type name) |
| Authorization | 6/10 | ✓ Role per device, TODO: session isolation + rate limit |
| DoS Protection | 8/10 | ✓ Frame size + connection limit, TODO: idle timeout |
| Privacy | 7/10 | ✓ No token in mDNS, TODO: no audio logging by default |
| Testing | 5/10 | TODO: security test suite + integration tests |
| **Overall** | **7/10** | **Production-ready for Phase 3; defer Phase 5 to post-launch** |

---

## VI. Go / No-Go Decision

### Recommendation: **GO** (with conditions)

**Required for launch:**
1. ✓ Fix service type name: `_finance-voice` → `_fvoice` (1 line)
2. ✓ Implement token persistence (Part 2 of runbook)
3. ✓ Windows firewall automation (Part 4 of runbook)
4. ✓ Complete Phase 1 testing (3 devices, 30 min, no crashes)

**Nice-to-have (post-launch):**
- Replicate-to-production capability (Part 3 of runbook)
- Opus codec support (Part 6 of runbook)
- Cloud ASR failover (Part 7 of architecture guide)
- Security audit + penetration testing (Phase 5)

**Risk level:** LOW (no financial transactions yet; audio-input only)

---

## VII. Sign-Off

- [ ] Security lead: __________________ Date: __________
- [ ] Product lead: __________________ Date: __________
- [ ] Network engineer: __________________ Date: __________

