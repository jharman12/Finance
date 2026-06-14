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

## Notes

- The assistant currently expects structured JSON responses so it can safely apply edits to the ledger.
- Recurring items are stored locally and posted into the transaction ledger when their due date arrives.
- The architecture is intentionally modular so budgeting, recurring bills, reports, and richer assistant actions can be added without rewriting the app.