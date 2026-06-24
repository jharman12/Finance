# LLM Integration Architecture for Local & Remote Voice

**Date**: 2026-06-24  
**Purpose**: Comprehensive technical architecture for extending the Finance app's LLM integration to handle both local and remote voice inputs with proper session management, prioritization, and long-term agent support.

---

## Executive Summary

This document provides a complete architecture for integrating the local LLM (Ollama/qwen2.5) with both local and remote voice pipelines. The system will:

1. **Unified LLM Interface** - Single abstraction handling both local mic and remote devices
2. **Multi-Session Architecture** - Independent conversation contexts per device/user with shared financial context
3. **Intelligent Queueing** - Priority-based request handling with metrics collection
4. **Voice-Optimized Responses** - Concurrent generation of display text + speakable audio
5. **Graceful Degradation** - Fallback responses while LLM processes
6. **Agent Framework** - Extensible multi-agent system for Finance, Calendar, To-Do, etc.

---

## 1. LLM Integration Architecture for Local & Remote Voice

### Current State
```
Local Voice Flow:
  USB Mic → Vosk/Whisper ASR → Text → AssistantService → Ollama → JSON Response

Remote Voice Flow (needs improvement):
  Remote Device → TLS Audio → RemoteStreamSource → Vosk/Whisper ASR → Text → ? → Ollama
```

### Proposed Unified Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         UNIFIED LLM ORCHESTRATOR                            │
│                                                                             │
│  Responsibilities:                                                         │
│  - Route text to appropriate LLM (local Ollama, cloud Claude, etc.)        │
│  - Manage session isolation per device/user                                │
│  - Priority queue management                                                │
│  - Response formatting for both display + TTS                              │
│  - Telemetry & performance tracking                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                ▲                   ▲                   ▲
                │                   │                   │
        ┌───────┴────────┬──────────┴────────┬──────────┴────────┐
        │                │                   │                   │
        ▼                ▼                   ▼                   ▼
   ┌────────────┐  ┌─────────────┐   ┌──────────────┐   ┌──────────────┐
   │   Finance  │  │  Calendar   │   │   To-Do     │   │   Custom     │
   │   Agent    │  │   Agent     │   │   Agent     │   │   Agent      │
   └────────────┘  └─────────────┘   └──────────────┘   └──────────────┘
        ▲                ▲                   ▲                   ▲
        │                │                   │                   │
        │ (use shared    │ (use shared       │ (use shared      │ (use shared
        │  LLM service)  │  LLM service)     │  LLM service)    │  LLM service)
        │                │                   │                   │
        └────────────────┴───────────────────┴───────────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │   LLM Service (New Layer)     │
        │                               │
        │  - LLM Provider Selection     │
        │  - Model Management           │
        │  - Streaming & Tokens         │
        │  - Response Generation        │
        └───────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │   Request Queue Manager       │
        │                               │
        │  - Priority: Local > Remote   │
        │  - Device Fairness            │
        │  - Timeout Handling           │
        │  - Metrics                    │
        └───────────────────────────────┘
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
    ┌──────────────┐          ┌──────────────┐
    │ Ollama Local │          │ Claude Cloud │
    │ (Primary)    │          │ (Optional)   │
    └──────────────┘          └──────────────┘
```

### Implementation Structure

```python
# New service: finance_app/services/llm_service.py
class LLMService:
    """Central abstraction for all LLM interactions."""
    
    def __init__(self, ollama_client, optional_cloud_client=None):
        self.ollama = ollama_client  # Primary
        self.cloud = optional_cloud_client  # Fallback
        self.request_queue = PriorityRequestQueue()
        self.metrics = LLMMetricsCollector()
    
    async def process_voice_command(
        self, 
        session_id: str,  # device or user + device
        text: str,
        source: str,  # "local" or "remote:device_id"
        context: VoiceContext,
        use_json_mode: bool = True
    ) -> LLMResponse:
        """
        Single entry point for all LLM requests.
        
        Returns: LLMResponse(
            reply_text: str,          # display text
            audio_script: str,        # version for TTS
            actions: List[Action],    # executable actions
            metadata: {               # for agents
                confidence: float,
                processing_time_ms: int,
                tokens_used: int,
                source_provider: str  # "ollama" or "claude"
            }
        )
        """
```

### Key Integration Points

1. **Voice Pipeline → LLM Service**
   ```
   WakeWordCommandRouter 
     → process_text_event()
     → VoiceCoordinator.route_command()
     → LLMService.process_voice_command()  # NEW
   ```

2. **AssistantService Refactor** (already exists, extend it)
   ```
   # Existing entry point remains for typed input
   # New method for voice input:
   
   def handle_voice_command(
       self, 
       command_text: str, 
       session_key: str,
       source_type: str = "local"  # or "remote:device_id"
   ) -> AssistantResult:
       # Route through new LLMService
   ```

3. **RemoteStreamSource Integration**
   ```
   RemoteStreamSource
     → on_audio_chunk(source_id, bytes)
     → route to voice pipeline
     → same text → LLMService (automatically includes source_id)
     → LLMResponse routes to RemoteAudioServer for TTS + playback
   ```

---

## 2. Session Management & Context Persistence

### Session Lifecycle Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         SESSION MANAGER                                  │
│                                                                          │
│  Tracks: Per-device/user conversation history, financial context        │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴──────────────┐
                    │                              │
                    ▼                              ▼
        ┌───────────────────────┐      ┌──────────────────────┐
        │  LOCAL SESSION        │      │  REMOTE SESSIONS     │
        │  (Main PC User)       │      │  (Paired Devices)    │
        │                       │      │                      │
        │ - Wake phrase active  │      │ Device: Living Room  │
        │ - Keyboard input too  │      │  - Audio streaming   │
        │ - Long-lived          │      │  - TLS authenticated │
        │ - UI context aware    │      │  - Device-isolated   │
        │                       │      │  - Timeout: 5 min    │
        │ Session: "local"      │      │                      │
        │                       │      │ Device: Kitchen      │
        │                       │      │  - Audio streaming   │
        │                       │      │  - TLS authenticated │
        │                       │      │  - Device-isolated   │
        │                       │      │  - Timeout: 5 min    │
        │                       │      │                      │
        │                       │      │ Session key pattern: │
        │                       │      │ "remote:{device_id}" │
        └───────────────────────┘      └──────────────────────┘
```

### Session Data Structure

