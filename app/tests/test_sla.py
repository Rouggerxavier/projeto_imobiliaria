"""
Testes para SLA Policy - Service Level Agreements e Fluxo Diferenciado
"""

import pytest
from app.agent.state import SessionState
from app.agent.sla import (
    classify_lead,
    compute_sla_action,
    get_sla_message,
    should_emit_hot_event,
    build_hot_lead_event,
    get_thresholds_info,
    HOT_THRESHOLD,
    WARM_THRESHOLD,
)


def test_classify_lead_hot():
    """Cenário 1: lead_score >= 80 deve classificar como HOT."""
    state = SessionState(session_id="test-hot-1")

    # Teste com score exatamente no limiar
    assert classify_lead(80, state) == "HOT"
    assert classify_lead(HOT_THRESHOLD, state) == "HOT"

    # Teste com score acima do limiar
    assert classify_lead(85, state) == "HOT"
    assert classify_lead(95, state) == "HOT"
    assert classify_lead(100, state) == "HOT"


def test_classify_lead_warm():
    """Cenário 2: lead_score 50-79 deve classificar como WARM."""
    state = SessionState(session_id="test-warm-1")

    # Teste com score no limiar inferior
    assert classify_lead(50, state) == "WARM"
    assert classify_lead(WARM_THRESHOLD, state) == "WARM"

    # Teste com score no meio do intervalo
    assert classify_lead(60, state) == "WARM"
    assert classify_lead(65, state) == "WARM"
    assert classify_lead(70, state) == "WARM"

    # Teste com score no limiar superior
    assert classify_lead(79, state) == "WARM"


def test_classify_lead_cold():
    """Cenário 3: lead_score < 50 deve classificar como COLD."""
    state = SessionState(session_id="test-cold-1")

    # Teste com scores baixos
    assert classify_lead(0, state) == "COLD"
    assert classify_lead(10, state) == "COLD"
    assert classify_lead(30, state) == "COLD"
    assert classify_lead(49, state) == "COLD"


def test_compute_sla_action_hot():
    """Testa ação SLA para lead HOT."""
    state = SessionState(session_id="test-hot-action")

    sla_action = compute_sla_action("HOT", "A", state)

    assert sla_action["sla_type"] == "immediate"
    assert sla_action["priority"] is True
    assert sla_action["should_emit_hot_event"] is True  # Primeira vez
    assert sla_action["message_template"] == "hot"
    assert sla_action["routing_strategy"] == "priority"


def test_compute_sla_action_warm():
    """Testa ação SLA para lead WARM."""
    state = SessionState(session_id="test-warm-action")

    sla_action = compute_sla_action("WARM", "B", state)

    assert sla_action["sla_type"] == "normal"
    assert sla_action["priority"] is False
    assert sla_action["should_emit_hot_event"] is False
    assert sla_action["message_template"] == "warm"
    assert sla_action["routing_strategy"] == "normal"


def test_compute_sla_action_cold_handoff():
    """Testa ação SLA para lead COLD com qualidade boa (handoff)."""
    state = SessionState(session_id="test-cold-handoff")

    # COLD com quality A ou B -> handoff normal
    sla_action = compute_sla_action("COLD", "A", state)

    assert sla_action["sla_type"] == "normal"
    assert sla_action["priority"] is False
    assert sla_action["should_emit_hot_event"] is False
    assert sla_action["message_template"] == "cold_handoff"
    assert sla_action["routing_strategy"] == "normal"


def test_compute_sla_action_cold_nurture():
    """Testa ação SLA para lead COLD com qualidade baixa (nutrição)."""
    state = SessionState(session_id="test-cold-nurture")

    # COLD com quality C ou D -> nutrição
    sla_action = compute_sla_action("COLD", "C", state)

    assert sla_action["sla_type"] == "nurture"
    assert sla_action["priority"] is False
    assert sla_action["should_emit_hot_event"] is False
    assert sla_action["message_template"] == "cold_nurture"
    assert sla_action["routing_strategy"] == "delayed"


