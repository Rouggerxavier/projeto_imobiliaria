from __future__ import annotations
from typing import Dict, List, Optional
from .state import SessionState


def has_location(state: SessionState) -> bool:
    return bool(state.criteria.neighborhood or state.criteria.city)


def has_budget(state: SessionState) -> bool:
    return state.criteria.budget is not None and state.criteria.budget > 0


def has_type(state: SessionState) -> bool:
    return state.criteria.property_type is not None


def can_search_properties(state: SessionState) -> bool:
    if state.intent not in {"comprar", "alugar", "investir"}:
        return False
    if not has_location(state):
        return False
    if not has_budget(state):
        return False
    if not has_type(state):
        return False
    return True


def can_answer_about_property(data: Optional[Dict]) -> bool:
    return bool(data and data.get("id"))


def missing_critical_fields(state: SessionState) -> List[str]:
    order = ["location", "budget", "property_type"]
    missing: List[str] = []
    if not has_location(state):
        missing.append("location")
    if not has_budget(state):
        missing.append("budget")
    if not has_type(state):
        missing.append("property_type")
    return [f for f in order if f in missing]


QUESTION_BANK: Dict[str, str] = {
    "location": "Qual cidade ou bairro você prefere?",
    "budget": "Qual o orçamento máximo? (pode ser aproximado)",
    "property_type": "Prefere apartamento, casa, studio ou aceita qualquer tipo?",
}


def next_best_question(state: SessionState) -> Optional[str]:
    missing = missing_critical_fields(state)
    if not missing:
        return None
    return QUESTION_BANK.get(missing[0])
