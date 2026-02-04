from unittest.mock import patch, MagicMock
from agent.controller import handle_message
from agent.state import store
from agent import llm as llm_module, rules as rules_module, controller as controller_module


def triage_patches():
    return [
        patch.object(llm_module, "TRIAGE_ONLY", True),
        patch.object(rules_module, "TRIAGE_ONLY", True),
        patch.object(controller_module, "TRIAGE_ONLY", True),
    ]


def test_no_repeat_intent_question_after_confirmed():
    session = "no_repeat_intent"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    # Stub LLM agent to no-op; rely on regex extraction
    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.controller.get_agent") as mock_get_agent, \
         patch("agent.tools.get_neighborhoods", return_value=["Manaira", "Cabo Branco"]), \
         patch("agent.extractor.extract_criteria") as mock_extract, \
         p1, p2, p3:

        mock_agent = MagicMock()
        mock_agent.decide.return_value = ({"intent": None, "criteria": {}, "extracted_updates": {}, "handoff": {"should": False}, "plan": {"action": "ASK", "message": ""}}, False)
        mock_get_agent.return_value = mock_agent

        # Primeira mensagem já traz intenção
        mock_extract.return_value = {
            "intent": "comprar",
            "neighborhood": "Manaira",
            "bedrooms": 3,
            "parking": 1,
            "budget": 800000,
        }
        resp1 = handle_message(session, "quero comprar apartamento em Manaira", correlation_id="t1")
        # Segunda mensagem adiciona cidade e prazo
        mock_extract.return_value = {"city": "Joao Pessoa", "timeline": "3m", "property_type": "apartamento"}
        resp2 = handle_message(session, "cidade joao pessoa e quero fechar em 3 meses", correlation_id="t2")

    combined_reply = (resp1["reply"] + " " + resp2["reply"]).lower()
    assert "comprar ou alugar" not in combined_reply

    state = store.get(session)
    assert state.intent == "comprar"
    assert state.asked_questions.count("intent") <= 1