```python
# New class: finance_app/services/voice/session_manager.py

@dataclass
class VoiceSession:
    """Single conversation context for a device/user."""
    
    session_id: str                          # "local" or "remote:device_id"
    created_at: datetime
    last_activity_at: datetime
    timeout_seconds: int = 300               # 5 minutes for remote, longer for local
    
    # Conversation state
    conversation_history: list[OllamaMessage]  # Last 20 turns
    current_wake_state: VoiceSessionState      # idle, wake_detected, etc.
    last_text_received: str | None
    last_response_id: str | None              # UUID for response tracking
    
    # Financial context (shared, but cached)
    cached_financial_snapshot: FinancialSnapshot
    snapshot_age_seconds: int
    
    # Voice-specific metadata
    source_device_id: str | None              # e.g., "kitchen_speaker"
    source_ip: str | None                     # For remote sources
    tts_preference: dict[str, str]           # {"voice": "female", "speed": "0.9"}
    
    # Performance tracking
    total_requests: int = 0
    avg_response_time_ms: float = 0.0
    error_count: int = 0
    
    def is_expired(self) -> bool:
        elapsed = datetime.now() - self.last_activity_at
        return elapsed.total_seconds() > self.timeout_seconds
    
    def touch(self):
        """Update last activity time."""
        self.last_activity_at = datetime.now()


class SessionManager:
    """Lifecycle manager for all active voice sessions."""
    
    def __init__(self, repository: FinanceRepository, cleanup_interval_seconds: int = 60):
        self.repository = repository
        self.sessions: dict[str, VoiceSession] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task = None
    
    async def get_or_create_session(
        self, 
        session_id: str,
        device_id: str | None = None,
        source_ip: str | None = None
    ) -> VoiceSession:
        """Get existing session or create new one."""
        
        async with self._lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                session.touch()
                return session
            
            # Create new session
            session = VoiceSession(
                session_id=session_id,
                created_at=datetime.now(),
                last_activity_at=datetime.now(),
                source_device_id=device_id,
                source_ip=source_ip,
                cached_financial_snapshot=self.repository.snapshot(),
                snapshot_age_seconds=0
            )
            self.sessions[session_id] = session
            return session
    
    async def add_to_history(
        self,
        session_id: str,
        role: str,
        content: str,
        max_history_size: int = 20
    ) -> None:
        """Add message to session conversation history."""
        
        session = self.sessions.get(session_id)
        if not session:
            return
        
        session.conversation_history.append(
            OllamaMessage(role=role, content=content)
        )
        
        # Keep history bounded
        if len(session.conversation_history) > max_history_size:
            session.conversation_history = session.conversation_history[-max_history_size:]
        
        session.touch()
    
    async def refresh_financial_context(self, session_id: str) -> None:
        """Update cached financial snapshot if stale."""
        
        session = self.sessions.get(session_id)
        if not session:
            return
        
        if session.snapshot_age_seconds > 300:  # 5 min refresh
            session.cached_financial_snapshot = self.repository.snapshot()
            session.snapshot_age_seconds = 0
    
    async def cleanup_expired_sessions(self) -> None:
        """Remove expired remote sessions."""
        
        async with self._lock:
            expired = [
                sid for sid, session in self.sessions.items()
                if session.is_expired() and sid != "local"  # Keep local
            ]
            for sid in expired:
                del self.sessions[sid]
```

### Prompt Template per Session Type

```python
# Context aware prompts based on source

LOCAL_VOICE_SYSTEM_PROMPT = (
    "You are a personal financial advisor integrated into a home finance desktop app. "
    "You can see the full UI and user's financial data. "
    "User is speaking to you locally. Responses will be displayed in the UI. "
    "Be thorough and professional."
)

REMOTE_VOICE_SYSTEM_PROMPT = (
    "You are a personal financial advisor accessible from a remote device. "
    "User is speaking to you from another room. Your response will be spoken aloud. "
    "Be concise and conversational. Avoid technical jargon. "
    "Prioritize the most important information first."
)

AGENT_FINANCE_SYSTEM_PROMPT = (
    "You are the Finance Agent of a home AI assistant system. "
    "Your domain: budget analysis, spending categorization, financial recommendations. "
    "You have access to: transaction history, budget allocations, recurring items. "
    "Collaborate with other agents (Calendar, To-Do) when relevant. "
    "Always reference financial data in your responses."
)

# Agents will compose their own system prompts
```

---

## 3. Response Prioritization & Request Queueing

### Queue Priority System

```
┌───────────────────────────────────────────────────────────┐
│              PRIORITY REQUEST QUEUE                       │
│                                                           │
│  Incoming requests enqueued with priority score          │
└───────────────────────────────────────────────────────────┘
              │
              ├──> Priority Calculation:
              │    - Source type:       LOCAL = +10
              │                        REMOTE = +5
              │                        CLOUD = +2
              │    - Request age:       Older = +1/sec
              │    - Device fairness:   Round-robin bonus
              │    - Timeout risk:      Deadline < 5s = +5
              │
              └──> Dequeue Strategy: Highest priority first
```

### Implementation

```python
# New class: finance_app/services/llm_request_queue.py

from enum import Enum
from dataclasses import dataclass, field
from heapq import heappush, heappop
import asyncio
import time


class RequestSource(Enum):
    LOCAL_VOICE = "local_voice"
    LOCAL_TYPED = "local_typed"
    REMOTE_VOICE = "remote_voice"
    REMOTE_TYPED = "remote_typed"


@dataclass
class LLMRequest:
    """Queued request for LLM processing."""
    
    request_id: str                    # UUID
    session_id: str                    # "local" or "remote:device_id"
    text: str
    source: RequestSource
    created_at: float = field(default_factory=time.time)
    priority_score: float = 0.0
    timeout_deadline: float | None = None
    
    # For voice requests specifically
    callback_on_response: Callable[[str], None] | None = None
    callback_on_error: Callable[[str], None] | None = None
    
    def __lt__(self, other):
        """Max-heap comparison (higher priority first)."""
        # Negate for max-heap behavior in heapq
        if self.priority_score != other.priority_score:
            return self.priority_score > other.priority_score
        # Tie-breaker: FIFO (older first)
        return self.created_at < other.created_at


class PriorityRequestQueue:
    """Thread-safe priority queue for LLM requests."""
    
    def __init__(self, max_queue_size: int = 100):
        self._queue: list[LLMRequest] = []
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition(self._lock)
        self._max_size = max_queue_size
        self._metrics = {
            "total_enqueued": 0,
            "total_processed": 0,
            "average_wait_time_ms": 0,
            "max_queue_depth": 0,
            "dropped_timeouts": 0
        }
    
    async def enqueue(
        self,
        request: LLMRequest,
        priority_override: float | None = None
    ) -> bool:
        """
        Add request to queue. Returns False if queue is full.
        
        Priority calculation:
        - source_weight: local_voice=10, local_typed=8, remote=5
        - age_weight: +0.1 per second old
        - device_fairness: track per device, boost underserved
        - deadline_risk: if deadline < 5s, +5
        """
        
        async with self._lock:
            if len(self._queue) >= self._max_size:
                return False
            
            # Calculate priority
            if priority_override is not None:
                request.priority_score = priority_override
            else:
                request.priority_score = self._calculate_priority(request)
            
            heappush(self._queue, request)
            self._metrics["total_enqueued"] += 1
            self._metrics["max_queue_depth"] = max(
                self._metrics["max_queue_depth"],
                len(self._queue)
            )
            
            self._not_empty.notify()
            return True
    
    async def dequeue(self, timeout_seconds: float = 1.0) -> LLMRequest | None:
        """Get highest priority request from queue."""
        
        async with self._not_empty:
            while not self._queue:
                try:
                    await asyncio.wait_for(
                        self._not_empty.wait(),
                        timeout=timeout_seconds
                    )
                except asyncio.TimeoutError:
                    return None
            
            request = heappop(self._queue)
            self._metrics["total_processed"] += 1
            
            # Check if request is expired
            if request.timeout_deadline and time.time() > request.timeout_deadline:
                self._metrics["dropped_timeouts"] += 1
                # Recursively try next
                return await self.dequeue(timeout_seconds)
            
            return request
    
    def _calculate_priority(self, request: LLMRequest) -> float:
        """Calculate request priority."""
        
        base_scores = {
            RequestSource.LOCAL_VOICE: 10.0,
            RequestSource.LOCAL_TYPED: 8.0,
            RequestSource.REMOTE_VOICE: 6.0,
            RequestSource.REMOTE_TYPED: 4.0,
        }
        
        priority = base_scores.get(request.source, 0.0)
        
        # Age bonus: +0.01 per 100ms old
        age_ms = (time.time() - request.created_at) * 1000
        priority += age_ms / 100 * 0.01
        
        # Deadline urgency
        if request.timeout_deadline:
            deadline_risk = request.timeout_deadline - time.time()
            if deadline_risk < 5.0:
                priority += (5.0 - deadline_risk)
        
        # Device fairness (track processed by device, boost underserved)
        # This would integrate with SessionManager for tracking
        
        return priority
    
    def get_metrics(self) -> dict:
        """Return queue performance metrics."""
        return self._metrics.copy()
    
    async def size(self) -> int:
        """Current queue depth."""
        async with self._lock:
            return len(self._queue)
```

