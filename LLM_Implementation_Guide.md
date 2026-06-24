# LLM Architecture Implementation Guide

**Purpose**: Map the high-level architecture to your existing codebase and provide concrete steps for implementation.

---

## Current Code State

### Existing Components to Leverage

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| `AssistantService` | `services/assistant_service.py` | Ollama client + conversation history | ✓ Exists |
| `OllamaClient` | `services/ollama_client.py` | HTTP wrapper for Ollama API | ✓ Exists |
| `VoiceSessionState` | `services/voice/session_state.py` | Enum for pipeline state | ✓ Exists |
| `RemoteStreamSource` | `services/voice/remote_stream_source.py` | Network audio receiver | ✓ Exists |
| `WakeWordCommandRouter` | `services/voice_pipeline.py` | Wake + command extraction | ✓ Exists |
| `VoiceTextEvent` | `services/voice_pipeline.py` | Text events from ASR | ✓ Exists |
| `StorageRepository` | `storage.py` | Financial data access | ✓ Exists |

### What Needs to Be Created

1. **`LLMService`** - Central abstraction layer (NEW)
2. **`SessionManager`** - Multi-session context tracking (NEW)
3. **`PriorityRequestQueue`** - Request queuing (NEW)
4. **`LLMErrorHandler`** - Graceful fallback handling (NEW)
5. **`ResponseFormatter`** - Multi-output response generation (NEW)
6. **`BaseAgent`** / **`FinanceAgent`** - Agent framework (NEW)
7. **`AgentOrchestrator`** - Agent coordinator (NEW)

---

## Phase 1: Create LLM Service Layer (Week 1)

### Step 1.1: Create `LLMService` Base Class

**File**: `finance_app/services/llm_service.py`

```python
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from finance_app.services.ollama_client import OllamaClient, OllamaMessage
from finance_app.storage import FinanceRepository


class LLMProvider(Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    CLAUDE = "claude"  # For future cloud fallback


@dataclass
class LLMResponse:
    """Multi-channel response from LLM."""
    
    reply_text: str                    # Display version
    audio_script: str                  # TTS version
    actions: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    remote_device_id: str | None = None
    should_play_audio: bool = True
    
    @classmethod
    def from_assistant_result(cls, result: Any, device_id: str | None = None) -> LLMResponse:
        """Convert existing AssistantResult to LLMResponse."""
        
        # Parse existing response format
        reply = result.payload.get("reply", "") if hasattr(result, 'payload') else str(result)
        actions = result.payload.get("actions", []) if hasattr(result, 'payload') else []
        
        # Generate audio script from reply
        audio_script = cls._generate_audio_script(reply)
        
        return cls(
            reply_text=reply,
            audio_script=audio_script,
            actions=actions,
            remote_device_id=device_id,
            metadata={"converted": True}
        )
    
    @staticmethod
    def _generate_audio_script(reply_text: str) -> str:
        """Convert display text to speakable format."""
        
        import re
        
        script = reply_text
        
        # Remove markdown
        script = re.sub(r'[*_~`]', '', script)
        script = re.sub(r'#+\s+', '', script)
        script = re.sub(r'[-•]\s+', 'Item: ', script)
        
        # Numbers to words
        script = re.sub(
            r'\$(\d+(?:\.\d{2})?)',
            lambda m: f"${float(m.group(1)):.0f} dollars",
            script
        )
        
        # Remove tables
        script = re.sub(r'\|.*\|', '', script)
        
        # Clean whitespace
        script = ' '.join(script.split())
        
        return script


