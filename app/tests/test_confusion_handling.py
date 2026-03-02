"""
Testes para detecção e tratamento de confusão do usuário
"""

import pytest
from app.agent.controller import handle_message
from app.agent.state import store


@pytest.fixture
def clear_session():
    """Limpa sessão entre testes"""
    session_id = "test_confusion_session"
    store.reset(session_id)
    yield session_id
    store.reset(session_id)


def test_user_asks_vagas_de_que(clear_session):
    """
    Caso: Bot pergunta "Quantas vagas?" → Usuário responde "vagas de que?"
    Esperado: Bot explica que é vagas de garagem e não avança para próximo campo
    """
    session_id = clear_session

    # Setup: chegar até a pergunta de vagas
    handle_message(session_id, "Oi")
    handle_message(session_id, "Quero comprar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Manaíra")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "3 quartos")

    # Agora deve perguntar sobre vagas
    # Usuário responde com confusão
    resp = handle_message(session_id, "vagas de que?")

    reply_lower = resp["reply"].lower()

    # Deve explicar que é vagas de garagem
    assert "garagem" in reply_lower or "estacionamento" in reply_lower or "carro" in reply_lower

    # NÃO deve ter pulado para orçamento
    assert "orçamento" not in reply_lower
    assert "preço" not in reply_lower

    # Deve ter explicado
    assert len(resp["reply"]) > 50  # Explicação não é muito curta


def test_user_asks_sondando(clear_session):
    """
    Caso: Bot pergunta sobre "pesquisando ou quer visitar?" → Usuário: "sondando?"
    Esperado: Bot explica o termo e re-pergunta
    """
    session_id = clear_session

    # Setup: chegar até intent_stage
    handle_message(session_id, "Oi")
    handle_message(session_id, "Quero alugar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Tambaú")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "2 quartos")
    handle_message(session_id, "1 vaga")
    handle_message(session_id, "até 3 mil")

    # Agora deve perguntar sobre timeline ou intent_stage
    # Simular confusão
    resp = handle_message(session_id, "sondando?")

    reply_lower = resp["reply"].lower()

    # Deve explicar o termo (pesquisando/urgência)
    assert (
        "pesquisando" in reply_lower
        or "pesquisa" in reply_lower
        or "pronto" in reply_lower
        or "visitar" in reply_lower
    )

    # Não deve ter marcado "sondando" como resposta válida
    state = store.get(session_id)
    assert not state.completed  # Não finalizou


def test_anti_loop_offers_options_after_2_attempts(clear_session):
    """
    Caso: Usuário não responde claramente 2 vezes → Bot oferece opções múltipla escolha
    Esperado: Após 2 tentativas falhadas, bot oferece opções estruturadas
    """
    session_id = clear_session

    # Setup: chegar até parking
    handle_message(session_id, "Oi")
    handle_message(session_id, "Quero comprar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Bessa")
    handle_message(session_id, "Casa")
    handle_message(session_id, "2 quartos")

    # Primeira tentativa: confusão
    resp1 = handle_message(session_id, "vagas?")
    assert "garagem" in resp1["reply"].lower()

    # Segunda tentativa: ainda confuso
    resp2 = handle_message(session_id, "não entendi")
    reply2_lower = resp2["reply"].lower()

    # Deve ter explicado novamente
    assert "garagem" in reply2_lower or "estacionamento" in reply2_lower

    # Terceira tentativa: deve oferecer opções
    resp3 = handle_message(session_id, "?")
    reply3_lower = resp3["reply"].lower()

    # Deve conter lista de opções
    assert "•" in resp3["reply"] or "1" in reply3_lower or "nenhuma" in reply3_lower
    # Pode conter "1 vaga", "2 vagas", etc.
    assert "vaga" in reply3_lower


def test_confusion_with_question_mark_only(clear_session):
    """
    Caso: Usuário responde apenas "?" ou "??" → Bot detecta confusão
    """
    session_id = clear_session

    # Setup
    handle_message(session_id, "Oi")
    handle_message(session_id, "Quero comprar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Cabo Branco")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "3 quartos")

    # Responde apenas com "?"
    resp = handle_message(session_id, "?")

    # Deve ter explicado ou oferecido ajuda
    assert len(resp["reply"]) > 30
    # Não deve ter avançado para outro campo crítico
    assert "orçamento" not in resp["reply"].lower() or "garagem" in resp["reply"].lower()


