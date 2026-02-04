"""Testes para sistema de follow-up automático."""

import os
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.followup import should_followup, next_followup_message, save_followup_sent, load_followup_history


def test_should_followup_warm_lead():
    """Lead warm parado deve precisar de follow-up."""
    # Lead warm, parado há 3 horas, grade B
    lead = {
        "session_id": "warm_123",
        "completed": False,
        "timestamp": (datetime.utcnow() - timedelta(hours=3)).timestamp(),
        "lead_score": {"temperature": "warm"},
        "quality_score": {"grade": "B"}
    }

    result = should_followup(lead, {})
    assert result is True, "Warm lead parado deve precisar de follow-up"


def test_should_not_followup_hot_grade_a():
    """Lead hot grade A não precisa de follow-up."""
    lead = {
        "session_id": "hot_123",
        "completed": False,
        "timestamp": datetime.utcnow().timestamp(),
        "lead_score": {"temperature": "hot"},
        "quality_score": {"grade": "A"}
    }

    result = should_followup(lead, {})
    assert result is False, "Hot grade A não deve precisar de follow-up"


def test_should_not_followup_completed():
    """Lead completed não precisa de follow-up."""
    lead = {
        "session_id": "completed_123",
        "completed": True,
        "timestamp": (datetime.utcnow() - timedelta(days=1)).timestamp(),
        "lead_score": {"temperature": "warm"},
        "quality_score": {"grade": "C"}
    }

    result = should_followup(lead, {})
    assert result is False, "Lead completed não deve precisar de follow-up"


def test_next_followup_missing_neighborhood():
    """Lead sem neighborhood deve gerar follow-up específico."""
    lead = {
        "session_id": "test_123",
        "intent": "alugar",
        "triage_fields": {
            "city": {"value": "Joao Pessoa"},
            "budget": {"value": 3000}
        }
    }

    result = next_followup_message(lead, {})

    assert result is not None
    assert result["followup_key"] == "neighborhood"
    assert "bairro" in result["message_text"].lower()


def test_next_followup_missing_payment_type_compra():
    """Lead de compra sem payment_type deve gerar follow-up."""
    lead = {
        "session_id": "compra_123",
        "intent": "comprar",
        "triage_fields": {
            "neighborhood": {"value": "Manaíra"},
            "budget": {"value": 400000},  # Baixo para não disparar condo_max
            "timeline": {"value": "6m"},
            "condo_max": {"value": 500}  # Preenchido
        }
    }

    result = next_followup_message(lead, {})

    assert result is not None
    assert result["followup_key"] == "payment_type"
    assert "pagamento" in result["message_text"].lower() or "pagar" in result["message_text"].lower()


def test_no_followup_if_already_sent():
    """Não deve gerar follow-up se já foi enviado."""
    lead = {
        "session_id": "test_456",
        "intent": "alugar",
        "triage_fields": {}
    }

    history = {"test_456": ["neighborhood", "timeline", "condo_max"]}

    # Já enviou 3 follow-ups (limite)
    result = should_followup(lead, history)
    assert result is False


def test_save_and_load_followup_history(tmp_path):
    """Testa persistência de follow-ups."""
    meta_path = tmp_path / "followups.jsonl"

    # Salva alguns follow-ups
    save_followup_sent("session_1", "neighborhood", str(meta_path))
    save_followup_sent("session_1", "timeline", str(meta_path))
    save_followup_sent("session_2", "payment_type", str(meta_path))

    # Carrega histórico
    history = load_followup_history(str(meta_path))

    assert "session_1" in history
    assert len(history["session_1"]) == 2
    assert "neighborhood" in history["session_1"]
    assert "timeline" in history["session_1"]
    assert "session_2" in history
    assert "payment_type" in history["session_2"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
