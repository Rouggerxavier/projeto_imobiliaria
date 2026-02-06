"""
Módulo de integração com LLM (OpenAI/Groq)
Fornece funções para chamar a IA de forma estruturada

OTIMIZAÇÃO: Uso único de LLM por mensagem com llm_decide()
"""

from __future__ import annotations

import json
import os
import re
import time
import hashlib
import logging
from enum import Enum
from typing import Any, Dict, Optional, List, Tuple, Union
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

load_dotenv()


def _env_int(name: str, default: int) -> int:
    """Lê int do .env com fallback seguro."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Lê bool do .env com fallback seguro."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("true", "1", "yes", "y", "on")

# Prioriza OpenAI/OpenRouter se disponível, senão usa Groq
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL")
TRIAGE_ONLY = os.getenv("TRIAGE_ONLY", "false").strip().lower() in ("true", "1", "yes", "on")

# Configuração do provedor LLM
if OPENAI_API_KEY:
    LLM_API_KEY = OPENAI_API_KEY
    LLM_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Modelo padrão
    LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # Auto-detecta provedor pela base URL ou chave
    if OPENAI_API_KEY.startswith("sk-or-v1"):
        LLM_PROVIDER = "openrouter"
        print(f"[LLM] Usando OpenRouter com modelo {LLM_MODEL}")
    elif "generativelanguage.googleapis.com" in LLM_BASE_URL:
        LLM_PROVIDER = "gemini"
        print(f"[LLM] Usando Google Gemini com modelo {LLM_MODEL}")
    else:
        LLM_PROVIDER = "openai"
        print(f"[LLM] Usando OpenAI com modelo {LLM_MODEL}")
elif GROQ_API_KEY:
    LLM_API_KEY = GROQ_API_KEY
    LLM_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_MODEL = LLM_MODEL
    LLM_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    LLM_PROVIDER = "groq"
    print(f"[LLM] Usando Groq com modelo {LLM_MODEL}")
else:
    LLM_API_KEY = None
    LLM_MODEL = None
    LLM_BASE_URL = None
    LLM_PROVIDER = None
    print("[LLM] Nenhuma API key configurada, usando apenas fallback")

USE_LLM = os.getenv("USE_LLM", "true").lower() in ("true", "1", "yes")

# Timeout padrão: 30s para provedores remotos, 120s para base local (Ollama/LM Studio)
_base = LLM_BASE_URL or ""
_default_timeout = 120 if ("127.0.0.1" in _base or "localhost" in _base) else 30
LLM_TIMEOUT = _env_int("LLM_TIMEOUT", _default_timeout)

# Ajustes locais para Ollama (aplicados apenas em base URL local)
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE")
LLM_NUM_CTX = _env_int("LLM_NUM_CTX", 0)
LLM_NUM_THREADS = _env_int("LLM_NUM_THREADS", 0)
LLM_USE_MMAP = _env_bool("LLM_USE_MMAP", True)
LLM_PREWARM = _env_bool("LLM_PREWARM", False)
logger = logging.getLogger("uvicorn.error")


class LLMErrorType(str, Enum):
    RATE_LIMIT_RPM = "RATE_LIMIT_RPM"
    RATE_LIMIT_TPM = "RATE_LIMIT_TPM"
    QUOTA_EXHAUSTED_DAILY = "QUOTA_EXHAUSTED_DAILY"
    AUTH_INVALID_KEY = "AUTH_INVALID_KEY"
    AUTH_PERMISSION_DENIED = "AUTH_PERMISSION_DENIED"
    BILLING_REQUIRED = "BILLING_REQUIRED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    BAD_REQUEST = "BAD_REQUEST"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN = "UNKNOWN"


class LLMServiceError(Exception):
    def __init__(self, normalized: Dict[str, Any]):
        super().__init__(normalized.get("raw_message"))
        self.normalized = normalized


def _is_local_base_url(url: str | None) -> bool:
    if not url:
        return False
    return ("127.0.0.1" in url) or ("localhost" in url)


def normalize_llm_error(exc: Any) -> Dict[str, Any]:
    """
    Retorna dicionário normalizado para qualquer erro de LLM compatível.
    É resiliente a formatos inesperados.
    """
    def safe_get(obj, path, default=None):
        cur = obj
        for p in path:
            if isinstance(cur, dict):
                cur = cur.get(p, default)
            else:
                cur = getattr(cur, p, default)
            if cur is default:
                break
        return cur

    status = safe_get(exc, ["status_code"], safe_get(exc, ["response", "status_code"]))
    headers = safe_get(exc, ["response", "headers"], {}) or {}
    message = str(exc)
    if hasattr(exc, "message"):
        try:
            message = exc.message
        except Exception:
            pass
    raw = safe_get(exc, ["response", "content"])
    code = None
    try:
        if raw:
            parsed = raw if isinstance(raw, dict) else json.loads(raw)
            code = safe_get(parsed, ["error", "code"])
            message = safe_get(parsed, ["error", "message"], message) or message
            if not status:
                status = safe_get(parsed, ["error", "status"])
    except Exception:
        pass

    retry_after = None
    if headers and isinstance(headers, dict):
        ra = headers.get("Retry-After") or headers.get("retry-after")
        try:
            if ra:
                retry_after = float(ra)
        except Exception:
            retry_after = None

    provider = "openai-compatible"
    typ = LLMErrorType.UNKNOWN

    # Heurísticas de tipos
    msg_low = str(message).lower()
    code_low = str(code).lower() if code else ""
    if isinstance(exc, TimeoutError):
        typ = LLMErrorType.NETWORK_TIMEOUT
        return {
            "type": typ.value,
            "provider": provider,
            "http_status": status,
            "retry_after_sec": retry_after,
            "raw_code": code,
            "raw_message": str(message),
            "request_id": safe_get(headers, ["x-request-id"]) or safe_get(headers, ["X-Request-Id"])
        }

    # Erros específicos da Gemini API
    if "api key not valid" in msg_low or "api_key_invalid" in code_low:
        typ = LLMErrorType.AUTH_INVALID_KEY
    elif status == 401 or "invalid api key" in msg_low or code_low == "invalid_api_key":
        typ = LLMErrorType.AUTH_INVALID_KEY
    elif status == 400 and ("unsupported" in msg_low or "invalid model" in msg_low or "model not found" in msg_low):
        typ = LLMErrorType.MODEL_NOT_FOUND
    elif status == 403 and ("permission" in msg_low or "not allowed" in msg_low):
        typ = LLMErrorType.AUTH_PERMISSION_DENIED
    elif status == 403 and ("billing" in msg_low or "payment" in msg_low):
        typ = LLMErrorType.BILLING_REQUIRED
    elif status == 404 or code_low == "model_not_found":
        typ = LLMErrorType.MODEL_NOT_FOUND
    elif status == 429:
        if "tpm" in msg_low:
            typ = LLMErrorType.RATE_LIMIT_TPM
        elif "rpm" in msg_low:
            typ = LLMErrorType.RATE_LIMIT_RPM
        elif "quota" in msg_low or "exceeded" in msg_low:
            typ = LLMErrorType.QUOTA_EXHAUSTED_DAILY
        else:
            typ = LLMErrorType.RATE_LIMIT_RPM
    elif status and status >= 500:
        typ = LLMErrorType.NETWORK_ERROR
    elif "timeout" in msg_low:
        typ = LLMErrorType.NETWORK_TIMEOUT
    elif status and 400 <= status < 500:
        typ = LLMErrorType.BAD_REQUEST

    return {
        "type": typ.value if isinstance(typ, LLMErrorType) else typ,
        "provider": provider,
        "http_status": status,
        "retry_after_sec": retry_after,
        "raw_code": code,
        "raw_message": str(message),
        "request_id": safe_get(headers, ["x-request-id"]) or safe_get(headers, ["X-Request-Id"])
    }

def _build_extra_body() -> Optional[Dict[str, Any]]:
    """Campos extras compatíveis com Ollama (keep_alive/options)."""
    if not _is_local_base_url(LLM_BASE_URL):
        return None

    extra: Dict[str, Any] = {}

    if LLM_KEEP_ALIVE:
        extra["keep_alive"] = LLM_KEEP_ALIVE

    options: Dict[str, Any] = {}
    if LLM_NUM_CTX > 0:
        options["num_ctx"] = LLM_NUM_CTX
    if LLM_NUM_THREADS > 0:
        options["num_thread"] = LLM_NUM_THREADS
    if LLM_USE_MMAP is not None:
        options["use_mmap"] = LLM_USE_MMAP

    if options:
        extra["options"] = options

    return extra or None

# Rate limit tracking
_rate_limit_until: float = 0.0  # Timestamp até quando não podemos chamar
_message_cache: Dict[str, Dict[str, Any]] = {}  # Cache de respostas
_CACHE_TTL = 300  # 5 minutos


def _client() -> OpenAI:
    """Cria cliente OpenAI (compatível com OpenAI e Groq)"""
    if not LLM_API_KEY:
        raise RuntimeError("Nenhuma API key configurada (OPENAI_API_KEY ou GROQ_API_KEY)")
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def _call_gemini_native(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Chama Gemini usando a API nativa (google.genai).
    Retorna string de resposta.
    """
    print(f"[DEBUG] Chamando Gemini nativo - Modelo: {LLM_MODEL}, Temp: {temperature}, MaxTokens: {max_tokens}")

    from google import genai
    from google.genai import types

    # Cria o cliente
    client = genai.Client(api_key=LLM_API_KEY)

    # Combina system prompt + user message
    full_prompt = f"{system_prompt}\n\n{user_message}"

    # Adiciona prefixo "models/" se não existir
    model_name = LLM_MODEL if LLM_MODEL.startswith("models/") else f"models/{LLM_MODEL}"

    # Gera resposta
    response = client.models.generate_content(
        model=model_name,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or 2048,
        )
    )

    return response.text


