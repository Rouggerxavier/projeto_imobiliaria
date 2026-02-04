"""
Testes para o sistema de roteamento de leads (Lead Router).

Valida pontuação, seleção, capacidade, persistência e casos edge.
"""

import os
import sys
import json
from pathlib import Path

# Setup path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.router import (
    load_agents,
    load_stats,
    save_stats,
    score_agent,
    choose_agent,
    route_lead,
    Agent,
    AgentStats,
)
from agent.state import SessionState, LeadScore


def create_test_agents(tmp_path: Path) -> Path:
    """Cria arquivo de agentes para teste."""
    agents_data = [
        {
            "id": "agent_senior",
            "name": "Maria Senior",
            "whatsapp": "+5583999991111",
            "active": True,
            "ops": ["buy", "rent"],
            "coverage_neighborhoods": ["Manaíra", "Tambaú"],
            "micro_location_tags": ["beira-mar", "orla"],
            "price_min": 500000,
            "price_max": 3000000,
            "specialties": ["alto_padrao", "orla"],
            "daily_capacity": 20,
            "priority_tier": "senior"
        },
        {
            "id": "agent_standard",
            "name": "João Standard",
            "whatsapp": "+5583999992222",
            "active": True,
            "ops": ["buy", "rent"],
            "coverage_neighborhoods": ["Cabo Branco", "Bessa"],
            "micro_location_tags": ["1_quadra", "2-3_quadras"],
            "price_min": 200000,
            "price_max": 1000000,
            "specialties": ["familia"],
            "daily_capacity": 25,
            "priority_tier": "standard"
        },
        {
            "id": "agent_junior",
            "name": "Ana Junior",
            "whatsapp": "+5583999993333",
            "active": True,
            "ops": ["rent"],
            "coverage_neighborhoods": [],
            "micro_location_tags": [],
            "price_min": 0,
            "price_max": 5000,
            "specialties": ["generalista"],
            "daily_capacity": 30,
            "priority_tier": "junior"
        },
        {
            "id": "agent_inactive",
            "name": "Carlos Inactive",
            "whatsapp": "+5583999994444",
            "active": False,
            "ops": ["buy"],
            "coverage_neighborhoods": ["Manaíra"],
            "micro_location_tags": [],
            "price_min": 0,
            "price_max": 999999999,
            "specialties": [],
            "daily_capacity": 10,
            "priority_tier": "standard"
        }
    ]

    agents_path = tmp_path / "agents.json"
    with open(agents_path, "w", encoding="utf-8") as f:
        json.dump(agents_data, f, indent=2)

    return agents_path


def create_test_stats(tmp_path: Path, initial_stats: dict = None) -> Path:
    """Cria arquivo de stats para teste."""
    stats_data = {
        "last_reset_date": "2026-02-04",
        "agents": initial_stats or {
            "agent_senior": {"assigned_today": 0, "last_assigned_at": None},
            "agent_standard": {"assigned_today": 0, "last_assigned_at": None},
            "agent_junior": {"assigned_today": 0, "last_assigned_at": None},
            "agent_inactive": {"assigned_today": 0, "last_assigned_at": None},
        }
    }

    stats_path = tmp_path / "agent_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats_data, f, indent=2)

    return stats_path


def test_load_agents(tmp_path):
    """Teste A: Carrega agentes do arquivo JSON."""
    agents_path = create_test_agents(tmp_path)
    agents = load_agents(str(agents_path))

    assert len(agents) == 4
    assert agents[0].id == "agent_senior"
    assert agents[0].active is True
    assert agents[3].id == "agent_inactive"
    assert agents[3].active is False


