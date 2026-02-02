from __future__ import annotations
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class LeadCriteria:
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    micro_location: Optional[str] = None  # beira-mar|1_quadra|2-3_quadras|>3_quadras|orla|null
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None  # mínimo
    suites: Optional[int] = None    # mínimo
    parking: Optional[int] = None   # mínimo
    budget: Optional[int] = None    # orçamento máximo (alias budget_max)
    budget_min: Optional[int] = None
    furnished: Optional[bool] = None
    pet: Optional[bool] = None
    urgency: Optional[str] = None
    financing: Optional[bool] = None
    timeline: Optional[str] = None   # 30d|3m|6m|12m|flexivel
    condo_max: Optional[int] = None
    floor_pref: Optional[str] = None
    sun_pref: Optional[str] = None
    view_pref: Optional[str] = None
    leisure_features: Optional[List[str]] = None

    @property
    def budget_max(self) -> Optional[int]:
        return self.budget

    @budget_max.setter
    def budget_max(self, value: Optional[int]) -> None:
        self.budget = value


@dataclass
class LeadScore:
    temperature: str = "cold"  # hot|warm|cold
    score: int = 0
    reasons: List[str] = field(default_factory=list)


@dataclass
class SessionState:
    session_id: str
    intent: Optional[str] = None  # comprar|alugar
    stage: str = "inicio"
    criteria: LeadCriteria = field(default_factory=LeadCriteria)
    criteria_status: Dict[str, str] = field(default_factory=dict)  # confirmed|inferred
    triage_fields: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # value|status|source|updated_at
    preferences: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    lead_profile: Dict[str, Any] = field(default_factory=lambda: {"name": None, "phone": None, "email": None})
    lead_score: LeadScore = field(default_factory=LeadScore)
    asked_questions: List[str] = field(default_factory=list)
    last_question_key: Optional[str] = None
    completed: bool = False
    fallback_reason: Optional[str] = None
    last_suggestions: List[str] = field(default_factory=list)
    human_handoff: bool = False
    schedule_requests: List[Dict[str, Any]] = field(default_factory=list)
    lead_name: Optional[str] = None
    history: List[Dict[str, str]] = field(default_factory=list)
    random_seed: Optional[int] = None

    # === Normalização helpers ===
    def _now(self) -> float:
        return time.time()

    def _normalize_numeric(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        try:
            txt = str(value).lower().strip()
            txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode("ascii")
            txt = txt.replace("r$", "").replace(" ", "")
            txt = txt.replace(".", "")
            if "milhao" in txt or "milhões" in txt or "milhoes" in txt or "mi" in txt:
                for token in ["milhao", "milhoes", "milhões", "mi"]:
                    txt = txt.replace(token, "")
                return int(float(txt.replace(",", ".")) * 1_000_000)
            if txt.endswith("k"):
                return int(float(txt[:-1].replace(",", ".")) * 1_000)
            if "mil" in txt:
                txt = txt.replace("mil", "")
                return int(float(txt.replace(",", ".")) * 1_000)
            return int(float(txt.replace(",", ".")))
        except Exception:
            return None

    def _normalize_timeline(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        lowered = str(value).lower()
        if "rapido" in lowered or "rápido" in lowered or "asap" in lowered or "o mais rapido" in lowered:
            return "3m"
        if "30" in lowered or "imedi" in lowered or "agora" in lowered:
            return "30d"
        if "3" in lowered and "mes" in lowered:
            return "3m"
        if "6" in lowered and "mes" in lowered:
            return "6m"
        if "12" in lowered or "ano" in lowered:
            return "12m"
        if "flex" in lowered or "sem pressa" in lowered:
            return "flexivel"
        return None

    def _normalize_micro_location(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        lowered = str(value).lower()
        if "beira" in lowered or "praia" in lowered:
            return "beira-mar (praia)"
        if "1" in lowered and "quadra" in lowered:
            return "1_quadra_da_praia"
        if ("2" in lowered or "3" in lowered) and "quadra" in lowered:
            return "2-3_quadras_da_praia"
        if "orla" in lowered or "praia" in lowered:
            return "orla (praia)"
        return value if isinstance(value, str) else str(value)

    def _normalize_boolean(self, value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        lowered = str(value).strip().lower()
        if lowered in {"sim", "s", "pode", "claro", "ok", "yes", "y", "positivo"}:
            return True
        if lowered in {"nao", "não", "n", "negativo", "nunca"}:
            return False
        return None

    def _apply_alias(self, key: str, value: Any) -> Tuple[str, Any]:
        alias = {
            "operation": ("intent", value),
            "budget_max": ("budget", value),
            "budget": ("budget", value),
            "budget_min": ("budget_min", value),
            "bedrooms_min": ("bedrooms", value),
            "suites_min": ("suites", value),
            "parking_min": ("parking", value),
            "timeline_bucket": ("timeline", value),
            "city_confirm": ("city", value),
        }
        return alias.get(key, (key, value))

    def _normalize_for_field(self, key: str, value: Any) -> Tuple[str, Any]:
        """Aplica alias e normalizações sem mutar estado."""
        key, value = self._apply_alias(key, value)
        if key in {"budget", "budget_min", "parking", "bedrooms", "suites", "condo_max"}:
            value = self._normalize_numeric(value)
        if key == "timeline":
            value = self._normalize_timeline(value) or value
        if key == "micro_location":
            value = self._normalize_micro_location(value)
        if key in {"furnished", "pet"}:
            bool_val = self._normalize_boolean(value)
            value = bool_val if bool_val is not None else value
        return key, value

    # === Mutators ===
    def set_criterion(self, key: str, value: Any, status: str = "confirmed", source: str = "user") -> None:
        if value is None:
            return
        key, value = self._apply_alias(key, value)

        if key in {"budget", "budget_min", "parking", "bedrooms", "suites", "condo_max"}:
            value = self._normalize_numeric(value)
        if key == "timeline":
            value = self._normalize_timeline(value) or value
        if key == "micro_location":
            value = self._normalize_micro_location(value)
        if key in {"furnished", "pet"}:
            bool_val = self._normalize_boolean(value)
            value = bool_val if bool_val is not None else value

        if hasattr(self.criteria, key) and value is not None:
            setattr(self.criteria, key, value)
            self.criteria_status[key] = status

        self.triage_fields[key] = {
            "value": value,
            "status": status,
            "source": source,
            "updated_at": self._now(),
        }

    def get_criterion(self, key: str) -> Any:
        return getattr(self.criteria, key, None)
    
    def get_criterion_status(self, key: str) -> Optional[str]:
        return self.criteria_status.get(key)
    
    def get_confirmed_criteria(self) -> Dict[str, Any]:
        confirmed = {}
        for key, status in self.criteria_status.items():
            if status == "confirmed":
                value = self.get_criterion(key)
                if value is not None:
                    confirmed[key] = value
        return confirmed
    
    def get_inferred_criteria(self) -> Dict[str, Any]:
        inferred = {}
        for key, status in self.criteria_status.items():
            if status == "inferred":
                value = self.get_criterion(key)
                if value is not None:
                    inferred[key] = value
        return inferred

    def set_triage_field(self, key: str, value: Any, status: str = "confirmed", source: str = "user") -> None:
        if value is None:
            return
        key, value = self._apply_alias(key, value)
        self.set_criterion(key, value, status=status, source=source)

    def apply_updates(self, updates: Dict[str, Any]) -> tuple[List[str], Dict[str, Dict[str, Any]]]:
        """
        Aplica updates extraídos ao estado, retornando conflitos e valores.
        Não sobrescreve campos confirmados.
        """
        conflicts: List[str] = []
        conflict_values: Dict[str, Dict[str, Any]] = {}

        for key, payload in (updates or {}).items():
            if payload is None:
                continue
            raw_value = payload.get("value") if isinstance(payload, dict) else payload
            status = payload.get("status", "confirmed") if isinstance(payload, dict) else "confirmed"
            source = payload.get("source", "llm") if isinstance(payload, dict) else "llm"

            if key in {"lead_name", "name"}:
                if raw_value and not self.lead_profile.get("name"):
                    self.lead_profile["name"] = raw_value
                continue
            if key in {"phone", "email"}:
                if raw_value:
                    self.lead_profile[key] = raw_value
                continue
            if key == "intent" or key == "operation":
                if status == "override" and raw_value:
                    self.intent = raw_value
                elif self.intent and raw_value and self.intent != raw_value and self.intent in {"comprar", "alugar"}:
                    conflicts.append("intent")
                    conflict_values["intent"] = {"previous": self.intent, "new": raw_value}
                elif raw_value:
                    self.intent = raw_value
                continue

            alias_key, norm_value = self._normalize_for_field(key, raw_value)
            prev = self.triage_fields.get(alias_key, {})
            prev_val = prev.get("value")
            prev_status = prev.get("status")

            if prev_status == "confirmed" and norm_value is not None and prev_val not in (None, norm_value):
                conflicts.append(alias_key)
                conflict_values[alias_key] = {"previous": prev_val, "new": norm_value}
                continue

            self.set_criterion(alias_key, norm_value, status=status, source=source)

        return conflicts, conflict_values

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "intent": self.intent,
            "stage": self.stage,
            "criteria": self.criteria.__dict__,
            "criteria_status": self.criteria_status,
            "triage_fields": self.triage_fields,
            "preferences": self.preferences,
            "constraints": self.constraints,
            "lead_profile": self.lead_profile,
            "lead_score": self.lead_score.__dict__,
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
