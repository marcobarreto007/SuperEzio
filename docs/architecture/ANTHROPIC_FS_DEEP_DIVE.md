# Deep Dive — Arquitetura anthropics/financial-services

**Data:** 2026-08-18 · **Complementa:** `AGENT_PATTERNS_ANTHROPIC_FS.md` (parte 1: padrões de prompt)
**Método:** 4 exploradores paralelos (orquestradores, skills, maquinário, packaging) + 1 fetch da sessão principal. Tudo leitura pública web read-only (F51_NO_GITHUB_DISK_ONLY: nada clonado/instalado). Gaps honestos: `meeting-prep-agent` extraído em modo resumo (sumarizador recusou verbatim); `scripts/recalc.py` 404 (path mudou ou não existe mais).

---

## 1. O sistema em uma página

```
MARKETPLACE (.claude-plugin/marketplace.json — catálogo mínimo: name/owner/plugins[])
   │
   ├── VERTICAL-PLUGINS (domínio)          ex.: financial-analysis, equity-research
   │     ├── .claude-plugin/plugin.json    (name/version/description — só isso)
   │     ├── .mcp.json                     (conectores CENTRALIZADOS por vertical)
   │     ├── commands/*.md                 (invocadores leves: "/thesis carrega thesis-tracker")
   │     ├── hooks/                        (lifecycle)
   │     └── skills/<slug>/SKILL.md        (a metodologia de verdade)
   │
   ├── AGENT-PLUGINS (especialista)        ex.: model-builder, pitch-agent
   │     ├── .claude-plugin/plugin.json
   │     ├── agents/<slug>.md              (orquestrador: What-you-produce/Workflow/Guardrails)
   │     └── skills/                       (CÓPIA curada das skills da vertical — sync-agent-skills.py)
   │
   └── MANAGED-AGENT-COOKBOOKS (deploy API)
         ├── agent.yaml                    (manifest: system.file+append, tools, mcp, skills, callable_agents)
         ├── steering-examples.json        (few-shots de roteamento handoff)
         └── subagents/*.yaml              (folhas depth-1: prompt mínimo + toolset + output_schema)

EVENT LOOP (scripts/orchestrate.py): stream → regex handoff_request → allowlist →
schema-validate → sessions.steer(alvo). GATES: check.py (estático, referências) +
validate.py (runtime, output_schema entre folha e orquestrador).
```

## 2. Catálogo dos 10 orquestradores

| Agente | Domínio | Tools notáveis | Skills invocadas | Guardrail único |
|---|---|---|---|---|
| model-builder | modelagem | Write + CapIQ/Daloopa | dcf/lbo/3-stmt/comps/audit-xls | "Every output is a formula" |
| market-researcher | pesquisa | Write + CapIQ/FactSet | sector-overview/competitive/comps/idea-gen | `[UNSOURCED]` em vez de estimar |
| earnings-reviewer | earnings | Write + FactSet/Daloopa | earnings-analysis/model-update/audit-xls/morning-note | transcripts = untrusted |
| pitch-agent | IB pitch | Write + CapIQ | 9 skills até ib-check-deck | stop-and-surface 2×; sem email/messaging |
| gl-reconciler | fund admin | **sem Write** | gl-recon/break-trace/audit-xls | **"The orchestrator never writes"** — resolver folha tem Write; sem GL posting |
| kyc-screener | onboarding | **sem Write** | kyc-doc-parse/kyc-rules | docs untrusted; **"recommends; compliance officer decides"** |
| month-end-closer | contabilidade | **sem Write** | accrual/roll-forward/variance | JE rascunho; posting exige controller |
| statement-auditor | LP statements | sem Write | nav-tieout/audit-xls | pass/hold; IR distribui com sign-off |
| valuation-reviewer | valuation | sem Write | returns/portfolio/ic-memo | pacotes GP untrusted; LP report exige IR+CCO |
| meeting-prep-agent | wealth | Write + CRM/CapIQ | client-review/client-report/investment-proposal | emails untrusted; **"No client-facing send"** |

**Padrão novo nº 1 — portões humanos por categoria de consequência.** Nenhum agente executa a ação consequential final: `No GL posting` (controller), `No external distribution` (analyst sênior/IR/CCO), `No risk-rating decision` (compliance), `No client-facing send` (advisor). O agente para em artefato + recomendação.

**Padrão novo nº 2 — orquestrador sem Write.** Nos 4 agentes de fund-admin o orquestrador é Read/Grep/Glob; a escrita vive numa folha nomeada (resolver/publisher/poster). Separar *decidir* de *executar no arquivo*.

## 3. Folhas (12 yamls)

