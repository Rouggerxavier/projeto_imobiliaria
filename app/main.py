from __future__ import annotations
import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from agent.controller import handle_message

load_dotenv()
app = FastAPI(title="Agente Imobiliário WhatsApp", version="0.1.0")


class WebhookRequest(BaseModel):
    session_id: str
    message: str
    name: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(body: WebhookRequest):
    result = handle_message(body.session_id, body.message, name=body.name)
    return result


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