def test_get_sla_message_hot():
    """Testa mensagem SLA para HOT lead."""
    # Sem nome de corretor
    message = get_sla_message("hot")
    assert "acionei" in message.lower()
    assert "instantes" in message.lower()

    # Com nome de corretor
    message_with_name = get_sla_message("hot", agent_name="João Silva")
    assert "João Silva" in message_with_name
    assert "acionei" in message_with_name.lower()

    # Com contato exposto
    message_with_contact = get_sla_message("hot", agent_name="João Silva", expose_contact=True, agent_whatsapp="+5583999991234")
    assert "+5583999991234" in message_with_contact


def test_get_sla_message_warm():
    """Testa mensagem SLA para WARM lead."""
    message = get_sla_message("warm")
    assert "corretor" in message.lower()
    assert "breve" in message.lower()

    message_with_name = get_sla_message("warm", agent_name="Maria Santos")
    assert "Maria Santos" in message_with_name


def test_get_sla_message_cold():
    """Testa mensagens SLA para COLD lead."""
    # Cold handoff
    message_handoff = get_sla_message("cold_handoff")
    assert "corretor" in message_handoff.lower()

    # Cold nurture
    message_nurture = get_sla_message("cold_nurture")
    assert "informado" in message_nurture.lower() or "anotei" in message_nurture.lower()


def test_should_emit_hot_event_first_time():
    """Testa emissão de HOT_LEAD na primeira vez."""
    state = SessionState(session_id="test-emit-first")
    state.hot_lead_emitted = False

    assert should_emit_hot_event(state, "HOT") is True


def test_should_emit_hot_event_already_emitted():
    """Cenário 4: hot_lead_emitted=True deve evitar emissão duplicada."""
    state = SessionState(session_id="test-emit-duplicate")
    state.hot_lead_emitted = True

    # Não deve emitir novamente
    assert should_emit_hot_event(state, "HOT") is False


def test_should_emit_hot_event_not_hot():
    """Testa que não emite evento para leads WARM/COLD."""
    state = SessionState(session_id="test-emit-not-hot")
    state.hot_lead_emitted = False

    assert should_emit_hot_event(state, "WARM") is False
    assert should_emit_hot_event(state, "COLD") is False


def test_build_hot_lead_event():
    """Testa construção do payload HOT_LEAD."""
    state = SessionState(session_id="test-event-build")
    state.intent = "comprar"
    state.set_criterion("city", "João Pessoa", status="confirmed")
    state.set_criterion("neighborhood", "Manaíra", status="confirmed")
    state.set_criterion("budget", 900000, status="confirmed")
    state.set_criterion("bedrooms", 3, status="confirmed")
    state.lead_profile["name"] = "Carlos Lima"
    state.lead_profile["phone"] = "+5583999998888"

    agent_info = {
        "id": "agent_senior",
        "name": "Maria Senior",
        "score": 95
    }

    event = build_hot_lead_event(
        lead_id="lead-123",
        session_state=state,
        lead_score=85,
        quality_grade="A",
        assigned_agent=agent_info,
        timestamp=1234567890.0
    )

    # Verificar estrutura do evento
    assert event["type"] == "HOT_LEAD"
    assert event["lead_id"] == "lead-123"
    assert event["session_id"] == "test-event-build"
    assert event["lead_score"] == 85
    assert event["lead_class"] == "HOT"
    assert event["quality_grade"] == "A"
    assert event["sla"] == "immediate"
    assert event["timestamp"] == 1234567890.0

    # Verificar perfil do lead
    assert event["lead_profile"]["name"] == "Carlos Lima"
    assert event["lead_profile"]["phone"] == "+5583999998888"

    # Verificar critérios
    assert event["criteria"]["intent"] == "comprar"
    assert event["criteria"]["city"] == "João Pessoa"
    assert event["criteria"]["neighborhood"] == "Manaíra"
    assert event["criteria"]["budget"] == 900000
    assert event["criteria"]["bedrooms"] == 3

    # Verificar agente atribuído
    assert event["assigned_agent"]["id"] == "agent_senior"
    assert event["assigned_agent"]["name"] == "Maria Senior"