Estrutura constante: `name: <time>-<folha>` · prompt de 1-4 linhas · tools deny-by-default (`default_config: {enabled: false}` + opt-in) · `callable_agents: []` (depth-1) · `output_schema` nas folhas que devolvem dados.

| Time | Folha | Tools | Schema notável |
|---|---|---|---|
| model-builder | data-puller | read, grep + CapIQ/Daloopa | ticker `^[A-Z.]+$`, historicals numérico |
| model-builder | builder | read, write, edit, bash (sandbox) | — ("ONLY worker with Write") |
| model-builder | auditor | read, grep | — (pass/fail com localizações) |
| market-researcher | sector-reader | read, grep | facts[]: claim ≤256 + source obrigatório, `additionalProperties:false` |
| market-researcher | comps-spreader | read, grep + CapIQ/FactSet | — |
| market-researcher | note-writer | read, write, edit | — ("Never open third-party reports directly") |
| earnings-reviewer | transcript-reader | read, grep | actuals numérico; guidance_notes ≤50 × 256 chars |
| earnings-reviewer | model-updater | + FactSet/Daloopa | "you do not write the final files" |
| earnings-reviewer | note-writer | read, write, edit | single-Write-holder |
| pitch-agent | researcher | + CapIQ/Daloopa | comps ≤30, precedents ≤30 (ticker/multiple/ev tipados) |
| pitch-agent | modeler | read + **bash** | calcula em Python, **devolve JSON** — não escreve o arquivo final |
| pitch-agent | deck-writer | read, write, edit | single-Write-holder |

**Padrão novo nº 3 — modeler computa e devolve JSON.** O cálculo (Bash/Python) é separado da escrita do artefato. Quem calcula não persiste; quem persiste não calcula.

**Padrão novo nº 4 — injeção tratada como classe universal.** Cada time declara sua fonte suja por nome (transcripts, custódia, pacotes GP, emails, onboarding) e o reader da folha fica SEM MCP e SEM write, devolvendo JSON limitado (`maxLength`/`maxItems`).

## 4. Skills — onde o domínio mora

Anatomia destilada de 15 SKILL.md:

```
frontmatter: name + description COM gatilhos ("Triggers on 'comps', 'trading multiples'...")
Workflow:    passos numerados, decisões explícitas, saída em ./out/<convenção de nome>
Key Principles (não-negociáveis)
Important Notes (erros comuns, hierarquia de fontes)
Output Checklist ([ ] itens de verificação)
DEFERRED:   references/ (enciclopédia de domínio) + scripts/ (validação executável)
            + TROUBLESHOOTING.md (catálogo de anti-padrões)
```

Fragmentos-chave (verbatim):

- **dcf-model:** "Formulas Over Hardcodes (NON-NEGOTIABLE) — Every projection... must be a live Excel formula — never a computed value. Correct: `ws["D20"] = "=D19*(1+$B$8)"` / Wrong: `ws["D20"] = calculated_revenue`"
- **comps-analysis (hierarquia de fontes):** "1. FIRST: Check MCP data sources... 2. DO NOT use web search if MCP sources available... NEVER use web search as primary data source"
- **audit-xls:** checklists executáveis — BS balanceia por período, RE rollforward, cash tie-out CF↔BS, CFO+CFI+CFF=ΔCash, D&A/CapEx cross-statement
- **thesis-tracker (falsificabilidade):** "A thesis should be falsifiable — if nothing could disprove it, it's not a thesis. Track disconfirming evidence as rigorously as confirming evidence... Store thesis data in a structured format for cross-session reference"
- **morning-note (opinião):** "Be opinionated — morning notes that just summarize news without a view are useless... If you're wrong, own it in the next morning note"
- **idea-generation:** bibliotecas de critérios reusáveis (value/growth/quality/short), "5-10 ideas, not 100"

**Nossa lacuna maior:** 31 skills locais, 100% dev-ops, 0 de domínio. A skill deles é onde o conhecimento financeiro-profundo vive (definições de métrica por indústria, convenções de cor, checklists de tie-out); nosso equivalente teria que codificar procedimento de mercado (leitura de candle/volume, gestão de risco por tamanho de posição, journaling).

## 5. Maquinário de orquestração