def _call_llm_gemini_native(
    system_prompt: str,
    user_message: str | Dict[str, Any],
    temperature: float = 0.3,
    response_format: str = "json_object",
    max_tokens: Optional[int] = None,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    Wrapper para call_llm usando API nativa do Gemini.
    """
    # Prepara mensagem do usuário
    if isinstance(user_message, dict):
        user_content = json.dumps(user_message, ensure_ascii=False, indent=2)
    else:
        user_content = str(user_message)

    # Se esperamos JSON, adiciona instrução no prompt
    if response_format == "json_object":
        system_prompt = system_prompt + "\n\nIMPORTANTE: Você DEVE responder APENAS com JSON válido, sem texto adicional antes ou depois. Formato: {\"chave\": \"valor\"}"

    # Tenta com retry
    last_exception = None
    for attempt in range(max_retries):
        try:
            content = _call_gemini_native(
                system_prompt=system_prompt,
                user_message=user_content,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Se esperamos JSON, faz parse
            if response_format == "json_object":
                try:
                    # Remove markdown code blocks se existirem (```json ... ```)
                    cleaned_content = content.strip()
                    if cleaned_content.startswith("```"):
                        # Remove primeira linha (```json ou ```)
                        lines = cleaned_content.split("\n")
                        lines = lines[1:] if len(lines) > 1 else lines
                        # Remove última linha se for ```)
                        if lines and lines[-1].strip() == "```":
                            lines = lines[:-1]
                        cleaned_content = "\n".join(lines).strip()

                    # Verifica se JSON parece truncado (não termina com } ou ])
                    if not cleaned_content.endswith("}") and not cleaned_content.endswith("]"):
                        if attempt < max_retries - 1:
                            print(f"[WARN] JSON parece truncado (não termina com }} ou ]), tentando novamente ({attempt + 1}/{max_retries})")
                            continue
                        raise RuntimeError(f"Gemini retornou JSON truncado após {max_retries} tentativas: {content}")

                    return json.loads(cleaned_content)
                except json.JSONDecodeError as exc:
                    # Se falhou no parse JSON, tenta novamente
                    if attempt < max_retries - 1:
                        print(f"[WARN] JSON inválido, tentando novamente ({attempt + 1}/{max_retries})")
                        continue
                    raise RuntimeError(f"Gemini retornou JSON inválido após {max_retries} tentativas: {content}") from exc

            # Caso contrário retorna texto em dict
            return {"response": content}

        except Exception as exc:
            last_exception = exc
            # Log detalhado do erro
            import traceback
            error_details = traceback.format_exc()
            print(f"[ERROR] Erro na chamada Gemini (tentativa {attempt + 1}/{max_retries}):")
            print(f"  Tipo: {type(exc).__name__}")
            print(f"  Mensagem: {exc}")
            print(f"  Traceback:\n{error_details}")

            if attempt < max_retries - 1:
                print(f"[WARN] Tentando novamente...")
                continue
            # Normaliza e lança erro estruturado
            normalized = {"type": LLMErrorType.UNKNOWN.value, "raw_message": str(exc), "exception_type": type(exc).__name__}
            raise LLMServiceError(normalized) from exc

    # Se chegou aqui, todas as tentativas falharam
    normalized = {"type": LLMErrorType.UNKNOWN.value, "raw_message": str(last_exception)}
    raise LLMServiceError(normalized) from last_exception


def call_llm(
    system_prompt: str,
    user_message: str | Dict[str, Any],
    temperature: float = 0.3,
    response_format: str = "json_object",
    conversation_history: Optional[List[Dict[str, str]]] = None,
    timeout: Optional[int] = None,
    max_tokens: Optional[int] = None,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    Chama a LLM (Groq) e retorna resposta estruturada em JSON.
    
    Args:
        system_prompt: Prompt de sistema definindo comportamento da IA
        user_message: Mensagem do usuário (str ou dict que será convertido para JSON)
        temperature: Controle de criatividade (0.0 = determinístico, 1.0 = criativo)
        response_format: "json_object" para forçar JSON, "text" para texto livre
        conversation_history: Histórico opcional de mensagens anteriores
        timeout: Timeout em segundos (padrão: 30s)
        max_retries: Número máximo de tentativas (padrão: 2)
        
    Returns:
        Dict com a resposta da LLM (já parseado de JSON)
        
    Raises:
        RuntimeError: Se API key não estiver configurada ou houver erro após todas as tentativas
    """
    # Se for Gemini, usa API nativa ao invés do endpoint OpenAI bugado
    if LLM_PROVIDER == "gemini":
        return _call_llm_gemini_native(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=temperature,
            response_format=response_format,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )

    client = _client()

    # Prepara mensagem do usuário
    if isinstance(user_message, dict):
        user_content = json.dumps(user_message, ensure_ascii=False, indent=2)
    else:
        user_content = str(user_message)
    
    # Monta mensagens
    messages = [{"role": "system", "content": system_prompt}]
    
    # Adiciona histórico se fornecido
    if conversation_history:
        messages.extend(conversation_history)
    
    messages.append({"role": "user", "content": user_content})
    
    # Configuração da chamada
    call_params = {
        "model": LLM_MODEL,
        "temperature": temperature,
        "messages": messages,
        "timeout": LLM_TIMEOUT if timeout is None else timeout,
    }

    if max_tokens is not None:
        call_params["max_tokens"] = max_tokens

    # Adiciona formato de resposta apenas se for json_object
    # IMPORTANTE: Gemini pode não suportar response_format diretamente via OpenAI API
    # Se estiver usando Gemini, injeta instrução no system prompt ao invés
    if response_format == "json_object":
        if LLM_PROVIDER == "gemini" or "gemini" in LLM_MODEL.lower():
            # Para Gemini: adiciona instrução no system prompt
            messages[0]["content"] = messages[0]["content"] + "\n\nIMPORTANTE: Você DEVE responder APENAS com JSON válido, sem texto adicional antes ou depois. Formato: {\"chave\": \"valor\"}"
        else:
            # Para OpenAI e compatíveis
            call_params["response_format"] = {"type": "json_object"}

    extra_body = _build_extra_body()
    if extra_body:
        call_params["extra_body"] = extra_body
    
    # Tenta com retry
    last_exception = None
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(**call_params)
            content = completion.choices[0].message.content
            
            # Se esperamos JSON, faz parse
            if response_format == "json_object":
                try:
                    return json.loads(content)
                except json.JSONDecodeError as exc:
                    # Se falhou no parse JSON, tenta novamente
                    if attempt < max_retries - 1:
                        print(f"[WARN] JSON inválido, tentando novamente ({attempt + 1}/{max_retries})")
                        continue
                    raise RuntimeError(f"LLM retornou JSON inválido após {max_retries} tentativas: {content}") from exc
            
            # Caso contrário retorna texto em dict
            return {"response": content}
            
        except OpenAIError as exc:
            last_exception = exc
            normalized = normalize_llm_error(exc)
            # Retry somente para timeout/network ou primeira tentativa
            if attempt < max_retries - 1 and normalized["type"] in (
                LLMErrorType.NETWORK_TIMEOUT.value,
                LLMErrorType.NETWORK_ERROR.value,
                LLMErrorType.RATE_LIMIT_RPM.value,
                LLMErrorType.RATE_LIMIT_TPM.value
            ):
                print(f"[WARN] Erro na chamada LLM, tentando novamente ({attempt + 1}/{max_retries}): {exc}")
                continue
            raise LLMServiceError(normalized) from exc
        except Exception as exc:  # segurança
            last_exception = exc
            normalized = normalize_llm_error(exc)
            raise LLMServiceError(normalized) from exc

    # Se chegou aqui, todas as tentativas falharam
    normalized = normalize_llm_error(last_exception) if last_exception else {"type": LLMErrorType.UNKNOWN.value}
    raise LLMServiceError(normalized) from last_exception


def call_llm_with_fallback(
    system_prompt: str,
    user_message: str | Dict[str, Any],
    fallback_result: Dict[str, Any],
    **kwargs
) -> Dict[str, Any]:
    """
    Chama LLM com fallback automático em caso de erro.

    Útil para degradação graciosa quando a API está indisponível.

    Args:
        system_prompt: Prompt de sistema
        user_message: Mensagem do usuário
        fallback_result: Resultado a retornar em caso de erro
        **kwargs: Argumentos adicionais para call_llm

    Returns:
        Resposta da LLM ou fallback em caso de erro
    """
    # Se não tiver API key, usa fallback imediatamente
    if not LLM_API_KEY:
        return fallback_result

    try:
        return call_llm(system_prompt, user_message, **kwargs)
    except Exception as e:
        # Log do erro (em produção, use logging adequado)
        print(f"[WARN] Falha na chamada LLM, usando fallback: {e}")
        return fallback_result


def call_llm_streaming(
    system_prompt: str,
    user_message: str | Dict[str, Any],
    temperature: float = 0.3,
):
    """
    Chama LLM em modo streaming (para respostas longas).
    
    Yields:
        Chunks de texto conforme a LLM gera
        
    Nota: Use apenas quando precisar de streaming. Para uso normal, use call_llm()
    """
    client = _client()
    
    if isinstance(user_message, dict):
        user_content = json.dumps(user_message, ensure_ascii=False, indent=2)
    else:
        user_content = str(user_message)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    
    try:
        stream = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=temperature,
            messages=messages,
            stream=True,
            extra_body=_build_extra_body() or None,
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
                
    except OpenAIError as exc:
        raise RuntimeError(f"Erro no streaming Groq API: {exc}") from exc


# Função auxiliar para debug
def test_llm_connection() -> bool:
    """
    Testa se a conexão com LLM está funcionando.

    Returns:
        True se conexão OK, False caso contrário
    """
    if not LLM_API_KEY:
        print(f"[ERROR] Nenhuma API key configurada")
        return False

    try:
        result = call_llm(
            system_prompt="Você é um assistente útil. Responda sempre em JSON.",
            user_message="Responda com JSON contendo apenas uma chave 'status' com valor 'OK'",
            temperature=0.0,
            max_tokens=128  # Aumentado para acomodar formatação markdown do Gemini
        )
        print(f"[OK] Conexão com {LLM_PROVIDER} OK: {result}")
        return True
    except Exception as e:
        print(f"[ERROR] Erro ao conectar com {LLM_PROVIDER}: {e}")
        return False


def prewarm_llm() -> None:
    """
    Faz uma chamada curta para aquecer o modelo local e evitar cold start.
    """
    if not USE_LLM or not LLM_API_KEY:
        return
    try:
        call_llm(
            system_prompt="Você é um assistente útil.",
            user_message="ping",
            temperature=0.0,
            response_format="text",
            max_tokens=8,
        )
        print("[LLM] Prewarm concluido")
    except Exception as e:
        print(f"[WARN] Prewarm LLM falhou: {e}")


# ==================== OTIMIZAÇÃO: CHAMADA ÚNICA ====================

def _parse_retry_after(error_message: str) -> float:
    """
    Extrai o tempo de espera de uma mensagem de erro 429.
    Retorna segundos para esperar.
    """
    # Exemplo: "Please try again in 3m41.184s"
    match = re.search(r"try again in (\d+)m([\d.]+)s", str(error_message))
    if match:
        minutes = int(match.group(1))
        seconds = float(match.group(2))
        return minutes * 60 + seconds

    # Fallback: "try again in 8.5s"
    match = re.search(r"try again in ([\d.]+)s", str(error_message))
    if match:
        return float(match.group(1))

    # Default: 60 segundos
    return 60.0


def _get_cache_key(message: str, state_summary: str) -> str:
    """Gera chave de cache para evitar chamadas duplicadas."""
    content = f"{message}|{state_summary}"
    return hashlib.md5(content.encode()).hexdigest()


def _is_rate_limited() -> Tuple[bool, float]:
    """
    Verifica se estamos em rate limit.

    Returns:
        (is_limited, seconds_remaining)
    """
    global _rate_limit_until
    now = time.time()
    if now < _rate_limit_until:
        return True, _rate_limit_until - now
    return False, 0.0


def _set_rate_limit(seconds: float) -> None:
    """Define o rate limit até quando não chamar a API."""
    global _rate_limit_until
    _rate_limit_until = time.time() + seconds
    print(f"[WAIT] Rate limit ativo por {seconds:.1f}s")


def llm_decide(
    message: str,
    state_summary: Dict[str, Any],
    use_cache: bool = True,
    triage_only: bool = False,
    correlation_id: Optional[str] = None
) -> Tuple[Dict[str, Any], bool]:
    """
    Função UNIFICADA para decisão via LLM.

    IMPORTANTE: Esta função faz NO MÁXIMO 1 chamada LLM por mensagem.

    Args:
        message: Mensagem do usuário
        state_summary: Resumo do estado (critérios, histórico limitado, etc)
        use_cache: Se True, usa cache para mensagens idênticas

    Returns:
        (decision_dict, used_llm)
        - decision_dict: JSON com intent, criteria, handoff, plan
        - used_llm: True se chamou LLM, False se usou cache/fallback

    O JSON retornado contém:
    {
        "intent": "comprar|alugar|...",
        "criteria": {"city": ..., "budget": ..., ...},
        "handoff": {"should": true/false, "reason": "..."},
        "plan": {
            "action": "ASK|SEARCH|...",
            "message": "...",
            "question_key": "...",
            "filters": {...}
        }
    }
    """
    from . import prompts

    triage_flag = triage_only or TRIAGE_ONLY

    # 1. Verifica se LLM está habilitado
    if not USE_LLM or not LLM_API_KEY:
        return _get_fallback_decision(message, state_summary, triage_flag), False

    # 2. Verifica rate limit ativo
    is_limited, wait_time = _is_rate_limited()
    if is_limited:
        print(f"[WARN] Rate limit ativo, usando fallback (aguardar {wait_time:.1f}s)")
        return _get_fallback_decision(message, state_summary, triage_flag), False

    # 3. Verifica cache
    cache_key = _get_cache_key(message, json.dumps(state_summary, sort_keys=True))
    if use_cache and cache_key in _message_cache:
        cached = _message_cache[cache_key]
        if time.time() - cached.get("_timestamp", 0) < _CACHE_TTL:
            print("[CACHE] Usando resposta do cache")
            return cached.get("decision", {}), False

    # 4. Prepara payload compacto
    payload = _build_compact_payload(message, state_summary)

    # 5. Faz chamada LLM
    try:
        system_prompt = prompts.TRIAGE_DECISION_PROMPT if triage_flag else prompts.UNIFIED_DECISION_PROMPT
        result = call_llm(
            system_prompt=system_prompt,
            user_message=payload,
            temperature=0.3,
            max_tokens=2048,  # Aumentado para evitar truncamento de JSON
            max_retries=3  # Mais tentativas para lidar com erros transitórios
        )

        # Valida e normaliza resposta
        decision = _validate_decision(result, state_summary, triage_flag)

        # Salva no cache
        if use_cache:
            _message_cache[cache_key] = {
                "decision": decision,
                "_timestamp": time.time()
            }

        return decision, True

    except LLMServiceError as e:
        norm = e.normalized
        cooldown = 0.0
        err_type = norm.get("type") or LLMErrorType.UNKNOWN.value
        retry_after = norm.get("retry_after_sec")

        if err_type in {LLMErrorType.RATE_LIMIT_RPM.value, LLMErrorType.RATE_LIMIT_TPM.value}:
            cooldown = retry_after or 60.0
        elif err_type == LLMErrorType.QUOTA_EXHAUSTED_DAILY.value:
            cooldown = max(retry_after or 3600.0, 900.0)
        elif err_type == LLMErrorType.NETWORK_TIMEOUT.value:
            cooldown = 10.0

        cooldown_applied = False
        if cooldown > 0:
            _set_rate_limit(cooldown)
            cooldown_applied = True

        logger.error(
            f"[LLM_ERROR] type={err_type} http={norm.get('http_status')} provider={norm.get('provider')} "
            f"model={LLM_MODEL} retry_after={retry_after} cooldown_applied={cooldown_applied} "
            f"correlation={correlation_id}"
        )

        # Evita mascarar: informa reason no fallback
        fallback_decision = _get_fallback_decision(message, state_summary, triage_flag)
        fallback_decision["fallback_reason"] = err_type
        if triage_flag:
            fallback_decision.setdefault("plan", {}).setdefault("message",
                "Estou com limite de uso do modelo agora. Vou seguir com perguntas rápidas para entender seu perfil.")
        return fallback_decision, False

    except Exception as e:
        error_str = str(e)
        logger.error(f"[LLM_ERROR] type={LLMErrorType.UNKNOWN.value} detail={error_str} correlation={correlation_id}")
        return _get_fallback_decision(message, state_summary, triage_flag), False


def _build_compact_payload(message: str, state_summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Constrói payload compacto para minimizar tokens.

    Inclui apenas:
    - Últimas 6 mensagens do histórico
    - Critérios confirmados
    - Campos faltantes
    - IDs dos últimos imóveis sugeridos
    """
    history = state_summary.get("history", [])

    # Limita histórico a 6 mensagens
    recent_history = history[-6:] if len(history) > 6 else history

    # Formata histórico de forma compacta
    compact_history = []
    for h in recent_history:
        role = "U" if h.get("role") == "user" else "A"
        text = h.get("text", "")[:200]  # Limita cada mensagem
        compact_history.append(f"{role}: {text}")

    return {
        "msg": message,
        "intent": state_summary.get("intent"),
        "criteria": state_summary.get("criteria", {}),
        "missing": state_summary.get("missing_fields", []),
        "history": compact_history,
        "stage": state_summary.get("stage"),
        "suggestions": state_summary.get("last_suggestions", [])[:5],
        "triage_fields": state_summary.get("triage_fields", {}),
        "asked_questions": state_summary.get("asked_questions", []),
        "last_question_key": state_summary.get("last_question_key"),
        "completed": state_summary.get("completed", False)
    }


def _validate_decision(result: Dict[str, Any], state_summary: Dict[str, Any], triage_only: bool = False) -> Dict[str, Any]:
    """
    Valida e normaliza a decisão da LLM.
    Aplica guard-rails para evitar ações inválidas.
    """
    if triage_only:
        ALLOWED_ACTIONS = {"ASK", "HANDOFF", "ANSWER_GENERAL", "CLARIFY", "TRIAGE_SUMMARY"}
    else:
        ALLOWED_ACTIONS = {"ASK", "SEARCH", "LIST", "REFINE", "SCHEDULE", "HANDOFF", "ANSWER_GENERAL", "CLARIFY"}

    # Extrai plan
    plan = result.get("plan", {})
    action = plan.get("action", "ASK")

    # Valida action
    if action not in ALLOWED_ACTIONS:
        action = "ASK"
        plan["action"] = action

    missing = state_summary.get("missing_fields", [])
    can_search = state_summary.get("can_search", False)

    # Guard-rail: Se triagem, nunca permite SEARCH/LIST/REFINE/SCHEDULE
    if triage_only and action in {"SEARCH", "LIST", "REFINE", "SCHEDULE"}:
        plan["action"] = "ASK" if missing else "ANSWER_GENERAL"

    # Guard-rail: Se action=SEARCH mas não pode buscar, força ASK
    if action == "SEARCH" and not can_search and missing:
        plan["action"] = "ASK"
        plan["question_key"] = missing[0]
        plan["message"] = _get_question_for_field(missing[0])

    # Em triagem, se todos críticos preenchidos, força TRIAGE_SUMMARY
    if triage_only and not missing:
        plan["action"] = "TRIAGE_SUMMARY"

    # Garante que sempre tem mensagem
    if not plan.get("message"):
        plan["message"] = plan.get("question_text") or "Como posso ajudar?"

    if triage_only and plan.get("question_key") and plan.get("question_key") not in state_summary.get("missing_fields", []):
        # evita perguntar campo já preenchido
        plan["action"] = "ANSWER_GENERAL" if not missing else "ASK"

    result["plan"] = plan
    return result


def _get_question_for_field(field: str) -> str:
    """Retorna pergunta padrão para campo faltante."""
    questions = {
        "intent": "Você quer alugar ou comprar?",
        "location": "Qual cidade ou bairro você prefere?",
        "city": "Qual cidade você prefere? (posso usar João Pessoa como base)",
        "city_confirm": "Confirma João Pessoa ou prefere outra cidade?",
        "neighborhood": "Quais bairros você quer considerar?",
        "micro_location": "Prefere beira-mar, 1 quadra ou 2-3 quadras da praia?",
        "budget": "Qual o orçamento máximo? Pode ser aproximado.",
        "property_type": "Prefere apartamento, casa, cobertura ou outro tipo?",
        "bedrooms": "Quantos quartos você precisa? Quer suíte?",
        "suites": "Quantas suítes no mínimo?",
        "parking": "Quantas vagas de garagem você precisa (1, 2, 3)?",
        "timeline": "Qual o prazo para mudar/fechar? (ex.: imediato, até 6 meses)",
        "lead_name": "Qual seu nome para eu registrar aqui?"
    }
    return questions.get(field, "Pode me dar mais detalhes?")


def _get_fallback_decision(message: str, state_summary: Dict[str, Any], triage_only: bool = False) -> Dict[str, Any]:
    """
    Retorna decisão usando fallback determinístico (sem LLM).
    """
    from .intent import classify_intent
    from .extractor import extract_criteria

    # 1. Classifica intent
    intent = classify_intent(message)
    current_intent = state_summary.get("intent")
    final_intent = intent or current_intent

    # 2. Extrai critérios
    neighborhoods = state_summary.get("neighborhoods", [])
    extracted = extract_criteria(message, neighborhoods)

    # 3. Detecta handoff
    handoff_should, handoff_reason = _fallback_handoff(message, state_summary)

    triage_fields = state_summary.get("triage_fields", {})

    # 4. Combina critérios existentes com extraídos para calcular missing
    current_criteria = state_summary.get("criteria", {})
    combined_criteria = {**current_criteria, **extracted}

    # Recalcula campos faltantes considerando os extraídos + triage_fields
    def _filled(key: str) -> bool:
        if key in triage_fields:
            return True
        return bool(combined_criteria.get(key))

    if triage_only:
        missing = []
        if not final_intent:
            missing.append("intent")
        if not _filled("city") and not _filled("neighborhood"):
            missing.append("city")
        if not _filled("neighborhood"):
            missing.append("neighborhood")
        if not _filled("property_type"):
            missing.append("property_type")
        if not _filled("bedrooms"):
            missing.append("bedrooms")
        if not _filled("parking"):
            missing.append("parking")
        if not _filled("budget"):
            missing.append("budget")
        if not _filled("timeline"):
            missing.append("timeline")
        # micro_location e lead_name são tratados como preferências
    else:
        missing = []
        if not final_intent:
            missing.append("intent")
        if not _filled("city") and not _filled("neighborhood"):
            missing.append("location")
        if not _filled("budget"):
            missing.append("budget")
        if not _filled("property_type"):
            missing.append("property_type")

    # Pode buscar se tem: intent + localização + orçamento
    can_search = bool(
        final_intent in {"comprar", "alugar", "investir"}
        and (combined_criteria.get("city") or combined_criteria.get("neighborhood"))
        and combined_criteria.get("budget")
    )

    summary_payload = None
    # 5. Decide ação
    if handoff_should:
        action = "HANDOFF"
        msg = "Vou te passar para um corretor."
        question_key = None
    elif not final_intent:
        action = "ASK"
        msg = "Voce quer alugar ou comprar?"
        question_key = "intent"
    elif missing:
        action = "ASK"
        question_key = missing[0]
        msg = _get_question_for_field(question_key)
    elif can_search and not triage_only:
        action = "SEARCH"
        msg = "Deixa eu buscar as melhores opcoes pra voce."
        question_key = None
    else:
        action = "TRIAGE_SUMMARY" if triage_only else "ASK"
        question_key = None
        msg = "Fechamos a triagem. Vou resumir para passar ao time."
        summary_payload = {
            "intent": final_intent,
            "criteria": combined_criteria,
            "confirmed": {k: v for k, v in combined_criteria.items() if k in current_criteria},
            "inferred": extracted,
        }

    return {
        "intent": final_intent,
        "criteria": extracted,
        "extracted_updates": {k: {"value": v, "status": "confirmed"} for k, v in extracted.items() if v is not None},
        "handoff": {
            "should": handoff_should,
            "reason": handoff_reason
        },
        "plan": {
            "action": action,
            "message": msg,
            "question_key": question_key,
            "filters": extracted,
            "summary_payload": summary_payload
        }
    }


def _fallback_handoff(message: str, state_summary: Dict[str, Any]) -> Tuple[bool, str]:
    """Detecta handoff usando keywords (fallback)."""
    import unicodedata

    def strip_accents(text: str) -> str:
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    low = strip_accents(message.lower())

    # Pedido explícito de humano (cuidado com "joao pessoa" -> cidade)
    human_keywords = ["falar com humano", "falar com pessoa", "atendente", "corretor humano", "pessoa real"]
    if any(k in low for k in human_keywords):
        return True, "pedido_humano"

    # Negociação
    if any(k in low for k in ["desconto", "negociar", "baixar preco", "consegue baixar"]):
        return True, "negociacao"

    # Visita (mas não "revisita" ou "visitar site")
    visit_patterns = ["agendar visita", "marcar visita", "quero visitar", "visita presencial", "visita virtual"]
    if any(k in low for k in visit_patterns):
        return True, "visita"

    # Reclamação
    if any(k in low for k in ["reclamacao", "pessimo", "muito ruim", "horrivel"]):
        return True, "reclamacao"

    # Jurídico
    if any(k in low for k in ["contrato", "juridico", "advogado", "documentacao"]):
        return True, "juridico"

    return False, ""
