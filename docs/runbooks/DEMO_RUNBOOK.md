# Runbook de Demo do SuperEzio

Procedimento para demonstrar o SuperEzio a visitantes. A demo de 2026-08-24
falhou por três estrangulamentos de capacidade (janela de contexto 8192 do
modelo local, slot único de inferência, sem mensagem honesta de degradação).
Este runbook elimina os três antes do primeiro convidado chegar.

## Pré-flight (30-60 min antes, obrigatório)

1. **Fechar TODAS as sessões que usam o slot do modelo** (:8080, `-np 1`):
   sessões Claude Code rodando contra o perfil local `cc`, o `watchdog_ceo.ps1`
   em recuperação, qualquer script de pipeline. O slot é UM atendente.
2. **Saúde**: `curl http://127.0.0.1:8002/health` deve dar 200 e
   `curl http://127.0.0.1:8080/health` deve dar 200. Em
   `/health/details`, circuit breakers todos `closed`.
3. **Janela de contexto**: verificar no log do CEO
   (`runtime/logs/ceo-serve-mmproj-*.err.log`) se não há `send_error ...
   exceeds the available context size` recente. Se houver, reiniciar o
   llama-server com `-c 16384` ou `-c 32768` (testar VRAM: `nvidia-smi`;
   a RTX 2070 8GB viva nao aguenta q8_0 maior que 8192; a 3060 esta FAILED_ADD).
4. **Código atualizado**: reiniciar a API `:8002` se o processo estiver
   rodando código anterior ao HEAD (`git log --oneline -1` vs horário de
   boot do processo). O frontend é servido do disco — sempre atual.
5. **Rede**: para convidados externos, a API precisa estar na interface
   certa (túnel/IP externo). A instância local padrão escuta só
   `127.0.0.1`.
6. **Aquecer o cache do modelo**: mandar 1 pergunta de teste pelo cockpit
   ("como está o mercado hoje?") e esperar a resposta completa. A segunda
   pergunta idêntica será ~4x mais rápida.

## Script da demo (o que mostrar, nessa ordem)

1. **Smalltalk**: "oi bob" — resposta instantânea (~1s). Mostra o fast-path.
2. **Uma análise com ticker**: "analise PETR4 pra mim" — resposta em
   ~1-2 min. AVISAR os convidados que a análise é profunda e leva esse
   tempo. Nunca deixar silêncio sem explicação.
3. **Um clique de trade**: mostrar o ticket criado (`Ticket ... — not
   submitted to broker`). Explicar que execução real está congelada por
   design (EXECUTION_FREEZE).
4. **NÃO fazer**: várias pessoas perguntando ao mesmo tempo (fila de ~2
   min por pergunta), conversa longa com o Bob (estoura a janela de 8192),
   anexar imagens na conversa (consome janela via mmproj).

## Se algo falhar na hora

| Sintoma | Causa provável | Ação |
|---|---|---|
| Bob mudo + "espaço de contexto insuficiente" | Janela 8192 estourada | Recarregar a página (zera o histórico); pergunta mais curta; sem anexos |
| Bob mudo + "cérebro sobrecarregado" | CEO fora / 3 falhas seguidas (MAN_AT_WORK) | `curl http://127.0.0.1:8080/health`; se fora, relançar o llama-server e aguardar o ANS recuperar (a cada ciclo) |
| Tudo lento | Slot ocupado por outra sessão | Fechar a outra sessão; aguardar a fila |
| Erro de trade no cockpit | `SUPEREZIO_API_KEY` setada sem open access (401) | Desligar a API_KEY ou ligar `SUPEREZIO_OPEN_ACCESS=1`; reiniciar a API |
| "CORE MAN_AT_WORK" no top bar | Modo diagnóstico ativo | Não é defeito — explicar aos convidados que o sistema detectou o cérebro fora e se protegeu |

## Pós-demo

- `curl /health/details` e conferir circuit breakers.
- Se MAN_AT_WORK engajou: aguardar a recuperação automática (checada a cada
  ciclo; sai sozinho quando o CEO voltar).
