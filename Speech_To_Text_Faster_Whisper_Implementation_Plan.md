# Speech-to-Text Faster-Whisper Implementation Plan

## Objective
Upgrade the current voice pipeline from basic wake + Vosk transcription to a more robust, modern speech experience with:
- Better recognition quality in normal speech
- Reduced early cut-offs
- Better performance in background noise
- Clear fallback behavior when higher-quality decode is unavailable

This plan is designed for the current codebase structure and controller boundaries.

## Current State (Codebase Snapshot)
- Voice routing and mic capture are in `finance_app/services/voice_pipeline.py`
- Voice UI actions and status handling are in `finance_app/ui/main_window.py`
- Voice command text is forwarded into the existing assistant flow (same path as typed prompts)
- Current dependencies include `vosk` and `sounddevice` in `requirements.txt`

## Target Architecture

### New service modules to add
- `finance_app/services/voice/stream_source.py`
  - Owns microphone stream capture and chunk buffering
- `finance_app/services/voice/vad_endpointing.py`
  - Voice activity detection and end-of-utterance logic
- `finance_app/services/voice/asr_provider.py`
  - Shared provider interfaces/types
- `finance_app/services/voice/asr_vosk.py`
  - Existing Vosk decode wrapped behind provider interface
- `finance_app/services/voice/asr_faster_whisper.py`
  - Faster-Whisper provider implementation
- `finance_app/services/voice/asr_router.py`
  - Chooses model/provider and fallback path
- `finance_app/services/voice/session_state.py`
  - Wake/session state machine (idle -> wake -> capture -> decode -> dispatch)
- `finance_app/services/voice/postprocess.py`
  - Finance-aware text normalization and correction

### Existing modules to update
- `finance_app/services/voice_pipeline.py`
  - Convert to coordinator/facade that composes new voice modules
- `finance_app/ui/main_window.py`
  - Keep callback wiring, add richer voice states and transcript UX
- `requirements.txt`
  - Add Faster-Whisper dependencies and optional acceleration extras
- `README.md`
  - Add setup section for Faster-Whisper models and runtime behavior

## Dependency and Runtime Setup Plan

### Required dependencies
Add these to `requirements.txt`:
- `faster-whisper>=1.0.0`
- `ctranslate2>=4.4.0`
- `onnxruntime>=1.18.0` (optional for VAD/noise components if selected)
- Keep existing:
  - `sounddevice>=0.4.6`
  - `vosk>=0.3.45`

### Recommended optional dependencies
- `openwakeword` for stronger wake detection
- `webrtcvad` or `silero-vad` for endpointing
- `noisereduce` or RNNoise wrapper for noise suppression

### Model strategy
Start with one local model and one fallback:
- Primary: Faster-Whisper `small.en` (good quality/perf balance)
- Optional upgrade: `medium.en` for better accuracy
- Fallback: existing Vosk model already used by app

### Suggested model config settings
Create app settings (through existing settings controller path):
- `voice_asr_primary`: `faster_whisper`
- `voice_asr_fallback`: `vosk`
- `voice_fw_model_size`: `small.en`
- `voice_fw_compute_type`: `int8` (CPU-friendly)
- `voice_endpoint_silence_ms`: `700`
- `voice_max_utterance_ms`: `12000`
- `voice_min_utterance_ms`: `600`

## Phased Implementation Tasks

## Phase 1: Introduce ASR abstraction and Faster-Whisper provider

### Tasks
1. Add `asr_provider.py` interface with:
- `transcribe_pcm16(audio_bytes, sample_rate) -> AsrResult`
- `AsrResult(text, confidence, latency_ms, provider, is_final)`

2. Extract current Vosk behavior into `asr_vosk.py`
- Keep existing logic, only move behind interface

3. Implement `asr_faster_whisper.py`
- Load model lazily on first call
- Configure with app settings (model size, compute type)
- Return standardized `AsrResult`

4. Add `asr_router.py`
- Primary decode on Faster-Whisper
- Fallback to Vosk on failure or low confidence

### Exit criteria
- Voice pipeline can run with either provider selected
- No UI behavior regression

## Phase 2: Replace fixed timeout with VAD-based endpointing

### Tasks
1. Add `vad_endpointing.py`
- Speech start detection
- Trailing silence end detection
- Minimum speech duration guard
- Max utterance duration guard

