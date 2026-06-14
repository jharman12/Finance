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

### 3) Start voice mode in the app

1. Open the **Assistant** tab
2. Click **Start Voice (Hey Steven)**
3. Say: **"Hey Steven"** then your command
	 - Example: "Hey Steven, analyze where I can cut spending this month"

The recognized command is sent through the same assistant workflow used by typed prompts, so actions and updates work the same way.

### Troubleshooting

- If you see "Voice dependencies missing", install `vosk` and `sounddevice`.
- If you see "Vosk model not found", check `FINANCE_APP_VOSK_MODEL_PATH` or the `models/...` folder.
- If your wrong mic is used, set your USB mic as the OS default input device.

## Notes

- The assistant currently expects structured JSON responses so it can safely apply edits to the ledger.
- Recurring items are stored locally and posted into the transaction ledger when their due date arrives.
- The architecture is intentionally modular so budgeting, recurring bills, reports, and richer assistant actions can be added without rewriting the app.
- Voice pipeline is modular: remote Alexa-like nodes can later send transcripts into the same coordinator without changing assistant logic.