def test_hot_lead_senior_agent(tmp_path):
    """
    Teste B: Lead hot em Manaíra/orla com budget 1M e 3 quartos
    deve escolher corretor senior com coverage Manaíra + micro_location orla.
    """
    agents_path = create_test_agents(tmp_path)
    stats_path = create_test_stats(tmp_path)

    # Cria lead hot
    state = SessionState(session_id="test_hot")
    state.intent = "comprar"
    state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
    state.set_triage_field("neighborhood", "Manaíra", status="confirmed", source="user")
    state.set_triage_field("micro_location", "beira-mar", status="confirmed", source="user")
    state.set_triage_field("property_type", "apartamento", status="confirmed", source="user")
    state.set_triage_field("bedrooms", 3, status="confirmed", source="user")
    state.set_triage_field("parking", 2, status="confirmed", source="user")
    state.set_triage_field("budget", 1000000, status="confirmed", source="user")
    state.set_triage_field("timeline", "3m", status="confirmed", source="user")
    state.lead_score = LeadScore(temperature="hot", score=85, reasons=["budget_high"])

    # Roteia
    result = route_lead(state, str(agents_path), str(stats_path), correlation_id="test_hot")

    assert result is not None
    assert result.agent_id == "agent_senior"
    assert result.agent_name == "Maria Senior"
    assert result.score > 50  # Deve ter score alto
    assert "neighborhood_match" in str(result.reasons).lower()
    assert "micro_location_match" in str(result.reasons).lower() or "beira-mar" in str(result.reasons).lower()
    assert result.fallback is False

    # Verifica que stats foi atualizado
    stats = load_stats(str(stats_path))
    assert stats["agent_senior"].assigned_today == 1
    assert stats["agent_senior"].last_assigned_at is not None


def test_cold_lead_generalista(tmp_path):
    """
    Teste C: Lead cold sem bairro/budget definido
    deve escolher corretor generalista/junior.
    """
    agents_path = create_test_agents(tmp_path)
    stats_path = create_test_stats(tmp_path)

    # Cria lead cold sem detalhes
    state = SessionState(session_id="test_cold")
    state.intent = "alugar"
    state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
    state.set_triage_field("property_type", "apartamento", status="confirmed", source="user")
    state.set_triage_field("bedrooms", 2, status="confirmed", source="user")
    state.set_triage_field("parking", 1, status="confirmed", source="user")
    state.set_triage_field("timeline", "flexivel", status="confirmed", source="user")
    # Sem neighborhood, sem budget
    state.lead_score = LeadScore(temperature="cold", score=20, reasons=["no_budget"])

    # Roteia
    result = route_lead(state, str(agents_path), str(stats_path), correlation_id="test_cold")

    assert result is not None
    # Deve escolher junior generalista
    assert result.agent_id == "agent_junior"
    assert "generalista" in str(result.reasons).lower() or "cold_junior" in str(result.reasons).lower()


def test_capacity_reached(tmp_path):
    """
    Teste D: Se agent.daily_capacity=1 e assigned_today=1,
    deve escolher próximo melhor agente.
    """
    agents_path = create_test_agents(tmp_path)

    # Agent senior já atingiu capacidade
    initial_stats = {
        "agent_senior": {"assigned_today": 20, "last_assigned_at": "2026-02-04T10:00:00Z"},
        "agent_standard": {"assigned_today": 0, "last_assigned_at": None},
        "agent_junior": {"assigned_today": 0, "last_assigned_at": None},
        "agent_inactive": {"assigned_today": 0, "last_assigned_at": None},
    }
    stats_path = create_test_stats(tmp_path, initial_stats)

    # Lead que normalmente iria para senior
    state = SessionState(session_id="test_capacity")
    state.intent = "comprar"
    state.set_triage_field("neighborhood", "Manaíra", status="confirmed", source="user")
    state.set_triage_field("micro_location", "beira-mar", status="confirmed", source="user")
    state.set_triage_field("budget", 1000000, status="confirmed", source="user")
    state.set_triage_field("bedrooms", 3, status="confirmed", source="user")
    state.set_triage_field("parking", 2, status="confirmed", source="user")
    state.set_triage_field("timeline", "3m", status="confirmed", source="user")
    state.lead_score = LeadScore(temperature="hot", score=85, reasons=[])

    # Roteia
    result = route_lead(state, str(agents_path), str(stats_path), correlation_id="test_capacity")

    assert result is not None
    # Deve escolher outro agente (não senior)
    assert result.agent_id != "agent_senior"

    # Stats do agente escolhido deve ter incrementado
    stats = load_stats(str(stats_path))
    assert stats[result.agent_id].assigned_today == 1


