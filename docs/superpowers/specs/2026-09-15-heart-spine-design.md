# Coração — spec da espinha (primeiro ciclo)

**Data:** 15 de Setembro de 2026  
**Estado:** desenho fechado em conversa; à espera de revisão do operador antes do plano de implementação  
**Repo:** SuperEzio  
**Pai:** `docs/superpowers/specs/2026-09-15-modulo-coracao-roadmap.md`  
**Isto não substitui o roadmap.** Restringe o *primeiro ciclo* a um caminho de ponta a ponta. Alargar o universo, os fios e os percursos vem depois, contra estes contratos.

## 1. Trabalho deste ciclo

Os três trabalhos correm ao mesmo tempo, num único caminho:

| Trabalho | Como aparece na espinha |
|---|---|
| Arquivo irrecuperável | P0 grava um RSS mockado em JSONL. P1 grava identidade + 5 barras as-traded de um símbolo. |
| Ciência honesta | P3 junta o halt à sessão. P5 pode **matar** o caminho (peso 0) se a barreira sintética não justificar. Matar é sucesso. |
| Atenção no TD | P4 mostra **uma** linha. Caminho morto continua visível com `path_status=killed`. |

Não é o universo de 18 400 nomes. Não é Perspective. Não é LightGBM em arquivo vivo.

## 2. O caminho único

```text
PathSpec(
    event_type="nyse.luld_pause",
    window="same_session",
    axis="gross_return",
)
path_id = "nyse.luld_pause|same_session|gross_return"
```

**Símbolo:** `FTFT`  
**MIC:** `XNAS`  
**first_seen (identidade congelada):** `2020-01-02`  
**Evento:** pausa LULD em **2026-09-14 14:44:20 America/New_York**  
**Sessão do movimento:** `2026-09-14`  
**identity do evento:** `nyse-halt:FTFT:2026-09-14T14:44:20-04:00`  
**timestamp_precision:** `second`

Linha CSV de fixture (P2):

```text
2026-09-14,14:44:20,FTFT,Future FinTech Group Inc.,Nasdaq,LULD Pause,2026-09-14,14:49:20
```

### Limitação declarada (não é bug)

Barras são **diárias**. O LULD às 14:44 ET cai **dentro** da barra de 2026-09-14. O `gross_ret` desse dia mistura manhã (antes) e resto (depois). A Peça 5 pode recusar este caminho por isso. O painel **não** esconde a recusa.

Não se inventa um 8-K às 16:10 para “limpar” a ciência neste ciclo. Esse é caminho 2, depois.

## 3. Contratos congelados

Tipos que já existem **não se renomeiam**. Extensões só se um teste da espinha o exigir, e com campo novo opcional — nunca partir `tests/test_heart_*.py` actuais.

### 3.1 `MarketEvent` (`event_book.py`)

Campos actuais. Para a espinha:

| Campo | Valor |
|---|---|
| `identity` | `nyse-halt:FTFT:2026-09-14T14:44:20-04:00` |
| `source` | `nyse_halts` |
| `event_type` | `nyse.luld_pause` |
| `occurred_at` | datetime aware, 14:44:20 `-04:00` |
| `timestamp_precision` | `second` |
| `symbol` | `FTFT` |
| `mic_code` | `XNAS` |

O matcher de precedência da Peça 3 **tem** de reconhecer `nyse.luld_pause` (hoje só olha para `LULD` / `HALT` / `TRADING_HALT`). Isso é correcção de contrato, não feature nova.

### 3.2 `DailyMove` (`attribution.py`)

TypedDict actual. Para a barra de 2026-09-14:

| Campo | Valor |
|---|---|
| `mic_code` | `XNAS` |
| `symbol` | `FTFT` |
| `first_seen` | `2020-01-02` |
| `session_date` | `2026-09-14` |
| `gross_ret` | `core.math.risk.log_return` entre close 2026-09-11 e close 2026-09-14 |
| `abnormal_ret` | `0.0` |
| `surprise_q` | `0.0` |
| `ewma_vol` | `0.0` |

Zeros nos três últimos **não são beta fingido**. Limitação de manifesto: `spine_no_beta`, `spine_no_surprise`, `spine_no_ewma`. O caminho da espinha usa só `gross_return`.

### 3.3 `RankingWeights` / `RankingAxes` (`ranking.py`)

Quatro eixos que somam 1. A espinha chama `RankingWeights.equal()`. Quem aprende **não** é o painel.

### 3.4 `PathSpec` (novo, `src/core/heart/paths.py`)

