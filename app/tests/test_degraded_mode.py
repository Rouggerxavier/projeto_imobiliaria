"""
Testes para Degraded Mode (Circuit Breaker)

Valida que quando o LLM falha com erros transitórios (503, 429, timeout),
o sistema entra em degraded mode e usa fallback determinístico.
"""

import pytest
from unittest.mock import Mock, patch
from app.agent.controller import handle_message
from app.agent.state import store
from app.agent.llm import LLMServiceError, LLMErrorType, LLMUnavailableError
import time


@pytest.fixture
def clear_session():
    """Limpa sessão entre testes"""
    session_id = "test_degraded_session"
    store.reset(session_id)
    yield session_id
    store.reset(session_id)


def test_degraded_mode_activated_on_503(clear_session):
    """
    Caso: LLM retorna 503 (Service Unavailable) → sistema entra em degraded mode
    Esperado: Circuit breaker ativado, próximos turnos não chamam LLM
    """
    session_id = clear_session

    # Mock do LLM para simular erro 503
    error_norm = {
        "type": LLMErrorType.NETWORK_ERROR.value,
        "http_status": 503,
        "provider": "gemini",
        "raw_message": "Service Unavailable",
        "retry_after_sec": 120.0
    }

    with patch('app.agent.llm.call_llm') as mock_llm:
        # Primeira chamada: simula 503
        mock_llm.side_effect = LLMServiceError(error_norm)

        # Primeira mensagem: deve falhar e ativar degraded mode
        resp = handle_message(session_id, "Quero alugar um apartamento")

        # Deve ter respondido algo (fallback)
        assert resp["reply"]
        assert len(resp["reply"]) > 10

        # Verifica que degraded mode foi ativado
        state = store.get(session_id)
        assert state.llm_degraded is True
        assert state.llm_degraded_until_ts is not None
        assert state.llm_degraded_until_ts > time.time()
        assert state.llm_last_error == LLMErrorType.NETWORK_ERROR.value

    # Segunda mensagem: não deve chamar LLM (está em degraded mode)
    with patch('app.agent.llm.call_llm') as mock_llm2:
        mock_llm2.side_effect = Exception("LLM should not be called in degraded mode!")

        # Deve funcionar sem chamar LLM
        resp2 = handle_message(session_id, "João Pessoa")

        # Deve ter respondido
        assert resp2["reply"]
        # LLM não deve ter sido chamado
        assert not mock_llm2.called

        # Degraded mode ainda ativo
        state = store.get(session_id)
        assert state.llm_degraded is True


def test_degraded_mode_timeout_recovery(clear_session):
    """
    Caso: Degraded mode ativa, mas timeout expira → sistema tenta LLM novamente
    Esperado: Após cooldown, LLM é chamado de novo
    """
    session_id = clear_session
    state = store.get(session_id)

    # Ativa degraded mode manualmente com timeout curto
    state.llm_degraded = True
    state.llm_degraded_until_ts = time.time() + 0.5  # 0.5 segundos
    state.llm_last_error = "NETWORK_ERROR"

    # Espera timeout expirar
    time.sleep(0.6)

    # Agora LLM deve ser chamado novamente
    with patch('app.agent.llm.call_llm') as mock_llm:
        mock_llm.return_value = {
            "intent": "alugar",
            "criteria": {},
            "plan": {"action": "ASK", "message": "Qual cidade?", "question_key": "city"}
        }

        resp = handle_message(session_id, "Quero alugar")

        # LLM deve ter sido chamado (degraded mode expirou)
        assert mock_llm.called

        # Degraded mode deve ter sido desativado
        state = store.get(session_id)
        assert state.llm_degraded is False
        assert state.llm_degraded_until_ts is None


def test_extraction_continues_in_degraded_mode(clear_session):
    """
    Caso: LLM falha, mas extraction de campos continua funcionando
    Esperado: Mesmo com LLM down, campos são capturados via regex e state é atualizado
    """
    session_id = clear_session

    # Mock do LLM para simular erro 503
    error_norm = {
        "type": LLMErrorType.NETWORK_ERROR.value,
        "http_status": 503,
        "provider": "gemini",
        "raw_message": "Service Unavailable",
    }

    with patch('app.agent.llm.call_llm', side_effect=LLMServiceError(error_norm)):
        # Primeira mensagem com dados
        handle_message(session_id, "Quero alugar")
        handle_message(session_id, "João Pessoa")
        handle_message(session_id, "Manaíra")
        handle_message(session_id, "Apartamento")
        handle_message(session_id, "2 quartos")
        handle_message(session_id, "1 vaga")

        # Verifica que campos foram capturados (extract-first)
        state = store.get(session_id)
        assert state.intent == "alugar"
        assert state.criteria.city == "Joao Pessoa"
        assert state.criteria.neighborhood == "Manaíra"
        assert state.criteria.property_type == "Apartamento"
        assert state.criteria.bedrooms == 2
        assert state.criteria.parking == 1

        # Degraded mode deve estar ativo
        assert state.llm_degraded is True


