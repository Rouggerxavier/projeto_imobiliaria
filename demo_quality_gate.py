"""
Demonstração do Quality Gate - Controle de Handoff Inteligente

Este script mostra como o quality gate funciona na prática.
"""

from app.agent.state import SessionState
from app.agent.quality import compute_quality_score
from app.agent.quality_gate import (
    should_handoff,
    identify_quality_gaps,
    next_question_from_quality_gaps,
    detect_field_refusal,
    mark_field_refusal,
)


def print_separator():
    print("\n" + "=" * 80 + "\n")


def demo_high_quality_immediate_handoff():
    """Cenário 1: Quality Score alto (A/B) -> Handoff imediato."""
    print("[CENARIO 1] Quality Score Alto (A/B) - Handoff Imediato")
    print_separator()

    state = SessionState(session_id="demo-1")
    state.intent = "comprar"
    state.set_criterion("city", "João Pessoa", status="confirmed")
    state.set_criterion("neighborhood", "Manaíra", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="confirmed")
    state.set_criterion("bedrooms", 3, status="confirmed")
    state.set_criterion("parking", 2, status="confirmed")
    state.set_criterion("budget", 800000, status="confirmed")
    state.set_criterion("timeline", "3m", status="confirmed")
    state.set_criterion("micro_location", "beira-mar", status="confirmed")
    state.set_criterion("payment_type", "financiamento", status="confirmed")
    state.lead_profile["name"] = "João Silva"

    quality = compute_quality_score(state)

    print(f"Quality Score: {quality['score']}/100")
    print(f"Grade: {quality['grade']}")
    print(f"Completude: {quality['completeness'] * 100:.0f}%")
    print(f"Confiança: {quality['confidence'] * 100:.0f}%")
    print(f"Motivos: {', '.join(quality['reasons'][:5])}")

    can_handoff = should_handoff(state, quality)
    print(f"\n[OK] Pode fazer handoff? {can_handoff}")
    print("-> Todos os campos críticos preenchidos e confirmados.")
    print("-> Handoff imediato para corretor.")


def demo_low_quality_blocked_handoff():
    """Cenário 2: Quality Score baixo (C/D) -> Handoff bloqueado, perguntas cirúrgicas."""
    print("[CENARIO CENÁRIO 2: Quality Score Baixo (C/D) - Handoff Bloqueado")
    print_separator()

    state = SessionState(session_id="demo-2")
    state.intent = "comprar"
    state.set_criterion("city", "João Pessoa", status="inferred")  # Baixa confiança
    state.set_criterion("neighborhood", "Tambaú", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="inferred")  # Baixa confiança
    state.set_criterion("bedrooms", 2, status="confirmed")
    state.set_criterion("parking", 1, status="inferred")  # Baixa confiança
    state.set_criterion("budget", 1200000, status="confirmed")  # Alto -> precisa condo_max
    state.set_criterion("timeline", "6m", status="confirmed")
    # Faltando: payment_type (compra), condo_max (budget alto), micro_location

    quality = compute_quality_score(state)
    gaps = identify_quality_gaps(state, quality)

    print(f"Quality Score: {quality['score']}/100")
    print(f"Grade: {quality['grade']}")
    print(f"Completude: {quality['completeness'] * 100:.0f}%")
    print(f"Confiança: {quality['confidence'] * 100:.0f}%")

    print(f"\n[GAPS] Gaps Identificados:")
    print(f"  - Campos missing: {gaps.missing_required_fields}")
    print(f"  - Dealbreakers: {gaps.dealbreakers}")
    print(f"  - Baixa confiança (inferred): {gaps.low_confidence_fields}")
    print(f"  - Ambíguos: {gaps.ambiguous_fields}")

    can_handoff = should_handoff(state, quality)
    print(f"\n[BLOQUEADO] Pode fazer handoff? {can_handoff}")

    next_key = next_question_from_quality_gaps(state, quality)
    print(f"\n[PROXIMA] Próxima pergunta cirúrgica: {next_key}")
    print("-> Sistema vai perguntar sobre o dealbreaker prioritário antes de handoff.")


