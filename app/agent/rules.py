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
    "suites",           # NOVO: obrigatório (aceita "indifferent")
    "bathrooms_min",    # NOVO: obrigatório (aceita "indifferent")
    "parking",
    "budget",
    "timeline",
    "micro_location",   # NOVO: obrigatório (aceita "indifferent")
    "leisure_required", # NOVO: obrigatório (aceita "indifferent")
    "lead_name",
    "lead_phone",
]

PREFERENCE_ORDER = [
    "budget_min",
    "condo_max",
    "leisure_level",    # NOVO: nível de lazer (após leisure_required)
    "floor_pref",       # já existia
    "sun_pref",         # já existia
    "view_pref",        # já existia
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


def _is_indifferent(val: any) -> bool:
    """Verifica se um valor representa 'indiferente/tanto faz'."""
    if val is None:
        return False
    val_str = str(val).lower().strip()
    return val_str in {"indifferent", "indiferente", "tanto faz", "qualquer", "nao importa", "não importa"}


def missing_critical_fields(state: SessionState) -> List[str]:
    missing: List[str] = []

    if not state.intent:
        missing.append("intent")

    city_val = _value(state, "city")
    if not city_val:
        missing.append("city")

    if not _value(state, "neighborhood"):
        missing.append("neighborhood")

    if not _value(state, "property_type"):
        missing.append("property_type")
    if _value(state, "bedrooms") is None:
        missing.append("bedrooms")

    # NOVO: Suítes (aceita "indifferent" como preenchido)
    suites_val = _value(state, "suites")
    if suites_val is None and not _is_indifferent(suites_val):
        missing.append("suites")

    # NOVO: Banheiros (aceita "indifferent" como preenchido)
    bathrooms_val = _value(state, "bathrooms_min")
    if bathrooms_val is None and not _is_indifferent(bathrooms_val):
        missing.append("bathrooms_min")

    if _value(state, "parking") is None:
        missing.append("parking")
    if _value(state, "budget") is None:
        missing.append("budget")
    if _value(state, "timeline") is None:
        missing.append("timeline")

    # Micro-location (proximidade da praia) - aceita "indifferent"
    micro_val = _value(state, "micro_location")
    micro_status = _status(state, "micro_location")
    if micro_val is None and not _is_indifferent(micro_val):
        missing.append("micro_location")
    elif micro_status == "inferred" or micro_val == "orla":
        missing.append("micro_location")

    # NOVO: Leisure required (aceita "indifferent" como preenchido)
    leisure_req = _value(state, "leisure_required")
    if leisure_req is None and not _is_indifferent(leisure_req):
        missing.append("leisure_required")

    return missing


QUESTION_BANK: Dict[str, List[str]] = {
    "intent": [
        "Pode me contar o que você está buscando 😊 é pra comprar ou alugar?",
        "É pra comprar ou alugar? Posso ajudar nos dois!",
        "Me conta, está em busca de algo pra comprar ou pra alugar?",
        "Você quer alugar ou comprar um imóvel?",
    ],
    "city": [
        "Em qual cidade você quer procurar o imóvel?",
        "Qual cidade tem sua preferência?",
        "Me diz a cidade onde você quer encontrar o imóvel.",
    ],
    "neighborhood": [
        "Qual bairro você prefere?",
        "Tem algum bairro específico que já está de olho?",
        "Me conta qual bairro faz mais sentido pra você.",
    ],
    "micro_location": [
        "Em relação à praia, você prefere beira-mar, 1 quadra, 2-3 quadras ou tanto faz?",
        "Proximidade da praia: beira-mar, 1 quadra, 2-3 quadras ou indiferente?",
        "Quer algo beira-mar, próximo (1-2 quadras) ou a distância não importa?",
    ],
    "property_type": [
        "Apartamento, casa ou cobertura — qual o tipo de imóvel que você busca?",
        "Você tem preferência pelo tipo, tipo apartamento, casa, cobertura?",
    ],
    "bedrooms": [
        "Quantos quartos no mínimo você precisa?",
        "Me diz o mínimo de quartos que funciona para você.",
        "Quantos quartos você quer no imóvel? (pode ser 1, 2, 3, 4...)",
    ],
    "suites": [
        "E suítes (quartos com banheiro próprio), quantas você precisa no mínimo? Pode ser nenhuma ou tanto faz.",
        "Quantas suítes seriam ideais? (Suíte = quarto com banheiro. Pode dizer 0 / 1 / 2+ / tanto faz)",
        "Quer pelo menos quantas suítes? (0 / 1 / 2 / 3+ / indiferente)",
    ],
    "bathrooms_min": [
        "E no total de banheiros, quantos no mínimo você precisa? (1 / 2 / 3+ / tanto faz)",
        "Quantos banheiros no total o imóvel deve ter no mínimo? (pode ser 1, 2, 3... ou tanto faz)",
        "Banheiros no total (incluindo suítes): quantos você quer no mínimo? (1 / 2 / 3+ / indiferente)",
    ],
    "suites_bathrooms_combined": [
        "Pra eu filtrar certinho: você faz questão de suíte? (0 / 1 / 2+ / tanto faz)\nE no total, quantos banheiros no mínimo? (1 / 2 / 3+ / tanto faz)",
        "Me conta: quantas suítes você quer (0 / 1 / 2 / indiferente)? E no total de banheiros? (1 / 2 / 3+ / tanto faz)",
    ],
    "parking": [
        "E vagas de garagem (para carro), quantas você precisa?",
        "Quantas vagas de garagem são necessárias? Pode ser 1, 2, 3 ou nenhuma.",
        "Quantas vagas de estacionamento (garagem) você precisa?",
        "Precisa de vaga de garagem pro carro? Quantas vagas seriam ideais?",
    ],
    "budget": [
        "Me da uma ideia da faixa de preço que faz sentido pra você, tipo de R$ X até R$ Y?",
        "Qual a faixa de orçamento que você tem em mente pra esse imóvel?",
        "Pode me contar a faixa de preço que seria ideal para você?",
        "Até quanto você pode investir nesse imóvel? (pode ser aproximado)",
    ],
    "timeline": [
        "E pensando no prazo, você quer algo pra dentro de 30 dias, 3 meses, 6 meses, 12 meses ou está flexível?",
        "Tem alguma urgência de prazo ou ainda está em fase de pesquisa?",
        "Pra quando você precisa do imóvel? (pode ser uma ideia aproximada: 1 mês, 3 meses, 6 meses...)",
    ],
    "leisure_required": [
        "Área de lazer no condomínio é importante pra você? (sim / não / tanto faz)",
        "Você faz questão de área de lazer completa ou tanto faz?",
        "Precisa de área de lazer (piscina, academia, etc.) ou não é essencial?",
    ],
    "leisure_level": [
        "Qual nível de lazer seria ideal: simples (básico), ok (médio) ou completa (com tudo)? Ou tanto faz?",
        "Lazer: prefere simples, razoável, completo ou indiferente?",
    ],
    "budget_min": [
        "Tem também um valor mínimo na faixa ou pode ser qualquer coisa abaixo do máximo?",
    ],
    "condo_max": [
        "Tem algum teto de condomínio mensal que faz sentido pra você?",
    ],
    "floor_pref": [
        "Preferência de andar: baixo, médio, alto ou tanto faz?",
        "Você prefere andar baixo, médio, alto ou é indiferente?",
    ],
    "sun_pref": [
        "Posição solar: nascente, poente ou indiferente?",
        "Tem preferência de sol nascente (manhã) ou poente (tarde), ou tanto faz?",
    ],
    "view_pref": [
        "Qual vista seria ideal pra você: mar, parque, cidade ou tanto faz?",
    ],
    "pet": [
        "O imóvel precisa aceitar pet (cachorro/gato)? (sim / não / tanto faz)",
        "Você tem pet (cachorro, gato)? Precisa que o imóvel aceite?",
    ],
    "furnished": [
        "Prefere imóvel mobiliado, sem móveis ou tanto faz?",
        "Mobiliado: sim, não ou indiferente?",
    ],
    "payment_type": [
        "E a forma de pagamento, está pensando em financiar, usar FGTS ou pagar à vista?",
    ],
    "lead_name": [
        "Antes de eu fechar o seu perfil aqui, qual é o seu nome?",
        "Só pra eu personalizar o atendimento, pode me dizer seu nome?",
    ],
    "lead_phone": [
        "E pra o corretor conseguir te contatar, qual o seu celular ou WhatsApp?",
        "Me passa também o seu número de WhatsApp pra o corretor entrar em contato.",
    ],
}

# Microcopy com motivo+pergunta humanizado (sem dois-pontos)
MICROCOPY_VARIANTS: Dict[str, List[str]] = {
    "budget": [
        "Me da uma ideia da faixa de preço que faz sentido pra você, tipo de R$ X até R$ Y",
        "Qual a faixa de orçamento que você tem em mente pra esse imóvel?",
        "Pode me contar a faixa de preço que seriam os limites ideais pra você?",
    ],
    "neighborhood": [
        "Tem algum bairro específico que já está de olho ou posso sugerir conforme seu perfil?",
        "Qual bairro você prefere ou tem mais interesse?",
        "Me diz o bairro que faz mais sentido pra você e a gente parte daí.",
    ],
    "timeline": [
        "E pensando no prazo, têm ideia do tempo que você tem pra fechar: 30 dias, 3, 6 ou 12 meses, ou ainda está flexível?",
        "Tem alguma urgência de prazo ou ainda está em fase de pesquisa mesmo?",
        "Em quanto tempo você imagina fechar isso: 30 dias, 3 meses, 6 meses, 12 meses ou sem pressa?",
    ],
    "condo_max": [
        "Condomínio pesa no custo fixo — tem algum valor mensal máximo que te deixa confortável?",
        "Até quanto de condomínio por mês ficaria dentro do seu orçamento?",
        "Qual seria o teto de condomínio mensal que faz sentido pra você?",
    ],
    "payment_type": [
        "Você já pensou na forma de pagamento, financiamento, FGTS ou à vista?",
        "Como você pretende pagar, financiar, usar FGTS ou pagar à vista?",
        "Qual formato de pagamento faz mais sentido pra você agora?",
    ],
    "intent_stage": [
        "Você está mais na fase de pesquisar as opções (sem pressa) ou já está pronto(a) para agendar visitas?",
        "Você está só pesquisando por enquanto ou já quer marcar visitas em breve?",
        "Prefere seguir pesquisando sem compromisso ou já quer agendar visitas nas próximas semanas?",
    ],
    "lead_phone": [
        "E pra o corretor conseguir te contatar, qual o seu celular ou WhatsApp?",
        "Me passa também o seu número de WhatsApp pra o corretor entrar em contato com você.",
    ],
}


def choose_question(key: str, state: SessionState) -> Optional[str]:
    if key == "city":
        if _should_offer_metro_city_question(state):
            return "Você quer procurar em João Pessoa ou em Cabedelo?"
        return (QUESTION_BANK.get("city") or ["Em qual cidade você quer procurar o imóvel?"])[0]
    if key == "neighborhood":
        city = _value(state, "city")
        if city:
            return f"Em qual bairro de {city} você prefere?"
    # Microcopy prioriza variantes com motivo+pergunta
    variants = MICROCOPY_VARIANTS.get(key) or QUESTION_BANK.get(key)
    if not variants:
        return None
    return choose_variant(state.session_id, key, variants)


def _should_offer_metro_city_question(state: SessionState) -> bool:
    if _value(state, "city") or _value(state, "neighborhood"):
        return False
    if not state.intent:
        return False
    if "city" in state.asked_questions:
        return False
    return True


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

    if "intent" in missing and "intent" not in state.asked_questions:
        return "intent"

    if "city" in missing:
        return "city"

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

    # Telefone obrigatório antes de concluir
    if not state.lead_profile.get("phone") and "lead_phone" not in state.asked_questions:
        return "lead_phone"

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