def test_build_hot_lead_event_no_agent():
    """Testa evento HOT_LEAD sem corretor atribuído (queue priority)."""
    state = SessionState(session_id="test-event-no-agent")
    state.intent = "alugar"
    state.set_criterion("city", "João Pessoa", status="confirmed")
    state.set_criterion("neighborhood", "Cabo Branco", status="confirmed")
    state.set_criterion("budget", 4000, status="confirmed")

    event = build_hot_lead_event(
        lead_id="lead-456",
        session_state=state,
        lead_score=90,
        quality_grade="B",
        assigned_agent=None
    )

    # Deve ter queue priority quando não há agente
    assert event["assigned_agent"] == {"queue": "priority"}


def test_get_thresholds_info():
    """Testa retorno de thresholds configurados."""
    info = get_thresholds_info()

    assert "HOT_THRESHOLD" in info
    assert "WARM_THRESHOLD" in info
    assert "COLD_RANGE" in info

    # Verificar valores padrão ou de env
    assert info["HOT_THRESHOLD"] == HOT_THRESHOLD
    assert info["WARM_THRESHOLD"] == WARM_THRESHOLD
    assert isinstance(info["COLD_RANGE"], str)


def test_sla_integration_hot_lead():
    """Teste de integração: lead com score 85 deve ser HOT com SLA immediate."""
    state = SessionState(session_id="test-integration-hot")
    state.intent = "comprar"
    state.set_criterion("city", "João Pessoa", status="confirmed")
    state.set_criterion("neighborhood", "Manaíra", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="confirmed")
    state.set_criterion("bedrooms", 3, status="confirmed")
    state.set_criterion("parking", 2, status="confirmed")
    state.set_criterion("budget", 800000, status="confirmed")
    state.set_criterion("timeline", "30d", status="confirmed")
    state.lead_profile["name"] = "Ana Paula"

    # Simular lead_score calculado
    lead_score = 85

    # Classificar
    lead_class = classify_lead(lead_score, state)
    assert lead_class == "HOT"

    # Computar ação SLA
    sla_action = compute_sla_action(lead_class, "A", state)
    assert sla_action["sla_type"] == "immediate"
    assert sla_action["priority"] is True

    # Verificar que deve emitir evento
    assert should_emit_hot_event(state, lead_class) is True

    # Simular emissão
    event = build_hot_lead_event("lead-789", state, lead_score, "A")
    assert event["type"] == "HOT_LEAD"
    assert event["lead_score"] == 85

    # Marcar como emitido
    state.hot_lead_emitted = True

    # Verificar proteção contra duplicata
    assert should_emit_hot_event(state, lead_class) is False


def test_sla_integration_warm_lead():
    """Teste de integração: lead com score 60 deve ser WARM com SLA normal."""
    state = SessionState(session_id="test-integration-warm")
    state.intent = "alugar"
    state.set_criterion("city", "João Pessoa", status="confirmed")
    state.set_criterion("neighborhood", "Tambaú", status="confirmed")
    state.set_criterion("budget", 3000, status="confirmed")
    state.set_criterion("timeline", "6m", status="confirmed")

    lead_score = 60

    lead_class = classify_lead(lead_score, state)
    assert lead_class == "WARM"

    sla_action = compute_sla_action(lead_class, "B", state)
    assert sla_action["sla_type"] == "normal"
    assert sla_action["priority"] is False

    # WARM não emite HOT_LEAD
    assert should_emit_hot_event(state, lead_class) is False


def test_sla_integration_cold_lead():
    """Teste de integração: lead com score 30 deve ser COLD."""
    state = SessionState(session_id="test-integration-cold")
    state.intent = "alugar"
    state.set_criterion("city", "João Pessoa", status="inferred")
    state.set_criterion("budget", 2000, status="confirmed")

    lead_score = 30

    lead_class = classify_lead(lead_score, state)
    assert lead_class == "COLD"

    # COLD com qualidade C -> nutrição
    sla_action = compute_sla_action(lead_class, "C", state)
    assert sla_action["sla_type"] == "nurture"
    assert sla_action["priority"] is False

    # COLD não emite HOT_LEAD
    assert should_emit_hot_event(state, lead_class) is False
