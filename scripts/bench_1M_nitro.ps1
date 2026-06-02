# F51 NITRO 1M BENCHMARK — 20 testes complexos
# Modelo: Qwen3-Coder-Next 80B IQ4_XS (39.7 GB) | Modo Nitro (-ngl 999 --cpu-moe)
param(
    [int]$MaxTokens = 128,
    [string]$PromptDir = "C:\F51_LAB\prompts_1M"
)

$model = "C:\Users\marco\F51\models\Qwen3-Coder-Next-IQ4_XS.gguf"
$llama = "C:\Users\marco\F51\tools\llama.cpp\llama-server.exe"
$outDir = "C:\F51_LAB"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
New-Item -ItemType Directory -Force -Path $PromptDir | Out-Null
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$results = "$outDir\bench_1M_nitro_$timestamp.txt"
$now = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

"# F51 NITRO 1M BENCHMARK — $now" | Out-File $results
"# Model: Qwen3-Coder-Next 80B IQ4_XS | Modo: GPU attn + CPU MoE (--cpu-moe)" | Out-File $results -Append
"# Context: progressivo 64K ate 1M | MaxTokens: $MaxTokens" | Out-File $results -Append
"" | Out-File $results -Append

# ============================================================
# 20 TESTES: 10 financas + 5 codigo + 5 raciocinio
# Contextos: 64K, 128K, 256K, 512K, 1M
# ============================================================

$tests = @(
    # === FINANCAS (10) ===
    @{Id="T01"; Name="Fin_64K_Risco";         Ctx=65536;  Cat="Financas"; Desc="Analise de risco de portfolio com 64K de dados de mercado"},
    @{Id="T02"; Name="Fin_64K_Macro";          Ctx=65536;  Cat="Financas"; Desc="Analise macroeconomica com indicadores e earnings reports"},
    @{Id="T03"; Name="Fin_128K_Fraud";         Ctx=131072; Cat="Financas"; Desc="Detectar padroes de fraude em 128K transacoes financeiras"},
    @{Id="T04"; Name="Fin_128K_Valuation";     Ctx=131072; Cat="Financas"; Desc="Valuation de empresa com 128K de dados (DCF + comparaveis)"},
    @{Id="T05"; Name="Fin_256K_Portfolio";     Ctx=262144; Cat="Financas"; Desc="Rebalanceamento de portfolio multi-asset com 256K de historico"},
    @{Id="T06"; Name="Fin_256K_MAndA";         Ctx=262144; Cat="Financas"; Desc="Analise de fusao e aquisicao com documentos longos"},
    @{Id="T07"; Name="Fin_512K_Regulatory";    Ctx=524288; Cat="Financas"; Desc="Verificar compliance regulatorio em 512K de filings SEC/IFRS"},
    @{Id="T08"; Name="Fin_512K_Quant";         Ctx=524288; Cat="Financas"; Desc="Estrategia quantitativa com 512K de series temporais"},
    @{Id="T09"; Name="Fin_750K_GlobalMacro";   Ctx=786432; Cat="Financas"; Desc="Cenario macro global com 750K de dados multi-pais"},
    @{Id="T10"; Name="Fin_1M_Forense";         Ctx=1048576;Cat="Financas"; Desc="Auditoria forense com 1M tokens de registros contabeis [FLAGSHIP]"},

    # === CODIGO (5) ===
    @{Id="T11"; Name="Code_64K_Review";        Ctx=65536;  Cat="Codigo";  Desc="Code review de sistema distribuido com 64K de codigo"},
    @{Id="T12"; Name="Code_128K_Refactor";     Ctx=131072; Cat="Codigo";  Desc="Refatoracao de monorepo com 128K de codigo multi-arquivo"},
    @{Id="T13"; Name="Code_256K_Architecture"; Ctx=262144; Cat="Codigo";  Desc="Proposta de arquitetura baseada em 256K de documentacao tecnica"},
    @{Id="T14"; Name="Code_512K_Debug";        Ctx=524288; Cat="Codigo";  Desc="Debug de sistema complexo com 512K de logs + codigo"},
    @{Id="T15"; Name="Code_1M_Migration";      Ctx=1048576;Cat="Codigo";  Desc="Plano de migracao com 1M tokens de legacy code + docs [FLAGSHIP]"},

    # === RACIOCINIO (5) ===
    @{Id="T16"; Name="Reason_64K_Logic";       Ctx=65536;  Cat="Raciocinio"; Desc="Enigma logico multi-etapa com 64K de premissas encadeadas"},
    @{Id="T17"; Name="Reason_128K_Debate";     Ctx=131072; Cat="Raciocinio"; Desc="Analisar debate complexo com 128K de argumentos contra e a favor"},
    @{Id="T18"; Name="Reason_256K_Synthesis";  Ctx=262144; Cat="Raciocinio"; Desc="Sintese de 256K de artigos cientificos contraditorios"},
    @{Id="T19"; Name="Reason_512K_Strategy";   Ctx=524288; Cat="Raciocinio"; Desc="Estrategia de negocios com 512K de inteligencia competitiva"},
    @{Id="T20"; Name="Reason_1M_Espionage";    Ctx=1048576;Cat="Raciocinio"; Desc="Correlacionar 1M tokens de inteligencia multi-fonte [FLAGSHIP]"}
)

