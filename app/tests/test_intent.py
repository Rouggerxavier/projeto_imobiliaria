from agent.intent import classify_intent


def test_intent_rent():
    assert classify_intent("quero alugar um apartamento") == "alugar"


def test_intent_buy():
    assert classify_intent("busco comprar casa no bessa") == "comprar"


def test_intent_invest():
    assert classify_intent("procuro investir em studio para renda") == "investir"