### Queue Consumer Loop

```python
# In LLMService

async def _process_queue_loop(self):
    """Main loop: dequeue, process, send responses."""
    
    while True:
        request = await self.request_queue.dequeue(timeout_seconds=5.0)
        if not request:
            continue
        
        try:
            # Track wait time
            wait_time_ms = (time.time() - request.created_at) * 1000
            
            # Process through appropriate agent
            response = await self._route_to_agent(request)
            
            # Update session
            session = await self.session_manager.get_or_create_session(request.session_id)
            await self.session_manager.add_to_history(
                request.session_id,
                "assistant",
                response.reply_text
            )
            
            # Send response
            if request.callback_on_response:
                request.callback_on_response(response)
            else:
                # Route to remote device or UI
                await self._send_response(request, response)
            
            # Metrics
            self.metrics.record_processed(
                request.session_id,
                request.source,
                wait_time_ms,
                response.metadata.get("processing_time_ms", 0)
            )
        
        except Exception as e:
            if request.callback_on_error:
                request.callback_on_error(str(e))
            else:
                await self._send_error_response(request, e)
```

---

## 4. Prompt Engineering Considerations for Voice vs Text

### Core Differences

| Aspect | Local Voice | Remote Voice | Typed Text |
|--------|------------|--------------|-----------|
| **Length** | Short (10-60s) | Very short (5-30s) | Medium-long |
| **Context** | Rich UI available | No visual context | UI context available |
| **Speed** | Real-time (< 2s) | Real-time (< 2s) | Can wait (< 10s) |
| **Formality** | Conversational | Conversational | Professional ok |
| **Output** | Display + optional TTS | Display + TTS required | Display only |
| **Recovery** | Can ask for clarification | Hard to recover | Can suggest actions |

### Prompt Templates by Modality

```python
# finance_app/services/voice/prompt_templates.py

class VoicePromptTemplate:
    """Dynamically construct prompts based on context."""
    
    VOICE_SYSTEM_PREAMBLE = (
        "You are a financial assistant responding to a voice command. "
        "Rules for voice responses:\n"
        "1. Be concise - speak in 1-3 sentences for basic queries\n"
        "2. Lead with the answer - don't build up to it\n"
        "3. Avoid numbers > 3 items unless specifically asked\n"
        "4. Avoid acronyms - spell out for clarity\n"
        "5. For detailed analysis, say 'Let me give you the full breakdown:' then summarize\n"
    )
    
    @staticmethod
    def build_voice_prompt(
        command: str,
        context: VoiceContext,
        source_type: str  # "local_voice", "remote_voice"
    ) -> str:
        """Build appropriate prompt for voice input."""
        
        if source_type == "remote_voice":
            preamble = (
                "You are a financial assistant responding to a remote voice command. "
                "The user cannot see your UI. "
                "Be VERY concise - 1-2 sentences max for factual queries. "
                "If the answer requires multiple points, signal that first: "
                "'I have three things to tell you: one, two, three.' "
                "Avoid jargon. Speak naturally."
            )
        else:  # local_voice
            preamble = (
                "You are a financial assistant responding to a voice command. "
                "The user can see the app UI alongside hearing your response. "
                "Be concise but thorough. You can reference what's on screen. "
                "For complex queries, structure your response clearly."
            )
        
        # Add relevant financial context
        context_section = f"""
Current financial snapshot:
- Income: ${context.snapshot.income_total:.2f}
- Expenses: ${context.snapshot.expense_total:.2f}
- Net: ${context.snapshot.net_total:.2f}

User command: "{command}"
"""
        
        return preamble + "\n\n" + context_section
    
    @staticmethod
    def build_agent_prompt(
        command: str,
        agent_type: str,  # "finance", "calendar", "todo"
        context: dict
    ) -> str:
        """Build agent-specific prompt."""
        
        agent_preambles = {
            "finance": (
                "You are the Finance Agent. Your role: budget analysis, spending patterns, "
                "financial recommendations. You have access to transaction history and budgets. "
                "When recommending actions (category changes, budgets), provide specific amounts "
                "and reasoning. Format recommendations as numbered lists."
            ),
            "calendar": (
                "You are the Calendar Agent. Your role: schedule awareness, event management, "
                "time-based recommendations. You can see upcoming events and busy times. "
                "Coordinate with Finance Agent for budget-impacting events (travel, dining, etc)."
            ),
            "todo": (
                "You are the To-Do Agent. Your role: task management, priority setting, "
                "deadline tracking. You can organize tasks by category and urgency. "
                "Coordinate with Calendar Agent for time-bound tasks."
            )
        }
        
        preamble = agent_preambles.get(agent_type, "")
        return f"{preamble}\n\nContext:\n{json.dumps(context)}\n\nRequest: {command}"


# Example prompts for response formatting

VOICE_RESPONSE_FORMAT = {
    "reply": "Conversational response for audio playback (1-3 sentences for voice)",
    "audio_script": "Version optimized for text-to-speech (natural phrasing, avoids numbers)",
    "actions": [
        {
            "type": "show_table",
            "payload": {"table": "upcoming_transactions"}
        }
    ]
}

AGENT_RESPONSE_FORMAT = {
    "reply": "Detailed professional response suitable for UI display",
    "actions": [
        {
            "type": "change_transaction_category",
            "payload": {"from_category": "Other", "to_category": "Groceries"}
        }
    ],
    "confidence": 0.95,
    "reasoning": "Explanation of why this action is recommended"
}
```