2. Integrate VAD into coordinator flow
- Buffer audio while speech is active
- Finalize utterance only when endpointing says complete

3. Keep wake timeout only as a safety net
- Remove it as the primary stop condition

### Exit criteria
- Reduced early termination in conversational commands
- Wake -> command flow remains responsive

## Phase 3: Session state machine and wake robustness

### Tasks
1. Add `session_state.py` explicit states:
- `IDLE`
- `WAKE_DETECTED`
- `CAPTURING`
- `DECODING`
- `DISPATCHING`
- `ERROR`

2. Optional wake upgrade:
- Add dedicated wake detector provider (OpenWakeWord) behind interface
- Keep phrase-based fallback for compatibility

3. Add pre-roll buffer (about 500 ms)
- Avoid clipping words spoken immediately after wake

### Exit criteria
- Lower false timeout and clipped-first-word issues
- Deterministic logs for state transitions

## Phase 4: Post-processing and command normalization

### Tasks
1. Add `postprocess.py`
- Normalize currency terms ("forty five dollars" -> 45.00 where context allows)
- Fix known category aliases (for example groceries/grocery)
- Light punctuation cleanup and trimming

2. Apply correction pass before assistant dispatch
- Keep original transcript for audit/debug display

3. Add low-confidence confirmation hook
- If confidence below threshold, prompt user in UI before sending

### Exit criteria
- Improved intent stability for finance commands
- Fewer assistant misfires from transcript noise

## Phase 5: UX and observability updates

### Tasks
1. Update Assistant tab voice section in `main_window.py`
- Show states clearly (idle/listening/processing/error)
- Show partial transcript + final transcript
- Add retry last utterance action

2. Add structured voice telemetry events
- wake detected
- endpoint reason
- ASR provider used
- confidence score
- fallback triggered
- total latency

3. Add lightweight debug log file
- Store recent session voice events for troubleshooting

### Exit criteria
- User can understand what happened when voice fails
- Metrics available for iterative tuning

## Testing Plan

### Unit tests to add
- `tests/test_voice_asr_router.py`
  - primary/fallback routing behavior
- `tests/test_voice_endpointing.py`
  - silence thresholds and endpoint decisions
- `tests/test_voice_session_state.py`
  - valid/invalid state transitions
- `tests/test_voice_postprocess.py`
  - finance normalization rules

### Integration tests to add
- `tests/test_voice_pipeline_integration.py`
  - wake -> utterance -> assistant dispatch path
  - fallback behavior under forced primary failure

### Manual QA checklist
- Quiet room dictation
- TV/background noise
- Fan/white noise
- Fast speech and short commands
- Long command with pauses
- Immediate command after wake phrase

## Rollout and Risk Control

### Safe rollout sequence
1. Ship ASR provider abstraction + Vosk adapter only
2. Add Faster-Whisper provider behind setting flag (default off)
3. Enable Faster-Whisper for local testing
4. Enable by default once confidence/latency targets are met

### Feature flags to use
- `voice_enable_faster_whisper`
- `voice_enable_vad_endpointing`
- `voice_enable_wake_model`
- `voice_enable_postprocess`

### Rollback plan
- If quality/performance regresses, switch `voice_asr_primary` back to `vosk`
- Keep Vosk path intact until Phase 5 completion

## Suggested Performance Targets
- Median decode latency (local CPU): under 1200 ms per command
- Command cutoff rate: under 2%
- Wake false positives: less than 1 per hour in normal room noise
- Fallback rate: under 20% after tuning

## Immediate Next 10 Implementation Tasks
1. Add voice settings keys in config and settings persistence path
2. Create `finance_app/services/voice/` package and interfaces
3. Move Vosk decode logic from `voice_pipeline.py` into `asr_vosk.py`
4. Add Faster-Whisper provider and lazy model loading
5. Add ASR router with confidence threshold fallback logic
6. Add VAD endpointing module and integrate utterance boundaries
7. Add state machine module and replace implicit boolean arming
8. Update `main_window.py` voice status UI for state + transcript
9. Add unit tests for router/endpointing/state/postprocess
10. Update README setup and troubleshooting sections

## Notes
- Keep compatibility with existing controller boundaries and architecture tests.
- Avoid direct repository calls from UI code during voice updates.
- Preserve current typed assistant behavior as baseline while upgrading voice path.
