"""
Testes para suporte a ranges de orçamento (budget_min/budget_max).

Verifica que:
1. Ranges explícitos são detectados corretamente ("entre X e Y")
2. Valores min/max são separados sem gerar conflito
3. Padrões "até X" e "a partir de X" funcionam
4. Conflitos reais são detectados (ex: max < min)
"""

import pytest
from app.agent.extractor import parse_budget_range, extract_criteria


class TestParseBudgetRange:
    """Testes para a função parse_budget_range()."""

    def test_range_entre_x_e_y(self):
        """Cenário 1: 'entre 800 mil a 1 milhão e 200 mil' -> min=800k, max=1.2M."""
        result = parse_budget_range("entre 800 mil a 1 milhão e 200 mil")
        assert result["budget_min"] == 800_000
        assert result["budget_max"] == 1_200_000
        assert result["is_range"] is True

    def test_range_de_x_a_y(self):
        """Cenário 2: 'de 900k a 1.1m' -> min=900k, max=1.1M."""
        result = parse_budget_range("de 900k a 1.1m")
        assert result["budget_min"] == 900_000
        assert result["budget_max"] == 1_100_000
        assert result["is_range"] is True

    def test_range_x_a_y(self):
        """Padrão 'X a Y' sem 'de'."""
        result = parse_budget_range("800 mil a 1 milhão")
        assert result["budget_min"] == 800_000
        assert result["budget_max"] == 1_000_000
        assert result["is_range"] is True

    def test_range_x_ate_y(self):
        """Padrão 'X até Y'."""
        result = parse_budget_range("700 mil até 1.2 milhão")
        assert result["budget_min"] == 700_000
        assert result["budget_max"] == 1_200_000
        assert result["is_range"] is True

    def test_range_x_dash_y(self):
        """Padrão 'X - Y' com hífen."""
        result = parse_budget_range("900 mil - 1.5 milhão")
        assert result["budget_min"] == 900_000
        assert result["budget_max"] == 1_500_000
        assert result["is_range"] is True

    def test_range_x_tilde_y(self):
        """Padrão 'X~Y' com til."""
        result = parse_budget_range("850k ~ 1.2m")
        assert result["budget_min"] == 850_000
        assert result["budget_max"] == 1_200_000
        assert result["is_range"] is True

    def test_range_inverted_values(self):
        """Range com valores invertidos (max antes de min) deve ser corrigido."""
        result = parse_budget_range("entre 1.2 milhão e 800 mil")
        assert result["budget_min"] == 800_000
        assert result["budget_max"] == 1_200_000
        assert result["is_range"] is True

    def test_only_max_ate(self):
        """Cenário 3: 'até 1 milhão' -> max=1M, min=None."""
        result = parse_budget_range("até 1 milhão")
        assert result["budget_min"] is None
        assert result["budget_max"] == 1_000_000
        assert result["is_range"] is False

    def test_only_max_maximo(self):
        """'máximo 900k' -> max=900k."""
        result = parse_budget_range("máximo 900k")
        assert result["budget_min"] is None
        assert result["budget_max"] == 900_000
        assert result["is_range"] is False

    def test_only_max_teto(self):
        """'teto de 1.5 milhão' -> max=1.5M."""
        result = parse_budget_range("teto de 1.5 milhão")
        assert result["budget_min"] is None
        assert result["budget_max"] == 1_500_000
        assert result["is_range"] is False

    def test_only_min_a_partir_de(self):
        """Cenário 4: 'a partir de 700 mil' -> min=700k, max=None."""
        result = parse_budget_range("a partir de 700 mil")
        assert result["budget_min"] == 700_000
        assert result["budget_max"] is None
        assert result["is_range"] is False

    def test_only_min_minimo(self):
        """'mínimo 800 mil' -> min=800k."""
        result = parse_budget_range("mínimo 800 mil")
        assert result["budget_min"] == 800_000
        assert result["budget_max"] is None
        assert result["is_range"] is False

    def test_only_min_pelo_menos(self):
        """'pelo menos 600k' -> min=600k."""
        result = parse_budget_range("pelo menos 600k")
        assert result["budget_min"] == 600_000
        assert result["budget_max"] is None
        assert result["is_range"] is False

    def test_single_value_generic(self):
        """Valor único sem contexto -> budget_max (comportamento legado)."""
        result = parse_budget_range("R$ 1.200.000")
        assert result["budget_min"] is None
        assert result["budget_max"] == 1_200_000
        assert result["is_range"] is False

    def test_single_value_mil(self):
        """'900 mil' -> budget_max=900k."""
        result = parse_budget_range("900 mil")
        assert result["budget_min"] is None
        assert result["budget_max"] == 900_000
        assert result["is_range"] is False

    def test_multiple_values_implicit_range(self):
        """Múltiplos valores sem padrão explícito -> range implícito."""
        result = parse_budget_range("busco algo por 800 mil mas aceito até 1 milhão")
        assert result["budget_min"] == 800_000
        assert result["budget_max"] == 1_000_000
        assert result["is_range"] is True

    def test_no_budget_found(self):
        """Sem valores monetários -> retorna vazio."""
        result = parse_budget_range("Quero um apartamento em Manaíra")
        assert result["budget_min"] is None
        assert result["budget_max"] is None
        assert result["is_range"] is False
        assert result["raw_matches"] == []


