# Finance Assistant

This repository now contains a working scaffold for a local-first personal finance app built with PyQt5.

The structure is designed around three core pieces:

- a polished desktop UI for tracking income, expenses, and recent activity
- a local SQLite ledger that persists data as soon as entries are added
- an Ollama-backed assistant layer that can answer questions and apply structured changes to the app

## What is included

- Overview dashboard with summary cards and recent activity
- Ledger tab for browsing all transactions
- Recurring tab for scheduling repeating expenses and income entries
- Assistant tab that talks to a locally running Ollama model
- Voice trigger mode in Assistant tab (wake phrase: "Hey Steven")
- Automatic Ollama startup attempt if the service is not already running
- Seeded finance categories and local SQLite storage

## Project layout

- `main.py` starts the desktop app
- `finance_app/config.py` stores app configuration and prompts
- `finance_app/storage.py` owns the SQLite schema and persistence logic
- `finance_app/services/ollama_client.py` talks to Ollama and starts it when needed
- `finance_app/services/assistant_service.py` turns model responses into app actions
- `finance_app/ui/main_window.py` contains the PyQt5 interface

## Run it

1. Create and activate a Python environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Make sure Ollama is installed locally.
4. Start the app with `python main.py`.

## Voice setup (USB mic test)

The app now supports wake-word style testing on your local USB microphone.
Voice command transcription defaults to Faster-Whisper with automatic Vosk fallback.

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Download a Vosk speech model

- Download an English model such as: `vosk-model-en-us-0.22-lgraph`
- Put it in this project under:
	- `models/vosk-model-en-us-0.22-lgraph`

Or set a custom path with:

```bash
set FINANCE_APP_VOSK_MODEL_PATH=C:\path\to\vosk-model-en-us-0.22-lgraph
```

### 2b) Faster-Whisper defaults and options

The app uses these defaults for command transcription:

- Primary ASR: Faster-Whisper (`small.en`)
- Fallback ASR: Vosk
- Endpointing: energy-based silence detection (prevents fixed-timeout cutoffs)

Optional environment overrides:

```bash
set FINANCE_APP_VOICE_ASR_PRIMARY=faster_whisper
set FINANCE_APP_FW_MODEL_SIZE=small.en
set FINANCE_APP_FW_DEVICE=cpu
set FINANCE_APP_FW_COMPUTE_TYPE=int8
set FINANCE_APP_FW_CPU_THREADS=4
set FINANCE_APP_VOICE_ENDPOINT_SILENCE_MS=700
set FINANCE_APP_VOICE_MIN_UTTERANCE_MS=300
set FINANCE_APP_VOICE_MAX_UTTERANCE_MS=12000
set FINANCE_APP_VOICE_ENERGY_THRESHOLD=450
set FINANCE_APP_VOICE_COOLDOWN_SECONDS=0.7
set FINANCE_APP_VOICE_CONTINUATION_SECONDS=0.7
set FINANCE_APP_VOICE_PARTIAL_INTERVAL_SECONDS=0.2
```

Wake detection modes:

```bash
set FINANCE_APP_WAKE_MODE=phrase_vosk
```

Optional dedicated wake model (if installed):

```bash
set FINANCE_APP_WAKE_MODE=openwakeword
set FINANCE_APP_WAKE_THRESHOLD=0.5
set FINANCE_APP_OPENWAKEWORD_MODEL_PATH=C:\path\to\hey_steven.onnx
```

Important: `openwakeword` does not automatically know the phrase `Hey Steven`.
You must provide a dedicated custom wake model for that exact phrase.
If you do not have a custom model, keep `FINANCE_APP_WAKE_MODE=phrase_vosk`.

Voice telemetry (JSONL) is written by default to:

`logs/voice_events.jsonl`

Override path:

```bash
set FINANCE_APP_VOICE_TELEMETRY_PATH=C:\path\to\voice_events.jsonl
```

To force legacy Vosk-first transcription:

```bash
set FINANCE_APP_VOICE_ASR_PRIMARY=vosk
```

### 3) Start voice mode in the app

1. Open the **Assistant** tab
2. Click **Start Voice (Hey Steven)**
3. Say: **"Hey Steven"** then your command
	 - Example: "Hey Steven, analyze where I can cut spending this month"

The Assistant tab now includes a **Voice Diagnostics** panel that shows live stage/provider/confidence/latency/fallback/endpoint details for tuning.

The recognized command is sent through the same assistant workflow used by typed prompts, so actions and updates work the same way.

### Troubleshooting

- If you see "Voice dependencies missing", install `vosk` and `sounddevice`.
- If Faster-Whisper import fails, install `faster-whisper`, `ctranslate2`, and `numpy`.
- If openWakeWord import fails, install `openwakeword` or switch to `FINANCE_APP_WAKE_MODE=phrase_vosk`.
- If `openwakeword` mode never triggers, verify `FINANCE_APP_OPENWAKEWORD_MODEL_PATH` points to a custom `Hey Steven` wake model. Otherwise use `phrase_vosk`.
- If you see "Vosk model not found", check `FINANCE_APP_VOSK_MODEL_PATH` or the `models/...` folder.
- If your wrong mic is used, set your USB mic as the OS default input device.

## Notes

- The assistant currently expects structured JSON responses so it can safely apply edits to the ledger.
- Recurring items are stored locally and posted into the transaction ledger when their due date arrives.
- The architecture is intentionally modular so budgeting, recurring bills, reports, and richer assistant actions can be added without rewriting the app.
- Voice pipeline is modular: remote Alexa-like nodes can later send transcripts into the same coordinator without changing assistant logic.