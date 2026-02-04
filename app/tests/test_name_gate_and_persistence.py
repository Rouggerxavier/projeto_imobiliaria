import json
import uuid
from unittest.mock import patch, MagicMock

from agent.controller import handle_message
from agent.state import store
from agent import llm as llm_module, rules as rules_module, controller as controller_module
from agent import persistence


def triage_patches():
    return [
        patch.object(llm_module, "TRIAGE_ONLY", True),
        patch.object(rules_module, "TRIAGE_ONLY", True),
        patch.object(controller_module, "TRIAGE_ONLY", True),
    ]


def stub_decision():
    return {
        "intent": None,
        "criteria": {},
        "extracted_updates": {},
        "handoff": {"should": False},
        "plan": {"action": "ASK", "message": ""},
    }


def test_name_gate_then_persist(tmp_path, monkeypatch):
    leads_path = tmp_path / "leads.jsonl"
    index_path = tmp_path / "leads_index.json"
    events_path = tmp_path / "events.jsonl"
    monkeypatch.setattr(persistence, "LEADS_PATH", str(leads_path))
    monkeypatch.setattr(persistence, "LEADS_INDEX_PATH", str(index_path))
    monkeypatch.setattr(persistence, "EVENTS_PATH", str(events_path))
    monkeypatch.setattr(persistence, "PERSIST_RAW_TEXT", False)

    session = "name_gate"
    store.reset(session)

    # Preenche todos os críticos menos nome
    state = store.get(session)
    state.intent = "comprar"
    state.set_criterion("city", "Joao Pessoa")
    state.set_criterion("neighborhood", "Manaira")
    state.set_criterion("property_type", "apartamento")
    state.set_criterion("bedrooms", 3)
    state.set_criterion("parking", 1)
    state.set_criterion("budget", 900000)
    state.set_criterion("timeline", "3m")

    p1, p2, p3 = triage_patches()
    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.controller.get_agent") as mock_get_agent, \
         patch("agent.tools.get_neighborhoods", return_value=["Manaira"]), \
         p1, p2, p3:
        stub_agent = MagicMock()
        stub_agent.decide.return_value = (stub_decision(), False)
        mock_get_agent.return_value = stub_agent

        # Turno 1: saudação genérica
        resp = handle_message(session, "oi", correlation_id="t0")
        # Turno 2 - deve pedir nome e não concluir
        resp = handle_message(session, "ok", correlation_id="t1")
        assert "nome" in resp["reply"].lower()
        assert "summary" not in resp

        # Turno 3 com nome - deve concluir e persistir
        resp2 = handle_message(session, "Meu nome é João Silva", correlation_id="t2")
        assert resp2.get("summary"), "Deve concluir após receber o nome"
        assert resp2["state"]["completed"] is True

    # Verifica leads.jsonl
    with open(leads_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) >= 1
    lead_obj = json.loads(lines[-1])
    assert lead_obj["lead_profile"]["name"].lower().startswith("joão") or lead_obj["lead_profile"]["name"].lower().startswith("joao")
    assert "lead_score" in lead_obj and "quality_score" in lead_obj

    # Index atualizado
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    found = False
    for k, ids in index.items():
        if "joao" in k:
            found = lead_obj["lead_id"] in ids
            if found:
                break
    assert found, "lead_id deve estar indexado pelo nome"

    # Sem raw_text
    triage_fields = lead_obj.get("triage_fields", {})
    for v in triage_fields.values():
        if isinstance(v, dict):
            assert "raw_text" not in v


def test_hot_lead_generates_event(tmp_path, monkeypatch):
    leads_path = tmp_path / "leads.jsonl"
    index_path = tmp_path / "leads_index.json"
    events_path = tmp_path / "events.jsonl"
    monkeypatch.setattr(persistence, "LEADS_PATH", str(leads_path))
    monkeypatch.setattr(persistence, "LEADS_INDEX_PATH", str(index_path))
    monkeypatch.setattr(persistence, "EVENTS_PATH", str(events_path))
    monkeypatch.setattr(persistence, "PERSIST_RAW_TEXT", False)

    session = "hot_lead"
    store.reset(session)
    state = store.get(session)
    state.intent = "comprar"
    state.set_criterion("city", "Joao Pessoa")
    state.set_criterion("neighborhood", "Manaira")
    state.set_criterion("property_type", "apartamento")
    state.set_criterion("bedrooms", 3)
    state.set_criterion("parking", 2)
    state.set_criterion("budget", 1_200_000)
    state.set_criterion("timeline", "30d")
    state.lead_profile["name"] = "Maria"

    p1, p2, p3 = triage_patches()
    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.controller.get_agent") as mock_get_agent, \
         patch("agent.tools.get_neighborhoods", return_value=["Manaira"]), \
         p1, p2, p3:
        stub_agent = MagicMock()
        stub_agent.decide.return_value = (stub_decision(), False)
        mock_get_agent.return_value = stub_agent

        resp = handle_message(session, "fechar rápido", correlation_id="hot1")
        assert resp.get("summary")

    # Evento HOT_LEAD
    with open(events_path, "r", encoding="utf-8") as f:
        events_lines = f.readlines()
    assert len(events_lines) == 1
    event = json.loads(events_lines[0])
    assert event["type"] == "HOT_LEAD"
    assert event["name"] == "Maria"
