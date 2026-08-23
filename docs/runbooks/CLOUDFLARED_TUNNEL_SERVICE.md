# Runbook — Cloudflared Tunnel (superezio) como Serviço Windows

## Serviço / Componente

- Nome: `Cloudflared` (Windows service, quando instalado) / processo `cloudflared.exe`
- Dono: Operação SuperEzio (reliability-sre-operator)
- Criticidade: Alta — o túnel expõe `https://supereziorealtime.com`, `www.*` e `cockpit.*` para a API local
- Binário: `C:\Program Files (x86)\cloudflared\cloudflared.exe` (v2026.8.2)
- Config: `C:\Users\marco\.cloudflared\config.yml`
- Túnel: `superezio` — UUID `22e6fc68-8166-43be-a5b2-6e8b33803571`
- Credencial: `C:\Users\marco\.cloudflared\22e6fc68-8166-43be-a5b2-6e8b33803571.json`

## Pré-requisitos

- Shell elevado (Administrador) para instalar/iniciar o serviço:
  - `sc create`/`sc start` exigem token elevado (UAC). Sem ele, `cloudflared service install` falha com
    `Cannot establish a connection to the service control manager: Access is denied`.
- API local no ar: `http://127.0.0.1:8002` (health 200). Nunca expor `:8080` no ingress.
- Config validada (ingress ÚNICO `127.0.0.1:8002`, nunca `:8080`):

```yaml
tunnel: 22e6fc68-8166-43be-a5b2-6e8b33803571
credentials-file: C:\Users\marco\.cloudflared\22e6fc68-8166-43be-a5b2-6e8b33803571.json
ingress:
  - hostname: cockpit.supereziorealtime.com
    service: http://127.0.0.1:8002
  - hostname: supereziorealtime.com
    service: http://127.0.0.1:8002
  - hostname: www.supereziorealtime.com
    service: http://127.0.0.1:8002
  - service: http_status:404
```

## Instalação como Serviço Windows (uma vez)

Em PowerShell/CMD **elevado** (Administrador):

```powershell
# 1. Instalar (registra o serviço "Cloudflared" com auto-start)
& 'C:\Program Files (x86)\cloudflared\cloudflared.exe' service install

# 2. Verificar o serviço registrado
sc.exe query Cloudflared
sc.exe qc Cloudflared   # Start Type deve ser AUTO_START

# 3. Iniciar
sc.exe start Cloudflared

# 4. Aguardar ~10-15s e confirmar estado RUNNING
sc.exe query Cloudflared
```

Depois que o serviço estiver RUNNING e o domínio responder 200, o processo avulso antigo
(que morre com a sessão) pode ser encerrado — validar identidade antes:

```cmd
tasklist | findstr /i cloudflared
wmic process where "name='cloudflared.exe'" get processid,commandline
taskkill /PID <PID> /F   :: somente se commandline == "tunnel run superezio" e o serviço estiver RUNNING
```

## Start (se o serviço cair)

```cmd
sc.exe start Cloudflared
```

Se o serviço não existir (erro 1060), refazer a instalação elevada (seção acima).

## Health Check

- Público: `curl -s -o /dev/null -w "%{http_code}" https://supereziorealtime.com` → `200`
- API local: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8002/health` → `200`
- Serviço: `sc.exe query Cloudflared` → `STATE: RUNNING`
- Túnel: `cloudflared tunnel list` → linha `superezio` com CONNECTIONS não vazia
  (ex.: `2xyul01, 1xyyz04, 1xyyz06` = IDs de edge; cada connector abre múltiplas conexões)
- Connector: `cloudflared tunnel info superezio` → CONNECTOR ID presente, VERSION ok

## Diagnóstico rápido

- Processo: `tasklist | findstr /i cloudflared` (avulso = Console session; serviço = Services session)
- Serviço: `sc.exe query Cloudflared` (1060 = não instalado)
- Logs: `C:\Users\marco\.cloudflared\` (config) + logs do serviço via `sc query` / Event Viewer
- Erro comum: `Access is denied` no install → shell não está elevado
- Erro comum: domínio 502/530 → API local `:8002` fora do ar OU ingress apontando para porta errada

## Recovery

- Passo 1: `sc.exe start Cloudflared` (ou, se 1060, reinstalar elevado + start)
- Passo 2: `curl -s -o /dev/null -w "%{http_code}" https://supereziorealtime.com` → aguardar 200
- Passo 3: `cloudflared tunnel list` + `cloudflared tunnel info superezio` → conexões ativas
- Passo 4: se o túnel aparecer sem conexões mas o processo vivo, reiniciar o serviço
  (`sc.exe stop Cloudflared && sc.exe start Cloudflared`)

## DNS

- Nameservers: Cloudflare (`armando.ns.cloudflare.com` / `dana.ns.cloudflare.com`)
- Apex `supereziorealtime.com` → Cloudflare anycast (ex.: `104.21.7.223`, `172.67.156.126`, IPv6 `2606:4700:...`)
- `www.*` e `cockpit.*` → A proxied Cloudflare (ex.: `172.64.80.1`)
- Zona sem CNAME explícito `<uuid>.cfargotunnel.com` (registros A proxied; roteamento via ingress do túnel)
- Verificação: `nslookup supereziorealtime.com 1.1.1.1` → IPs Cloudflare; domínio 200 ⇒ tráfego chega ao túnel

## Escalonamento

- Quando escalar: domínio fora do ar por > 5 min, serviço não sobe, tunnel list vazio por mais de 10 min
- Para quem: operador SuperEzio com shell elevado (instalação exige UAC/admin)

## Evidências de execução

- Data/hora: 2026-08-23 18:55–19:00 (diagnóstico R2)
- Operador: reliability-sre-operator
- Estado no diagnóstico: serviço NÃO instalado (SC 1060); cloudflared avulso PID 12876
  (`tunnel run superezio`); domínio 200; API `:8002` 200; túnel 3 conexões de edge
- Ação pendente: rodar `cloudflared service install` em shell elevado (bloqueado por privilégio no agente)
