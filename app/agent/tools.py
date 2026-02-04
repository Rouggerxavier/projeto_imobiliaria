from __future__ import annotations
import json
import os
from typing import Any, Dict, List, Optional

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "properties.json")
EXPOSE_AGENT_CONTACT = os.getenv("EXPOSE_AGENT_CONTACT", "false").lower() in ("true", "1", "yes")


def load_properties() -> List[Dict[str, Any]]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


PROPERTIES_CACHE = load_properties()


def get_neighborhoods() -> List[str]:
    seen = set()
    for p in PROPERTIES_CACHE:
        bairro = p.get("bairro")
        if bairro:
            seen.add(bairro)
    return sorted(seen)


def get_property(prop_id: str) -> Optional[Dict[str, Any]]:
    for p in PROPERTIES_CACHE:
        if p.get("id") == prop_id:
            return p
    return None


def _price_for_intent(prop: Dict[str, Any], intent: str) -> Optional[int]:
    if intent == "alugar":
        price = prop.get("preco_aluguel") or 0
    else:
        price = prop.get("preco_venda") or 0
    return price if price > 0 else None


def _match_location(prop: Dict[str, Any], city: Optional[str], neighborhood: Optional[str]) -> bool:
    if neighborhood:
        return prop.get("bairro", "").lower() == neighborhood.lower()
    if city:
        return prop.get("cidade", "").lower() == city.lower()
    return False


def search_properties(filters: Dict[str, Any], intent: str) -> List[Dict[str, Any]]:
    city = filters.get("city")
    neighborhood = filters.get("neighborhood")
    prop_type = filters.get("property_type")
    bedrooms = filters.get("bedrooms")
    pet = filters.get("pet")
    furnished = filters.get("furnished")
    budget = filters.get("budget")

    results: List[Dict[str, Any]] = []
    for prop in PROPERTIES_CACHE:
        if not _match_location(prop, city, neighborhood):
            continue
        if prop_type and prop_type != "qualquer" and prop.get("tipo") != prop_type:
            continue
        price = _price_for_intent(prop, intent)
        if price is None or (budget and price > budget * 1.1):  # small tolerance
            continue
        if bedrooms and prop.get("quartos") and prop.get("quartos") < bedrooms:
            continue
        if pet is not None and prop.get("aceita_pet") is not None and prop.get("aceita_pet") != pet:
            continue
        if furnished is not None and prop.get("mobiliado") is not None and prop.get("mobiliado") != furnished:
            continue

        score = 0
        if neighborhood and prop.get("bairro", "").lower() == neighborhood.lower():
            score += 5
        elif city and prop.get("cidade", "").lower() == city.lower():
            score += 3
        if prop_type and prop_type != "qualquer" and prop.get("tipo") == prop_type:
            score += 3
        if bedrooms and prop.get("quartos") == bedrooms:
            score += 2
        if pet is not None and prop.get("aceita_pet") == pet:
            score += 1
        if furnished is not None and prop.get("mobiliado") == furnished:
            score += 1
        if budget and price:
            diff = abs(price - budget)
            budget_score = max(0, 3 - (diff / max(budget, 1)) * 3)
            score += budget_score
        prop["_score"] = score
        results.append(prop)

    results.sort(key=lambda x: x.get("_score", 0), reverse=True)
    return results[:6]


# stubs for scheduling/handoff

def schedule_visit(property_id: str, preferred_times: List[str], mode: str) -> Dict[str, Any]:
    return {
        "property_id": property_id,
        "preferred_times": preferred_times,
        "mode": mode,
        "status": "registrado",
    }


def handoff_human(summary: str) -> Dict[str, Any]:
    return {
        "status": "handoff",
        "summary": summary,
    }