### Dynamic Prompt Adjustment

```python
def adjust_prompt_for_context(
    base_prompt: str,
    session: VoiceSession,
    request_source: RequestSource
) -> str:
    """Adjust prompt based on session history and source."""
    
    # If user has made similar requests recently, provide consistency prompt
    if session.conversation_history:
        last_turns = session.conversation_history[-4:]
        if any("budget" in msg.content.lower() for msg in last_turns):
            base_prompt += (
                "\nNote: User recently asked about budgets. "
                "Maintain consistency with previous budget recommendations."
            )
    
    # Adjust complexity based on response time budget
    if request_source == RequestSource.REMOTE_VOICE:
        base_prompt += (
            "\n\nIMPORTANT: This is a remote voice request with 2-second response budget. "
            "If analysis would take > 1.5s, provide quick answer first, "
            "then offer 'Would you like the full analysis?'"
        )
    
    return base_prompt
```

---

## 5. Response Structure: Display & Speakable

### Dual-Output Response Architecture

The key insight: **Same logical response, different renderings**

```python
@dataclass
class LLMResponse:
    """Multi-channel response from LLM."""
    
    # Primary outputs
    reply_text: str           # For UI display (can include formatting, links, emojis)
    audio_script: str         # For text-to-speech (natural, spoken phrasing)
    
    # Secondary outputs
    actions: list[Action]     # Executable actions (add transaction, etc)
    
    # Metadata
    metadata: dict = field(default_factory=dict)
    """
    Includes:
    - confidence: float (0-1)
    - processing_time_ms: int
    - tokens_used: int
    - source_provider: str ("ollama" or "claude")
    - agent: str ("finance", "calendar", etc)
    - source_type: str ("local_voice", "remote_voice", "typed")
    """
    
    # For remote responses specifically
    remote_device_id: str | None = None
    should_play_audio: bool = True


# Example response generation

class ResponseFormatter:
    """Generate multi-channel responses."""
    
    @staticmethod
    def parse_llm_output(
        raw_response: str,
        source_type: str
    ) -> LLMResponse:
        """
        Parse LLM JSON output and generate audio version.
        
        LLM returns: {"reply": "...", "actions": [...]}
        We generate: audio_script + determine audio urgency
        """
        
        payload = json.loads(raw_response)
        reply = payload.get("reply", "")
        actions = payload.get("actions", [])
        
        # Generate audio script (simplified, conversational)
        audio_script = ResponseFormatter._generate_audio_script(reply)
        
        response = LLMResponse(
            reply_text=reply,
            audio_script=audio_script,
            actions=actions,
            metadata={
                "source_type": source_type,
                "tokens_used": len(raw_response) // 4,  # Rough estimate
            }
        )
        
        return response
    
    @staticmethod
    def _generate_audio_script(reply_text: str) -> str:
        """
        Convert display text to speakable format.
        
        Transforms:
        - "Category: Groceries ($150)" → "Groceries at one fifty dollars"
        - Bullets → spoken numbered list
        - Markdown formatting → removed
        """
        
        script = reply_text
        
        # Remove markdown
        script = re.sub(r'[*_~`]', '', script)
        script = re.sub(r'#+\s+', '', script)  # Headers
        script = re.sub(r'[-•]\s+', 'Item: ', script)  # Bullets
        
        # Numbers to words (for amounts)
        script = re.sub(
            r'\$(\d+(?:\.\d{2})?)',
            lambda m: f"${float(m.group(1)) / 1:.0f} dollars",
            script
        )
        
        # Remove tables (can't speak them well)
        script = re.sub(r'\|.*\|', '', script)
        
        # Clean whitespace
        script = ' '.join(script.split())
        
        return script
    
    @staticmethod
    def format_for_display(
        response: LLMResponse,
        ui_context: dict | None = None
    ) -> dict:
        """Format response for UI display."""
        
        return {
            "text": response.reply_text,
            "actions": response.actions,
            "metadata": response.metadata,
            "timestamp": datetime.now().isoformat(),
            "ui_hints": {
                "action_emphasis": "high" if response.actions else "none",
                "read_aloud": False  # Local can show text instead
            }
        }
    
    @staticmethod
    def format_for_remote_playback(
        response: LLMResponse,
        device_config: dict | None = None
    ) -> dict:
        """Format response for remote device TTS."""
        
        device_config = device_config or {}
        
        return {
            "audio_script": response.audio_script,
            "device_id": response.remote_device_id,
            "tts_config": {
                "voice": device_config.get("preferred_voice", "default"),
                "speed": device_config.get("speech_speed", 1.0),
                "volume": device_config.get("volume", 0.8),
            },
            "playback_mode": "immediate" if len(response.audio_script) < 200 else "stream",
            "fallback_text": response.reply_text,  # If TTS fails
        }
```

### Real-World Example: Budget Query

```
User (remote voice): "What's my spending this month?"

LLM Input Prompt:
  System: "Remote voice assistant. Be very concise..."
  Context: "Current expenses: $2,456 total, Dining: $890, Groceries: $620..."
  User: "What's my spending this month?"

LLM Output (JSON):
  {
    "reply": "Your total spending this month is $2,456 across 8 categories. 
             Dining ($890) and Groceries ($620) are your top two. 
             You're on track with your $3,000 budget.",
    "actions": [
      {"type": "show_table", "payload": {"table": "monthly_summary"}}
    ]
  }

Response Generation:
  reply_text: Same as above (for UI if they return)
  
  audio_script: "Your total spending this month is twenty-four fifty-six 
                 across eight categories. Dining at eight ninety 
                 and Groceries at six twenty are your top two. 
                 You're on track with your three thousand dollar budget."
  
  Remote Playback:
  - TTS encodes audio_script with natural prosody
  - Plays over remote device speaker
  - If user is back at main PC UI, reply_text displays instead
```

---

## 6. Error Handling & Fallback Strategies

### Error Classification & Recovery

```
┌────────────────────────────────────────────────────────┐
│           LLM ERROR HANDLING STRATEGY                  │
│                                                        │
│ Errors cascade through fallback chain until success   │
└────────────────────────────────────────────────────────┘

Level 1: LLM Processing Error (Ollama timeout, crash)
  ↓
  Try: Retry with exponential backoff (100ms, 200ms, 400ms)
  ↓
  Fallback: Deterministic rule-based response
  ↓
  Fallback: Cloud LLM (if configured)
  ↓
  Fallback: Generic error response + suggest later

Level 2: Slow Response (Processing taking > threshold)
  ↓
  Try: Continue processing in background
  ↓
  Fallback: Send quick response immediately, offer follow-up
  
Level 3: Session Timeout (Remote device waiting too long)
  ↓
  Fallback: Cached response or simple reply
  ↓
  Fallback: Queue for processing when device returns
```

### Implementation

```python
# finance_app/services/llm_error_handling.py

