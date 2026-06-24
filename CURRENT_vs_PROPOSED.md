# Current vs. Proposed Architecture Comparison

**Purpose**: Visual comparison of existing voice system vs recommended LLM architecture

---

## System Comparison

### CURRENT STATE

```
LOCAL VOICE                              REMOTE VOICE
┌──────────────┐                        ┌──────────────┐
│ USB Mic      │                        │ Network      │
│ Audio input  │                        │ Audio stream │
└──────┬───────┘                        └──────┬───────┘
       │                                       │
       ├─────────────────────────────────────┬─┘
       │                                     │
       ▼                                     ▼
┌──────────────────────────────────────────────────┐
│ ASR (Vosk / Faster Whisper)                      │
│ "what's my budget"                               │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│ WakeWordCommandRouter                            │
│ Wake phrase extracted                            │
└──────────────────┬───────────────────────────────┘
                   │
                   ├─ Local:
                   │    │
                   │    ▼
                   │  ┌────────────────────┐
                   │  │ AssistantService   │
                   │  │ (Ollama)           │
                   │  └─────────┬──────────┘
                   │            │
                   │            ▼
                   │  ┌────────────────────┐
                   │  │ Response JSON      │
                   │  │ {"reply": "...",   │
                   │  │  "actions": [...]} │
                   │  └─────────┬──────────┘
                   │            │
                   │            ▼
                   │  ┌────────────────────┐
                   │  │ Display on UI      │
                   │  └────────────────────┘
                   │
                   ├─ Remote: ???
                        (Not clear where response goes)
                        │
                        ▼
                   ┌─────────────────────┐
                   │ Remote device gets  │
                   │ JSON response text? │
                   │ No TTS generation   │
                   │ No device isolation │
                   └─────────────────────┘

PROBLEMS:
✗ No session isolation between devices
✗ Same Ollama call for local & remote (doesn't consider difference)
✗ Response is JSON text, not audio for remote
✗ If Ollama slow, remote device hangs
✗ If multiple remotes send requests simultaneously, no priority
✗ No foundation for specialized agents
```

---

### PROPOSED STATE

```
LOCAL VOICE                                    REMOTE VOICE
┌──────────────┐                              ┌──────────────┐
│ USB Mic      │                              │ Network      │
│ Audio input  │                              │ Audio stream │
└──────┬───────┘                              └──────┬───────┘
       │                                             │
       └─────────────────────────┬───────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────────┐
                    │ ASR Pipeline                │
                    │ (Vosk / Faster Whisper)     │
                    │ → "what's my budget"        │
                    └────────────┬────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────────┐
                    │ WakeWordCommandRouter       │
                    │ (source_id extracted)       │
                    └────────────┬────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
           source_id: None          source_id: "kitchen"
                    │                         │
                    ▼                         ▼
    ┌──────────────────────────┐   ┌──────────────────────────┐
    │ LLMService               │   │ LLMService               │
    │ .process_voice_command() │   │ .process_voice_command() │
    │                          │   │                          │
    │ session_id: "local"      │   │ session_id: "remote:kitch"
    │ source_type: local_voice │   │ source_type: remote_voice│
    └────────┬────────┬────────┘   └────────┬────────┬────────┘
             │        │                     │        │
             │        ▼                     │        ▼
             │   ┌────────────────┐         │   ┌────────────────┐
             │   │ SessionManager │         │   │ SessionManager │
             │   │ Get/create     │         │   │ Get/create     │
             │   │ session        │         │   │ session        │
             │   └────────┬───────┘         │   └────────┬───────┘
             │            │                 │            │
             │            ▼                 │            ▼
             │   ┌──────────────────────┐   │   ┌──────────────────────┐
             │   │ VoiceSession         │   │   │ VoiceSession         │
             │   │ - history: [...]     │   │   │ - history: [...]     │
             │   │ - cached_snapshot    │   │   │ - cached_snapshot    │
             │   │ - timeout: ∞         │   │   │ - timeout: 300s      │
             │   └──────────────────────┘   │   └──────────────────────┘
             │            │                 │            │
             │            ▼                 │            ▼
             │   ┌──────────────────────┐   │   ┌──────────────────────┐
             │   │ Enqueue to Priority  │   │   │ Enqueue to Priority  │
             │   │ Queue                │   │   │ Queue                │
             │   │ Priority: 10         │   │   │ Priority: 6          │
             │   └──────────┬───────────┘   │   └──────────┬───────────┘
             │              │               │              │
             └──────────────┼───────────────┴──────────────┘
                            │
                            ▼
                ┌──────────────────────────────┐
                │ PriorityRequestQueue         │
                │                              │
                │ Dequeue: LOCAL first         │
                │ (Priority 10 > 6)            │
                └──────────────┬───────────────┘
                               │
                               ▼
                ┌──────────────────────────────┐
                │ AgentOrchestrator            │
                │ Route to appropriate agent   │
                │ (FinanceAgent for budgets)   │
                └──────────────┬───────────────┘
                               │
                               ▼
                ┌──────────────────────────────┐
                │ LLMErrorHandler              │
                │ with fallback cascade        │
                └──────────────┬───────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
      ┌─────────┐         ┌──────────┐        ┌──────────┐
      │ Ollama  │         │ Fallback │        │ Error    │
      │ (2.0s)  │         │ Cloud    │        │ Message  │
      └────┬────┘         │ (1.5s)   │        └──────────┘
           │              └────┬─────┘
           ▼                   ▼
         ┌──────────────────────────┐
         │ Response {"reply": "...",│
         │            "actions": []}│
         └────────┬─────────────────┘
                  │
                  ▼
        ┌──────────────────────────────┐
        │ ResponseFormatter            │
        │ - reply_text (for UI)        │
        │ - audio_script (for TTS)     │
        │ - actions                    │
        └────────┬────────────────┬────┘
                 │                │
        ┌────────▼──────┐  ┌──────▼────────┐
        │ Local UI Path │  │ Remote Path   │
        │               │  │               │
        │ Display:      │  │ TTS:          │
        │ - reply_text  │  │ - audio_script│
        │ - table       │  │ - play audio  │
        │ - execute     │  │ - execute     │
        │   actions     │  │   actions     │
        └───────────────┘  └───────────────┘

IMPROVEMENTS:
✓ Session isolation per device
✓ Source-aware prompts (local vs remote)
✓ Dual-output (display + audio)
✓ Error cascade with graceful fallback
✓ Request priority (local > remote)
✓ Foundation for agents (Finance, Calendar, etc)
```

