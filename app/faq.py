from __future__ import annotations
import unicodedata
from enum import Enum, auto
from typing import Optional
from app.agent.state import SessionState


def _norm(text: str) -> str:
    txt = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in txt if not unicodedata.combining(ch))


class FAQIntent(Enum):
    FINANCIAMENTO = auto()
    FGTS = auto()
    DOCUMENTOS = auto()
    TAXAS = auto()
    PRAZO = auto()
    NEGOCIACAO = auto()
    VISITA = auto()
    STATUS = auto()


KEYWORDS = {
    FAQIntent.FINANCIAMENTO: ["financiamento", "financiar", "banco", "entrada", "parcelar", "financia"],
    FAQIntent.FGTS: ["fgts", "fundo de garantia"],
    FAQIntent.DOCUMENTOS: ["escritura", "registro", "documentos", "cartorio", "regularizado", "habite-se", "habite se"],
    FAQIntent.TAXAS: ["itbi", "cartorio", "taxa", "custos", "condominio", "impostos", "escritura e registro"],
    FAQIntent.PRAZO: ["quanto tempo", "prazo", "demora", "leva quanto", "quando entrega", "chaves"],
    FAQIntent.NEGOCIACAO: ["negociar", "negociacao", "desconto", "abaixa", "aceita proposta"],
    FAQIntent.VISITA: ["visitar", "agendar", "visita", "conhecer", "ver o imovel", "ver o imóvel"],
    FAQIntent.STATUS: ["e agora", "proximo passo", "quando", "vai chamar", "corretor", "atendimento", "ja tem opcoes", "me manda opcoes"],
}

QUESTION_CUES = ("?", "como ", "quanto", "pode", "aceita", "precisa", "quando")


def detect_faq_intent(user_text: str) -> Optional[FAQIntent]:
    if not user_text:
        return None
    norm = _norm(user_text.strip())
    has_question_form = ("?" in user_text) or any(norm.startswith(cue) for cue in QUESTION_CUES)
    if not has_question_form:
        return None

    # evitar falso positivo em faixas de preço
    if any(token in norm for token in ["milhao", "milhao", "mil ", "k"]) and "-" in norm:
        return None

    for intent, kws in KEYWORDS.items():
        for kw in kws:
            if kw in norm:
                return intent
    return None


def _maybe(field: Optional[str], prefix: str) -> str:
    return f"{prefix}{field}" if field else ""


def answer_faq(intent: FAQIntent, state: SessionState) -> str:
    city = state.criteria.city
    intent_op = state.intent
    budget = state.criteria.budget

    if intent == FAQIntent.FINANCIAMENTO:
        extra = ""
        if intent_op == "comprar":
            extra = " Você pretende pagar à vista ou financiamento?"
        return (
            "Muitos imóveis aceitam financiamento, mas depende do imóvel e da documentação. "
            "O corretor confirma no seu caso." + extra
        )

    if intent == FAQIntent.FGTS:
        return (
            "Geralmente dá para usar FGTS na compra se o perfil e o imóvel estiverem dentro das regras. "
            "Recomendo validar com seu banco e o corretor confirma no seu caso."
        )

    if intent == FAQIntent.DOCUMENTOS:
        return (
            "O ideal é o imóvel estar regularizado: matrícula sem ônus, habite-se e documentos do vendedor ok. "
            "Quando enviarmos opções, o corretor verifica tudo isso para você."
        )

    if intent == FAQIntent.TAXAS:
        return (
            "Além do valor do imóvel, costuma haver custos de impostos/registro/cartório e condomínio quando existir. "
            "O corretor passa uma estimativa conforme o imóvel e a cidade."
        )

    if intent == FAQIntent.PRAZO:
        return (
            "O tempo varia conforme documentação e, se for financiamento, também do banco. "
            "Para visitas, o corretor agenda rápido dentro dos horários que você preferir."
        )

    if intent == FAQIntent.NEGOCIACAO:
        return (
            "Desconto depende do vendedor e do imóvel. "
            "O corretor negocia e orienta a melhor proposta, sem prometer nada fora do perfil."
        )

    if intent == FAQIntent.VISITA:
        return (
            "Depois de alinhar seu perfil, o corretor agenda a visita. "
            "Me diz os dias/horários que funcionam melhor e ele confirma."
        )

    if intent == FAQIntent.STATUS:
        missing = []
        from app.agent.rules import missing_critical_fields

        pending = missing_critical_fields(state)
        if pending:
            # destacar 1-2 campos
            missing = pending[:2]
            campos = " e ".join(missing)
            return f"Já estou cuidando disso. Só preciso confirmar {campos} pra te passar pro corretor."
        if state.completed:
            return "Já repassei seu perfil para um corretor, ele te chama por aqui em seguida."
        return "Quase lá! Estou finalizando seu perfil e já conecto você a um corretor."

    return "Posso ajudar nisso, mas o corretor confirma no seu caso."
