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
    budget_min: Optional[int] = None
    furnished: Optional[bool] = None
    pet: Optional[bool] = None
    urgency: Optional[str] = None
    financing: Optional[bool] = None
    suites: Optional[bool] = None
    timeline: Optional[str] = None


@dataclass
class SessionState:
    session_id: str
    intent: Optional[str] = None  # comprar, alugar, investir, pesquisar, suporte, humano
    stage: str = "inicio"
    criteria: LeadCriteria = field(default_factory=LeadCriteria)
    criteria_status: Dict[str, str] = field(default_factory=dict)  # confirmed|inferred
    triage_fields: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # value + status
    asked_questions: List[str] = field(default_factory=list)
    last_question_key: Optional[str] = None
    completed: bool = False
    fallback_reason: Optional[str] = None
    last_suggestions: List[str] = field(default_factory=list)
    human_handoff: bool = False
    schedule_requests: List[Dict[str, Any]] = field(default_factory=list)
    lead_name: Optional[str] = None
    history: List[Dict[str, str]] = field(default_factory=list)

    def set_criterion(self, key: str, value: Any, status: str = "confirmed") -> None:
        """
        Define um critério com status explícito.
        
        Args:
            key: Nome do critério
            value: Valor do critério
            status: "confirmed" (dito pelo usuário) ou "inferred" (assumido pela IA)
        """
        if hasattr(self.criteria, key) and value is not None:
            setattr(self.criteria, key, value)
            self.criteria_status[key] = status
        # Mantém registro unificado em triage_fields
        self.triage_fields[key] = {"value": value, "status": status}

    def get_criterion(self, key: str) -> Any:
        return getattr(self.criteria, key, None)
    
    def get_criterion_status(self, key: str) -> Optional[str]:
        """Retorna o status de um critério: confirmed, inferred ou None"""
        return self.criteria_status.get(key)
    
    def get_confirmed_criteria(self) -> Dict[str, Any]:
        """
        Retorna apenas critérios CONFIRMADOS (explicitamente ditos pelo usuário).
        Use isso para decisões críticas de negócio.
        """
        confirmed = {}
        for key, status in self.criteria_status.items():
            if status == "confirmed":
                value = self.get_criterion(key)
                if value is not None:
                    confirmed[key] = value
        return confirmed
    
    def get_inferred_criteria(self) -> Dict[str, Any]:
        """
        Retorna apenas critérios INFERIDOS (assumidos pela IA).
        Use para sugestões, não para decisões finais.
        """
        inferred = {}
        for key, status in self.criteria_status.items():
            if status == "inferred":
                value = self.get_criterion(key)
                if value is not None:
                    inferred[key] = value
        return inferred

    def set_triage_field(self, key: str, value: Any, status: str = "confirmed") -> None:
        """Armazena qualquer campo de triagem (crítico ou preferencial)."""
        if value is None:
            return
        self.triage_fields[key] = {"value": value, "status": status}
        # Se campo crítico mapeia para criteria, atualiza também
        if hasattr(self.criteria, key):
            setattr(self.criteria, key, value)
            self.criteria_status[key] = status

    def apply_updates(self, updates: Dict[str, Any]) -> tuple[List[str], Dict[str, Dict[str, Any]]]:
        """
        Aplica updates extraídos ao estado, retornando conflitos e seus valores.

        Args:
            updates: Dicionário de updates {field: {value, status} ou value}

        Returns:
            Tupla (conflicts, conflict_values) onde:
            - conflicts: Lista de campos com conflito
            - conflict_values: Dict com {field: {previous, new}}
        """
        conflicts: List[str] = []
        conflict_values: Dict[str, Dict[str, Any]] = {}

        for key, payload in (updates or {}).items():
            if payload is None:
                continue
            value = payload.get("value") if isinstance(payload, dict) else payload
            status = payload.get("status", "confirmed") if isinstance(payload, dict) else "confirmed"

            # Intent pode vir separada
            if key == "intent":
                if self.intent and value and self.intent != value and self.intent in {"comprar", "alugar"}:
                    conflicts.append("intent")
                    conflict_values["intent"] = {"previous": self.intent, "new": value}
                elif value:
                    self.intent = value
                continue

            prev = self.triage_fields.get(key, {})
            prev_val = prev.get("value")
            prev_status = prev.get("status")

            if prev_status == "confirmed" and value is not None and prev_val not in (None, value):
                conflicts.append(key)
                conflict_values[key] = {"previous": prev_val, "new": value}
                continue  # não sobrescreve; precisa clarificar

            self.set_triage_field(key, value, status=status)

        return conflicts, conflict_values

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "intent": self.intent,
            "stage": self.stage,
            "criteria": self.criteria.__dict__,
            "criteria_status": self.criteria_status,
            "triage_fields": self.triage_fields,
            "asked_questions": self.asked_questions,
            "last_question_key": self.last_question_key,
            "completed": self.completed,
            "confirmed_criteria": self.get_confirmed_criteria(),
            "inferred_criteria": self.get_inferred_criteria(),
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
