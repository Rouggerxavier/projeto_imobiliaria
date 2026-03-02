from __future__ import annotations
import os
import secrets
import logging
from datetime import datetime
from fastapi import FastAPI, Request, Depends, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.agent.controller import handle_message
from app.agent.llm import LLM_PREWARM, prewarm_llm
from app.core.logging import setup_logging
from app.core.config import settings
from app.routes.whatsapp import router as whatsapp_router

load_dotenv()

# Setup logging first
setup_logging()

logger = logging.getLogger(__name__)

# Rate limiter: chave por IP
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Agente Imobiliário WhatsApp", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routers
app.include_router(whatsapp_router)


class WebhookRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=5000)
    name: str | None = Field(default=None, max_length=128)


async def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Valida a chave de API no header X-API-Key.

    Se WEBHOOK_API_KEY não estiver configurado, loga um aviso mas permite
    acesso (compatibilidade com ambientes de desenvolvimento sem chave).
    """
    if not settings.WEBHOOK_API_KEY:
        logger.warning("WEBHOOK_API_KEY não configurado - endpoint /webhook sem autenticação")
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.WEBHOOK_API_KEY):
        logger.warning("Tentativa de acesso ao /webhook com chave inválida")
        raise HTTPException(status_code=401, detail="Chave de API inválida ou ausente")


@app.get("/")
async def home():
    """Home page with API status and useful links."""
    timestamp = datetime.now().isoformat()
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Agente Imobiliário API</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            .container {{
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{ color: #333; margin-top: 0; }}
            .status {{ color: #28a745; font-weight: bold; }}
            .links {{ margin-top: 20px; }}
            .links a {{
                display: inline-block;
                margin-right: 15px;
                color: #007bff;
                text-decoration: none;
                padding: 8px 15px;
                border: 1px solid #007bff;
                border-radius: 4px;
                transition: all 0.2s;
            }}
            .links a:hover {{
                background: #007bff;
                color: white;
            }}
            .info {{ margin-top: 20px; color: #666; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Agente Imobiliário API</h1>
            <p class="status">Status: Online</p>
            <div class="links">
                <a href="/docs">API Documentation</a>
                <a href="/health">Health Check</a>
            </div>
            <div class="info">
                <p><strong>Endpoints disponíveis:</strong></p>
                <ul>
                    <li><code>GET /</code> - Esta página</li>
                    <li><code>GET /health</code> - Health check</li>
                    <li><code>POST /webhook</code> - Webhook do agente (requer X-API-Key)</li>
                    <li><code>GET /webhook/whatsapp</code> - Verificação WhatsApp</li>
                    <li><code>POST /webhook/whatsapp</code> - Eventos WhatsApp</li>
                    <li><code>GET /docs</code> - Documentação interativa</li>
                </ul>
                <p style="margin-top: 20px;">
                    <small>Timestamp: {timestamp}</small>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/health")
async def health():
    """Health check endpoint - returns 200 OK with status."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.on_event("startup")
async def _startup():
    """Application startup - validate settings and log configuration."""
    # Validate WhatsApp configuration
    validation = settings.validate_whatsapp_config()
    if validation["errors"]:
        for error in validation["errors"]:
            logger.error("Configuration error: %s", error)
    if validation["warnings"]:
        for warning in validation["warnings"]:
            logger.warning("Configuration warning: %s", warning)

    logger.info(
        "Application started - env=%s, log_level=%s, whatsapp_send=%s",
        settings.APP_ENV,
        settings.LOG_LEVEL,
        "disabled" if settings.DISABLE_WHATSAPP_SEND else "enabled",
    )

    # Prewarm desativado para evitar chamadas iniciais ao LLM.
    return


@app.post("/webhook", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def webhook(body: WebhookRequest, request: Request):
    correlation_id = os.urandom(8).hex()
    request.state.correlation_id = correlation_id
    logger.info(
        "webhook request - session=%s, msg_len=%d, correlation=%s",
        body.session_id,
        len(body.message),
        correlation_id,
    )
    # Only expose the textual reply to the client; hide internal state/session details.
    result = handle_message(body.session_id, body.message, name=body.name, correlation_id=correlation_id)
    if isinstance(result, dict) and "reply" in result:
        return {"reply": result["reply"]}
    return result


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