# ============================================================
# GERAR PROMPTS (Python)
# ============================================================
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GERANDO PROMPTS LONGOS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$genScript = @"
import os, json, math

out = r'$PromptDir'
os.makedirs(out, exist_ok=True)

# Base texts for different categories
finance_base = '''
ANNUAL FINANCIAL REPORT — FISCAL YEAR 2025
============================================

ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS

Overview
--------
The Company reported total revenue of \$847.3 million for the fiscal year ended December 31, 2025,
representing a 12.4% increase compared to \$754.1 million in fiscal 2024. Net income attributable to
common shareholders was \$142.7 million, or \$3.82 per diluted share, compared to \$98.3 million, or
\$2.64 per diluted share, in the prior year.

The increase in revenue was primarily driven by:
- 18.2% growth in Enterprise SaaS segment (\$312.5M vs \$264.4M)
- 9.7% growth in Professional Services (\$289.1M vs \$263.5M)
- 8.1% growth in Consumer segment (\$245.7M vs \$226.2M)

Gross margin improved to 72.3% from 69.8%, driven by economies of scale in cloud infrastructure
and optimization of our microservices architecture. Operating expenses increased 15.3% to \$412.5M,
primarily due to R&D investment in AI/ML capabilities (\$187.3M, +22.1% YoY) and sales expansion
in APAC markets (\$94.2M, +18.7% YoY).

BALANCE SHEET HIGHLIGHTS (in millions USD):
Cash and cash equivalents: \$1,247.3
Accounts receivable (net): \$312.7
Short-term investments: \$523.9
Total current assets: \$2,183.4
Property and equipment (net): \$487.2
Intangible assets (net): \$342.6
Goodwill: \$1,127.8
Total assets: \$4,821.5
Accounts payable: \$187.3
Short-term debt: \$150.0
Long-term debt: \$1,250.0
Total liabilities: \$2,487.3
Shareholders equity: \$2,334.2

CASH FLOW ANALYSIS:
Operating cash flow: \$287.4M (vs \$213.6M in 2024)
Free cash flow: \$198.3M (FCF margin: 23.4%)
CapEx: \$89.1M (10.5% of revenue, focused on data center expansion)
Dividends paid: \$45.2M (\$1.20 per share)
Share buybacks: \$120.5M (2.1M shares repurchased)

RISK FACTORS:
1. Cybersecurity threats and potential data breaches
2. Regulatory changes in AI/ML governance (EU AI Act, US Executive Orders)
3. Foreign exchange volatility (35% of revenue from non-USD markets)
4. Key person dependency in AI research division
5. Supply chain concentration in semiconductor procurement
6. Climate-related disclosure requirements (SEC, CSRD)
7. Intellectual property litigation risk

SEGMENT PERFORMANCE DETAIL:
North America: \$423.7M (+11.2% YoY, 50.0% of total)
EMEA: \$198.4M (+14.7% YoY, 23.4% of total)
APAC: \$156.2M (+15.9% YoY, 18.4% of total)
LATAM: \$69.0M (+8.3% YoY, 8.2% of total)

MARKET DATA (as of December 31, 2025):
Stock price: \$87.43
52-week range: \$62.15 - \$92.80
P/E ratio (TTM): 22.9x
EV/EBITDA: 15.7x
Market cap: \$3,264.5M
Dividend yield: 1.37%
Beta: 1.23
Shares outstanding: 37.3M (fully diluted: 38.9M)

COMPETITOR BENCHMARK:
                    Revenue(B)  GrossMargin  P/E   EV/EBITDA  FCF Yield
Company A           \$1,247M    74.1%       28.3x  19.2x      3.1%
Company B           \$892M      68.5%       18.7x  12.4x      4.8%
Company C           \$1,523M    71.2%       24.1x  16.8x      3.7%
Our Company         \$847M      72.3%       22.9x  15.7x      6.1%

Our FCF yield of 6.1% is the highest in the peer group, suggesting potential undervaluation
relative to our growth profile (12.4% revenue growth vs peer median of 9.8%).

MACROECONOMIC CONTEXT:
- US GDP growth: 2.7% (2025E), 2.1% (2026E)
- Federal Funds Rate: 4.25-4.50% (December 2025)
- 10Y Treasury Yield: 3.87%
- VIX: 18.3 (moderate volatility regime)
- US Dollar Index (DXY): 104.7
- Brent Crude: \$78.40/bbl
- Bitcoin: \$98,234 (December 31, 2025)
- S&P 500: 6,247.83 (+18.7% in 2025)
- NASDAQ: 22,893.12 (+24.3% in 2025)

The Federal Reserve signaled 2-3 rate cuts in 2026, which would reduce our interest expense
on the variable-rate portion of our debt (\$450M of \$1,250M total) by approximately \$9-13.5M
annually per 100bps reduction.

FORWARD GUIDANCE (Fiscal 2026):
Revenue: \$965-995M (14-17% YoY growth)
Gross margin: 73-75%
Operating margin: 18-20% (vs 16.2% in 2025)
EPS: \$4.15-4.45
CapEx: \$110-130M (data center + GPU cluster for internal AI training)

The company plans to deploy an internal MoE (Mixture of Experts) language model for automated
financial analysis, expected to reduce analyst headcount by 15-20% while improving report
turnaround time by 3x. Total investment: \$45M over 2 years, with projected \$30M/year savings
starting in 2027.

ITEM 1A. RISK FACTORS (Expanded)
[... additional risk disclosure continues for regulatory compliance ...]

TRANSACTION AUDIT LOG — Q4 2025
================================
'''

