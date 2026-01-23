from __future__ import annotations
from typing import Optional


INTENT_KEYWORDS = {
    "alugar": ["alugar", "aluguel", "alugo", "alocacao", "locacao"],
    "comprar": ["comprar", "compra", "adquirir", "compraria", "quero comprar"],
    "investir": ["investir", "investimento", "renda", "rentabilidade"],
    "pesquisar": ["pesquisar", "olhando", "ver opcoes", "apenas olhando", "so olhando"],
    "suporte": ["reclama", "suporte", "problema", "erro"],
    "humano": ["atendente", "humano", "corretor", "pessoa"],
}


def classify_intent(message: str) -> Optional[str]:
    text = message.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        for k in keywords:
            if k in text:
                return intent
    if "aluguel" in text or "alug" in text:
        return "alugar"
    if "venda" in text:
        return "comprar"
    return None