---

## Feature Comparison Table

| Feature | Current | Proposed |
|---------|---------|----------|
| **Local Voice** | ✓ Working | ✓ Improved (via LLMService) |
| **Remote Voice** | ✓ Connected | ⚠ → ✓ Integrated (audio response) |
| **Session Isolation** | ✗ None | ✓ Per-device |
| **Conversation History** | ✓ Per user | ✓ Per device (isolated) |
| **Response Optimization** | ✗ Same for all | ✓ Modality-specific |
| **Audio Playback** | ✗ N/A | ✓ TTS auto-generated |
| **Request Queueing** | ✗ None | ✓ Priority-based |
| **Error Handling** | ⚠ Hangs if Ollama slow | ✓ 4-level fallback |
| **Agent Framework** | ✗ Monolithic | ✓ Extensible |
| **Multi-Device** | ⚠ Unclear | ✓ Well-defined |
| **Cloud LLM Support** | ✗ No | ✓ Yes (fallback) |
| **Performance Metrics** | ✗ None | ✓ Built-in telemetry |

---

## Code Flow Comparison

### CURRENT: Local Voice Only
```python
# RemoteStreamSource receives audio
on_audio_chunk(source_id, bytes)
  → AsrRouter.process(source_id, bytes)
    → ASR outputs text
      → WakeWordCommandRouter.process_text(text)
        → on_command callback
          → What happens? ???
            → Unclear path for remote
```

### PROPOSED: Unified Path
```python
# RemoteStreamSource receives audio
on_audio_chunk(source_id, bytes)
  → AsrRouter.process(source_id, bytes)
    → ASR outputs text
      → WakeWordCommandRouter.process_text(text)
        → on_command callback
          → VoiceCoordinator.execute_command(text, source_id)
            → llm_service.process_voice_command(
                  session_id="remote:kitchen",
                  text=text,
                  source_type="remote_voice",
                  device_id=source_id
              )
              → SessionManager.get_or_create_session()
                → LLMErrorHandler.process_with_fallback()
                  → LLMResponse (with audio_script)
                    → RemoteAudioServer.queue_response(audio_script)
                      → TTS encoding
                        → Audio playback on remote device ✓
```

---

## Session Lifecycle Comparison

### CURRENT
```
Local user types/speaks
  → AssistantService.handle_prompt()
    → Ollama chat
      → Response displayed
        → History kept in memory (no cleanup)

Remote device sends audio
  → What happens?
  → Response type unclear
  → No device isolation
```

### PROPOSED
```
┌─ LOCAL DEVICE
│  Session: "local"
│  Timeout: Never (long-lived)
│  History: Unlimited
│  Context: UI-aware
│
├─ REMOTE DEVICE 1 (Kitchen)
│  Session: "remote:kitchen"
│  Timeout: 5 min idle
│  History: Bounded (20 turns)
│  Context: Conversation-aware
│  Auto-cleanup: Yes
│
└─ REMOTE DEVICE 2 (Bedroom)
   Session: "remote:bedroom"
   Timeout: 5 min idle
   History: Bounded (20 turns)
   Context: Conversation-aware
   Auto-cleanup: Yes

Each session completely isolated:
- Kitchen conversation doesn't leak to Bedroom
- Each gets independent response
- Both can talk simultaneously
- Cleanup happens automatically
```

