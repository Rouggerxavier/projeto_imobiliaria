from __future__ import annotations
import os
import hashlib
import random
from typing import Dict, List, Optional
from .state import SessionState

TRIAGE_ONLY = os.getenv("TRIAGE_ONLY", "false").strip().lower() in ("true", "1", "yes", "on")
QUESTION_SEED = os.getenv("QUESTION_SEED")


def _stable_rng(session_id: str, salt: str = "") -> random.Random:
    seed_source = f"{session_id}:{salt}:{QUESTION_SEED or 'default'}"
    seed = int(hashlib.md5(seed_source.encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)


def choose_variant(session_id: str, key: str, variants: List[str]) -> str:
    """
    Retorna variante estável por sessão/tema para manter testabilidade.
    """
    rng = _stable_rng(session_id, salt=key)
    return rng.choice(variants)


def has_location(state: SessionState) -> bool:
    return bool(state.criteria.neighborhood or state.criteria.city)


def has_budget(state: SessionState) -> bool:
    return state.criteria.budget is not None and state.criteria.budget > 0


def has_type(state: SessionState) -> bool:
    return state.criteria.property_type is not None


def can_search_properties(state: SessionState) -> bool:
    # Guard-rail: TRIAGE_ONLY desativa totalmente busca/lista
    if TRIAGE_ONLY:
        return False
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


CRITICAL_ORDER = [
    "intent",
    "city",
    "neighborhood",
    "property_type",
    "bedrooms",
    "parking",
    "budget",
    "timeline",
]

PREFERENCE_ORDER = [
    "micro_location",
    "lead_name",
    "budget_min",
    "condo_max",
    "floor_pref",
    "sun_pref",
    "view_pref",
    "leisure_features",
    "suites",
    "payment_type",
    "entry_amount",
    "furnished",
    "pet",
    "area_min",
]


def _value(state: SessionState, key: str):
    if key in state.triage_fields:
        return state.triage_fields[key].get("value")
    if hasattr(state.criteria, key):
        return getattr(state.criteria, key)
    if key in state.lead_profile:
        return state.lead_profile.get(key)
    return None


def _status(state: SessionState, key: str) -> Optional[str]:
    if key in state.triage_fields:
        return state.triage_fields[key].get("status")
    if key == "intent":
        return "confirmed" if state.intent else None
    return None


def _micro_location_complete(val: Optional[str]) -> bool:
    if not val:
        return False
    return val in {"beira-mar", "1_quadra", "2-3_quadras", ">3_quadras"}


def missing_critical_fields(state: SessionState) -> List[str]:
    missing: List[str] = []

    if not state.intent:
        missing.append("intent")

    city_val = _value(state, "city")
    if not city_val:
        missing.append("city")
    elif _status(state, "city") == "inferred":
        missing.append("city_confirm")

    if not _value(state, "neighborhood"):
        missing.append("neighborhood")

    if not _value(state, "property_type"):
        missing.append("property_type")
    if _value(state, "bedrooms") is None:
        missing.append("bedrooms")
    if _value(state, "parking") is None:
        missing.append("parking")
    if _value(state, "budget") is None:
        missing.append("budget")
    if _value(state, "timeline") is None:
        missing.append("timeline")
    micro_val = _value(state, "micro_location")
    micro_status = _status(state, "micro_location")
    if micro_status == "inferred" or micro_val == "orla":
        missing.append("micro_location")
    return missing


QUESTION_BANK: Dict[str, List[str]] = {
    "intent": [
        "Prefere comprar ou alugar? Posso ajudar nos dois.",
        "Só pra alinhar: quer comprar ou alugar?",
        "Me conta: é compra ou aluguel que você busca?",
    ],
    "city": [
        "Vamos focar em João Pessoa/PB, tudo bem pra você?",
        "Posso seguir com João Pessoa/PB como cidade base. Confirma?",
    ],
    "city_confirm": [
        "Entendi João Pessoa como padrão. Confirma ou prefere outra cidade?",
        "Posso seguir com João Pessoa ou quer trocar a cidade?",
    ],
    "neighborhood": [
        "Qual bairro você deseja em João Pessoa? Pode citar 1–3 opções.",
        "Tem algum bairro em mente por aqui em João Pessoa? Pode listar rapidinho.",
    ],
    "micro_location": [
        "Quer ficar beira-mar, a 1 quadra ou 2-3 quadras da praia?",
        "Sobre distância da praia: beira-mar, 1 quadra ou 2-3 quadras?",
    ],
    "property_type": [
        "Prefere apartamento, casa ou cobertura?",
        "O tipo de imóvel é apê, casa ou cobertura?",
    ],
    "bedrooms": [
        "Quantos quartos no mínimo você precisa?",
        "Me diz o mínimo de quartos que funciona pra você.",
    ],
    "suites": [
        "Precisa de quantas suítes no mínimo?",
        "Quer pelo menos quantas suítes?",
    ],
    "parking": [
        "Quantas vagas você precisa no mínimo?",
        "Vagas de garagem: 1, 2 ou 3+?",
    ],
    "budget": [
        "Qual o orçamento máximo? Pode ser aproximado.",
        "Pra eu filtrar certo, qual teto de preço você imagina?",
    ],
    "timeline": [
        "Qual prazo você trabalha: 30d, 3m, 6m, 12m ou flexível?",
        "Pensando no prazo: até 30 dias, 3 meses, 6 meses, 12 meses ou flexível?",
    ],
    "budget_min": [
        "Existe um valor mínimo ou ponto de partida?",
    ],
    "condo_max": [
        "Tem teto de condomínio mensal? (R$)",
    ],
    "floor_pref": [
        "Prefere andar alto ou qualquer andar serve?",
    ],
    "sun_pref": [
        "Tem preferência de posição solar (nascente/poente/indiferente)?",
    ],
    "view_pref": [
        "Vista desejada: mar, parque ou tanto faz?",
    ],
    "leisure_features": [
        "Quais itens de lazer são importantes? (piscina, academia, gourmet, playground, coworking...)",
    ],
    "payment_type": [
        "Como pretende pagar? Financiamento, à vista, FGTS ou misto?",
    ],
    "lead_name": [
        "Qual seu nome para eu registrar aqui?",
        "Me diz seu nome, por favor.",
    ],
}

# Microcopy com motivo+pergunta (uma só interrogação)
MICROCOPY_VARIANTS: Dict[str, List[str]] = {
    "budget": [
        "Pra eu não te mandar opções fora do seu perfil: qual teto de orçamento você quer considerar?",
        "Só pra eu calibrar bem as opções: até quanto você quer chegar no orçamento?",
        "Pra filtrar direitinho: qual é o valor máximo que faz sentido pra você?",
    ],
    "neighborhood": [
        "Pra sugerir algo no seu raio de interesse: qual bairro você quer priorizar em João Pessoa?",
        "Pra focar onde faz sentido pra você: qual bairro prefere começar?",
        "Pra não sair da sua região-alvo: quais bairros você quer considerar primeiro?",
    ],
    "timeline": [
        "Pra ajustar urgência e agenda: qual prazo você tem em mente (30d, 3m, 6m, 12m, flexível)?",
        "Pra organizar o ritmo das próximas etapas: em quanto tempo quer avançar (30d, 3m, 6m, 12m ou flexível)?",
        "Pra alinhar expectativa de tempo: prefere algo para 30 dias, 3 meses, 6 meses, 12 meses ou flexível?",
    ],
    "condo_max": [
        "Condomínio pesa no custo fixo: qual valor mensal máximo te deixa confortável?",
        "Pra evitar surpresas no boleto: até quanto de condomínio por mês você aceita?",
        "Pra caber bem no custo mensal: qual é o teto de condomínio que faz sentido pra você?",
    ],
    "payment_type": [
        "Pra ajustar às formas de pagamento: você pretende financiar, usar FGTS ou pagar à vista?",
        "Pra alinhar viabilidade: vai ser financiamento, FGTS ou pagamento à vista?",
        "Pra eu considerar as condições certas: qual formato de pagamento você prefere (financiamento/FGTS/à vista)?",
    ],
    "intent_stage": [
        "Você está mais na fase de pesquisar, ou pretende visitar opções nas próximas semanas?",
        "Hoje você está só sondando, ou já quer marcar visitas em breve?",
        "Prefere seguir pesquisando ou já quer agendar visitas nas próximas semanas?",
    ],
}


def choose_question(key: str, state: SessionState) -> Optional[str]:
    # Microcopy prioriza variantes com motivo+pergunta
    variants = MICROCOPY_VARIANTS.get(key) or QUESTION_BANK.get(key)
    if not variants:
        return None
    return choose_variant(state.session_id, key, variants)


def _intent_stage_ready(state: SessionState) -> bool:
    if state.intent_stage != "unknown":
        return False
    has_location = bool(state.criteria.neighborhood or state.criteria.city)
    budget_ok = has_budget(state)
    has_bedrooms = state.criteria.bedrooms is not None
    critical_filled = sum(
        1
        for val in [
            state.criteria.neighborhood,
            state.criteria.city,
            state.criteria.budget,
            state.criteria.bedrooms,
            state.criteria.property_type,
        ]
        if val
    )
    return budget_ok and (has_bedrooms or has_location) and critical_filled >= 2


def next_best_question_key(state: SessionState) -> Optional[str]:
    missing = missing_critical_fields(state)

    # Sempre priorizar micro_location quando inferido/orla
    if "micro_location" in missing and "micro_location" not in state.asked_questions:
        return "micro_location"

    # Pergunta de estágio de intenção pode entrar antes de campos menos críticos (ex.: parking/timeline)
    gating_blockers = {"intent", "city", "neighborhood", "property_type", "budget", "bedrooms", "micro_location"}
    if (
        _intent_stage_ready(state)
        and "intent_stage" not in state.asked_questions
        and not (gating_blockers & set(missing))
    ):
        return "intent_stage"

    for key in missing:
        if key not in state.asked_questions:
            return key
    if missing:
        return missing[0]

    # Nome obrigatório antes de concluir
    if not state.lead_profile.get("name") and "lead_name" not in state.asked_questions:
        return "lead_name"

    # Campos importantes extras (pegar 2–4 no máximo: faremos 1 de cada vez)
    for key in PREFERENCE_ORDER:
        if _value(state, key) is None:
            if key not in state.asked_questions:
                return key
    return None


def next_best_question(state: SessionState) -> Optional[str]:
    key = next_best_question_key(state)
    if not key:
        return None
    return choose_question(key, state)