def demo_quality_gate_progression():
    """Cenário 3: Progressão através do quality gate (3 perguntas)."""
    print("[CENARIO CENÁRIO 3: Progressão Através do Quality Gate")
    print_separator()

    state = SessionState(session_id="demo-3")
    state.intent = "comprar"
    state.set_criterion("city", "João Pessoa", status="confirmed")
    state.set_criterion("neighborhood", "Cabo Branco", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="confirmed")
    state.set_criterion("bedrooms", 3, status="confirmed")
    state.set_criterion("parking", 2, status="confirmed")
    state.set_criterion("budget", 1000000, status="confirmed")
    state.set_criterion("timeline", "6m", status="confirmed")
    # Faltando múltiplos dealbreakers

    print("Turn 1: Campos críticos preenchidos, mas faltam dealbreakers...")
    quality = compute_quality_score(state)
    print(f"  Quality Score: {quality['score']}/100 (Grade {quality['grade']})")
    print(f"  Quality Gate Turns: {state.quality_gate_turns}")

    next_key = next_question_from_quality_gaps(state, quality)
    print(f"  -> Pergunta: {next_key}")
    state.quality_gate_turns += 1
    state.asked_questions.append(next_key)

    # Simular resposta
    print(f"\nUsuário responde: '{next_key}' fornecido")
    state.set_criterion(next_key, "financiamento" if next_key == "payment_type" else "800", status="confirmed")

    print("\nTurn 2: Primeiro gap resolvido, verifica novamente...")
    quality = compute_quality_score(state)
    print(f"  Quality Score: {quality['score']}/100 (Grade {quality['grade']})")
    print(f"  Quality Gate Turns: {state.quality_gate_turns}")

    next_key = next_question_from_quality_gaps(state, quality)
    if next_key:
        print(f"  -> Pergunta: {next_key}")
        state.quality_gate_turns += 1
        state.asked_questions.append(next_key)
        state.set_criterion(next_key, "beira-mar" if next_key == "micro_location" else "1500", status="confirmed")

    print("\nTurn 3: Segundo gap resolvido, verifica novamente...")
    quality = compute_quality_score(state)
    print(f"  Quality Score: {quality['score']}/100 (Grade {quality['grade']})")
    print(f"  Quality Gate Turns: {state.quality_gate_turns}")

    can_handoff = should_handoff(state, quality)
    print(f"\n[OK] Pode fazer handoff? {can_handoff}")
    print(f"-> Quality gate permitiu handoff: grade melhorou para {quality['grade']} ou limite de perguntas atingido.")


def demo_field_refusal():
    """Cenário 4: Usuário recusa informar campo."""
    print("[CENARIO CENÁRIO 4: Detecção de Recusa de Campo")
    print_separator()

    state = SessionState(session_id="demo-4")
    state.intent = "comprar"
    state.set_criterion("city", "João Pessoa", status="confirmed")
    state.set_criterion("neighborhood", "Manaíra", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="confirmed")
    state.set_criterion("bedrooms", 3, status="confirmed")
    state.set_criterion("parking", 2, status="confirmed")
    state.set_criterion("budget", 900000, status="confirmed")
    state.set_criterion("timeline", "3m", status="confirmed")
    # Faltando: payment_type, condo_max

    quality = compute_quality_score(state)
    next_key = next_question_from_quality_gaps(state, quality)

    print(f"Sistema pergunta: {next_key}")
    print("Usuário responde: 'não sei, prefiro não informar'")

    # Detectar recusa
    user_message = "não sei, prefiro não informar"
    is_refusal = detect_field_refusal(user_message)
    print(f"\n[DETECTADO] Detectou recusa? {is_refusal}")

    if is_refusal:
        mark_field_refusal(state, next_key)
        state.asked_questions.append(next_key)

        print(f"+ Campo '{next_key}' marcado como recusado.")
        print(f"  Field refusals: {state.field_refusals}")

        # Próxima pergunta não deve repetir o campo recusado
        next_key_2 = next_question_from_quality_gaps(state, quality)
        print(f"\n-> Próxima pergunta (ignora campo recusado): {next_key_2}")
        print(f"+ Sistema passou para o próximo gap relevante.")


def demo_max_turns_bypass():
    """Cenário 5: Bypass do quality gate após 3 perguntas."""
    print("[CENARIO CENÁRIO 5: Bypass Após Limite de Perguntas")
    print_separator()

    state = SessionState(session_id="demo-5")
    state.intent = "alugar"
    state.set_criterion("city", "João Pessoa", status="inferred")
    state.set_criterion("neighborhood", "Tambaú", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="inferred")
    state.set_criterion("bedrooms", 2, status="confirmed")
    state.set_criterion("parking", 1, status="confirmed")
    state.set_criterion("budget", 3500, status="confirmed")
    state.set_criterion("timeline", "flexivel", status="confirmed")

    # Simular 3 perguntas já feitas
    state.quality_gate_turns = 3

    quality = compute_quality_score(state)

    print(f"Quality Score: {quality['score']}/100 (Grade {quality['grade']})")
    print(f"Quality Gate Turns: {state.quality_gate_turns}/3")
    print(f"Ainda há campos inferred: {len([r for r in quality['reasons'] if 'inferred' in r])} campos")

    can_handoff = should_handoff(state, quality)
    print(f"\n[OK] Pode fazer handoff? {can_handoff}")
    print("-> Limite de 3 perguntas atingido: handoff permitido mesmo com grade baixa.")
    print("-> Resumo incluirá aviso de 'qualidade baixa: campos X, Y, Z não informados'.")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("  DEMONSTRAÇÃO: QUALITY GATE - CONTROLE INTELIGENTE DE HANDOFF")
    print("=" * 80)

    demo_high_quality_immediate_handoff()
    print_separator()

    demo_low_quality_blocked_handoff()
    print_separator()

    demo_quality_gate_progression()
    print_separator()

    demo_field_refusal()
    print_separator()

    demo_max_turns_bypass()

    print("\n" + "=" * 80)
    print("  FIM DA DEMONSTRAÇÃO")
    print("=" * 80 + "\n")