---

## Request Handling Comparison

### CURRENT
```
Request arrives
  → Sent to Ollama immediately
    → If Ollama slow: User waits 2-10s (hangs)
    → If Ollama crashes: No error handling
    → Multiple requests: No queueing (race condition)
```

### PROPOSED
```
Request arrives
  ├─ Enqueue with priority score:
  │  Local voice: 10
  │  Remote voice: 6
  │  Typed text: 8
  │
  ├─ Consumer dequeues highest priority
  │  Local users always prioritized
  │
  ├─ Process with error cascade:
  │  Try Ollama (2s)
  │    → Success: Return response
  │    → Timeout: Try Cloud (1.5s)
  │      → Success: Return response
  │      → Timeout: Rule-based response
  │        → Success: Return response
  │        → Timeout: Error message
  │
  └─ Always return something (never hang)
```

---

## Agent Architecture Comparison

### CURRENT
```
User: "Add milk to shopping and what's my budget?"

Flow:
  → AssistantService
    → Single LLM call
      → LLM tries to handle everything
        → Mixed response (finance + shopping)
          → Confusing output
```

### PROPOSED
```
User: "Add milk to shopping and what's my budget?"

Flow:
  → AgentOrchestrator.process_request()
    → Identify: Finance + Shopping domains
    → Route to: FinanceAgent (primary)
      → FinanceAgent recognizes shopping item
        → Delegates to: ShoppingAgent
      → Get response from ShoppingAgent
        → Synthesize combined response
          → "Added milk to list. Your budget is $3000."
             (coordinated, coherent)
```

---

## Performance Impact

### Latency

| Scenario | Current | Proposed | Change |
|----------|---------|----------|--------|
| Local voice (Ollama ok) | ~1.5s | ~1.7s | +0.2s (minimal) |
| Remote voice (Ollama ok) | ??? | ~2.0s | Clear path |
| Ollama timeout | 30s+ hang | <2s response | ⚡ Huge improvement |
| Multiple requests | Race condition | Fair queueing | ✓ Resolved |

### Memory

| Aspect | Current | Proposed | Note |
|--------|---------|----------|------|
| Session memory | Unbounded | 20 turns × N devices | Capped, cleanup |
| Queue depth | None | Max 100 requests | Prevents bloat |
| Snapshot cache | Per call | Per session (5m) | More efficient |

---

## Summary: What Changes

### For End Users
- ✓ Remote devices now get audio responses (TTS playback)
- ✓ Multiple devices can talk simultaneously (fair queueing)
- ✓ Slow LLM doesn't hang anyone (fallback responses)
- ✓ Conversations isolated per device
- ✓ Future: Specialized agents for different domains

### For Developers
- ✓ Single LLMService abstraction (easier to maintain)
- ✓ Clear error handling (don't guess when LLM fails)
- ✓ Session isolation (fewer bugs from device crosstalk)
- ✓ Agent framework (foundation for extensibility)
- ✓ Metrics & telemetry (understand performance)

### For Architecture
- ✓ Scalable to 100+ remote devices
- ✓ Extensible to new agents (Calendar, To-Do, etc)
- ✓ Supportive of future cloud LLM fallback
- ✓ Clear separation of concerns
- ✓ Testable in isolation

---

## Implementation Effort

| Phase | Effort | Existing Code | New Code |
|-------|--------|---------------|----------|
| Phase 1 | 1 week | 70% | 30% |
| Phase 2 | 1 week | 80% | 20% |
| Phase 3 | 1 week | 90% | 10% |
| Phase 4 | 2 weeks | 75% | 25% |
| Phase 5 | 1 week | 85% | 15% |
| Phase 6 | 1 week | 95% | 5% |

**Total**: 8 weeks of development

---

## Migration Path

### Week 1 (Phase 1)
```
Current: AssistantService called directly from voice coordinator
    ↓ (add LLMService wrapper)
New: VoiceCoordinator → LLMService → AssistantService (temporary)
```

### Week 3 (Phase 2)
```
LLMService → AssistantService stays, add queue in front
```

### Week 4 (Phase 3)
```
LLMService → ErrorHandler → (Ollama or Cloud or Fallback)
```

### Weeks 5-6 (Phase 4)
```
LLMService → AgentOrchestrator → Agents
(AssistantService gradually replaced by specialized agents)
```

---

## Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Phase 1 breaks local voice** | High | Comprehensive testing, fallback to old code |
| **Session cleanup bugs** | Medium | Metrics tracking, manual cleanup tool |
| **Queue starvation** | Low | Fairness algorithm, timeouts |
| **Ollama failures** | High | 4-level fallback cascade |
| **Agent delegation bugs** | Medium | Unit tests, delegation logs |

---

**Bottom Line**: Proposed architecture is fully backward-compatible in Phase 1, then gradually replaces old code with more capable system.