class LLMErrorHandler:
    """Intelligent error recovery for LLM requests."""
    
    ERROR_TIMEOUT_SECONDS = 2.0
    SLOW_RESPONSE_SECONDS = 1.5
    
    def __init__(self, ollama_client, cloud_client=None, rules_engine=None):
        self.ollama = ollama_client
        self.cloud = cloud_client
        self.rules_engine = rules_engine  # Fallback deterministic response
    
    async def process_with_fallback(
        self,
        request: LLMRequest,
        session: VoiceSession
    ) -> LLMResponse:
        """
        Execute LLM with comprehensive fallback chain.
        
        Returns response or degraded response, never fails.
        """
        
        start_time = time.time()
        
        try:
            # Try primary: Ollama with timeout
            response = await asyncio.wait_for(
                self._process_with_ollama(request, session),
                timeout=self.ERROR_TIMEOUT_SECONDS
            )
            
            processing_time = time.time() - start_time
            response.metadata["processing_time_ms"] = int(processing_time * 1000)
            response.metadata["source_provider"] = "ollama"
            
            return response
        
        except asyncio.TimeoutError:
            logger.warning(f"Ollama timeout for request {request.request_id}")
            
            # Check if we have time for fallback
            elapsed = time.time() - start_time
            remaining = self.ERROR_TIMEOUT_SECONDS - elapsed
            
            if remaining > 0.5 and self.cloud:
                try:
                    # Try cloud LLM (faster for simple queries)
                    response = await asyncio.wait_for(
                        self._process_with_cloud(request, session),
                        timeout=remaining - 0.2
                    )
                    response.metadata["source_provider"] = "cloud_fallback"
                    logger.info(f"Used cloud fallback for {request.request_id}")
                    return response
                except asyncio.TimeoutError:
                    logger.warning(f"Cloud timeout for {request.request_id}")
            
            # Return rule-based response
            return await self._fallback_deterministic_response(request, session)
        
        except Exception as e:
            logger.error(f"LLM error: {type(e).__name__}: {e}")
            return await self._fallback_error_response(request, session, str(e))
    
    async def _process_with_ollama(
        self,
        request: LLMRequest,
        session: VoiceSession
    ) -> LLMResponse:
        """Process through Ollama with session context."""
        
        # Build messages with history
        messages = [OllamaMessage(role="system", content=self._build_system_prompt(request.source))]
        
        # Add conversation history
        messages.extend(session.conversation_history[-10:])
        
        # Add current request
        messages.append(OllamaMessage(role="user", content=request.text))
        
        # Call Ollama
        raw_response = self.ollama.chat(messages, json_mode=True)
        
        # Parse and generate audio script
        response = ResponseFormatter.parse_llm_output(raw_response, request.source.value)
        response.remote_device_id = session.source_device_id
        
        return response
    
    async def _fallback_deterministic_response(
        self,
        request: LLMRequest,
        session: VoiceSession
    ) -> LLMResponse:
        """
        Generate response using rule-based system.
        
        Handles common patterns:
        - Budget status: "You're at X% of budget"
        - Recent spending: List top categories
        - Category balance: "You've spent $X in {category}"
        - Next bills: "Upcoming recurring item is $X"
        """
        
        text = request.text.lower()
        
        if "budget" in text or "spending" in text:
            return self._quick_budget_response(session)
        elif "upcoming" in text or "next" in text:
            return self._quick_upcoming_response(session)
        elif "category" in text or "where" in text:
            return self._quick_category_response(session)
        else:
            return LLMResponse(
                reply_text="I'm having trouble processing that right now. Try again in a moment.",
                audio_script="I'm having trouble processing that right now. Try again in a moment.",
                actions=[],
                metadata={
                    "source_provider": "fallback_error",
                    "reason": "LLM timeout"
                }
            )
    
    def _quick_budget_response(self, session: VoiceSession) -> LLMResponse:
        """Fast deterministic budget response."""
        
        snapshot = session.cached_financial_snapshot
        pct_of_budget = (snapshot.expense_total / session.cached_financial_snapshot.budget_target * 100) if session.cached_financial_snapshot.budget_target else 0
        
        reply = (
            f"You've spent ${snapshot.expense_total:.0f} this month. "
            f"That's {pct_of_budget:.0f}% of your budget."
        )
        
        return LLMResponse(
            reply_text=reply,
            audio_script=reply,
            actions=[{"type": "show_table", "payload": {"table": "monthly_summary"}}],
            metadata={"source_provider": "fallback_rule", "reason": "timeout"}
        )
    
    async def _fallback_error_response(
        self,
        request: LLMRequest,
        session: VoiceSession,
        error_msg: str
    ) -> LLMResponse:
        """Final fallback: friendly error message."""
        
        source_type = "voice" if "voice" in request.source.value else "text"
        
        reply = "I'm experiencing technical difficulties. Please try again in a moment."
        
        logger.error(f"Final fallback for {request.request_id}: {error_msg}")
        
        return LLMResponse(
            reply_text=reply,
            audio_script=reply,
            actions=[],
            metadata={
                "source_provider": "error_fallback",
                "error": error_msg
            }
        )
    
    def _build_system_prompt(self, source: RequestSource) -> str:
        """Appropriate system prompt for request source."""
        
        if "remote" in source.value:
            return VoicePromptTemplate.VOICE_SYSTEM_PREAMBLE + " (Remote device - be concise.)"
        elif "voice" in source.value:
            return VoicePromptTemplate.VOICE_SYSTEM_PREAMBLE
        else:
            return SYSTEM_PROMPT  # From config.py


# Slow response handling

class SlowResponseManager:
    """Detect when LLM is slow and provide intermediate responses."""
    
    SLOW_THRESHOLD_SECONDS = 1.2
    
    def __init__(self, llm_service):
        self.llm_service = llm_service
    
    async def process_with_intermediate(
        self,
        request: LLMRequest,
        session: VoiceSession
    ) -> LLMResponse:
        """
        Process request with optional intermediate response.
        
        If processing takes > threshold:
        1. Send quick "thinking" response
        2. Continue processing
        3. Send full response when ready
        """
        
        start_time = time.time()
        processing_task = asyncio.create_task(
            self.llm_service._process_with_ollama(request, session)
        )
        
        try:
            # Wait for response with timeout
            response = await asyncio.wait_for(
                processing_task,
                timeout=self.SLOW_THRESHOLD_SECONDS
            )
            return response
        
        except asyncio.TimeoutError:
            # Send intermediate response
            quick_reply = self._generate_quick_response(request)
            await self._send_intermediate_response(request.session_id, quick_reply)
            
            # Continue waiting for full response in background
            try:
                response = await asyncio.wait_for(
                    processing_task,
                    timeout=5.0  # Extended timeout
                )
                await self._send_followup_response(request.session_id, response)
                return response
            except asyncio.TimeoutError:
                # Even slower - return quick response as final
                return quick_reply
    
    def _generate_quick_response(self, request: LLMRequest) -> LLMResponse:
        """Generate immediate response while processing continues."""
        
        if "remote" in request.source.value:
            reply = "Let me think about that for you."
        else:
            reply = "Analyzing your finances... one moment."
        
        return LLMResponse(
            reply_text=reply,
            audio_script=reply,
            actions=[],
            metadata={"type": "intermediate_response"}
        )
