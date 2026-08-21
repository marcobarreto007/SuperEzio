# SuperEzio — Investor Playbook & Capital Allocation Framework

Guia Oficial e Manual de Alocação de Capital para o Investidor Pessoal e Institucional no ecossistema SuperEzio (Canadá e Mercado Global).

---

## 1. Filosofia Operacional: Sobrevivência Antes do Ganho

O SuperEzio foi construído sob o princípio de **antifragilidade e conservação estrita de capital**. Não operamos como um cassino nem perseguimos ganhos irresponsáveis de curto prazo sem controle de risco.

### A Pirâmide de Alocação de Capital

```
                 ▲
                / \
               /   \  [4. Explore / Tático (10-15%)] -> Mangala / Swings (Stop 3%)
              /-----\
             /       \  [3. Core / Longo Prazo (85-90%)] -> ETFs Globais / TFSA
            /---------\
           /           \  [2. Quitação de Dívidas Caras] -> Juros > 6-8% a.a.
          /-------------\
         /               \  [1. Reserva de Emergência] -> 3 a 6 meses em Caixa/HISA
        /_________________\
```

1. **Camada 1 — Reserva de Emergência Intocável**:
   - Manter 3 a 6 meses de custo fixo familiar em instrumentos líquidos em CAD (ex: conta HISA, `CASH.TO` ou `CBIL.TO`).
   - Garante que eventos imprevisíveis não forcem liquidação de ações em momentos de baixa.
2. **Camada 2 — Eliminação de Dívidas de Alto Custo**:
   - Dívidas com taxa de juros acima de 6% a 8% ao ano (cartão de crédito, linha de crédito pessoal) devem ser liquidadas antes de alocações de risco. Quitar dívida é retorno garantido e livre de impostos.
3. **Camada 3 — Núcleo de Longo Prazo (*Core*)**:
   - 80% a 90% do excedente investível alocado em fundos de índice (ETFs) globais de custo ultra-baixo.
4. **Camada 4 — Satélite Tático (*Explore*)**:
   - Máximo de 10% a 15% para swing trades e oportunidades do scanner Mangala com stop-loss rígido de 3% a 5%.

---

## 2. Estratégia de ETFs no Canadá (TD Direct Investing)

Para evitar que taxas de corretagem corroam os aportes mensais (*drag de corretagem*), o SuperEzio utiliza o catálogo oficial de **108 ETFs Commission-Free** do TD Direct Investing Canadá.

### Portfólios Recomendados por Perfil

#### A. Portfólio All-in-One Simples (Rebalanceamento Automático)
| Ticker | Nome do Fundo | Perfil | Composição |
|---|---|---|---|
| **`VEQT.TO`** | Vanguard All-Equity ETF | Crescimento / 100% Ações | ~44% EUA, ~30% Canadá, ~19% Desenvolvidos, ~7% Emergentes |
| **`VGRO.TO`** | Vanguard Growth ETF Portfolio | Moderado / 80-20 | 80% Ações Globais / 20% Renda Fixa |
| **`VBAL.TO`** | Vanguard Balanced ETF | Conservador / 60-40 | 60% Ações Globais / 40% Renda Fixa |
| **`VCNS.TO`** | Vanguard Conservative Income ETF | Defensivo / 40-60 | 40% Ações Globais / 60% Renda Fixa |

> Todos os tickers acima fazem parte do universo de 108 ETFs sem comissão do
> TD Direct Investing (`config/td_direct_commission_free_etfs.json`).

#### B. Portfólio Modular de 3 Blocos (Personalizável)
| Bloco | Ticker Sugerido | Peso Típico | Taxa (MER) | Objetivo |
|---|---|:---:|:---:|---|
| **EUA** | `VFV.TO` ou `VSP.TO` | 45% a 50% | 0.09% | Acompanhar o índice S&P 500 em CAD |
| **Canadá** | `VCN.TO` ou `VCE.TO` | 20% a 25% | 0.06% | Exposição ao mercado canadense (TSX) |
| **Internacional** | `VIU.TO` ou `VXC.TO` | 20% a 25% | 0.22% | Mercados desenvolvidos e globais ex-Canadá |

---

## 3. Roteamento de Contas e Eficiência Tributária no Canadá

1. **TFSA (*Tax-Free Savings Account*) — Prioridade Máxima**:
   - Todos os rendimentos, dividendos e ganhos de capital são **100% livres de impostos para sempre**.
   - Ideal para alocar o *Core* de ações globais e ETFs de alto crescimento.
2. **RRSP (*Registered Retirement Savings Plan*)**:
   - Contribuições dedutíveis do imposto de renda atual.
   - Ideal para investidores em faixas de renda mais altas.
3. **FHSA (*First Home Savings Account*)**:
   - Dedutível na entrada e isento na saída para compra do primeiro imóvel.

---

## 4. O Sistema de Proteção: Money Gate e SDCA Firewall

O SuperEzio possui travas rígidas de código para proteger o capital:

- **Modo `BLOCKED_BY_DESIGN`**: O sistema nunca envia ordens a mercado automaticamente.
- **Rascunho de Tickets TD Direct (`src/core/trading/td_direct_ticket.py`)**:
  - Aceita apenas ordens do tipo **`LIMIT`**.
  - Rejeita credenciais ou senhas bancárias (prevenção contra vazamento).
  - Valida se o ativo pertence aos 108 ETFs sem comissão.
- **SDCA Risk Firewall**:
  - Toda resposta do Bob Copilot passa por um filtro de utilidade e incerteza antes de ser apresentada ao usuário.

---

## 5. Ferramentas de Linha de Comando (CLI)

O SuperEzio inclui o script interativo de alocação de portfólio:

```powershell
# Executar cálculo de alocação para CAD $25.000
python scripts/investor_portfolio_allocator.py --capital 25000 --expenses 3500 --emergency-months 4 --risk moderate

# Saída em JSON para integração com pipelines
python scripts/investor_portfolio_allocator.py --capital 25000 --json
```

---

## 6. Rotina Mensal do Investidor (Checklist de 15 Minutos)

1. **Dia 1 do Mês**: Verificar o saldo da reserva de emergência em CAD.
2. **Aporte DCA**: Acessar o TD WebBroker e comprar cotas do ETF selecionado (`VEQT.TO` ou `VFV.TO`) usando ordem `LIMIT`.
3. **Auditoria no SuperEzio**: Abrir o Cockpit (`http://127.0.0.1:8002`), verificar os indicadores técnicos e registrar eventuais notas de tese.
4. **Sem Estresse**: Fechar a plataforma e não acompanhar oscilações diárias desnecessárias.
