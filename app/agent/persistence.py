from __future__ import annotations
import json
import os
import threading
import time
from typing import Dict, Any

LEADS_PATH = os.getenv("LEADS_LOG_PATH") or (
    "/mnt/data/leads.jsonl" if os.path.exists("/mnt/data") else "data/leads.jsonl"
)
_lock = threading.Lock()


def _ensure_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def append_lead_line(payload: Dict[str, Any], path: str | None = None) -> None:
    target = path or LEADS_PATH
    _ensure_dir(target)
    line = json.dumps(payload, ensure_ascii=False)
    with _lock:
        with open(target, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def persist_state(state) -> None:
    payload = {
        "timestamp": time.time(),
        "session_id": state.session_id,
        "lead_profile": state.lead_profile,
        "triage_fields": state.triage_fields,
        "lead_score": state.lead_score.__dict__,
        "completed": state.completed,
    }
    append_lead_line(payload)