```python
# scripts/orchestrate.py — o coração (~30 linhas úteis)
ALLOWED_TARGETS = {"pitch-agent", "market-researcher", ..., "statement-auditor"}  # allowlist dura
HANDOFF_RE = re.compile(r'\{"type":\s*"handoff_request".*?\}', re.DOTALL)        # extração por regex
HANDOFF_PAYLOAD_SCHEMA = {"additionalProperties": False, "required": ["event"],
                          "properties": {"event": {"maxLength": 2000},
                                         "context_ref": {"maxLength": 256, "pattern": ...}}}
for event in stream:                      # 1. stream do agente-fonte
    handoff = extract_handoff(event.text)  # 2. regex no texto de SAÍDA
    if handoff["target_agent"] not in ALLOWED_TARGETS: continue   # 3. allowlist
    validate(handoff["payload"], HANDOFF_PAYLOAD_SCHEMA)          # 4. schema
    client...sessions.steer(agent_id=alvo, input=payload["event"]) # 5. roteia
```

Coordenação = **contrato no texto de saída + allowlist + schema + steer**. Nada de infra pesada. `agent.yaml` resolve tudo em deploy: `system.file` inlineado + `system.append` (contexto de ambiente, ex.: "You are running headless"), skills `from_plugin` expandido em paths, `callable_agents` deployados recursivamente.

## 6. Gates de qualidade (os checkers da própria Anthropic)

`check.py` (estático; exit 0 limpo / 1 issues):
1. Todo yaml parseia
2. Todo plugin.json/marketplace.json/steering-examples.json parseia
3. Todo agents/*.md tem frontmatter válida com name + description
4. **Todo `system.file`, `skills[].path`, `callable_agents[].manifest` resolve para arquivo existente**
5. Todo cookbook tem agent.yaml + README + steering-examples.json
6. Skill bundled == fonte vertical (byte-compare via `filecmp.dircmp`)
7. **Toda menção de skill em prosa existe na pasta skills/** (regex kebab-case)

`validate.py` (runtime): `jsonschema.validate(saída_da_folha, output_schema_do_yaml)` rodando **entre a folha e o orquestrador** — o contrato de saída é executado, não decorativo.

**Nós não tínhamos equivalente** — cross-refs quebrados em nossos 17 agentes/31 skills passariam em silêncio. → aplicado nesta task (seção 8).

## 7. Packaging

- Manifestos mínimos (name/version/description) — sem grafo de dependência; diferenciação vertical×agente só pela estrutura de diretórios.
- `.mcp.json` centralizado por vertical; `{"mcpServers": {nome: {type: "http", url}}}` — zero segredo no repo, env externa.
- **Command ≠ skill:** command = invocador leve (`/thesis [TICKER]` → "Load the `thesis-tracker` skill..."); skill = metodologia completa com verificação embutida. Command despacha, skill sabe.

## 8. Aplicação no SuperEzio (2026-08-18)

| Aplicação | O quê | Status |
|---|---|---|
| Gate de cross-refs | `scripts/check_agents.py`: frontmatter de agentes/skills, menções de skill existem, `subagent_type=`/roster existem como arquivo | **FEITO nesta task** (+ teste) |
| Skill de domínio nº 1 | `.claude/skills/tese-tracker/` — tese falsificável, scorecard de pilares, invalidação, catalysts, estado estruturado cross-session (`runtime/theses/`), anatomia oficial | **FEITO nesta task** |
| Wiring | `market-thesis-writer` agora invoca `tese-tracker` (workflow invoca skill nomeada, como no padrão) | **FEITO nesta task** |
| Orquestrador sem Write | captain degrada para dispatch-only (savekeeper = write-holder único) | **NÃO aplicado** — captain quase já é; deixar para task dedicada (mudança de comportamento, não de estrutura) |
| Portões por consequência | mapear TWO_PHASE_ORDER + money-gate como portões formais por categoria | **Roadmap** — já existe mecanismo; falta nomear/documentar |
| Event loop handoff | bus local com allowlist + schema | **Roadmap** — só quando houver >1 orquestrador residente interagindo |
| Skills de mercado (candle/volume, sizing, journaling) | próximas skills de domínio na anatomia oficial | **Roadmap** |
| Manifesto plugin local | desnecessário — não há distribuição; diretórios .claude/ já são o contrato | **Descartado** |

## 9. Veredito do mergulho

1. A arquitetura é **contratos o tempo todo**: frontmatter é contrato, output_schema é contrato, handoff é contrato, gate valida contrato. Nada de prosa sem verificação.
2. O conhecimento fica nas **skills** (procedimento + referências + troubleshooting), não nos agentes — agente é roteador com guardrails.
3. Segurança por **geometria** (quem lê não escreve; quem escreve não lê fonte suja; quem calcula não persiste), não por instrução.
4. Consequência real (postar, distribuir, decidir risco, enviar ao cliente) **sempre** sai do sistema por um portão humano nomeado.
5. Tudo é markdown + yaml + ~200 linhas de Python. Zero infra. Replicável disk-only — que é o que fizemos.
