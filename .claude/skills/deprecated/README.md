# Cemitério de Skills — deprecated/

Skills movidas para cá são duplicatas ou absorvidas por canônicas. Política:
- **Nada é apagado** — git mv preserva histórico.
- A canônica de cada movida está anotada no topo do SKILL.md movido.
- Após 30 dias sem uso, o operador decide: arquivar em `.f51/archive/` ou matar.

Movidas em 2026-08-26 — onda 1 (auditoria de legado — agent-explorer):
- f51-contract-watchdog → canônica: f51-contracts
- arqueologist → canônica: agente recon-researcher
- f51-orchestrator → canônica: agente captain
- f51-executor → canônica: agente product-implementer
- f51-metrics-dash → canônica: f51-observability

Movidas em 2026-08-26 — onda 5 (decisão skill a skill sobre órfãs — agent-explorer):
- f51-audit → canônica: f51-quality-gate (auditoria de risco/regressão absorvida pelo gate + release-readiness-manager)
- f51-dependency-scout → canônica: f51-dead-code (deps órfãs via deptry; upgrade-risk sem dono)
- f51-loop-breaker → função absorvida por .claude/commands/agent-lab.md (stop conditions); nome colidia com f51-circuit-breaker ativo
- f51-regression-hunter → canônica: f51-quality-gate + f51-tests (cluster de verificação)
- f51-release → canônica: f51-quality-gate + agente release-readiness-manager (PASS/FAIL duplicado)
- f51-test-finder → canônica: f51-tests (~100% duplicata)