class TestExtractCriteriaWithRange:
    """Testes para extract_criteria() usando ranges."""

    def test_extract_range_sets_both_fields(self):
        """extract_criteria deve retornar budget, budget_min e budget_is_range."""
        result = extract_criteria("entre 800 mil e 1 milhão e 200 mil", [])
        assert result.get("budget") == 1_200_000  # budget_max
        assert result.get("budget_min") == 800_000
        assert result.get("budget_is_range") is True

    def test_extract_only_max(self):
        """'até 1 milhão' deve retornar apenas budget (max)."""
        result = extract_criteria("até 1 milhão", [])
        assert result.get("budget") == 1_000_000
        assert result.get("budget_min") is None
        assert result.get("budget_is_range") is False or "budget_is_range" not in result

    def test_extract_only_min(self):
        """'a partir de 700 mil' deve retornar apenas budget_min."""
        result = extract_criteria("a partir de 700 mil", [])
        assert result.get("budget_min") == 700_000
        # budget_max pode não existir ou ser None
        assert result.get("budget") is None or "budget" not in result


class TestBudgetRangeIntegration:
    """Testes de integração com SessionState."""

    def test_range_no_conflict_on_apply_updates(self):
        """
        Range válido não deve gerar conflito ao aplicar updates.
        """
        from app.agent.state import SessionState

        state = SessionState(session_id="test-range")

        # Simular update com range
        updates = {
            "budget": {"value": 1_200_000, "status": "confirmed", "source": "user"},
            "budget_min": {"value": 800_000, "status": "confirmed", "source": "user"},
            "budget_is_range": {"value": True, "status": "confirmed", "source": "user"},
        }

        conflicts, conflict_values = state.apply_updates(updates)

        # Não deve haver conflito
        assert len(conflicts) == 0
        assert state.criteria.budget == 1_200_000
        assert state.criteria.budget_min == 800_000

    def test_conflict_when_new_max_below_existing_min(self):
        """
        Cenário 5: Range 800k-1.2M existente, usuário diz 'máximo 600k' -> conflito real.
        """
        from app.agent.state import SessionState

        state = SessionState(session_id="test-conflict")

        # Configurar range existente
        state.set_criterion("budget_min", 800_000, status="confirmed", source="user")
        state.set_criterion("budget", 1_200_000, status="confirmed", source="user")

        # Tentar atualizar budget_max para valor menor que budget_min
        updates = {
            "budget": {"value": 600_000, "status": "confirmed", "source": "user"},
        }

        conflicts, conflict_values = state.apply_updates(updates)

        # Deve detectar conflito
        assert "budget" in conflicts
        assert conflict_values["budget"]["previous"] == 1_200_000
        assert conflict_values["budget"]["new"] == 600_000

    def test_no_conflict_updating_max_within_range(self):
        """
        Atualizar budget_max para valor >= budget_min não deve gerar conflito.
        """
        from app.agent.state import SessionState

        state = SessionState(session_id="test-update")

        # Configurar budget_min
        state.set_criterion("budget_min", 800_000, status="confirmed", source="user")

        # Atualizar budget_max para valor válido (> min)
        updates = {
            "budget": {"value": 1_000_000, "status": "confirmed", "source": "user"},
        }

        conflicts, conflict_values = state.apply_updates(updates)

        # Não deve haver conflito
        assert len(conflicts) == 0
        assert state.criteria.budget == 1_000_000
        assert state.criteria.budget_min == 800_000


class TestBudgetFormatting:
    """Testes para formatação de valores monetários."""

    def test_format_budget_thousands(self):
        """Valores abaixo de 1M devem usar pontos."""
        from app.agent.controller import _format_budget

        assert _format_budget(800_000) == "R$ 800.000"
        assert _format_budget(950_000) == "R$ 950.000"

    def test_format_budget_millions_int(self):
        """Valores em milhões inteiros."""
        from app.agent.controller import _format_budget

        assert _format_budget(1_000_000) == "R$ 1 milhão"
        assert _format_budget(2_000_000) == "R$ 2 milhões"

    def test_format_budget_millions_decimal(self):
        """Valores em milhões com decimais."""
        from app.agent.controller import _format_budget

        assert _format_budget(1_200_000) == "R$ 1.2 milhões"
        assert _format_budget(1_500_000) == "R$ 1.5 milhões"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