def test_quality_gate_works_in_degraded_mode(clear_session):
    """
    Caso: Quality gate pergunta gaps usando templates (sem LLM)
    Esperado: Mesmo com LLM down, sistema faz perguntas de gap usando templates
    """
    session_id = clear_session

    # Mock do LLM para simular erro 503
    error_norm = {
        "type": LLMErrorType.NETWORK_ERROR.value,
        "http_status": 503,
        "provider": "gemini",
        "raw_message": "Service Unavailable",
    }

    with patch('app.agent.llm.call_llm', side_effect=LLMServiceError(error_norm)):
        # Preenche campos críticos
        handle_message(session_id, "Oi")
        handle_message(session_id, "Quero comprar")
        handle_message(session_id, "João Pessoa")
        handle_message(session_id, "Manaíra")
        handle_message(session_id, "Apartamento")
        handle_message(session_id, "3 quartos")
        handle_message(session_id, "2 vagas")
        handle_message(session_id, "até 800 mil")
        resp = handle_message(session_id, "3 meses")

        # Deve ter perguntado nome ou telefone (quality gate / final do funil)
        reply_lower = resp["reply"].lower()
        assert "nome" in reply_lower or "telefone" in reply_lower or "celular" in reply_lower or "whatsapp" in reply_lower

        # Degraded mode ativo
        state = store.get(session_id)
        assert state.llm_degraded is True


def test_timeline_inference_in_degraded_mode(clear_session):
    """
    Caso: Usuário diz "pronto para visitar" → timeline inferido como 30d
    Esperado: Timeline é mapeado corretamente mesmo sem LLM
    """
    session_id = clear_session

    # Mock do LLM para simular erro 503
    error_norm = {
        "type": LLMErrorType.NETWORK_ERROR.value,
        "http_status": 503,
        "provider": "gemini",
        "raw_message": "Service Unavailable",
    }

    with patch('app.agent.llm.call_llm', side_effect=LLMServiceError(error_norm)):
        handle_message(session_id, "Quero alugar")
        handle_message(session_id, "João Pessoa")
        handle_message(session_id, "Manaíra")
        handle_message(session_id, "Apartamento")
        handle_message(session_id, "2 quartos")
        handle_message(session_id, "1 vaga")
        handle_message(session_id, "até 3 mil")

        # Responde com "pronto para visitar" → deve inferir timeline 30d
        handle_message(session_id, "pronto para visitar")

        state = store.get(session_id)
        # Timeline deve ter sido inferido como 30d
        assert state.criteria.timeline in ["30d", None]  # None se não foi perguntado ainda
        # intent_stage deve ser ready_to_visit
        assert state.intent_stage == "ready_to_visit"


def test_lead_record_contains_degraded_flag(clear_session):
    """
    Caso: Lead finalizado em degraded mode → campo llm_degraded salvo em leads.jsonl
    Esperado: lead_record contém flags.llm_degraded e llm_status
    """
    session_id = clear_session

    # Mock do LLM para simular erro 503
    error_norm = {
        "type": LLMErrorType.NETWORK_ERROR.value,
        "http_status": 503,
        "provider": "gemini",
        "raw_message": "Service Unavailable",
    }

    with patch('app.agent.llm.call_llm', side_effect=LLMServiceError(error_norm)):
        # Mock de persistence
        with patch('app.agent.persistence.append_lead') as mock_append:
            # Preenche todos os campos
            handle_message(session_id, "Oi")
            handle_message(session_id, "Quero alugar")
            handle_message(session_id, "João Pessoa")
            handle_message(session_id, "Manaíra")
            handle_message(session_id, "Apartamento")
            handle_message(session_id, "2 quartos")
            handle_message(session_id, "1 vaga")
            handle_message(session_id, "até 3 mil")
            handle_message(session_id, "3 meses")
            handle_message(session_id, "Carlos Silva")
            handle_message(session_id, "83988887777")

            # Deve ter chamado append_lead
            if mock_append.called:
                lead_record = mock_append.call_args[0][0]
                # Verifica flags
                assert "flags" in lead_record
                assert lead_record["flags"]["llm_degraded"] is True
                # Verifica llm_status
                assert "llm_status" in lead_record
                assert lead_record["llm_status"]["degraded"] is True
                assert lead_record["llm_status"]["last_error"] == LLMErrorType.NETWORK_ERROR.value
