# 📱 WhatsApp Integration - Implementação Completa

## ✅ Status da Implementação

**Implementado e testado com sucesso!**

- ✅ Recepção de mensagens via webhook
- ✅ Extração de `from` e `text.body` do payload
- ✅ Envio de respostas via WhatsApp Cloud API
- ✅ Logs estruturados e seguros
- ✅ Modo teste (DISABLE_WHATSAPP_SEND)
- ✅ Tratamento de erros e timeouts

---

## 📂 Arquivos Criados

### 1. Serviço de Envio ([app/services/whatsapp_sender.py](app/services/whatsapp_sender.py))

**Funções:**
- `send_whatsapp_message(to, message)`: Envia mensagem via WhatsApp Cloud API
- `extract_message_from_webhook(payload)`: Extrai dados de mensagem do webhook

**Recursos:**
- Chamada assíncrona com `httpx`
- Rate limiting e timeout (30s)
- Logs sanitizados (oculta parte do número de telefone)
- Modo teste integrado

### 2. Webhook Atualizado ([app/routes/whatsapp.py](app/routes/whatsapp.py))

**Fluxo POST:**
1. Valida assinatura X-Hub-Signature-256
2. Extrai mensagem do payload
3. Loga evento com segurança
4. Envia resposta: "Olá! Recebi sua mensagem."
5. Retorna 200 OK rapidamente

### 3. Teste End-to-End ([test_whatsapp_flow.py](test_whatsapp_flow.py))

**Cenários testados:**
- Mensagem de texto recebida → resposta enviada
- Mensagem não-texto (imagem) → ignorada graciosamente

---

## 🧪 Testes Locais (Modo Teste)

### Executar Testes Automatizados

```bash
# Testar fluxo completo
python test_whatsapp_flow.py

# Testes existentes ainda funcionam
python test_endpoints.py
```

**Resultado esperado:**
```
[SUCCESS] All WhatsApp flow tests passed!
```

### Simular Webhook Manualmente

```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "id": "123456",
      "changes": [{
        "value": {
          "messages": [{
            "from": "5511999999999",
            "id": "msg_123",
            "timestamp": "1234567890",
            "type": "text",
            "text": {"body": "Olá, quero informações"}
          }]
        }
      }]
    }]
  }'
```

**Logs esperados:**
```
WhatsApp webhook received - type=whatsapp_business_account, entries=1, messages=1
Message received - from=55119***, msg_id=msg_123, text_preview=Olá, quero informações
WhatsApp send disabled - would send to 55119***9999: Olá! Recebi sua mensagem.
Response sent - to=55119***, response=Olá! Recebi sua mensagem.
```

---

## 🚀 Configuração para Produção (WhatsApp Real)

### Passo 1: Obter Credenciais do Meta

1. Acesse: https://developers.facebook.com/apps/
2. Selecione seu App → **WhatsApp** → **Getting Started**
3. Copie:
   - **Access Token** (temporário ou gere permanente)
   - **Phone Number ID**
   - **App Secret** (Settings → Basic)

### Passo 2: Configurar no Render

Adicione as variáveis de ambiente:

```bash
# Obrigatórias para envio real
WHATSAPP_ACCESS_TOKEN=EAAxxxxxxxxxxxxx  # Token do Meta
WHATSAPP_PHONE_NUMBER_ID=123456789      # Phone Number ID

# Habilitar envio real
DISABLE_WHATSAPP_SEND=false

# Recomendado
WHATSAPP_APP_SECRET=xxxxxxxxxxxxxxxx
WHATSAPP_VERIFY_TOKEN=seu_token_seguro
APP_ENV=production
LOG_LEVEL=INFO
```

### Passo 3: Configurar Webhook no Meta

1. WhatsApp → **Configuration** → **Webhook**
2. Preencha:
   ```
   Callback URL: https://seu-app.onrender.com/webhook/whatsapp
   Verify Token: <mesmo valor de WHATSAPP_VERIFY_TOKEN>
   ```
3. **Verify and Save**
4. Subscribe: `messages`

### Passo 4: Testar com Número Real

1. Adicione seu número de teste no Meta Developers
2. Envie mensagem pelo WhatsApp para o número configurado
3. Verifique logs no Render:
   ```
   Message received - from=55119***
   Response sent - to=55119***, response=Olá! Recebi sua mensagem.
   ```
4. Confirme recebimento da resposta no WhatsApp

---

## 🔄 Próximas Integrações

### Fase 1: Integração com Agente IA (Recomendado)

Atualmente envia resposta fixa. Para integrar com o agente inteligente:

**Editar `app/routes/whatsapp.py`:**

```python
from app.agent.controller import handle_message

# No webhook POST, após extrair message_data:
if message_data:
    from_number = message_data["from"]
    text = message_data["text"]

    # Usar número como session_id (ou mapear para session existente)
    session_id = f"whatsapp_{from_number}"

    # Chamar agente
    result = handle_message(
        session_id=session_id,
        message=text,
        name=None,  # Pode extrair do payload se disponível
    )

    # Enviar resposta do agente
    response_text = result.get("reply", "Desculpe, houve um erro.")
    await send_whatsapp_message(from_number, response_text)
```

