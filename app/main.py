from __future__ import annotations
import os
import asyncio
from fastapi import FastAPI, Request
from pydantic import BaseModel
from dotenv import load_dotenv
from app.agent.controller import handle_message
from app.agent.llm import LLM_PREWARM, prewarm_llm

load_dotenv()
app = FastAPI(title="Agente Imobiliário WhatsApp", version="0.1.0")


class WebhookRequest(BaseModel):
    session_id: str
    message: str
    name: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.on_event("startup")
async def _startup():
    if LLM_PREWARM:
        # Pre-warm do modelo local para reduzir cold start.
        await asyncio.to_thread(prewarm_llm)


@app.post("/webhook")
async def webhook(body: WebhookRequest, request: Request):
    correlation_id = os.getenv("CORRELATION_ID") or os.urandom(8).hex()
    request.state.correlation_id = correlation_id
    # Only expose the textual reply to the client; hide internal state/session details.
    result = handle_message(body.session_id, body.message, name=body.name, correlation_id=correlation_id)
    if isinstance(result, dict) and "reply" in result:
        return {"reply": result["reply"]}
    return result


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