def test_vagas_question_not_saved_as_answer(clear_session):
    """
    Caso: Usuário pergunta "vagas de carro?" → NÃO deve ser salvo como resposta
    """
    session_id = clear_session

    # Setup: chegar até parking
    handle_message(session_id, "Oi")
    handle_message(session_id, "Quero comprar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Altiplano")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "4 quartos")

    # Pergunta meta: "vagas de carro?"
    resp = handle_message(session_id, "vagas de carro?")

    state = store.get(session_id)

    # NÃO deve ter salvo nada em parking
    assert not state.criteria.parking or state.criteria.parking == 0

    # Deve ter explicado
    assert "garagem" in resp["reply"].lower() or "estacionamento" in resp["reply"].lower()


def test_clear_answer_after_confusion_clears_flag(clear_session):
    """
    Caso: Usuário confuso, depois responde claramente → Flag de confusão é limpa
    """
    session_id = clear_session

    # Setup
    handle_message(session_id, "Oi")
    handle_message(session_id, "Quero alugar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Manaíra")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "2 quartos")

    # Confusão
    handle_message(session_id, "vagas??")

    state = store.get(session_id)
    assert state.awaiting_clarification  # Flag setado

    # Agora responde claramente
    handle_message(session_id, "2 vagas")

    state = store.get(session_id)

    # Flag deve estar limpo
    assert not state.awaiting_clarification
    # Parking deve estar salvo
    assert state.criteria.parking == 2


def test_confusion_detector_module_direct():
    """
    Testa o módulo confusion_detector diretamente
    """
    from app.agent.confusion_detector import detect_confusion
    from app.agent.state import SessionState

    state = SessionState(session_id="direct_test")
    state.last_question_key = "parking"

    # Testa detecção de meta-pergunta
    confusion = detect_confusion("vagas de carro?", state)
    assert confusion is not None
    assert confusion["is_confused"]
    assert confusion["type"] == "meta_question"
    assert confusion["field"] == "parking"

    # Testa detecção de "como assim"
    state.last_question_key = "timeline"
    confusion2 = detect_confusion("como assim?", state)
    assert confusion2 is not None
    assert confusion2["is_confused"]

    # Testa que resposta clara NÃO é detectada como confusão
    state.last_question_key = "bedrooms"
    confusion3 = detect_confusion("3 quartos", state)
    assert confusion3 is None


def test_offer_options_threshold():
    """
    Testa que opções são oferecidas apenas após limiar de tentativas
    """
    from app.agent.confusion_detector import should_offer_options

    # 1 tentativa: não oferece
    should, opts = should_offer_options("parking", 1)
    assert not should

    # 2 tentativas: ainda não
    should, opts = should_offer_options("parking", 2)
    assert should
    assert opts is not None
    assert len(opts) > 0
    assert "vaga" in str(opts).lower()


def test_formatted_options_message():
    """
    Testa formatação de mensagem com opções
    """
    from app.agent.confusion_detector import format_options_message

    options = ["1 vaga", "2 vagas", "3 ou mais"]
    message = format_options_message("parking", options)

    assert "•" in message or all(opt in message for opt in options)
    assert "vaga" in message.lower()


def test_is_answering_field_detection():
    """
    Testa detecção de se mensagem é resposta ou pergunta
    """
    from app.agent.confusion_detector import is_answering_field

    # Pergunta (com ?)
    assert not is_answering_field("vagas de carro?", "parking")
    assert not is_answering_field("como assim?", "parking")

    # Resposta válida
    assert is_answering_field("2", "parking")
    assert is_answering_field("duas vagas", "parking")
    assert is_answering_field("nenhuma", "parking")

    # Budget
    assert is_answering_field("500 mil", "budget")
    assert is_answering_field("entre 800k e 1mi", "budget")

    # Intent
    assert is_answering_field("quero comprar", "intent")
    assert is_answering_field("alugar", "intent")


def test_field_ask_count_increments():
    """
    Testa que contador de tentativas incrementa corretamente
    """
    session_id = "test_ask_count"
    store.reset(session_id)

    # Setup: chegar até parking
    handle_message(session_id, "Oi")
    handle_message(session_id, "Quero comprar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Manaíra")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "3 quartos")

    state = store.get(session_id)

    # Primeira vez que pergunta parking
    assert state.field_ask_count.get("parking", 0) == 1

    # Usuário confuso, bot re-pergunta
    handle_message(session_id, "vagas??")

    state = store.get(session_id)
    # Contador deve ter incrementado
    assert state.field_ask_count.get("parking", 0) == 2

    store.reset(session_id)


def test_pending_field_tracked():
    """
    Testa que pending_field é rastreado corretamente
    """
    session_id = "test_pending"
    store.reset(session_id)

    handle_message(session_id, "Oi")
    state = store.get(session_id)
    assert state.pending_field == "intent"

    handle_message(session_id, "Quero comprar")
    state = store.get(session_id)
    # Deve ter avançado para city
    assert state.pending_field == "city" or state.pending_field == "neighborhood"

    store.reset(session_id)