```

---

## 7. Long-Term Agent Architecture

### Multi-Agent System Design

The goal: Specialized agents for each domain (Finance, Calendar, To-Do, etc.) that can collaborate, remember conversations, and learn preferences.

```
┌──────────────────────────────────────────────────────────────────┐
│                    AGENT ORCHESTRATOR                            │
│                                                                  │
│  - Routes user requests to appropriate agent                     │
│  - Maintains agent registry                                      │
│  - Coordinates multi-agent responses                             │
│  - Manages shared context (user preferences, time, etc)          │
│  - Telemetry & learning                                          │
└──────────────────────────────────────────────────────────────────┘
        │
        ├─────────────────────────┬─────────────────────┬────────────────┐
        │                         │                     │                │
        ▼                         ▼                     ▼                ▼
    ┌─────────┐           ┌──────────┐         ┌──────────┐       ┌────────┐
    │ Finance │           │ Calendar │         │  To-Do   │       │ Custom │
    │ Agent   │           │  Agent   │         │  Agent   │       │ Agent  │
    │         │           │          │         │          │       │        │
    │ Context:│           │ Context: │         │ Context: │       │        │
    │ - Txns  │           │ - Events │         │ - Tasks  │       │        │
    │ - Budget│           │ - Schedule       │ - Reminders     │        │
    │ - Categ │           │ - Timezones     │ - Priority     │        │
    └────┬────┘           └────┬─────┘       └────┬──────┘       └───┬────┘
         │                     │                  │                   │
         └─────────────────────┴──────────────────┴───────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────┐
        │  Shared Context Layer              │
        │  - User preferences                │
        │  - Conversation memory             │
        │  - Device info                     │
        │  - Time/timezone                   │
        └────────────────────────────────────┘
```

### Agent Class Structure

```python
# finance_app/services/agents/base_agent.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentContext:
    """Shared context accessible to all agents."""
    
    user_id: str
    session_id: str
    source_device_id: str | None
    current_time: datetime
    timezone: str
    user_preferences: dict[str, Any]  # Learned preferences
    conversation_history: list[OllamaMessage]


class BaseAgent(ABC):
    """Base class for domain-specific agents."""
    
    def __init__(
        self,
        name: str,
        domain: str,  # "finance", "calendar", "todo"
        llm_service: "LLMService",
        system_prompt_template: str
    ):
        self.name = name
        self.domain = domain
        self.llm_service = llm_service
        self.system_prompt_template = system_prompt_template
        self.conversation_memory: dict[str, list[OllamaMessage]] = {}
    
    async def handle_request(
        self,
        user_input: str,
        context: AgentContext
    ) -> "AgentResponse":
        """
        Process user request in this agent's domain.
        
        Returns AgentResponse with:
        - reply_text
        - actions
        - confidence
        - delegation_request (if needs other agents)
        """
        
        # Build agent-specific prompt
        system_prompt = self._build_system_prompt(context)
        
        # Route through LLM
        messages = self._build_message_history(context)
        messages.append(OllamaMessage(role="user", content=user_input))
        
        response_text = self.llm_service.ollama.chat(messages, json_mode=True)
        
        # Parse response
        response = self._parse_agent_response(response_text, context)
        
        # Check if delegation needed
        if self._should_delegate(response, user_input):
            response.delegation_request = self._identify_delegation(user_input)
        
        return response
    
    async def handle_delegation(
        self,
        user_input: str,
        context: AgentContext,
        from_agent: str
    ) -> "AgentResponse":
        """
        Handle request delegated from another agent.
        
        Example: Finance Agent gets "Add reminder to pay rent" 
        → delegates To-Do Agent to create reminder
        """
        
        # Slightly different framing for delegated requests
        system_prompt = self._build_system_prompt(context, delegated_from=from_agent)
        
        messages = [OllamaMessage(role="system", content=system_prompt)]
        messages.append(
            OllamaMessage(
                role="assistant",
                content=f"Handling delegated request from {from_agent} agent."
            )
        )
        messages.extend(self.conversation_memory.get(context.session_id, []))
        messages.append(OllamaMessage(role="user", content=user_input))
        
        response_text = self.llm_service.ollama.chat(messages, json_mode=True)
        return self._parse_agent_response(response_text, context)
    
    @abstractmethod
    def _build_system_prompt(
        self,
        context: AgentContext,
        delegated_from: str | None = None
    ) -> str:
        """Build domain-specific system prompt."""
        pass
    
    @abstractmethod
    def _parse_agent_response(
        self,
        response_text: str,
        context: AgentContext
    ) -> "AgentResponse":
        """Parse LLM response into structured format."""
        pass
    
    @abstractmethod
    def _should_delegate(self, response: "AgentResponse", user_input: str) -> bool:
        """Determine if this request needs other agents."""
        pass
    
    def _identify_delegation(self, user_input: str) -> list[str]:
        """Identify which agents should be involved."""
        # Uses keyword matching or LLM inference
        pass


@dataclass
class AgentResponse:
    """Response from an agent."""
    
    agent_name: str
    reply_text: str
    actions: list[dict]
    confidence: float
    reasoning: str
    delegation_request: list[str] | None = None  # Other agents to involve


# Concrete implementations

class FinanceAgent(BaseAgent):
    """Manages all financial queries and actions."""
    
    def __init__(self, llm_service, repository):
        super().__init__(
            name="Finance",
            domain="finance",
            llm_service=llm_service,
            system_prompt_template=AGENT_FINANCE_SYSTEM_PROMPT
        )
        self.repository = repository
    
    def _build_system_prompt(self, context: AgentContext, delegated_from=None) -> str:
        """Finance-specific system prompt."""
        
        base = (
            "You are the Finance Agent. Your expertise: budget analysis, spending patterns, "
            "category management, recurring items, financial recommendations. "
            "You have access to full transaction history and budget data. "
            "When recommending actions, provide specific amounts and clear reasoning. "
        )
        
        if delegated_from:
            base += f"\nYou are handling a request delegated from the {delegated_from} Agent. "
            base += "Coordinate your response to integrate with their domain."
        
        # Add live financial context
        context_data = {
            "current_budget_status": self.repository.snapshot(),
            "categories": [c.name for c in self.repository.list_categories()],
            "upcoming_recurring": self._get_upcoming_recurring(context),
        }
        
        base += f"\n\nCurrent Financial Context:\n{json.dumps(context_data, default=str)}"
        
        return base
    
    def _parse_agent_response(self, response_text: str, context: AgentContext) -> AgentResponse:
        """Parse finance agent response."""
        
        payload = json.loads(response_text)
        
        return AgentResponse(
            agent_name="Finance",
            reply_text=payload.get("reply", ""),
            actions=payload.get("actions", []),
            confidence=payload.get("confidence", 0.8),
            reasoning=payload.get("reasoning", "")
        )
    
    def _should_delegate(self, response: AgentResponse, user_input: str) -> bool:
        """Finance agent should delegate calendar/todo items."""
        
        if any(kw in user_input.lower() for kw in ["remind", "schedule", "event", "calendar"]):
            return True
        if any(kw in user_input.lower() for kw in ["task", "todo", "add to list"]):
            return True
        return False