class LLMService:
    """Central LLM orchestration service."""
    
    def __init__(
        self,
        repository: FinanceRepository,
        ollama_client: OllamaClient | None = None,
        cloud_client: Optional[Any] = None
    ):
        self.repository = repository
        self.ollama = ollama_client or OllamaClient()
        self.cloud = cloud_client
        
        # Session management
        self._sessions: dict[str, VoiceSession] = {}
        self._session_lock = asyncio.Lock()
        
        # Request queuing (implemented in Phase 2)
        self._request_queue = None
        
        # Metrics
        self.metrics = {
            "total_processed": 0,
            "errors": 0,
            "avg_response_time_ms": 0.0,
        }
    
    async def process_voice_command(
        self,
        session_id: str,
        text: str,
        source_type: str = "local_voice",
        device_id: str | None = None
    ) -> LLMResponse:
        """
        Process voice command through LLM.
        
        Session_id: "local" for main PC, "remote:{device_id}" for remote devices
        """
        
        # Get or create session
        session = await self._get_or_create_session(session_id, device_id)
        session.last_text_received = text
        
        # Route to handler (will integrate AssistantService later)
        response = await self._process_with_assistant(text, session, source_type)
        
        # Store in history
        await self._add_to_history(session_id, "assistant", response.reply_text)
        
        return response
    
    async def _process_with_assistant(
        self,
        text: str,
        session: VoiceSession,
        source_type: str
    ) -> LLMResponse:
        """
        Bridge to existing AssistantService.
        
        This is temporary until we refactor AssistantService.
        """
        
        from finance_app.services.assistant_service import AssistantService
        
        assistant = AssistantService(self.repository, self.ollama)
        
        # Use session ID as conversation key for history isolation
        result = assistant.handle_prompt(text, session_key=session.session_id)
        
        # Convert to new format
        response = LLMResponse.from_assistant_result(result, session.source_device_id)
        response.metadata["source_type"] = source_type
        response.metadata["processing_time_ms"] = 0  # TODO: track
        
        await self._add_to_history(session.session_id, "user", text)
        
        return response
    
    async def _get_or_create_session(
        self,
        session_id: str,
        device_id: str | None = None
    ) -> VoiceSession:
        """Get existing session or create new one."""
        
        async with self._session_lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.last_activity_at = datetime.now()
                return session
            
            # Create new
            session = VoiceSession(
                session_id=session_id,
                created_at=datetime.now(),
                last_activity_at=datetime.now(),
                source_device_id=device_id,
                cached_financial_snapshot=self.repository.snapshot(),
            )
            self._sessions[session_id] = session
            return session
    
    async def _add_to_history(
        self,
        session_id: str,
        role: str,
        content: str,
        max_history: int = 20
    ) -> None:
        """Add message to session history."""
        
        session = self._sessions.get(session_id)
        if not session:
            return
        
        session.conversation_history.append(
            OllamaMessage(role=role, content=content)
        )
        
        if len(session.conversation_history) > max_history:
            session.conversation_history = session.conversation_history[-max_history:]
        
        session.last_activity_at = datetime.now()


@dataclass
class VoiceSession:
    """Single voice conversation session."""
    
    session_id: str
    created_at: datetime
    last_activity_at: datetime
    source_device_id: str | None = None
    source_ip: str | None = None
    timeout_seconds: int = 300  # 5 min for remote, can override
    
    conversation_history: list[OllamaMessage] = field(default_factory=list)
    cached_financial_snapshot: Any | None = None
    last_text_received: str | None = None
    
    total_requests: int = 0
    error_count: int = 0
    
    def is_expired(self) -> bool:
        elapsed = (datetime.now() - self.last_activity_at).total_seconds()
        return elapsed > self.timeout_seconds
    
    @property
    def is_remote(self) -> bool:
        return self.session_id.startswith("remote:")
```

### Step 1.2: Update Voice Pipeline to Use LLMService

**File**: `finance_app/ui/main_window.py` (or wherever voice coordinator is initialized)

```python
# In VoiceCoordinator or similar initialization

from finance_app.services.llm_service import LLMService