### Fase 2: Persistência de Sessão

- Mapear `phone_number` → `session_id`
- Armazenar mapeamento em Redis ou banco
- Recuperar sessão existente ou criar nova

### Fase 3: Funcionalidades Avançadas

- **Mensagens com mídia**: Enviar imagens de imóveis
- **Botões interativos**: Quick replies para opções
- **Templates**: Mensagens pré-aprovadas pelo Meta
- **Status de entrega**: Processar webhooks de `message_status`

---

## 📊 Estrutura do Payload WhatsApp

### Mensagem Recebida (Webhook POST)

```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "business_account_id",
    "changes": [{
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {
          "display_phone_number": "15551234567",
          "phone_number_id": "123456789"
        },
        "contacts": [{
          "profile": {"name": "John Doe"},
          "wa_id": "5511999999999"
        }],
        "messages": [{
          "from": "5511999999999",
          "id": "wamid.xxx",
          "timestamp": "1234567890",
          "type": "text",
          "text": {"body": "Mensagem do usuário"}
        }]
      },
      "field": "messages"
    }]
  }]
}
```

### Envio de Mensagem (API Request)

```bash
POST https://graph.facebook.com/v21.0/{phone_number_id}/messages
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "messaging_product": "whatsapp",
  "to": "5511999999999",
  "type": "text",
  "text": {
    "body": "Olá! Recebi sua mensagem."
  }
}
```

### Resposta de Envio

```json
{
  "messaging_product": "whatsapp",
  "contacts": [{
    "input": "5511999999999",
    "wa_id": "5511999999999"
  }],
  "messages": [{
    "id": "wamid.HBgNNTUxMTk5OTk5OTk5ORUCABIYIDNFQjBDMDRGRj..."
  }]
}
```

---

## 🔒 Segurança

### Implementado

- ✅ Validação de assinatura X-Hub-Signature-256
- ✅ Sanitização de logs (telefones parcialmente ocultos)
- ✅ Tokens sanitizados automaticamente
- ✅ Timeout de 30s para evitar travamentos
- ✅ Tratamento de erros sem expor detalhes ao cliente

### Boas Práticas

1. **Sempre valide assinatura em produção**: Configure `WHATSAPP_APP_SECRET`
2. **Use System User Token**: Token temporário expira em 24h
3. **Rate limiting**: WhatsApp tem limites (1000 msg/dia para iniciantes)
4. **Não logue PII**: Números de telefone são parcialmente mascarados
5. **Respostas rápidas**: Webhook deve responder em <20s

---

## 🐛 Troubleshooting

### Erro: "WHATSAPP_ACCESS_TOKEN not configured"

**Causa:** Credenciais não configuradas e `DISABLE_WHATSAPP_SEND=false`

**Solução:**
- Configurar `WHATSAPP_ACCESS_TOKEN` e `WHATSAPP_PHONE_NUMBER_ID`
- OU manter `DISABLE_WHATSAPP_SEND=true` para modo teste

### Erro: "WhatsApp API returned 401"

**Causa:** Access token inválido ou expirado

**Solução:**
- Renovar token no Meta Developers
- Gerar System User Token permanente

### Erro: "WhatsApp API returned 400"

**Possíveis causas:**
- Formato de telefone inválido (deve ser internacional: 5511999999999)
- Phone Number ID incorreto
- Mensagem vazia ou muito longa (> 4096 caracteres)

**Solução:**
- Verificar logs para detalhes do erro
- Confirmar Phone Number ID no Meta

### Mensagens não chegam

**Checklist:**
1. Webhook configurado corretamente no Meta? (verde)
2. `messages` subscrito nos eventos?
3. Número de teste adicionado no Meta?
4. Serviço no Render está rodando?
5. Logs mostram "Message received"?

---

## 📚 Recursos

- **WhatsApp Business API**: https://developers.facebook.com/docs/whatsapp/cloud-api/
- **Mensagens**: https://developers.facebook.com/docs/whatsapp/cloud-api/messages
- **Webhooks**: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
- **Rate Limits**: https://developers.facebook.com/docs/whatsapp/cloud-api/overview#throughput

---

## ✅ Checklist de Deploy

- [ ] Credenciais configuradas no Render
- [ ] `DISABLE_WHATSAPP_SEND=false` para produção
- [ ] Webhook verificado no Meta (verde)
- [ ] Eventos `messages` subscritos
- [ ] Número de teste adicionado
- [ ] Teste enviando mensagem real
- [ ] Resposta recebida no WhatsApp
- [ ] Logs verificados no Render
- [ ] (Opcional) Integração com agente IA implementada

---

**🎉 Parabéns!** Seu WhatsApp está pronto para receber e responder mensagens automaticamente!

Para integrar com o agente IA inteligente, edite [app/routes/whatsapp.py](app/routes/whatsapp.py) conforme **Fase 1** acima.
