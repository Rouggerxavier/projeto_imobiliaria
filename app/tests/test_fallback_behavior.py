import logging
from unittest.mock import patch

import pytest

from agent.controller import handle_message
from agent.state import store
from agent import llm as llm_module
from agent.llm import LLMServiceError, LLMErrorType


def _make_error(err_type, retry_after=None):
    return LLMServiceError({
        "type": err_type,
        "http_status": 429 if "RATE_LIMIT" in err_type or "QUOTA" in err_type else 401,
        "retry_after_sec": retry_after,
        "provider": "test",
        "raw_message": err_type,
    })


def test_controller_quota_daily_logs_and_fallback(caplog):
    session = "fallback_quota"
    store.reset(session)
    llm_module._rate_limit_until = 0
    caplog.set_level(logging.ERROR, logger="uvicorn.error")

    with patch.object(llm_module, "USE_LLM", True), \
         patch.object(llm_module, "LLM_API_KEY", "fake"), \
         patch.object(llm_module, "call_llm", side_effect=_make_error(LLMErrorType.QUOTA_EXHAUSTED_DAILY.value, retry_after=1200)):
        resp = handle_message(session, "ola")

    # Log should contain normalized type
    assert any("QUOTA_EXHAUSTED_DAILY" in rec.message for rec in caplog.records)
    assert "reply" in resp
    assert "limite" in resp["reply"].lower() or "modo" in resp["reply"].lower()


def test_controller_auth_invalid_key_no_cooldown(caplog):
    session = "fallback_auth"
    store.reset(session)
    llm_module._rate_limit_until = 0
    caplog.set_level(logging.ERROR, logger="uvicorn.error")

    with patch.object(llm_module, "USE_LLM", True), \
         patch.object(llm_module, "LLM_API_KEY", "fake"), \
         patch.object(llm_module, "call_llm", side_effect=_make_error(LLMErrorType.AUTH_INVALID_KEY.value)):
        resp = handle_message(session, "ola")

    assert any("AUTH_INVALID_KEY" in rec.message for rec in caplog.records)
    assert "ajuste" in resp["reply"].lower() or "configurar" in resp["reply"].lower() or "modo" in resp["reply"].lower()


def test_fallback_does_not_repeat_budget(caplog):
    session = "fallback_budget"
    state = store.get(session)
    state.set_criterion("budget", 800000, status="confirmed")
    state.last_question_key = "budget"
    llm_module._rate_limit_until = 0
    caplog.set_level(logging.ERROR, logger="uvicorn.error")

    with patch.object(llm_module, "USE_LLM", True), \
         patch.object(llm_module, "LLM_API_KEY", "fake"), \
         patch.object(llm_module, "call_llm", side_effect=_make_error(LLMErrorType.RATE_LIMIT_RPM.value, retry_after=30)):
        resp = handle_message(session, "continuando")

    reply_low = resp["reply"].lower()
    assert "orcamento" not in reply_low  # não repetir orçamento
    # deve perguntar outro campo (ex: tipo ou vagas)
    assert any(word in reply_low for word in ["vagas", "tipo", "quartos", "cidade", "bairro", "alugar", "comprar"])