class CalendarAgent(BaseAgent):
    """Manages calendar and scheduling."""
    
    def __init__(self, llm_service, calendar_service):
        super().__init__(
            name="Calendar",
            domain="calendar",
            llm_service=llm_service,
            system_prompt_template=AGENT_CALENDAR_SYSTEM_PROMPT
        )
        self.calendar = calendar_service
    
    # Similar structure...


class ToDoAgent(BaseAgent):
    """Manages tasks and priorities."""
    
    def __init__(self, llm_service, todo_service):
        super().__init__(
            name="ToDo",
            domain="todo",
            llm_service=llm_service,
            system_prompt_template=AGENT_TODO_SYSTEM_PROMPT
        )
        self.todo = todo_service
    
    # Similar structure...
```

### Agent Orchestrator

```python
# finance_app/services/agent_orchestrator.py

class AgentOrchestrator:
    """Coordinates all agents and their interactions."""
    
    def __init__(self, llm_service, agents: dict[str, BaseAgent]):
        self.llm_service = llm_service
        self.agents = agents  # {"finance": FinanceAgent(), "calendar": CalendarAgent(), ...}
        self.router_model = None  # Optional: trained router to pick best agent
    
    async def process_user_request(
        self,
        user_input: str,
        context: AgentContext
    ) -> "OrchestratorResponse":
        """
        Route user input to appropriate agent(s).
        
        May involve:
        1. Single agent handling
        2. Multi-agent coordination
        3. Sequential delegation
        """
        
        # Identify which agent(s) should handle this
        primary_agent = await self._route_to_primary_agent(user_input, context)
        
        # Get primary response
        primary_response = await primary_agent.handle_request(user_input, context)
        
        # Check for delegations
        if primary_response.delegation_request:
            delegated_responses = await self._execute_delegations(
                user_input,
                context,
                primary_agent.name,
                primary_response.delegation_request
            )
        else:
            delegated_responses = []
        
        # Synthesize final response
        final_response = self._synthesize_responses(
            primary_response,
            delegated_responses,
            context
        )
        
        return final_response
    
    async def _route_to_primary_agent(
        self,
        user_input: str,
        context: AgentContext
    ) -> BaseAgent:
        """Determine which agent should handle this request."""
        
        # Simple keyword routing (can be replaced with ML router)
        keywords = {
            "finance": ["budget", "spending", "expense", "income", "transaction", "category"],
            "calendar": ["event", "schedule", "calendar", "meeting", "appointment"],
            "todo": ["task", "reminder", "todo", "add to list"],
        }
        
        for agent_name, kws in keywords.items():
            if any(kw in user_input.lower() for kw in kws):
                return self.agents[agent_name]
        
        # Default to Finance agent
        return self.agents["finance"]
    
    async def _execute_delegations(
        self,
        user_input: str,
        context: AgentContext,
        from_agent: str,
        delegated_agents: list[str]
    ) -> list[AgentResponse]:
        """Execute delegated requests to other agents."""
        
        responses = []
        for agent_name in delegated_agents:
            if agent_name in self.agents:
                agent = self.agents[agent_name]
                response = await agent.handle_delegation(user_input, context, from_agent)
                responses.append(response)
        
        return responses
    
    def _synthesize_responses(
        self,
        primary: AgentResponse,
        delegated: list[AgentResponse],
        context: AgentContext
    ) -> "OrchestratorResponse":
        """Combine primary + delegated responses into final answer."""
        
        all_actions = primary.actions.copy()
        all_reasoning = [primary.reasoning]
        
        for delegated_resp in delegated:
            all_actions.extend(delegated_resp.actions)
            all_reasoning.append(f"{delegated_resp.agent_name}: {delegated_resp.reasoning}")
        
        # For voice: synthesize into single response
        if "voice" in context.source_device_id or True:  # Assuming voice for now
            combined_reply = self._synthesize_voice_response(
                primary.reply_text,
                [d.reply_text for d in delegated],
                context
            )
        else:
            combined_reply = primary.reply_text
        
        return OrchestratorResponse(
            reply_text=combined_reply,
            actions=all_actions,
            agent_responses={
                "primary": primary,
                "delegated": {d.agent_name: d for d in delegated}
            },
            reasoning=all_reasoning
        )
    
    def _synthesize_voice_response(
        self,
        primary_reply: str,
        delegated_replies: list[str],
        context: AgentContext
    ) -> str:
        """Combine multi-agent responses into coherent speech."""
        
        # If delegated agents have output, weave it together
        if delegated_replies:
            combined = f"{primary_reply} Additionally, {' and '.join(delegated_replies)}"
        else:
            combined = primary_reply
        
        # Limit length for voice
        if len(combined) > 500:
            combined = combined[:500] + "... Tell me if you want more details."
        
        return combined


@dataclass
class OrchestratorResponse:
    """Final response from orchestrator."""
    
    reply_text: str
    actions: list[dict]
    agent_responses: dict[str, AgentResponse]
    reasoning: list[str]
    metadata: dict = field(default_factory=dict)
```

### Agent Learning & Preferences

```python
# finance_app/services/agent_preferences.py

class AgentPreferenceManager:
    """Learn user preferences and optimize agent behavior."""
    
    def __init__(self, repository: FinanceRepository):
        self.repository = repository
        self.user_preferences = {}  # Load from DB
    
    async def record_interaction(
        self,
        user_input: str,
        agent_response: AgentResponse,
        user_feedback: dict  # {"helpful": True, "action_applied": True}
    ) -> None:
        """
        Record interaction to learn preferences.
        
        Examples:
        - User always chooses Finance recommendations
        - User prefers email communication
        - User typically says "yes" to high-confidence suggestions
        """
        
        # Extract patterns
        if user_feedback.get("action_applied"):
            # Agent's recommendation was accepted
            self._record_successful_agent_recommendation(agent_response)
        
        # Update confidence calibration
        if user_feedback.get("confidence_match"):
            # Agent's confidence matched user's actual satisfaction
            self._update_confidence_calibration(agent_response.agent_name)
    
    def get_user_preference(self, key: str, default=None):
        """Get learned user preference."""
        return self.user_preferences.get(key, default)
    
    def set_user_preference(self, key: str, value: Any) -> None:
        """Explicitly set user preference."""
        self.user_preferences[key] = value
        # Persist to DB
