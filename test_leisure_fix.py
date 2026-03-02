"""
Quick test to verify leisure_required is not auto-filled by 'tanto faz' from other fields
"""
from app.agent.state import store
from app.agent.controller import handle_message
from app.agent.rules import missing_critical_fields


def test_leisure_not_auto_filled():
    """
    Verifica que quando o usuário diz 'tanto faz' para outros campos,
    leisure_required NÃO é preenchido automaticamente.
    """
    session_id = "test_leisure_fix_001"
    store.reset(session_id)

    # Simula fluxo até parking
    handle_message(session_id, "Quero alugar apartamento")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Manaíra")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "3 quartos")
    handle_message(session_id, "tanto faz")  # suites
    handle_message(session_id, "tanto faz")  # bathrooms
    handle_message(session_id, "tanto faz")  # parking
    handle_message(session_id, "até 1 milhão")  # budget

    state = store.get(session_id)

    # Verifica que leisure_required NÃO foi preenchido
    leisure_val = state.triage_fields.get("leisure_required", {}).get("value")
    print(f"leisure_required value: {leisure_val}")

    # Verifica que leisure_required ainda está na lista de missing
    missing = missing_critical_fields(state)
    print(f"Missing fields: {missing}")

    if leisure_val is not None:
        print(f"❌ ERRO: leisure_required foi preenchido automaticamente com '{leisure_val}'")
        print(f"   Isso NÃO deveria acontecer!")
        return False

    if "leisure_required" not in missing:
        print(f"❌ ERRO: leisure_required não está na lista de missing, mas deveria estar!")
        return False

    print("✅ SUCESSO: leisure_required não foi auto-preenchido e ainda está missing")
    return True


def test_leisure_explicit_tanto_faz():
    """
    Verifica que quando o bot PERGUNTA sobre lazer e o usuário diz 'tanto faz',
    então leisure_required É preenchido.
    """
    session_id = "test_leisure_fix_002"
    store.reset(session_id)

    # Simula fluxo completo até leisure
    handle_message(session_id, "Alugar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Manaíra")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "3 quartos")
    handle_message(session_id, "2 suítes")
    handle_message(session_id, "3 banheiros")
    handle_message(session_id, "2 vagas")
    handle_message(session_id, "800 mil")
    handle_message(session_id, "30 dias")
    handle_message(session_id, "beira-mar")

    # Agora o bot deve perguntar sobre leisure
    # Quando responder "tanto faz" aqui, DEVE preencher
    response = handle_message(session_id, "tanto faz")

    state = store.get(session_id)
    leisure_val = state.triage_fields.get("leisure_required", {}).get("value")
    print(f"\nleisure_required value após responder: {leisure_val}")

    missing = missing_critical_fields(state)
    print(f"Missing fields: {missing}")

    if leisure_val != "indifferent":
        print(f"❌ ERRO: leisure_required deveria ser 'indifferent', mas é '{leisure_val}'")
        return False

    if "leisure_required" in missing:
        print(f"❌ ERRO: leisure_required ainda está missing, mas não deveria!")
        return False

    print("✅ SUCESSO: leisure_required foi preenchido corretamente como 'indifferent'")
    return True


if __name__ == "__main__":
    print("=" * 70)
    print("TESTE 1: Verificar que 'tanto faz' não auto-preenche leisure")
    print("=" * 70)
    test1_passed = test_leisure_not_auto_filled()

    print("\n" + "=" * 70)
    print("TESTE 2: Verificar que 'tanto faz' preenche quando perguntado")
    print("=" * 70)
    test2_passed = test_leisure_explicit_tanto_faz()

    print("\n" + "=" * 70)
    if test1_passed and test2_passed:
        print("✅ TODOS OS TESTES PASSARAM!")
    else:
        print("❌ ALGUM TESTE FALHOU")
    print("=" * 70)
