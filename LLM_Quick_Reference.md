# LLM Remote Voice Architecture - Quick Reference

**Date**: 2026-06-24 | **Status**: Complete Architecture + Implementation Guide  
**For**: Finance app extending to multi-device AI home assistant

---

## The Problem You're Solving

Your finance app has:
- ✓ Local voice input working (Vosk/Whisper ASR)
- ✓ Local LLM working (Ollama qwen2.5)
- ✓ Remote device network connection (TLS + auth)

**But**: Remote voice uses same LLM without:
- Session isolation per device
- Priority if multiple devices send requests
- Optimized responses for voice playback
- Graceful handling when LLM is slow
- Foundation for specialized agents (Finance, Calendar, To-Do)

---

## The Solution: 7 Recommendations

### 1. **LLM Integration Architecture**
**Single abstraction layer handles all sources**
- Local voice → LLMService
- Remote voice → LLMService  
- Typed text → LLMService

Benefits: Unified response handling, easier agent integration, consistent error handling

### 2. **Session Management**
**Each device gets isolated conversation context**
- Local: session_id = "local" (long-lived)
- Remote: session_id = "remote:device_id" (5-min timeout)
- Conversation history: Last 20 turns per session
- Financial context: Cached, refreshed every 5 min

Benefits: Multi-device support, conversation memory, session cleanup

### 3. **Response Prioritization**
**Priority queue ensures responsive experience**
- Priority scores: LOCAL_VOICE(10) > REMOTE_VOICE(6)
- Age bonus: Older requests get boost (+0.01/100ms)
- Deadline urgency: Near-timeout requests bumped
- Fairness: Device-aware queueing

Benefits: Main PC stays snappy, remote devices get fair access, no starvation

### 4. **Prompt Engineering by Modality**
**Different prompts for voice vs text vs agents**

| Source | Prompt Focus | Example |
|--------|--------------|---------|
| Remote Voice | **Very concise**, 1-2 sentences, natural speech | "You're 50% through budget" |
| Local Voice | Concise but can add context, references UI | "Your budget is $3,000. You've spent $1,500..." |
| Typed Input | Professional, detailed, structured | Full analysis with bullets/tables |
| Finance Agent | Domain expertise, budget data, recommendations | Deterministic + LLM explanation |

Benefits: Optimized for each use case, better UX

### 5. **Dual-Output Response**
**Same response, different renderings**
```
LLM Output:
{
  "reply_text": "Your spending is $2,456 with categories shown below.",
  "actions": [{"type": "show_table"}]
}

Generated Automatically:
→ reply_text: Display on UI (formatted, can have markdown)
→ audio_script: Speak aloud (simplified: "Your spending is twenty-four fifty-six")
→ actions: Execute ledger changes
```

Benefits: Reuse same logic, automatic TTS adaptation, consistency

### 6. **Error Handling & Fallback**
**Cascade through increasingly degraded responses**
```
Try Ollama (2s timeout)
  ↓ fail
Try Cloud LLM (1.5s timeout, if configured)
  ↓ fail
Deterministic rule-based response ("You're X% through budget")
  ↓ fail
Generic error message ("Try again in a moment")
```

Benefits: Always respond (never hang), graceful degradation, user satisfaction

### 7. **Multi-Agent Foundation**
**Extensible agents for Finance, Calendar, To-Do, etc.**
```
User: "Add milk to shopping list and remind me to pay rent"
  ↓
AgentOrchestrator routes to Finance Agent
  ↓
Finance Agent recognizes "pay rent" needs CalendarAgent
  ↓
Delegates to CalendarAgent + ToDoAgent
  ↓
Combined response: "Added milk to your list. 
                   Set reminder for rent payment."
```

Benefits: Specialization per domain, agent collaboration, future-proof

---

## Architecture Overview (Visual)

