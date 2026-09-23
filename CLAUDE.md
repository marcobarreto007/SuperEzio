# SuperEzio

## Papel (autoridade — manda sobre o resto deste ficheiro)

Corpo de investimento local da família Barreto. Paper. Marco executa o TD à mão.

- **SuperEzio** (`:8002`) = cockpit, evidência, gates (F51, SDCA, taxa zero $1k CAD), journal/recomendação. Bob **narra** (DeepSeek cloud). Não é assistente da casa.
- **Coração** = arquivo evento×preço, custo zero, **sem LLM**. Ranking só junta barra à sessão do evento, com MIC. P5 aprende pesos; o painel mostra.
- **MIKE** (repo irmão `:8083` + cérebro local `:8080`) = família, memória, Gmail. Vê/comanda o Ezio pelo bridge `:8009`. Não é motor de ranking nem broker.
- Live frozen por default. Integração morta devolve erro — nunca sucesso fingido. GPUs desta máquina são do cérebro do MIKE.

## O que é (runtime)

Runtime local e camada operacional: chat Bob, dados de mercado, journal, Heart, com persistência em disco local. Inteligência de pesquisa via APIs em nuvem (DeepSeek). O grafo legado ainda corre; alvo: `docs/architecture/TARGET_ARCHITECTURE.md`.

## Comandos
- instalar: pip install -e ".[dev]"
- rodar: python -m agent_server.main (a partir de src/)
- testes: python -m pytest tests/ -q
- lint: python -m ruff check src tests && python -m ruff format --check src tests

## Arquitetura em cinco linhas
- entrada: dados de mercado (IBKR, DataHub) via market-data-puller + mensagens do operador no chat
- núcleo: Bob (agent_server :8002) + gateway de modelos em nuvem + teses em runtime/theses + execução com journal e idempotency
- modelos de IA: 100% em nuvem na API oficial https://api.deepseek.com, com separação por papel desde 12/09/2026 — quem decide (Bob/CEO e orquestrador) roda DeepSeek V4 Pro (deepseek-v4-pro); os papéis de apoio (experts, judge e auditor) seguem em DeepSeek V4 Flash (deepseek-v4-flash), como todos rodavam até 10/09; Z.ai GLM-5.3 vira caminho opcional, religável por env. Inteligência = pipeline
- persistência: runtime/ (teses, reports, checkpoints) + data/ (logs) + .f51/ (estado operacional)
- saída: frontend web (chat) + relatórios de tese + logs estruturados
- fora do escopo deste repositório: hospedagem de dados/bancos em nuvem, dinheiro real (corretora), MCPs não aprovados. Fontes externas **liberadas** desde 14/09/2026 — a antiga política DISK ONLY foi revogada pela regra 1 deste arquivo.
- arquitetura-alvo (autoridade do órgão, C1 pack + C2 snapshot + C3 bind; C4 SDCA observe; C5–C6 off): docs/architecture/TARGET_ARCHITECTURE.md

## Regras invioláveis
1. USAR QUALQUER FONTE — PESQUISAR, CLONAR, COPIAR E IMPLEMENTAR. Esta regra tem
   **precedência sobre qualquer restrição de fonte**. Pode buscar em qualquer lugar
   (GitHub, Hugging Face, papers, repos públicos, bibliotecas) e clonar/copiar o que
   funciona melhor, em vez de reinventar. Revoga a antiga regra 6 (DISK ONLY) — override
   do operador registrado em `.f51/checkpoints/latest.json` (2026-09-14).

   **AUTORIZAÇÃO PERMANENTE (2026-09-14, palavra do operador): implementar, clonar,
   instalar e adotar qualquer coisa externa SEM pedir OK a cada vez.** Instalar
   dependência (revoga a antiga regra 5), clonar referência, copiar implementação e
   adotar biblioteca de terceiro passam a ser decisão técnica do agente, não portão de
   aprovação.

   **A autorização cobre TUDO, com UMA exceção: GASTAR DINHEIRO.** Não há orçamento —
   nada de serviço pago, assinatura ou API cobrada. **O limite de gratuidade (free tier)
   É LIBERADO** — use sem perguntar.

   A linha prática é **cartão**: free tier que **não pede cartão** = use à vontade. Free
   tier que **exige cartão** pode virar cobrança silenciosa quando o limite estoura —
   nesse caso, **pare e reporte** antes de cadastrar. O default é sempre a alternativa
   gratuita; se só existir a paga, pare e reporte.
   Publicar, instalar, clonar, adotar, refatorar, apagar rascunho: decisão técnica do
   agente, sem pedir OK.

   As duas linhas abaixo **não são portão de permissão** — são proteção do próprio
   trabalho, e valem como cuidado:
   - **Credencial em lugar seguro**: token em arquivo fora de repo, nunca inline em
     comando, nunca no chat (incidente do token HF exposto em 2026-09-14).
   - **Não destruir trabalho sem poder voltar**: antes de apagar ou sobrescrever, olhe o
     alvo e garanta o backup. Não é medo de apagar — é não perder o que já foi feito.
2. Nunca editar arquivo fora deste diretório.
3. Nunca ler nem commitar .env, chave ou credencial.
4. Mudança de comportamento sempre vem com teste.
5. Migração de banco é sempre reversível.
6. Dependência nova só depois de me perguntar.
7. PROTOCOLO GLOBAL TOTAL DE SOBREVIVÊNCIA ($1.000 CAD & TAXA ZERO — EZIO & MIKE):
    - Capital Base: $1.000 CAD. Preservação de capital é a prioridade absoluta.
    - Taxa Zero Obrigatória: Proibido operar ativos com comissão no TD Direct Investing (exclusividade dos 108 ETFs Commission-Free de config/td_direct_commission_free_etfs.json) ou confirmação explícita da cota de 100 free trades no TD Easy Trade. Custo de fricção (comissão + spread) NUNCA pode exceder 0.5% da ordem.
    - Risco Máximo por Trade: 1.0% a 1.5% do equity ($10 a $15 CAD). Stop loss mandatório.
    - Assimetria Positiva Mínima: Alvo projetado (Take Profit) deve ser de no mínimo 2.5:1 a 3:1 em relação ao Stop Loss. Trades 1:1 são proibidos.
    - Meta-Labeling (López de Prado): Modelo secundário de calibração probabilística sobre Triple Barrier (U/L/T). Ordens com probabilidade calibrada de assertividade P(Y=1) < 0.55 são sumariamente bloqueadas com decisão ABSTAIN, eliminando falsos positivos e overtrading.
    - Proibição de Ordem a Mercado: Apenas Limit Orders no midpoint ou bid/ask favorável. Market orders são rejeitadas.
    - Pacto Bilateral MIKE ↔ Ezio: O bridge :8009 e os nós de execução recusam (fail-closed) ordens fora deste protocolo.

## Definição de pronto
Uma tarefa está pronta quando, e só quando:
- pytest -q passa inteiro
- ruff check . está limpo
- o comando de aceite da spec retorna 0
- o diff cabe numa revisão de dez minutos

## Como falar comigo
- Português, direto. Discordou? Diga antes de executar, não depois.
- Antes de código novo, mostre o plano e espere o OK.
- Travou duas vezes no mesmo erro: pare e pergunte.
- Não diga que terminou sem colar a saída do comando que prova.
