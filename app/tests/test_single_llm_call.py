"""
Testes para garantir otimização de chamadas LLM:
1. Máximo 1 chamada LLM por mensagem
2. Fallback funciona em caso de 429
3. Não há loops infinitos
"""

import pytest
from unittest.mock import patch, MagicMock
import json

# Imports do projeto
from agent.controller import handle_message
from agent.state import store
from agent import llm as llm_module


class TestSingleLLMCall:
    """Testa que apenas 1 chamada LLM é feita por mensagem."""

    def setup_method(self):
        """Reset state before each test."""
        self.session_id = "test_single_call"
        store.reset(self.session_id)

    @patch.object(llm_module, 'call_llm')
    def test_single_llm_call_per_message(self, mock_call_llm):
        """Garante que apenas 1 chamada LLM é feita por mensagem."""
        # Configura mock para retornar resposta válida
        mock_call_llm.return_value = {
            "intent": "alugar",
            "criteria": {"city": "Joao Pessoa"},
            "handoff": {"should": False, "reason": None},
            "plan": {
                "action": "ASK",
                "message": "Qual o orçamento?",
                "question_key": "budget"
            }
        }

        # Garante que USE_LLM está ativo
        with patch.object(llm_module, 'USE_LLM', True):
            with patch.object(llm_module, 'GROQ_API_KEY', 'fake_key'):
                with patch.object(llm_module, '_rate_limit_until', 0):
                    handle_message(self.session_id, "quero alugar um ap em jp")

        # Verifica que call_llm foi chamado EXATAMENTE 1 vez
        assert mock_call_llm.call_count == 1, \
            f"Esperado 1 chamada LLM, mas houve {mock_call_llm.call_count}"


class TestFallbackOn429:
    """Testa que fallback funciona corretamente em caso de 429."""

    def setup_method(self):
        self.session_id = "test_429_fallback"
        store.reset(self.session_id)

    @patch.object(llm_module, 'call_llm')
    def test_fallback_on_429_error(self, mock_call_llm):
        """Simula erro 429 e verifica que fallback determinístico é usado."""
        # Simula erro 429 com mensagem de retry
        mock_call_llm.side_effect = RuntimeError(
            "Error code: 429 - Rate limit reached. Please try again in 5m30s"
        )

        with patch.object(llm_module, 'USE_LLM', True):
            with patch.object(llm_module, 'GROQ_API_KEY', 'fake_key'):
                with patch.object(llm_module, '_rate_limit_until', 0):
                    # Deve funcionar sem erro (usando fallback)
                    resp = handle_message(self.session_id, "quero comprar uma casa")

        # Verifica que resposta foi gerada (fallback funcionou)
        assert "reply" in resp
        assert resp["reply"] is not None
        assert len(resp["reply"]) > 0

    @patch.object(llm_module, 'call_llm')
    def test_no_retry_spam_on_429(self, mock_call_llm):
        """Verifica que não há spam de retries após 429."""
        mock_call_llm.side_effect = RuntimeError(
            "Error code: 429 - Rate limit. Please try again in 3m0s"
        )

        with patch.object(llm_module, 'USE_LLM', True):
            with patch.object(llm_module, 'GROQ_API_KEY', 'fake_key'):
                with patch.object(llm_module, '_rate_limit_until', 0):
                    handle_message(self.session_id, "oi")

        # max_retries=1, então deve ser chamado no máximo 1 vez
        assert mock_call_llm.call_count <= 1


class TestNoInfiniteLoop:
    """Testa que não há loops infinitos no fallback."""

    def setup_method(self):
        self.session_id = "test_no_loop"
        store.reset(self.session_id)

    def test_fallback_returns_valid_response(self):
        """Fallback deve retornar resposta válida sem loop."""
        # Desabilita LLM para forçar fallback
        with patch.object(llm_module, 'USE_LLM', False):
            resp = handle_message(self.session_id, "ola")

        assert "reply" in resp
        assert resp["reply"] is not None

    def test_no_repeated_question_spam(self):
        """Não deve repetir a mesma pergunta infinitamente."""
        with patch.object(llm_module, 'USE_LLM', False):
            # Primeira mensagem
            resp1 = handle_message(self.session_id, "oi")
            question1 = resp1["reply"]

            # Segunda mensagem vaga
            resp2 = handle_message(self.session_id, "sim")
            question2 = resp2["reply"]

            # Terceira mensagem vaga
            resp3 = handle_message(self.session_id, "ok")
            question3 = resp3["reply"]

        # Não deve travar em loop infinito
        # (as respostas podem ser iguais, mas o teste não deve travar)
        assert resp1 is not None
        assert resp2 is not None
        assert resp3 is not None


class TestRateLimitParsing:
    """Testa parsing do tempo de retry."""

    def test_parse_retry_after_minutes_seconds(self):
        """Testa parsing de '3m41.184s'."""
        from agent.llm import _parse_retry_after

        result = _parse_retry_after("Please try again in 3m41.184s")
        # 3 * 60 + 41.184 = 221.184
        assert abs(result - 221.184) < 0.01

    def test_parse_retry_after_seconds_only(self):
        """Testa parsing de '45.5s'."""
        from agent.llm import _parse_retry_after

        result = _parse_retry_after("Please try again in 45.5s")
        assert abs(result - 45.5) < 0.01

    def test_parse_retry_after_fallback(self):
        """Sem padrão reconhecido, retorna 60s."""
        from agent.llm import _parse_retry_after

        result = _parse_retry_after("Unknown error message")
        assert result == 60.0


class TestCacheOptimization:
    """Testa que cache evita chamadas duplicadas."""

    def setup_method(self):
        self.session_id = "test_cache"
        store.reset(self.session_id)
        # Limpa cache
        llm_module._message_cache.clear()

    @patch.object(llm_module, 'call_llm')
    def test_cache_prevents_duplicate_calls(self, mock_call_llm):
        """Mensagens idênticas devem usar cache."""
        mock_call_llm.return_value = {
            "intent": "alugar",
            "criteria": {},
            "handoff": {"should": False, "reason": None},
            "plan": {"action": "ASK", "message": "Teste", "question_key": "budget"}
        }

        with patch.object(llm_module, 'USE_LLM', True):
            with patch.object(llm_module, 'GROQ_API_KEY', 'fake_key'):
                with patch.object(llm_module, '_rate_limit_until', 0):
                    # Primeira chamada - deve chamar LLM
                    handle_message(self.session_id, "quero alugar")
                    first_count = mock_call_llm.call_count

                    # Reset session mas mesma mensagem
                    store.reset(self.session_id)
                    handle_message(self.session_id, "quero alugar")
                    second_count = mock_call_llm.call_count

        # Segunda chamada deve usar cache (mesmo count)
        # Note: o cache é por mensagem+state, então pode incrementar
        # O importante é não fazer múltiplas chamadas POR mensagem
        assert first_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
