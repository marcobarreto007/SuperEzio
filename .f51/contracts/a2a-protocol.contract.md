# A2A Protocol Contract

**Module:** `src/core/ports/protocol.py`
**Classification:** core

## Public API

### MessageType (Enum)

| Value | String | Uso |
|-------|--------|-----|
| CAPABILITIES_REQUEST | "CAPABILITIES.REQUEST" | Solicita capacidades do agente |
| CAPABILITIES_RESPONSE | "CAPABILITIES.RESPONSE" | Resposta de capacidades |
| TASK_SUBMIT | "TASK.SUBMIT" | Submissão de tarefa ao pipeline |
| TASK_RESULT | "TASK.RESULT" | Resultado final da tarefa |
| TASK_STREAM | "TASK.STREAM" | Streaming de chunks |
| EVENT_PUBLISH | "EVENT.PUBLISH" | Publicação de evento |
| ERROR | "ERROR" | Mensagem de erro |

### A2AMessage (BaseModel)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| version | str | yes | "a2a/1.0" | Versão do protocolo |
| msg_id | str | auto | uuid4() | ID único da mensagem |
| correlation_id | str | auto | uuid4() | ID de correlação (respostas usam o mesmo) |
| trace_id | str | auto | uuid4() | ID de trace (pipeline run) |
| from_agent | str | yes (alias "from") | — | Agente remetente |
| to_agent | str | yes (alias "to") | — | Agente destinatário |
| type | MessageType | yes | — | Tipo da mensagem |
| timestamp | float | auto | time.time() | Timestamp Unix |
| deadline_ms | int | no | None | Deadline em ms |
| priority | int | no | 1 | Prioridade (1-5) |
| budget | float | no | None | Budget computacional |
| payload | dict | auto | {} | Corpo da mensagem |
| attachments | list | auto | [] | Anexos |

### A2AMessage.create_response (classmethod)

Cria resposta vinculada à mensagem original:
- `correlation_id` = original.correlation_id
- `trace_id` = original.trace_id
- `from_agent` = caller especificado
- `to_agent` = original.from_agent
- `type` = caller especificado
- `payload` = caller especificado

## Invariants

1. `msg_id`, `correlation_id`, `trace_id` são UUID4 strings.
2. `from_agent` e `to_agent` são obrigatórios (validado por Pydantic).
3. `type` é sempre um MessageType válido (validado por Pydantic).
4. `create_response` preserva correlation_id e trace_id da mensagem original.

## Dependencies

- `pydantic` (BaseModel, ConfigDict, Field)
- `uuid`, `time`, `enum`
- Sem dependências de rede ou modelo