code_base = '''
// FILE: src/core/trading/engine.rs
// Quantitative Trading Engine v3.7.2 — Production
// Architecture: Event-driven, lock-free order matching

use std::collections::{HashMap, VecDeque};
use std::sync::{Arc, Mutex, RwLock};
use std::time::{Duration, Instant};
use tokio::sync::mpsc::{self, Sender, Receiver};
use serde::{Serialize, Deserialize};
use tracing::{info, warn, error, instrument, span};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OrderSide { Buy, Sell }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OrderType {
    Market,
    Limit { price: f64 },
    StopLoss { trigger: f64 },
    TrailingStop { trail_percent: f64 },
    OCO { limit_price: f64, stop_price: f64 }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TimeInForce { GTC, IOC, FOK, Day }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Order {
    pub id: String,
    pub symbol: String,
    pub side: OrderSide,
    pub order_type: OrderType,
    pub quantity: f64,
    pub filled: f64,
    pub status: OrderStatus,
    pub timestamp: i64,
    pub account_id: String,
    pub strategy_id: Option<String>,
    pub metadata: HashMap<String, String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OrderStatus { New, PartiallyFilled, Filled, Cancelled, Rejected, Expired }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trade {
    pub id: String,
    pub buy_order_id: String,
    pub sell_order_id: String,
    pub symbol: String,
    pub price: f64,
    pub quantity: f64,
    pub timestamp: i64,
    pub liquidity_flag: LiquidityFlag,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LiquidityFlag { Maker, Taker, Auction }

pub struct MatchingEngine {
    order_books: HashMap<String, OrderBook>,
    trades: VecDeque<Trade>,
    order_index: HashMap<String, String>,  // order_id -> symbol
    risk_limits: RiskParameters,
    circuit_breakers: CircuitBreakerState,
    metrics: EngineMetrics,
}

impl MatchingEngine {
    pub fn new(config: EngineConfig) -> Self {
        let mut books = HashMap::new();
        for symbol in &config.traded_symbols {
            books.insert(symbol.clone(), OrderBook::new(symbol.clone()));
        }
        Self {
            order_books: books,
            trades: VecDeque::with_capacity(100_000),
            order_index: HashMap::with_capacity(1_000_000),
            risk_limits: config.risk_params,
            circuit_breakers: CircuitBreakerState::new(),
            metrics: EngineMetrics::default(),
        }
    }

    #[instrument(skip(self), fields(order_id = %order.id))]
    pub fn submit_order(&mut self, mut order: Order) -> Result<OrderAck, EngineError> {
        // Circuit breaker check — prevent cascading failures
        if self.circuit_breakers.tripped {
            return Err(EngineError::CircuitBreakerActive);
        }

        // Risk pre-check: position limits, notional limits, concentration
        self.risk_check(&order)?;

        // Validate and normalize order
        if order.quantity <= 0.0 {
            return Err(EngineError::InvalidQuantity(order.quantity));
        }

        let book = self.order_books.get_mut(&order.symbol)
            .ok_or(EngineError::UnknownSymbol(order.symbol.clone()))?;

        order.status = OrderStatus::New;
        order.timestamp = chrono::Utc::now().timestamp_nanos_opt().unwrap_or(0);

        let order_id = order.id.clone();
        let symbol = order.symbol.clone();
        self.order_index.insert(order_id.clone(), symbol);

        // Match immediately if possible
        let trades = book.match_order(&order);
        let mut matched_qty = 0.0;

        for (trade, remaining) in trades {
            matched_qty += trade.quantity;
            self.trades.push_back(trade.clone());

            // Publish trade event to market data feed
            self.publish_trade_event(&trade);

            if let Some(unfilled) = remaining {
                // Partial fill — add remaining to book
                book.add_order(unfilled);
            }
        }

        if matched_qty == 0.0 {
            book.add_order(order);
        }

        self.metrics.orders_received += 1;
        self.metrics.total_volume += matched_qty;

        // Update circuit breaker state
        self.circuit_breakers.evaluate(&self.metrics);

        Ok(OrderAck {
            order_id,
            status: if matched_qty == 0.0 { OrderStatus::New }
                    else if matched_qty < order.quantity { OrderStatus::PartiallyFilled }
                    else { OrderStatus::Filled },
            matched_quantity: matched_qty,
        })
    }

    fn risk_check(&self, order: &Order) -> Result<(), EngineError> {
        // Position concentration check
        let current_exposure = self.get_account_exposure(&order.account_id, &order.symbol);
        let max_exposure = self.risk_limits.max_single_position_pct *
                          self.get_account_equity(&order.account_id);

        if current_exposure + order.quantity > max_exposure {
            return Err(EngineError::RiskLimitExceeded {
                current: current_exposure,
                limit: max_exposure,
                requested: order.quantity,
            });
        }
        Ok(())
    }
}
'''

