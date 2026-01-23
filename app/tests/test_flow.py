from agent.controller import handle_message
from agent.state import store


def test_happy_path_rent_manaira():
    session = "t1"
    store.reset(session)
    resp = handle_message(session, "quero alugar um ape em Manaíra até 3 mil, 2 quartos")
    assert resp["state"]["intent"] == "alugar"
    assert "Manaira" in resp["reply"]
    assert resp.get("properties")


def test_missing_location_triggers_question():
    session = "t2"
    store.reset(session)
    resp = handle_message(session, "quero alugar por 2000 um apartamento")
    assert "Qual cidade" in resp["reply"]


def test_zero_results_handles_gracefully():
    session = "t3"
    store.reset(session)
    resp = handle_message(session, "quero alugar casa em Manaíra até 500")
    assert "Não encontrei" in resp["reply"]
