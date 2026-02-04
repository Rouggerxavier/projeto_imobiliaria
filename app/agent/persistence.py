from __future__ import annotations
import json
import os
import threading
import time
import unicodedata
from typing import Dict, Any

LEADS_PATH = os.getenv("LEADS_LOG_PATH") or (
    "/mnt/data/leads.jsonl" if os.path.exists("/mnt/data") else "data/leads.jsonl"
)
LEADS_INDEX_PATH = os.getenv("LEADS_INDEX_PATH") or (
    "/mnt/data/leads_index.json" if os.path.exists("/mnt/data") else "data/leads_index.json"
)
EVENTS_PATH = os.getenv("EVENTS_PATH") or (
    "/mnt/data/events.jsonl" if os.path.exists("/mnt/data") else "data/events.jsonl"
)
PERSIST_RAW_TEXT = os.getenv("PERSIST_RAW_TEXT", "false").lower() in ("true", "1", "yes")
_lock = threading.Lock()
_index_lock = threading.Lock()


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
        "intent_stage": getattr(state, "intent_stage", "unknown"),
        "completed": state.completed,
    }
    append_lead_line(payload)


def _normalize_name(name: str) -> str:
    txt = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return txt.strip().lower()


def _strip_raw_text(data: Dict[str, Any]) -> Dict[str, Any]:
    if PERSIST_RAW_TEXT:
        return data
    cleaned = json.loads(json.dumps(data))  # deep copy
    triage = cleaned.get("triage_fields", {})
    for field in triage.values():
        if isinstance(field, dict) and "raw_text" in field:
            field.pop("raw_text", None)
    return cleaned


def append_lead(payload: Dict[str, Any], path: str | None = None) -> None:
    cleaned = _strip_raw_text(payload)
    append_lead_line(cleaned, path)


def update_lead_index(name: str, lead_id: str, path: str | None = None) -> None:
    target = path or LEADS_INDEX_PATH
    _ensure_dir(target)
    key = _normalize_name(name)
    with _index_lock:
        data = {}
        if os.path.exists(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        if key not in data:
            data[key] = []
        if lead_id not in data[key]:
            data[key].append(lead_id)
        temp = target + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if os.path.exists(target):
            os.replace(temp, target)
        else:
            os.rename(temp, target)


def append_event(event: Dict[str, Any], path: str | None = None) -> None:
    target = path or EVENTS_PATH
    _ensure_dir(target)
    with _lock:
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
