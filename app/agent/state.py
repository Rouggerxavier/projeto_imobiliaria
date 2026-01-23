from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class LeadCriteria:
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    parking: Optional[int] = None
    budget: Optional[int] = None
    furnished: Optional[bool] = None
    pet: Optional[bool] = None
    urgency: Optional[str] = None
    financing: Optional[bool] = None


@dataclass
class SessionState:
    session_id: str
    intent: Optional[str] = None  # comprar, alugar, investir, pesquisar, suporte, humano
    stage: str = "inicio"
    criteria: LeadCriteria = field(default_factory=LeadCriteria)
    criteria_status: Dict[str, str] = field(default_factory=dict)  # confirmed|inferred
    last_suggestions: List[str] = field(default_factory=list)
    human_handoff: bool = False
    schedule_requests: List[Dict[str, Any]] = field(default_factory=list)
    lead_name: Optional[str] = None
    history: List[Dict[str, str]] = field(default_factory=list)

    def set_criterion(self, key: str, value: Any, status: str = "confirmed") -> None:
        if hasattr(self.criteria, key) and value is not None:
            setattr(self.criteria, key, value)
            self.criteria_status[key] = status

    def get_criterion(self, key: str) -> Any:
        return getattr(self.criteria, key, None)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "intent": self.intent,
            "stage": self.stage,
            "criteria": self.criteria.__dict__,
            "criteria_status": self.criteria_status,
            "last_suggestions": self.last_suggestions,
            "human_handoff": self.human_handoff,
        }


class InMemoryStore:
    def __init__(self) -> None:
        self._store: Dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._store:
            self._store[session_id] = SessionState(session_id=session_id)
        return self._store[session_id]

    def save(self, state: SessionState) -> None:
        self._store[state.session_id] = state

    def reset(self, session_id: str) -> None:
        if session_id in self._store:
            del self._store[session_id]


store = InMemoryStore()
