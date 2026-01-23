from __future__ import annotations
import re
import unicodedata
from typing import Dict, Iterable, Optional, Set


def _strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


PROPERTY_TYPES = {
    "apartamento": ["apto", "ape", "apartamento", "ap"],
    "casa": ["casa", "sobrado"],
    "cobertura": ["cobertura"],
    "studio": ["studio", "st"],
    "flat": ["flat"],
    "kitnet": ["kitnet", "kitinete", "kit"],
    "terreno": ["terreno", "lote"],
}

CITY_ALIASES = {
    "joao pessoa": "Joao Pessoa",
    "campina grande": "Campina Grande",
    "recife": "Recife",
    "natal": "Natal",
    "cabedelo": "Cabedelo",
}


def _parse_currency(fragment: str, suffix: Optional[str]) -> int:
    fragment = fragment.replace(".", "").replace(",", ".")
    try:
        base = float(fragment)
    except ValueError:
        return 0
    mult = 1
    if suffix:
        suf = suffix.lower()
        if suf in {"mi", "milhao", "milhoes", "m"}:
            mult = 1_000_000
        elif suf in {"mil", "k"}:
            mult = 1_000
    return int(base * mult)


def extract_budget(text: str) -> Optional[int]:
    patterns = [
        r"(?:ate|ate|teto|maximo|max|orcamento|budget|limite|por mes|mensal)[^\d]{0,10}(\d+[\.,]?\d*)\s*(mi|milhao|milhoes|mil|k|mi|m)?",
        r"r\$\s*(\d+[\.,]?\d*)\s*(mi|milhao|milhoes|mil|k|mi|m)?",
    ]
    lowered = _strip_accents(text.lower())
    for pattern in patterns:
        m = re.search(pattern, lowered, re.IGNORECASE)
        if m:
            value = _parse_currency(m.group(1), m.group(2))
            return value if value > 0 else None
    generic = re.search(r"(\d+[\.,]?\d*)\s*(mil|mi|milhao|milhoes|k)", lowered)
    if generic:
        val = _parse_currency(generic.group(1), generic.group(2))
        return val if val > 0 else None
    return None


def extract_number(text: str, pattern: str) -> Optional[int]:
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def detect_type(text: str) -> Optional[str]:
    lowered = _strip_accents(text.lower())
    for canonical, aliases in PROPERTY_TYPES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}s?\b", lowered):
                return canonical
    if "qualquer" in lowered or "tanto faz" in lowered:
        return "qualquer"
    return None


def detect_city(text: str) -> Optional[str]:
    normalized = _strip_accents(text.lower())
    for alias, canonical in CITY_ALIASES.items():
        if alias in normalized:
            return canonical
    return None


def detect_neighborhood(text: str, known: Iterable[str]) -> Optional[str]:
    normalized = _strip_accents(text.lower())
    for bairro in known:
        if bairro and _strip_accents(bairro.lower()) in normalized:
            return bairro
    return None


def extract_boolean(text: str, keywords_true: Set[str], keywords_false: Set[str]) -> Optional[bool]:
    lowered = _strip_accents(text.lower())
    if any(k in lowered for k in keywords_true):
        return True
    if any(k in lowered for k in keywords_false):
        return False
    return None


def extract_criteria(message: str, known_neighborhoods: Iterable[str]) -> Dict[str, object]:
    text = message
    result: Dict[str, object] = {}

    city = detect_city(text)
    if city:
        result["city"] = city
    neighborhood = detect_neighborhood(text, known_neighborhoods)
    if neighborhood:
        result["neighborhood"] = neighborhood

    prop_type = detect_type(text)
    if prop_type:
        result["property_type"] = prop_type

    lowered = _strip_accents(text.lower())
    bedrooms = extract_number(lowered, r"(\d+)\s*(quarto|qtos|dorm|q\b|qts)")
    if bedrooms:
        result["bedrooms"] = bedrooms
    parking = extract_number(lowered, r"(\d+)\s*(vaga|vagas)")
    if parking is not None:
        result["parking"] = parking

    budget = extract_budget(message)
    if budget:
        result["budget"] = budget

    pet = extract_boolean(text, {"pet", "cachorro", "gato", "aceita pet", "pet friendly"}, {"nao aceita pet", "sem pet"})
    if pet is not None:
        result["pet"] = pet

    furnished = extract_boolean(text, {"mobiliado", "mobiliada", "moveis", "mobilia"}, {"sem mobilia", "nao mobiliado"})
    if furnished is not None:
        result["furnished"] = furnished

    urgency = None
    if any(k in lowered for k in ["urgente", "hoje", "agora", "esse mes", "o quanto antes"]):
        urgency = "alta"
    elif any(k in lowered for k in ["proximo mes", "duas semanas", "em breve"]):
        urgency = "media"
    if urgency:
        result["urgency"] = urgency

    return result
