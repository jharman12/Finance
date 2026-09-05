"""Run unittest modules quietly and write a compact summary to _testsummary.txt.

Vosk logs from native code flood the console, so the summary is written to a file.
"""
from __future__ import annotations

import io
import os
import pathlib
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The small model loads far faster; UI tests never exercise real recognition.
if not os.getenv("FINANCE_APP_VOSK_MODEL_PATH"):
    small_model = ROOT / "models" / "vosk-model-small-en-us-0.15"
    if small_model.exists():
        os.environ["FINANCE_APP_VOSK_MODEL_PATH"] = str(small_model)

modules = sys.argv[1:]
suite = unittest.TestLoader().loadTestsFromNames(modules)
result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)

lines = [
    f"stamp={time.strftime('%H:%M:%S')}",
    f"modules={','.join(modules)}",
    f"run={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}",
    f"ok={result.wasSuccessful()}",
]
for test, trace in list(result.failures) + list(result.errors):
    lines.append(f"--- {test}")
    lines.append(trace)

(ROOT / "_testsummary.txt").write_text("\n".join(lines), encoding="utf-8")
