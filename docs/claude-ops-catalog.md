# Claude Ops Catalog

Catálogo local dos skills e MCPs pedidos para o ecossistema do SuperEzio.

## Skills adicionados neste patch

Os seguintes skills passaram a existir em `.claude/skills/`:

- `deep-architect`
- `f51-impact-map`
- `f51-quality-gate`
- `f51-regression-hunter`
- `simplify`
- `review`
- `init`
- `loop`
- `schedule`
- `claude-api`
- `update-config`
- `security-review`
- `fewer-permission-prompts`

## Skills já existentes no repositório

Já estavam presentes:

- `skill-router`
- `f51-auditor`
- `f51-executor`
- `f51-productizer`
- `f51-safety-science`
- `detection-engineer`
- `specialized-file-analyzer`

## MCPs catalogados

Inventário machine-readable:

- `.claude/mcp-catalog.json`

Script de registro no Claude Code:

- `scripts/setup_claude_mcp.ps1`

### MCPs incluídos

- Google Calendar — `https://calendarmcp.googleapis.com/mcp/v1`
- Gmail — `https://gmailmcp.googleapis.com/mcp/v1`
- Google Drive — `https://drivemcp.googleapis.com/mcp/v1`
- Notion — `https://mcp.notion.com/mcp`
- Vercel — `https://mcp.vercel.com`
- Canva — `https://mcp.canva.com/mcp`
- Hugging Face — `https://huggingface.co/mcp`
- Play Sheet Music — `https://modelcontextprotocol.io/sheet-music/mcp`

## Como registrar os MCPs

No PowerShell, a partir da raiz do projeto:

`powershell -ExecutionPolicy Bypass -File .\scripts\setup_claude_mcp.ps1`

Escopo alternativo:

`powershell -ExecutionPolicy Bypass -File .\scripts\setup_claude_mcp.ps1 -Scope user`

## Fluxos recomendados

### Nova Feature Crítica

1. `deep-architect`
2. `f51-impact-map`
3. `f51-executor`
4. `f51-quality-gate`

### Bug em Produção

1. `f51-auditor`
2. `f51-executor`
3. `f51-regression-hunter`
4. Vercel MCP

### Agente Autônomo

1. `claude-api`
2. `schedule`
3. Gmail + Calendar MCP
4. `loop`

### Produto → Mercado

1. `f51-productizer`
2. Canva MCP
3. Notion MCP
4. Vercel MCP

## Observações

- As URLs dos MCPs foram registradas exatamente como pedidas pelo usuário.
- A consulta web desses endpoints foi bloqueada por política de rede do ambiente atual, então o catálogo local foi montado a partir do inventário fornecido pelo usuário e da sintaxe validada pelo próprio `claude mcp add --transport http`.
- Alguns MCPs podem exigir OAuth ou autenticação específica no primeiro uso.