def test_persist_stats(tmp_path):
    """
    Teste E: Após escolher, agent_stats.json deve ser atualizado
    com assigned_today e last_assigned_at.
    """
    agents_path = create_test_agents(tmp_path)
    stats_path = create_test_stats(tmp_path)

    # Lead simples
    state = SessionState(session_id="test_persist")
    state.intent = "alugar"
    state.set_triage_field("neighborhood", "Cabo Branco", status="confirmed", source="user")
    state.set_triage_field("budget", 3000, status="confirmed", source="user")
    state.set_triage_field("bedrooms", 2, status="confirmed", source="user")
    state.set_triage_field("parking", 1, status="confirmed", source="user")
    state.set_triage_field("timeline", "3m", status="confirmed", source="user")
    state.lead_score = LeadScore(temperature="warm", score=50, reasons=[])

    # Roteia primeira vez
    result1 = route_lead(state, str(agents_path), str(stats_path), correlation_id="test_persist_1")
    assert result1 is not None

    agent1_id = result1.agent_id

    # Verifica stats
    stats = load_stats(str(stats_path))
    assert stats[agent1_id].assigned_today == 1
    assert stats[agent1_id].last_assigned_at is not None

    # Roteia segunda vez (mesmo agente ou outro)
    state2 = SessionState(session_id="test_persist2")
    state2.intent = "alugar"
    state2.set_triage_field("neighborhood", "Cabo Branco", status="confirmed", source="user")
    state2.set_triage_field("budget", 3500, status="confirmed", source="user")
    state2.set_triage_field("bedrooms", 3, status="confirmed", source="user")
    state2.set_triage_field("parking", 1, status="confirmed", source="user")
    state2.set_triage_field("timeline", "6m", status="confirmed", source="user")
    state2.lead_score = LeadScore(temperature="warm", score=50, reasons=[])

    result2 = route_lead(state2, str(agents_path), str(stats_path), correlation_id="test_persist_2")
    assert result2 is not None

    # Recarrega stats
    stats2 = load_stats(str(stats_path))
    # Deve ter pelo menos 1 atribuição
    total_assigned = sum(s.assigned_today for s in stats2.values())
    assert total_assigned == 2


def test_no_agents_graceful(tmp_path):
    """
    Teste F: Se agents.json não existe, router deve retornar None
    sem quebrar o endpoint (graceful degradation).
    """
    # Não cria agents.json
    stats_path = create_test_stats(tmp_path)
    fake_agents_path = str(tmp_path / "nonexistent.json")

    state = SessionState(session_id="test_noagents")
    state.intent = "comprar"
    state.set_triage_field("budget", 500000, status="confirmed", source="user")
    state.set_triage_field("bedrooms", 2, status="confirmed", source="user")
    state.set_triage_field("parking", 1, status="confirmed", source="user")
    state.set_triage_field("timeline", "3m", status="confirmed", source="user")
    state.lead_score = LeadScore(temperature="warm", score=50, reasons=[])

    result = route_lead(state, fake_agents_path, str(stats_path), correlation_id="test_noagents")

    # Deve retornar None graciosamente
    assert result is None


def test_inactive_agent_filtered(tmp_path):
    """
    Teste G: Agentes inativos (active=false) não devem ser selecionados.
    """
    agents_path = create_test_agents(tmp_path)
    stats_path = create_test_stats(tmp_path)

    agents = load_agents(str(agents_path))
    stats = load_stats(str(stats_path))

    # Cria lead que seria ideal para agent_inactive
    state = SessionState(session_id="test_inactive")
    state.intent = "comprar"
    state.set_triage_field("neighborhood", "Manaíra", status="confirmed", source="user")
    state.set_triage_field("budget", 800000, status="confirmed", source="user")
    state.set_triage_field("bedrooms", 3, status="confirmed", source="user")
    state.set_triage_field("parking", 2, status="confirmed", source="user")
    state.set_triage_field("timeline", "6m", status="confirmed", source="user")
    state.lead_score = LeadScore(temperature="hot", score=80, reasons=[])

    # Score do inativo deve ser negativo
    inactive_agent = next(a for a in agents if a.id == "agent_inactive")
    score, reasons = score_agent(inactive_agent, state, stats)
    assert score == -1000
    assert "agent_inactive" in reasons

    # Router não deve escolher inativo
    result = route_lead(state, str(agents_path), str(stats_path), correlation_id="test_inactive")
    assert result is not None
    assert result.agent_id != "agent_inactive"