reasoning_base = '''
COMPLEX REASONING SCENARIO — MULTI-STAKEHOLDER STRATEGIC ANALYSIS
===================================================================

CONTEXT:
You are advising a \$50B sovereign wealth fund on strategic asset allocation for 2026-2030.
Below is a comprehensive intelligence report covering geopolitics, macroeconomics, technology
trends, and market dynamics. You must synthesize this information and provide actionable
recommendations.

SECTION 1: GEOPOLITICAL LANDSCAPE
[... detailed geopolitical analysis covering 15 major economies ...]

SECTION 2: MACROECONOMIC FORECASTS
[... multi-factor economic models with 47 variables across 30 countries ...]

SECTION 3: TECHNOLOGY DISRUPTION VECTORS
[... deep analysis of AI, quantum, biotech, energy, space economy ...]

SECTION 4: MARKET PRICING ANOMALIES
[... quantitative screening results across 12,000+ global securities ...]

SECTION 5: TAIL RISK SCENARIOS
[... 8 black-swan scenarios with probability-weighted impact analysis ...]
'''

# Generate prompts
for test_id, ctx, category in [
    ("T01", 65536, "finance"), ("T02", 65536, "finance"),
    ("T03", 131072, "finance"), ("T04", 131072, "finance"),
    ("T05", 262144, "finance"), ("T06", 262144, "finance"),
    ("T07", 524288, "finance"), ("T08", 524288, "finance"),
    ("T09", 786432, "finance"), ("T10", 1048576, "finance"),
    ("T11", 65536, "code"), ("T12", 131072, "code"),
    ("T13", 262144, "code"), ("T14", 524288, "code"),
    ("T15", 1048576, "code"),
    ("T16", 65536, "reasoning"), ("T17", 131072, "reasoning"),
    ("T18", 262144, "reasoning"), ("T19", 524288, "reasoning"),
    ("T20", 1048576, "reasoning"),
]:
    if category == "finance":
        base = finance_base
        prefix = "Analyze the following financial data and answer the question at the end.\n\n"
    elif category == "code":
        base = code_base
        prefix = "Review the following codebase and answer the technical question at the end.\n\n"
    else:
        base = reasoning_base
        prefix = "Study the following intelligence and answer the strategic question at the end.\n\n"

    # Estimate tokens per char (~0.25 for English text) and repeat base accordingly
    # Target: ctx tokens, need ~ctx*4 chars with base text
    base_chars = len(base)
    needed_chars = ctx * 4  # rough: 4 chars per token for English
    repeats = max(1, needed_chars // base_chars)

    prompt_text = prefix + (base * repeats)[:needed_chars]

    # Add ending question
    if category == "finance":
        prompt_text += "\n\n--- END OF DATA ---\n\nQUESTION: Based on the financial data above, identify the TOP 3 risks, TOP 3 opportunities, and provide a concrete capital allocation recommendation. Be specific with numbers and reasoning."
    elif category == "code":
        prompt_text += "\n\n--- END OF CODE ---\n\nQUESTION: Review the trading engine above. Identify 3 potential bugs or race conditions, 3 security vulnerabilities, and propose a refactoring plan. Be specific about which functions and lines."
    else:
        prompt_text += "\n\n--- END OF INTELLIGENCE ---\n\nQUESTION: Synthesize all intelligence above. Provide: (1) Recommended asset allocation with percentages, (2) Top 5 risks with mitigations, (3) Three contrarian bets. Be specific."

    total_chars = len(prompt_text)
    est_tokens = total_chars // 4  # rough estimate

    fpath = os.path.join(out, f"prompt_{test_id}_{category}.txt")
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(prompt_text)

    # Also create JSON for API call
    jpath = os.path.join(out, f"payload_{test_id}.json")
    with open(jpath, 'w', encoding='utf-8') as f:
        json.dump({
            "model": "test",
            "messages": [{"role": "user", "content": prompt_text}],
            "max_tokens": 128,
            "temperature": 0
        }, f)

    print(f"  {test_id}: {len(prompt_text):,} chars, ~{est_tokens:,} tokens -> {os.path.basename(fpath)} (category: {category})")

print("\\nDone. All prompts generated.")
"@

# Save and run generator
$genScript | Set-Content -Encoding UTF8 "$PromptDir\gen_prompts.py"
python "$PromptDir\gen_prompts.py"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  INICIANDO BENCHMARK — 20 TESTES" -ForegroundColor Cyan
Write-Host "  Modelo: Qwen3-Coder-Next 80B Nitro" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# INICIAR SERVIDOR UMA UNICA VEZ
# ============================================================
$port = 8099
$logFile = "$outDir\bench_1M_server.log"

Write-Host "Iniciando llama-server em modo Nitro na porta $port ..." -ForegroundColor Yellow
$serverArgs = "-m `"$model`" --port $port -ngl 999 --cpu-moe -c 1048576 -ctk q4_0 -ctv q4_0 -fa on --reasoning off --mlock"

$proc = Start-Process -FilePath $llama -ArgumentList $serverArgs -NoNewWindow -RedirectStandardError $logFile -PassThru

Write-Host "  Aguardando servidor (pode levar 2-3 min com --mlock)..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 300; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($r.StatusCode -eq 200) {
            $ready = $true
            Write-Host "  Servidor pronto em ${i}s" -ForegroundColor Green
            break
        }
    } catch {}
    if ($proc.HasExited) {
        Write-Host "  ERRO: Servidor morreu (exit $($proc.ExitCode))" -ForegroundColor Red
        Get-Content $logFile -Tail 10
        exit 1
    }
}

if (-not $ready) {
    Write-Host "  FALHA: timeout" -ForegroundColor Red
    $proc | Stop-Process -Force
    Get-Content $logFile -Tail 20
    exit 1
}

# Health + VRAM snapshot inicial
$health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 5
"HEALTH: OK | slots_idle=$($health.slots_idle) | slots_processing=$($health.slots_processing)" | Out-File $results -Append

$vram = & nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader 2>$null
if ($vram) {
    "--- VRAM inicial ---" | Out-File $results -Append
    foreach ($line in $vram) { "  $line" | Out-File $results -Append }
}
"" | Out-File $results -Append

# ============================================================
# EXECUTAR TESTES
# ============================================================
$testNum = 0
foreach ($test in $tests) {
    $testNum++
    $id = $test.Id
    $name = $test.Name
    $ctx = $test.Ctx
    $cat = $test.Cat
    $desc = $test.Desc

    Write-Host ""
    Write-Host "--- Teste $testNum/20: $id — $desc ---" -ForegroundColor Cyan
    Write-Host "    Contexto: $([math]::Round($ctx/1024,0))K tokens | Categoria: $cat" -ForegroundColor DarkGray

    "## $id — $desc" | Out-File $results -Append
    "Contexto: $ctx tokens | Categoria: $cat" | Out-File $results -Append

    # Load prompt
    $category_map = @{Financas="finance"; Codigo="code"; Raciocinio="reasoning"}
    $cat_key = $category_map[$cat]
    $payloadPath = "$PromptDir\payload_$id.json"

    if (-not (Test-Path $payloadPath)) {
        Write-Host "  ERRO: Prompt nao encontrado: $payloadPath" -ForegroundColor Red
        "STATUS: SKIP (prompt not found)" | Out-File $results -Append
        continue
    }

    $payload = Get-Content $payloadPath -Raw -Encoding UTF8

    # Warmup para contextos grandes: health check para confirmar que server esta vivo
    if ($ctx -ge 524288) {
        Write-Host "  Pre-aquecendo..." -ForegroundColor DarkGray
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 5 | Out-Null
        } catch {
            Write-Host "  ALERTA: Server nao respondeu health check" -ForegroundColor Red
        }
    }

    Write-Host "  Enviando prompt ($([math]::Round($ctx/1024,0))K tokens)..." -ForegroundColor Yellow
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $startTime = Get-Date -Format 'HH:mm:ss'
    "Inicio: $startTime" | Out-File $results -Append

    try {
        # Timeout escalonado: 2 min para 64K, 5 min para 128K, 10 min para 256K, 20 min para 512K, 30 min para 1M
        $timeout_map = @{65536=180; 131072=360; 262144=720; 524288=1440; 786432=1800; 1048576=2100}
        $timeout = $timeout_map[$ctx]
        if (-not $timeout) { $timeout = [math]::Max(300, $ctx / 500) }

        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$port/v1/chat/completions" `
            -Method Post -Body $payload -ContentType "application/json" `
            -TimeoutSec $timeout

        $sw.Stop()
        $lat = [math]::Round($sw.Elapsed.TotalSeconds, 1)
        $answer = $response.choices[0].message.content
        $total_tokens = $response.usage.total_tokens
        $prompt_tokens = $response.usage.prompt_tokens
        $completion_tokens = $response.usage.completion_tokens

        $answer_preview = if ($answer.Length -gt 200) { $answer.Substring(0, 200) + "..." } else { $answer }

        Write-Host "  RESPOSTA ($($completion_tokens) tokens): $answer_preview" -ForegroundColor White
        Write-Host "  LATENCIA: ${lat}s | Prefill: $prompt_tokens tokens | Gen: $completion_tokens tokens" -ForegroundColor Green

        "STATUS: OK" | Out-File $results -Append
        "LATENCIA_TOTAL_S: $lat" | Out-File $results -Append
        "PROMPT_TOKENS: $prompt_tokens" | Out-File $results -Append
        "COMPLETION_TOKENS: $completion_tokens" | Out-File $results -Append
        "TOTAL_TOKENS: $total_tokens" | Out-File $results -Append
        "RESPOSTA: $answer_preview" | Out-File $results -Append

    } catch {
        $sw.Stop()
        $lat = [math]::Round($sw.Elapsed.TotalSeconds, 1)
        $errMsg = $_.Exception.Message

        Write-Host "  ERRO (${lat}s): $errMsg" -ForegroundColor Red
        "STATUS: FAIL (${lat}s)" | Out-File $results -Append
        "ERROR: $errMsg" | Out-File $results -Append

        # Check if server died
        if ($proc.HasExited) {
            Write-Host "  SERVIDOR MORREU! Exit: $($proc.ExitCode)" -ForegroundColor Red
            "SERVER_DIED: exit code $($proc.ExitCode)" | Out-File $results -Append
            Get-Content $logFile -Tail 15 | Out-File $results -Append
            break
        }
    }

    # Extract server log tokens/s
    Start-Sleep -Seconds 1
    $logContent = Get-Content $logFile -ErrorAction SilentlyContinue
    $tokensLines = $logContent | Select-String "tokens per second|eval time|prompt eval|total time" | Select-Object -Last 5
    foreach ($line in $tokensLines) {
        $t = $line.Line.Trim()
        Write-Host "  $t" -ForegroundColor DarkGray
        "  PERF: $t" | Out-File $results -Append
    }

    "" | Out-File $results -Append
}

# ============================================================
# FINALIZAR
# ============================================================
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  BENCHMARK CONCLUIDO!" -ForegroundColor Green
Write-Host "  Resultados: $results" -ForegroundColor Green
Write-Host "  Server log: $logFile" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

# VRAM final
$vram_end = & nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader 2>$null
if ($vram_end) {
    "--- VRAM final ---" | Out-File $results -Append
    foreach ($line in $vram_end) { "  $line" | Out-File $results -Append }
}

# Resumo
Write-Host ""
Write-Host "--- RESUMO ---" -ForegroundColor Yellow
Get-Content $results | Select-String "STATUS|LATENCIA_TOTAL|PROMPT_TOKENS|COMPLETION_TOKENS|PERF:" | ForEach-Object { Write-Host $_ }

# Stop server
$proc | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Servidor parado. Resultados em: $results" -ForegroundColor White