class VoiceCoordinator:
    def __init__(self, repository, ...):
        # Create centralized LLM service
        self.llm_service = LLMService(
            repository=repository,
            ollama_client=self.ollama_client
        )
    
    async def on_command_recognized(self, command_text: str, source: str):
        """
        Called when ASR produces a command.
        
        source: "local" or "remote:{device_id}"
        """
        
        # Get device ID from source
        if source.startswith("remote:"):
            device_id = source.split(":", 1)[1]
            session_id = source
            source_type = "remote_voice"
        else:
            device_id = None
            session_id = "local"
            source_type = "local_voice"
        
        # Process through LLM service
        response = await self.llm_service.process_voice_command(
            session_id=session_id,
            text=command_text,
            source_type=source_type,
            device_id=device_id
        )
        
        # Handle response
        await self._handle_llm_response(response)
    
    async def _handle_llm_response(self, response: LLMResponse):
        """Route LLM response to UI or remote device."""
        
        if response.remote_device_id:
            # Send to remote device
            await self._send_to_remote_device(response)
        else:
            # Display on main PC UI
            self._display_on_ui(response)
    
    async def _send_to_remote_device(self, response: LLMResponse):
        """Send response to remote device for TTS playback."""
        
        # This will be implemented in Phase 5
        # For now, just route to remote audio server
        if self.remote_audio_server:
            await self.remote_audio_server.queue_response(
                device_id=response.remote_device_id,
                audio_script=response.audio_script,
                text_fallback=response.reply_text
            )
    
    def _display_on_ui(self, response: LLMResponse):
        """Display response on main PC UI."""
        
        # Emit signal or call UI handler
        self.on_assistant_response(response.reply_text, response.actions)
```

### Step 1.3: Create Adapter to Keep AssistantService Compatibility

**File**: `finance_app/services/assistant_service.py` (update)

```python
# At the end of assistant_service.py, add compatibility method:

class AssistantService:
    # ... existing code ...
    
    def handle_prompt(
        self,
        prompt_text: str,
        session_key: str | None = None,
        use_voice_mode: bool = False
    ) -> AssistantResult:
        """
        Original method - keep for backward compatibility.
        
        use_voice_mode: If True, optimize for voice (concise, audio-friendly)
        """
        
        # ... existing implementation ...
        
        # If called from LLMService, we'll parse result into LLMResponse
        return result
```

---

## Phase 1.5: Add Response Formatting

**File**: `finance_app/services/response_formatter.py` (NEW)

```python
from __future__ import annotations

import json
import re
from typing import Any


class ResponseFormatter:
    """Generate multi-channel responses from LLM output."""
    
    @staticmethod
    def parse_llm_output(
        raw_response: str,
        source_type: str
    ) -> dict[str, Any]:
        """
        Parse LLM JSON response.
        
        Returns dict with reply_text, audio_script, actions.
        """
        
        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError:
            # Fallback if LLM returns non-JSON
            payload = {"reply": raw_response, "actions": []}
        
        reply = payload.get("reply", "")
        audio_script = ResponseFormatter.generate_audio_script(reply, source_type)
        actions = payload.get("actions", [])
        
        return {
            "reply_text": reply,
            "audio_script": audio_script,
            "actions": actions
        }
    
    @staticmethod
    def generate_audio_script(
        reply_text: str,
        source_type: str = "voice"
    ) -> str:
        """
        Convert display text to speakable format.
        
        Transforms:
        - $150 → one fifty dollars
        - Markdown → plain text
        - Tables → skipped (can't speak)
        - Bullets → numbered list items
        """
        
        script = reply_text
        
        # Remove markdown formatting
        script = re.sub(r'\*\*(.*?)\*\*', r'\1', script)  # Bold
        script = re.sub(r'\*(.*?)\*', r'\1', script)      # Italic
        script = re.sub(r'___(.*?)___', r'\1', script)    # Bold italic
        script = re.sub(r'__(.*?)__', r'\1', script)      # Italic
        script = re.sub(r'~~(.*?)~~', r'\1', script)      # Strikethrough
        script = re.sub(r'`(.*?)`', r'\1', script)        # Inline code
        
        # Remove headers
        script = re.sub(r'^#+\s+', '', script, flags=re.MULTILINE)
        
        # Convert bullets to text
        script = re.sub(r'^[-•]\s+', 'Item: ', script, flags=re.MULTILINE)
        
        # Convert currency to words
        def dollar_to_words(match):
            amount = float(match.group(1))
            if amount == int(amount):
                return f"{int(amount)} dollars"
            else:
                return f"{amount} dollars"
        
        script = re.sub(r'\$(\d+(?:\.\d{2})?)', dollar_to_words, script)
        
        # Remove tables (hard to speak)
        script = re.sub(r'\|.*?\|', '', script, flags=re.DOTALL)
        
        # Remove links (keep just text)
        script = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', script)
        
        # Clean up excessive whitespace
        script = ' '.join(script.split())
        
        # For remote voice, keep it shorter
        if source_type == "remote_voice" and len(script) > 300:
            script = script[:300] + "... Tell me if you'd like more details."
        
        return script
    
    @staticmethod
    def format_for_display(response: dict, ui_context: dict | None = None) -> dict:
        """Format response for UI display."""
        
        return {
            "text": response["reply_text"],
            "actions": response["actions"],
            "read_aloud": False,  # Main PC can show text instead
            "timestamp": None
        }
    
    @staticmethod
    def format_for_remote_playback(
        response: dict,
        device_id: str | None = None
    ) -> dict:
        """Format response for remote device audio playback."""
        
        return {
            "audio_script": response["audio_script"],
            "device_id": device_id,
            "text_fallback": response["reply_text"],
            "playback_mode": "immediate" if len(response["audio_script"]) < 200 else "stream",
            "tts_config": {
                "voice": "default",
                "speed": 1.0,
                "volume": 0.8
            }
        }