```
┌─────────────────────────────────────────┐
│   UNIFIED LLM ORCHESTRATOR              │
│   - Session routing                     │
│   - Queue management                    │
│   - Error handling                      │
└─────────────┬─────────────────────────┬─┘
              │                         │
       ┌──────▼──────┐        ┌────────▼────────┐
       │ Agents      │        │ LLM Providers   │
       │ - Finance   │        │ - Ollama (prim) │
       │ - Calendar  │        │ - Claude (fallb)│
       │ - To-Do     │        └─────────────────┘
       └─────┬───────┘
             │
             ▼
    ┌────────────────────┐
    │ Request Queue      │
    │ Priority: Local>   │
    │ Remote > Cloud     │
    └────────┬───────────┘
             │
      ┌──────┴──────┐
      ▼             ▼
   Remote        Main PC
   Devices       UI
```

---

## Key Files to Create

### Phase 1 (Start Here)
1. **`finance_app/services/llm_service.py`** (500 lines)
   - LLMService class
   - VoiceSession dataclass
   - SessionManager logic

2. **`finance_app/services/response_formatter.py`** (300 lines)
   - Parse LLM output
   - Generate audio scripts
   - Format for display/remote

3. **`tests/test_llm_service.py`** (200 lines)
   - Session isolation tests
   - Response formatting tests
   - Integration tests

### Implementation Steps
1. Create above files (code provided in Implementation Guide)
2. Update voice coordinator to route through LLMService
3. Test end-to-end with local + remote voice
4. Proceed to Phase 2 (queueing)

---

## Design Decisions

| What | Why |
|------|-----|
| **LLMService** | Single control point for all LLM routing |
| **Per-session history** | Device isolation + independent conversations |
| **Priority queue** | Ensures local UX responsive, remote fair |
| **Error cascade** | Always return something (never fail completely) |
| **Dual-output** | Same logic, different renderings (efficient) |
| **Agent inheritance** | Extensible, composable, domain-specific |
| **Session timeout** | Remote sessions auto-cleanup after 5 min |

---

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Local voice response | < 2.0s | Ollama timeout |
| Remote voice response | < 2.5s | Includes network overhead |
| Queue depth (max) | 20 requests | Prevents memory bloat |
| Session timeout | 300s (5 min) | Remote devices only |
| Conversation history | 20 turns | Bounded for token limits |

---

## Integration Checklist

### Phase 1: Core Service
- [ ] Create LLMService with SessionManager
- [ ] Create ResponseFormatter
- [ ] Update voice coordinator to use LLMService
- [ ] Write and pass unit tests
- [ ] Test local voice end-to-end
- [ ] Test remote voice end-to-end

### Phase 2: Queueing (Week 3)
- [ ] Implement PriorityRequestQueue
- [ ] Add queue consumer loop
- [ ] Test priority ordering
- [ ] Add metrics collection

### Phase 3: Error Handling (Week 4)
- [ ] LLMErrorHandler with retry logic
- [ ] SlowResponseManager (intermediate responses)
- [ ] Deterministic fallback responses
- [ ] Test timeout scenarios

### Phase 4: Agents (Weeks 5-6)
- [ ] Create BaseAgent class
- [ ] Implement FinanceAgent
- [ ] Create AgentOrchestrator
- [ ] Add delegation system

---

## Common Questions

**Q: Won't per-session history blow up memory?**  
A: No, capped at 20 turns per session, auto-cleanup after 5 min for remote.

**Q: What if Ollama is slow?**  
A: SlowResponseManager sends intermediate "thinking..." response, continues processing.

**Q: Can agents talk to each other?**  
A: Yes, through AgentOrchestrator delegation system.

**Q: How do I add a new agent (Shopping, Fitness, etc)?**  
A: Inherit BaseAgent, implement _build_system_prompt() and _parse_response(), register in orchestrator.

**Q: Is this backward compatible?**  
A: Yes, existing AssistantService stays; LLMService wraps it during Phase 1.

---

## Next Step

Read: **LLM_Remote_Voice_Architecture.md** (comprehensive)  
Then: **LLM_Implementation_Guide.md** (implementation)  
Start: Phase 1 code in Implementation Guide

---

**Questions?** Refer to the comprehensive architecture document for detailed technical specs, implementation details, and decision rationale.