```python
@dataclass(frozen=True, slots=True)
class PathSpec:
    event_type: str
    window: str  # só "same_session" neste ciclo
    axis: str    # um de: abnormal_return, gross_return, lifetime_score, surprise

    @property
    def path_id(self) -> str:
        return f"{self.event_type}|{self.window}|{self.axis}"


@dataclass(frozen=True, slots=True)
class PathDecision:
    path_id: str
    status: str  # "kept" | "killed"
    weight: float  # >= 0; killed => 0.0
```

Dois sistemas, sem fundir:

- `PathDecision` — este *percurso* entra ou sai.
- `RankingWeights` — como misturar os quatro eixos **numa** linha que entrou.

`river.expert` neste ciclo actualiza `PathDecision.weight` quando a barreira fecha. **Não** mexe em `RankingWeights` neste ciclo (ficam 0.25 cada). Se o caminho morre, `status=killed`, `weight=0.0`; a linha do painel permanece.

Dono do ficheiro: Peça 5. Importam: P3 (opcional), P4 (obrigatório para `path_status`), P5.

### 3.5 Relógio

Todos os `datetime` da espinha são **timezone-aware**. Comparações em `America/New_York`.

`session_impact_date`:

- instante local `< 16:00 ET` → a data local (mesma sessão)
- instante local `>= 16:00:00 ET` → próximo **calendário** civil (já é o código actual; não inventar calendário de pregão neste ciclo)

LULD 14:44:20 ET em 2026-09-14 → `session_date=2026-09-14` → `window=same_session`.

**Bug conhecido a corrigir neste ciclo (P3):** `tests/test_heart_attribution.py` carimba `tzinfo=UTC` em horas que o spec trata como ET. Os testes passam a construir `America/New_York`. UTC 16:10 **não** é 16:10 ET.

### 3.6 Identidade de universo

`(mic_code, symbol, first_seen)` = `(XNAS, FTFT, 2020-01-02)`. Ticker sozinho é bug.

### 3.7 Gravador cru

`RawCapture` / `RawRecorder` actuais. P0 neste ciclo: **um** ciclo mockado, um ficheiro JSONL, zero parse de negócio. O item RSS **não** precisa de ganhar a junção P3. Precedência LULD > RSS já está no código.

## 4. Barras da fixture (P1)

Cinco sessões, as-traded, sem `adjclose` como detetor de split. Sem rede.

| session_date | close |
|---|---|
| 2026-09-09 | 10.00 |
| 2026-09-10 | 10.20 |
| 2026-09-11 | 10.10 |
| 2026-09-14 | 8.00 |
| 2026-09-15 | 8.20 |

Open/high/low podem repetir o close. Volume constante `1000`. Formato: parquet de teste **ou** JSON de fixture se parquet pesar o setup — o teste da espinha não vive de Yahoo.

## 5. Fluxo

```text
P0  RSS mock ──► JSONL append-only          (arquivo; fora da junção)
P1  listing + 5 barras ──► DailyMove FTFT 2026-09-14
P2  CSV NYSE ──► MarketEvent nyse.luld_pause
P3  attribute_move(move, [event]) ──► Attribution
     MIN_AUTO_CONFIDENCE = 0.6 (já declarado)
     LULD auto-aceite (confiança 0.95)
P4  rank_moves([move], equal, attributions) ──► uma linha
     + path_status a partir de PathDecision
P5  PathSpec único + evaluate_triple_barrier nas 5 barras
     + PathDecision kept|killed (regra §5.1)
```

### 5.1 Regra determinística de `PathDecision` (sem LightGBM)

`ewma_vol` no `DailyMove` continua `0.0` (painel). Os rótulos usam um sigma **congelado** `0.05` (`limitations: spine_label_sigma_frozen`).

- `stop_loss`, `take_profit` = `barrier_widths(0.05, 1.0, 1.0)` aplicados ao close de 2026-09-14
- `time_horizon_bars = vertical_bars_for_sessions(1)` (só 2026-09-15 à frente)
- `label_with_existing_barrier` a partir do índice da barra 2026-09-14
- `status=kept`, `weight=1.0` **só** se o toque for take-profit
- qualquer outro resultado (`stop`, tempo, `None`) → `killed`, `weight=0.0`

Com estes closes (10.10 → 8.00 → 8.20) o caminho **deve morrer**. O teste da espinha afirma `path_status=killed` e a linha FTFT **presente**. Se o avaliador de barreira existente se comportar de outro modo, o teste documenta o toque real e a regra acima ainda vale — não se aperta o sigma para forçar um `kept`.

Ordem de *código* depois do plano: as 6 peças em paralelo **contra estes contratos e estas fixtures**. O teste que as amarra é o sétimo passo, no processo-pai, quando as unidades estiverem verdes. Não é um sétimo agente a escrever os mesmos ficheiros.