```

---

## Testing Phase 1

**File**: `tests/test_llm_service.py` (NEW)

```python
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from finance_app.services.llm_service import LLMService, VoiceSession, LLMResponse
from finance_app.services.ollama_client import OllamaClient, OllamaMessage


@pytest.mark.asyncio
async def test_llm_service_creates_session_for_local():
    """Test that local voice gets 'local' session ID."""
    
    mock_repo = Mock()
    mock_repo.snapshot.return_value = Mock(
        income_total=5000, expense_total=2000, net_total=3000
    )
    
    service = LLMService(mock_repo)
    
    session = await service._get_or_create_session("local", device_id=None)
    
    assert session.session_id == "local"
    assert session.source_device_id is None
    assert not session.is_remote


@pytest.mark.asyncio
async def test_llm_service_creates_session_for_remote():
    """Test that remote voice gets device-specific session ID."""
    
    mock_repo = Mock()
    mock_repo.snapshot.return_value = Mock()
    
    service = LLMService(mock_repo)
    
    session = await service._get_or_create_session("remote:kitchen", device_id="kitchen")
    
    assert session.session_id == "remote:kitchen"
    assert session.source_device_id == "kitchen"
    assert session.is_remote


@pytest.mark.asyncio
async def test_llm_service_isolates_conversation_history():
    """Test that sessions have independent conversation histories."""
    
    mock_repo = Mock()
    mock_repo.snapshot.return_value = Mock()
    
    service = LLMService(mock_repo)
    
    # Add messages to different sessions
    await service._add_to_history("local", "user", "what's my budget")
    await service._add_to_history("remote:kitchen", "user", "what's my budget")
    
    local_session = service._sessions["local"]
    remote_session = service._sessions["remote:kitchen"]
    
    assert len(local_session.conversation_history) == 1
    assert len(remote_session.conversation_history) == 1
    assert local_session.conversation_history is not remote_session.conversation_history


def test_response_formatter_converts_dollars():
    """Test that $150 becomes 'one fifty dollars' in audio script."""
    
    from finance_app.services.response_formatter import ResponseFormatter
    
    text = "You spent $150 on groceries and $25 on coffee."
    audio = ResponseFormatter.generate_audio_script(text)
    
    assert "150 dollars" in audio
    assert "25 dollars" in audio
    assert "$" not in audio


def test_response_formatter_removes_markdown():
    """Test that markdown formatting is removed."""
    
    from finance_app.services.response_formatter import ResponseFormatter
    
    text = "**Bold** and *italic* text with `code`."
    audio = ResponseFormatter.generate_audio_script(text)
    
    assert "**" not in audio
    assert "*" not in audio
    assert "`" not in audio
    assert "Bold" in audio