```

---

## Implementation Roadmap

### Phase 1: Core LLM Service (Weeks 1-2)
- [ ] Create `LLMService` abstraction
- [ ] Implement `SessionManager` with conversation history
- [ ] Create `ResponseFormatter` for dual-output
- [ ] Update `AssistantService` to route through new service

### Phase 2: Queue Management & Prioritization (Week 3)
- [ ] Implement `PriorityRequestQueue`
- [ ] Add queue consumer loop
- [ ] Integrate with voice pipeline
- [ ] Add metrics collection

### Phase 3: Error Handling & Fallbacks (Week 4)
- [ ] Implement `LLMErrorHandler` with retry logic
- [ ] Create `SlowResponseManager`
- [ ] Add deterministic fallback responses
- [ ] Test timeout scenarios

### Phase 4: Agent Framework (Weeks 5-6)
- [ ] Create `BaseAgent` and Finance Agent
- [ ] Implement `AgentOrchestrator`
- [ ] Add delegation logic
- [ ] Create Calendar and To-Do agents

### Phase 5: Remote Voice Integration (Week 7)
- [ ] Route remote voice through new LLM service
- [ ] Generate TTS from audio scripts
- [ ] Test multi-device scenarios
- [ ] Add device-specific preferences

### Phase 6: Testing & Optimization (Week 8)
- [ ] Load testing with multiple queued requests
- [ ] Test agent coordination
- [ ] Optimize LLM response times
- [ ] User testing with actual voice

---

## Data Flow Diagram: Complete Request Lifecycle

```
Remote Device (Kitchen Speaker)
    │
    ├─> Audio captured
    │    │
    └─> Audio streamed to Main PC (TLS + auth)
         │
         ▼
    ┌─────────────────┐
    │ RemoteStreamSource
    │ (receives audio) │
    └────────┬────────┘
             │
             ▼
    ┌──────────────────────┐
    │ ASR Pipeline         │
    │ (Vosk/Faster Whisper)│
    │ → "what's my budget" │
    └────────┬─────────────┘
             │
             ▼
    ┌────────────────────────────┐
    │ WakeWordCommandRouter      │
    │ (already awake, no wake) │
    │ → Extracted command text   │
    └────────┬───────────────────┘
             │
             ▼
    ┌─────────────────────────────────────┐
    │ LLMService.process_voice_command()  │
    │ - source_id: "remote:kitchen"       │
    │ - text: "what's my budget"          │
    │ - context: voice + financial data   │
    └────────┬────────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────┐
    │ Check/Create Session             │
    │ session_id: "remote:kitchen"     │
    │ - Load conversation history      │
    │ - Refresh cached snapshot        │
    └────────┬─────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────┐
    │ Enqueue to PriorityRequestQueue  │
    │ - Priority: REMOTE_VOICE = 6.0   │
    │ - Timeout deadline: now + 2s     │
    └────────┬─────────────────────────┘
             │
             ▼
    ┌────────────────────────────────────────┐
    │ Queue Consumer dequeues request        │
    │ (higher priority than buffered         │
    │  local keyboard input)                 │
    └────────┬───────────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────────────┐
    │ Route to Agent (AgentOrchestrator)      │
    │ - Identify: Finance agent domain       │
    │ - Build finance-specific prompt        │
    └────────┬─────────────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────────────────┐
    │ LLMService._process_with_ollama()           │
    │ - System prompt + history + current query  │
    │ - Send to Ollama                           │
    │ - Timeout: 2 seconds                       │
    └────────┬──────────────────────────────────┘
             │
             ├─ SUCCESS: Response from Ollama
             │   {
             │     "reply": "Your budget is $3000...",
             │     "actions": [...],
             │     "confidence": 0.95
             │   }
             │   │
             │   ▼
             │  ┌──────────────────────────┐
             │  │ ResponseFormatter       │
             │  │ - Parse JSON            │
             │  │ - Generate audio_script │
             │  │  (numbers to words,     │
             │  │   simplified phrasing)  │
             │  └──────┬───────────────────┘
             │         │
             │         ▼
             │  ┌────────────────────────────────┐
             │  │ LLMResponse object:            │
             │  │ reply_text: "Your budget..."  │
             │  │ audio_script: "Your budget..." │
             │  │ actions: [...]                 │
             │  │ remote_device_id: "kitchen"    │
             │  └──────┬────────────────────────┘
             │         │
             │         ▼
             │  ┌──────────────────────────────────┐
             │  │ SessionManager.add_to_history()  │
             │  │ - Store assistant response       │
             │  │ - Keep conversation context      │
             │  └────────┬─────────────────────────┘
             │           │
             │           ▼
             │  ┌──────────────────────────────────┐
             │  │ RemoteAudioServer               │
             │  │ - Pick up audio_script          │
             │  │ - Generate TTS audio stream     │
             │  │ - Send over TLS to kitchen      │
             │  │   speaker                       │
             │  └────────┬─────────────────────────┘
             │           │
             │           ▼
             │  Kitchen Speaker
             │    │
             │    └─> "Your budget is..."
             │        (spoken response)
             │
             └─ TIMEOUT: LLM too slow (> 1.5s)
                 │
                 ▼
                ┌──────────────────────────┐
                │ SlowResponseManager      │
                │ - Send "Thinking..." TTS │
                │ - Continue processing   │
                │ - Send full response    │
                │   when ready            │
                └──────────────────────────┘

PARALLEL PATH (Local User at Main PC):
    Local User (Keyboard)
         │
         ├─> Type: "update budget to 3500"
         │
         └─> Text input through UI
              │
              ▼
         ┌────────────────────────┐
         │ UI captures input      │
         │ - Queue to LLMService  │
         │ - Source: LOCAL_TYPED  │
         │ - Priority: 8.0 (high) │
         │                        │
         │ But remote voice gets  │
         │ priority 6.0, already  │
         │ in queue first         │
         └────────────────────────┘
              │
              ▼
         Wait in queue until
         remote request finishes
         (should be ~500ms)
```

---

## Summary Table: Architectural Decisions

| Aspect | Approach | Rationale |
|--------|----------|-----------|
| **LLM Abstraction** | Single `LLMService` with agent routing | Unified interface for local+remote, enables agent system |
| **Sessions** | Per-device-id with shared financial context | Device isolation + efficiency |
| **Queueing** | Priority-based heap queue | Local voice > remote voice > background tasks |
| **Error Handling** | Cascade: Ollama → Cloud → Deterministic → Error msg | Graceful degradation, always return response |
| **Response Format** | Dual-output (display + audio script) | Same logic, different renderings |
| **Agents** | Inheritance-based with delegation | Extensible, composable, collaborative |
| **Remote Voice** | TLS + device ID + session isolation | Security + multi-device support |
| **Conversation Memory** | Last 20 turns per session | Bounded context, respects token limits |

---

## Next Steps

1. **Start with Phase 1**: Create `LLMService` as the central abstraction
2. **Integrate existing components**: Route `AssistantService` through new service
3. **Add remote voice routing**: Ensure remote audio goes through same LLM path
4. **Test multi-session scenarios**: Verify isolation and priority
5. **Build agent framework incrementally**: Finance agent first, then calendar/todo
6. **Deploy and gather telemetry**: Track response times, error rates, user satisfaction

This architecture provides a scalable foundation for your vision of a multi-agent AI home assistant system.
