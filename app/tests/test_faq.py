import pytest
from unittest.mock import patch

from agent.controller import handle_message
from agent.state import store
from agent import llm as llm_module, rules as rules_module, controller as controller_module
from app import faq


def triage_patches():
    return [
        patch.object(llm_module, "TRIAGE_ONLY", True),
        patch.object(rules_module, "TRIAGE_ONLY", True),
        patch.object(controller_module, "TRIAGE_ONLY", True),
    ]


def test_detect_financiamento():
    intent = faq.detect_faq_intent("aceita financiamento?")
    assert intent == faq.FAQIntent.FINANCIAMENTO


def test_detect_fgts():
    intent = faq.detect_faq_intent("posso usar fgts?")
    assert intent == faq.FAQIntent.FGTS


def test_detect_documentos():
    intent = faq.detect_faq_intent("o imovel tem escritura?")
    assert intent == faq.FAQIntent.DOCUMENTOS


def test_detect_prazo():
    intent = faq.detect_faq_intent("quanto tempo demora?")
    assert intent == faq.FAQIntent.PRAZO


def test_detect_negociacao():
    intent = faq.detect_faq_intent("da pra negociar?")
    assert intent == faq.FAQIntent.NEGOCIACAO


def test_detect_status():
    intent = faq.detect_faq_intent("e agora?")
    assert intent == faq.FAQIntent.STATUS


def test_no_false_positive_price_range():
    intent = faq.detect_faq_intent("entre 800 mil e 1,2 milhao")
    assert intent is None


def test_faq_answer_then_continue_triage():
    session = "faq_flow"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    with patch.object(llm_module, "USE_LLM", False), p1, p2, p3:
        resp = handle_message(session, "aceita financiamento?")

    reply = resp["reply"].lower()
    assert "financiamento" in reply
    assert "cidade" in reply or "bairro" in reply or "imovel" in reply or "comprar ou alugar" in reply