def test_llm_response_from_assistant_result():
    """Test conversion from existing AssistantResult format."""
    
    # Mock existing result format
    mock_result = Mock()
    mock_result.payload = {
        "reply": "Your budget is $3000",
        "actions": [{"type": "show_table", "payload": {}}]
    }
    
    response = LLMResponse.from_assistant_result(mock_result, "kitchen")
    
    assert response.reply_text == "Your budget is $3000"
    assert len(response.actions) == 1
    assert response.remote_device_id == "kitchen"
    assert "dollars" in response.audio_script.lower()
```

---

## Integration Points with Existing Code

### Current Voice Flow

```
RemoteStreamSource (receives audio)
  → RemoteAudioServer
    → RemoteStreamSource.start(on_audio_chunk)
      → AsrRouter.process_audio(source_id, bytes)
        → Vosk/Whisper ASR
          → WakeWordCommandRouter.process_text()
            → on_command callback
              → VoiceCoordinator.execute_command()
                → Currently calls AssistantService directly
                → CHANGE THIS: Call LLMService instead
```

### Refactoring Required

**File**: `finance_app/ui/main_window.py` or equivalent coordinator

```python
# BEFORE:
async def execute_command(self, command_text, source_id):
    result = self.assistant_service.handle_prompt(command_text)
    self.display_result(result)

# AFTER:
async def execute_command(self, command_text, source_id):
    response = await self.llm_service.process_voice_command(
        session_id="remote:{}".format(source_id) if source_id else "local",
        text=command_text,
        source_type="remote_voice" if source_id else "local_voice",
        device_id=source_id
    )
    await self.handle_llm_response(response)
```

---

## Checkpoint: Phase 1 Complete

✓ LLMService created and can handle local + remote voice  
✓ SessionManager built into LLMService  
✓ ResponseFormatter handles multi-channel output  
✓ Voice pipeline updated to use new service  
✓ Backward compatibility maintained with AssistantService  
✓ Tests verify session isolation and response formatting  

**Next**: Phase 2 - Add request queueing and prioritization

---

## Common Gotchas

### 1. Async/Await in Existing Code
The current code may use threading instead of asyncio. Gradually migrate to async, or use `asyncio.run()` to bridge:

```python
# Bridge existing sync code to async
import asyncio

result = asyncio.run(
    llm_service.process_voice_command(...)
)
```

### 2. Session Timeout for Remote Devices
Remote device sessions should timeout after 5 minutes of inactivity:

```python
# In periodic cleanup loop
async def cleanup_expired_sessions():
    async with self._session_lock:
        now = datetime.now()
        expired = [
            sid for sid, session in self._sessions.items()
            if session.is_expired() and sid != "local"
        ]
        for sid in expired:
            del self._sessions[sid]
```

### 3. Financial Context Freshness
Cache financial snapshot but refresh if stale:

```python
# In process_voice_command
if (datetime.now() - session.created_at).total_seconds() > 300:
    session.cached_financial_snapshot = self.repository.snapshot()
```

---

## Files to Create/Modify Summary

### NEW files (create):
- `finance_app/services/llm_service.py` - Core service
- `finance_app/services/response_formatter.py` - Multi-channel responses
- `tests/test_llm_service.py` - Unit tests

### MODIFY (minimal changes):
- `finance_app/ui/main_window.py` - Update voice coordinator
- `finance_app/services/assistant_service.py` - Add compatibility note

### UNCHANGED (leverage existing):
- `finance_app/services/ollama_client.py`
- `finance_app/services/voice_pipeline.py`
- `finance_app/services/voice/remote_stream_source.py`
- `finance_app/storage.py`

---

This implementation guide takes the high-level architecture from the main document and gives you concrete, executable steps to integrate it with your existing codebase. Start with Phase 1, get it working end-to-end, then proceed to queueing, error handling, and agents.
