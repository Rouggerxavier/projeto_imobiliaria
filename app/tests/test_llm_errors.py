import logging
import types
import pytest
from agent.llm import normalize_llm_error, LLMErrorType, LLMServiceError, llm_decide, call_llm, LLM_API_KEY, USE_LLM
from agent import llm as llm_module
from agent.state import SessionState


class DummyResp:
    def __init__(self, status_code=429, headers=None, content=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content


class DummyExc(Exception):
    def __init__(self, status, msg, headers=None, content=None):
        super().__init__(msg)
        self.status_code = status
        self.response = DummyResp(status, headers, content)
        self.message = msg


def test_normalize_rate_limit_with_retry_after():
    exc = DummyExc(429, "rate limit: RPM", headers={"Retry-After": "12"})
    norm = normalize_llm_error(exc)
    assert norm["type"] in (LLMErrorType.RATE_LIMIT_RPM.value, "RATE_LIMIT_RPM")
    assert norm["retry_after_sec"] == 12.0


def test_normalize_quota_exceeded_message():
    body = {"error": {"message": "quota exceeded today", "code": "quota_exceeded"}}
    exc = DummyExc(429, "quota exceeded", content=body)
    norm = normalize_llm_error(exc)
    assert norm["type"] == LLMErrorType.QUOTA_EXHAUSTED_DAILY.value


def test_normalize_invalid_key():
    exc = DummyExc(401, "Invalid API key provided")
    norm = normalize_llm_error(exc)
    assert norm["type"] == LLMErrorType.AUTH_INVALID_KEY.value


def test_normalize_model_not_found():
    exc = DummyExc(404, "model_not_found: gpt-foo")
    norm = normalize_llm_error(exc)
    assert norm["type"] == LLMErrorType.MODEL_NOT_FOUND.value


def test_normalize_timeout():
    exc = TimeoutError("Request timed out")
    norm = normalize_llm_error(exc)
    assert norm["type"] == LLMErrorType.NETWORK_TIMEOUT.value