def test_familia_specialty(tmp_path):
    """
    Teste H: Lead com 3+ quartos deve dar bônus para specialty "familia".
    """
    agents_path = create_test_agents(tmp_path)
    stats_path = create_test_stats(tmp_path)
    agents = load_agents(str(agents_path))
    stats = load_stats(str(stats_path))

    # Lead família (3 quartos)
    state = SessionState(session_id="test_familia")
    state.intent = "comprar"
    state.set_triage_field("neighborhood", "Cabo Branco", status="confirmed", source="user")
    state.set_triage_field("budget", 600000, status="confirmed", source="user")
    state.set_triage_field("bedrooms", 3, status="confirmed", source="user")
    state.set_triage_field("parking", 2, status="confirmed", source="user")
    state.set_triage_field("timeline", "6m", status="confirmed", source="user")
    state.lead_score = LeadScore(temperature="warm", score=60, reasons=[])

    # Agent standard tem specialty "familia" e coverage Cabo Branco
    standard_agent = next(a for a in agents if a.id == "agent_standard")
    score, reasons = score_agent(standard_agent, state, stats)

    assert score > 0
    assert "specialty_familia" in reasons or any("familia" in r for r in reasons)


def test_alto_padrao_specialty(tmp_path):
    """
    Teste I: Lead com budget >= 900k deve dar bônus para specialty "alto_padrao".
    """
    agents_path = create_test_agents(tmp_path)
    stats_path = create_test_stats(tmp_path)
    agents = load_agents(str(agents_path))
    stats = load_stats(str(stats_path))

    # Lead alto padrão
    state = SessionState(session_id="test_alto_padrao")
    state.intent = "comprar"
    state.set_triage_field("neighborhood", "Manaíra", status="confirmed", source="user")
    state.set_triage_field("budget", 1500000, status="confirmed", source="user")
    state.set_triage_field("bedrooms", 4, status="confirmed", source="user")
    state.set_triage_field("parking", 3, status="confirmed", source="user")
    state.set_triage_field("timeline", "6m", status="confirmed", source="user")
    state.lead_score = LeadScore(temperature="hot", score=90, reasons=[])

    # Agent senior tem specialty "alto_padrao"
    senior_agent = next(a for a in agents if a.id == "agent_senior")
    score, reasons = score_agent(senior_agent, state, stats)

    assert score > 0
    assert "specialty_alto_padrao" in reasons or any("alto_padrao" in r for r in reasons)


def test_round_robin_on_tie(tmp_path):
    """
    Teste J: Em caso de empate de score, deve escolher agente com menor assigned_today.
    """
    agents_path = create_test_agents(tmp_path)

    # Agent standard já recebeu 5 leads, junior recebeu 0
    initial_stats = {
        "agent_senior": {"assigned_today": 10, "last_assigned_at": "2026-02-04T09:00:00Z"},
        "agent_standard": {"assigned_today": 5, "last_assigned_at": "2026-02-04T10:00:00Z"},
        "agent_junior": {"assigned_today": 0, "last_assigned_at": None},
        "agent_inactive": {"assigned_today": 0, "last_assigned_at": None},
    }
    stats_path = create_test_stats(tmp_path, initial_stats)

    # Lead genérico que pode ir para standard ou junior
    state = SessionState(session_id="test_roundrobin")
    state.intent = "alugar"
    state.set_triage_field("budget", 2500, status="confirmed", source="user")
    state.set_triage_field("bedrooms", 2, status="confirmed", source="user")
    state.set_triage_field("parking", 1, status="confirmed", source="user")
    state.set_triage_field("timeline", "3m", status="confirmed", source="user")
    state.lead_score = LeadScore(temperature="cold", score=30, reasons=[])

    result = route_lead(state, str(agents_path), str(stats_path), correlation_id="test_roundrobin")

    assert result is not None
    # Deve preferir junior (assigned_today=0) sobre standard (assigned_today=5)
    assert result.agent_id == "agent_junior"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