## 6. Erros

Integração em falta devolve erro real. Nunca corpo RSS inventado, nunca barra inventada, nunca 200 de painel com ranking fingido.

| Caso | Comportamento |
|---|---|
| `SUPEREZIO_HEART_USER_AGENT` em falta | erro (não default silencioso em produção; testes podem setar `marco@example.com`) |
| HTTP 304 | não escreve JSONL |
| HTTP 4xx/5xx | `HeartHttpError` |
| Reddit sem OAuth | fail closed (fora da espinha; não implementar OAuth neste ciclo) |
| Yahoo 404 | fora da espinha (fixtures locais) |
| `skfolio` / `river` em falta | `pytest.importorskip`; o módulo `paths.py` e a decisão sintético-pura **existem mesmo assim** |
| Painel sem linhas | estado vazio real |
| Caminho `killed` | HTTP 200 com a linha e `path_status=killed` — não 204 |

Sem LLM. Sem segundo FastAPI. Sem página no MIKE. Sem `apps.tmx.com`. Sem `mlfinpy` CPCV.

## 7. Testes

Rede proibida no pytest.

| Teste | Dono |
|---|---|
| Unidades P0 (http, identities, recorder, poller, cli) | heart-p0-ingest |
| Unidades P1 (listings, universe, bars, yahoo mock, freeze) | heart-p1-archive — yahoo mock só se tocar `yahoo_chart.py`; a espinha **não** exige Yahoo vivo |
| Unidades P2 (nyse_halts, event_book) | heart-p2-events — EDGAR Atom **fora** deste ciclo |
| Unidades P3 (attribution ET, join FTFT, clusters não obrigatório na espinha) | heart-p3-cause — clusters 300 biotechs **fora** deste ciclo |
| Unidades P4 (ranking, `/api/heart/ranking` uma linha) | heart-p4-panel — Perspective e Playwright **fora** deste ciclo |
| Unidades P5 (paths, labels, decisão sintético, tracking se couber) | heart-p5-ml — LightGBM/CatBoost/tsfresh **fora** deste ciclo |
| `tests/test_heart_spine.py` | processo-pai, depois das unidades |

Portão de regressão na fronteira da espinha: `tests/test_heart_*.py` verde. Suíte completa 2 890 **só** quando a espinha fechar, não a cada agente.

Fixture partilhada: `tests/fixtures/heart/spine/` (`halts.csv`, `bars.json` ou parquet, `rss.xml`). Quem cria a pasta: plano de implementação (um dono). Os outros leem, não reescrevem números.

## 8. Fora deste ciclo (proibido fingir que está feito)

- Universo nasdaqtraded/TSX/CSE completo
- ArcticDB / DuckDB de produção
- Lote noturno HAC/GARCH
- EDGAR Atom, Business Wire classificado na junção
- Clusters Ibragimov-Müller / Kolari-Pynnönen
- Perspective, lightweight-charts, 100k linhas
- LightGBM, CatBoost, tsfresh, MLflow cloud, GPU
- Alterar `RankingWeights` via `river.expert`
- Caminho `next_session` ou eixo `abnormal_return`
- Poller 24h em produção como aceite (CLI + um ciclo mockado chega)

## 9. Rulings

1. **Espinha = LULD same_session gross_return em FTFT**, não 8-K. Custo se errado: a Peça 5 mata o caminho e o arquivo continua — rework é um segundo `PathSpec`, não um redesign.
2. **P0 fora da junção neste ciclo.** Custo se errado: o gravador pode estar “verde” sem o fio ser útil; o ciclo 2 mete um BW com ticker na junção.
3. **`test_heart_spine.py` é do pai, não de um sétimo agente paralelo.** Custo se errado: atraso de um passo; evita seis writers no mesmo teste.
4. **Sem commit neste spec até o operador pedir.** (Regra da casa.)

## 10. Aceite da espinha

A espinha está aceite quando, **sem rede**:

1. JSONL P0 tem exactamente o ciclo mockado (ou skip explícito de duplicado SHA-256).
2. `MarketEvent` LULD e `DailyMove` FTFT 2026-09-14 existem com os campos da §3.
3. `attribute_move` liga os dois; `event_identity` = identity da §3.1; `confidence >= 0.6`.
4. `GET /api/heart/ranking` (TestClient) devolve uma linha FTFT com `path_id` e `path_status`.
5. `PathDecision` existe; a espinha espera `killed` + linha presente (regra §5.1).
6. `tests/test_heart_spine.py` + `tests/test_heart_*.py` verdes.
7. Nada disto declara o universo TD fechado nem o ML de produção fechado.
