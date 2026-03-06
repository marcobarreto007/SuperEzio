# SuperEzio Frontpage Design

## Goal

Create the new first screen for SuperEzio from zero, replacing the old trading-terminal framing with a trust-first product experience.

The approved direction is a hybrid:

- **Calm Institutional** as the emotional base: relief, confidence, evidence, restraint.
- **SaaS Operational** as the product structure: clear navigation, repeatable workflows, low cognitive load.
- **Premium Dark Decision Room** as the special decision moment: technical depth appears only when the user is close to acting.

The frontpage must embody the thesis: people do not buy financial tools only for market prediction; they buy reduced anxiety, personal context, and confidence that the system will not push them into a weak decision.

## Positioning

Primary product line:

> SuperEzio Trust OS

Hero promise:

> Decisao financeira com alivio auditavel.

Supporting copy:

> SuperEzio pesquisa, cruza evidencias, aponta riscos e transforma ruido de mercado em um proximo passo permitido.

The page must avoid promises of prediction, guaranteed profit, market timing, or investment advice. The product is framed as a decision-support and risk-guardrail system.

## Information Architecture

The product surface has five primary destinations:

1. **Hoje**
   - Default landing state after login or first load.
   - Shows only what changed, what matters, and what can be ignored.
   - Psychological role: reduce anxiety immediately.

2. **Radar**
   - Watchlist, alerts, SpiderSense signals, and market anomalies.
   - Psychological role: discovery without casino behavior.

3. **Decision Room**
   - Dedicated room for one asset, one question, one decision brief.
   - Psychological role: separate research mode from action mode.

4. **Portfolio**
   - User context: positions, cash, concentration, horizon, risk profile, objectives.
   - Psychological role: make the system feel personally aware rather than generic.

5. **Diario**
   - Saved decision briefs, rationales, outcomes, avoided errors, follow-up reviews.
   - Psychological role: build longitudinal trust and accountability.

No separate top-level tabs for charts, news, agents, sentiment, macro, or backtests. Those are supporting evidence inside workflows, not primary destinations.

## First Viewport

The first viewport should show the real product immediately, not a marketing splash.

Required composition:

- Top navigation with SuperEzio mark, "Trust Operating System", and the five destinations.
- Left hero block with the main promise and two actions:
  - Primary: **Abrir Decision Room**
  - Secondary: **Ver radar de hoje**
- Right product preview combining:
  - A light "Hoje" panel showing a short list of relevant market items.
  - A dark "Decision Room" panel showing a sample decision brief.
- Bottom strip with the five destinations and their jobs.

Sample decision preview:

```text
SNDL hoje
WAIT
Confianca: 61%

Motivo: risco combinado alto, liquidez fraca e evidencia fundamental incompleta.

14 evidencias | 8/12 consenso | 2 faltas
```

This preview is illustrative. It must not imply a live recommendation unless backed by actual data in later implementation.

## Visual Language

Use a restrained, premium, finance-safe palette:

- Main background: warm off-white or very pale sage.
- Primary text: deep green-black or near-black.
- Surfaces: white with thin sage/stone borders.
- Decision Room: deep green-black surface with low-glow evidence accents.
- Accent colors:
  - Evidence/verified: muted lime.
  - Risk/caution: muted amber/clay.
  - Data/consensus: muted blue.

Avoid:

- Neon-heavy full-page cyberpunk.
- Purple/blue AI gradients.
- Casino/trader urgency visuals.
- Oversized decorative blobs or orbs.
- Hero copy inside a generic floating card.

Typography should feel precise and modern. Large headlines use tight spacing but no negative letter spacing. Dense product panels use smaller, scannable type.

## Core Components

### Decision Brief

The central trust object. Every important recommendation-like output should reduce to this structure:

```text
Ativo
Acao permitida
Confianca
Risco combinado
Motivo principal
Evidencias verificadas
Conflitos entre especialistas
Dados faltantes
O que mudaria o veredito
Proxima revisao
```

### Trust Stack

A visual explanation of why the system reached the current permitted action:

- Evidence count.
- Veracity Gate status.
- Expert consensus.
- SpiderSense warnings.
- Missing data.
- Risk constraints.

No single unexplained "AI confidence" number.

### Anxiety Reducer

Small, calm copy that converts uncertainty into a next step:

- "Nao agir agora tambem e uma decisao valida."
- "Nao encontrei evidencia suficiente para agir hoje."
- "O risco principal nao e preco. E liquidez + hype."
- "Eu reanaliso quando uma das condicoes abaixo mudar."

### Decision Room Entry

Entering the room should feel like a deliberate state change:

```text
Agora nao estamos pesquisando.
Agora estamos decidindo se existe acao permitida.
```

This room can be visually darker and more technical than the landing surface, but it must stay calm and legible.

## Interaction Model

Primary flow:

```text
Hoje identifies what matters
-> Radar explains the signal
-> User opens Decision Room
-> SuperEzio generates Decision Brief
-> User saves to Diario or schedules reanalysis
```

The frontpage should make this flow obvious without requiring explanatory marketing text.

## Data Flow Expectations

Initial frontpage can ship with mock-safe sample content if no live UI backend contract exists yet. Once connected, it should consume:

- Product manifest.
- Health/status endpoint.
- Ticker/chart data endpoint where needed.
- Pipeline task streaming for Decision Room requests.

All live financial numbers must have a visible source/evidence path when shown in a decision context.

## Error Handling

The UI should never collapse into generic failure states.

Required fallback language:

- API offline: "Motor indisponivel. Voce ainda pode revisar decisoes salvas."
- Missing data: "Dados insuficientes para conclusao forte."
- Model unavailable: "Rota deterministica ativa. Analise limitada por falta de modelo."
- High risk or conflicting evidence: default to WAIT, STUDY_MORE, or AVOID depending on backend output.

## Accessibility And Responsiveness

The frontpage must work at:

- Mobile: 375px width.
- Tablet: 768px width.
- Desktop: 1280px and wider.

Requirements:

- Keyboard navigable controls.
- Clear focus states.
- No text overlap.
- Stable dimensions for decision cards, nav, and status chips.
- Sufficient contrast in both light landing area and dark Decision Room panel.

## Testing

Implementation should be verified with:

- Static load in browser or local server.
- Responsive screenshot checks at mobile and desktop sizes.
- No console errors.
- Health endpoint unavailable state.
- Long ticker/name text does not break cards.
- Decision Room preview remains readable in dark mode.

## Out Of Scope For First Implementation

- Full authenticated app shell.
- Real portfolio import.
- Payments.
- Live social proof or testimonials.
- Advanced charting.
- Full Decision Room backend integration beyond a safe first visual shell.

## Acceptance Criteria

- The old terminal/casino feel is gone.
- First screen communicates calm, trust, and next-step clarity.
- The five destinations are visible and understandable.
- Decision Room is clearly a separate state for action-level decisions.
- The UI sells relief and evidence, not prediction.
- The page can become the foundation for the future full app without redesigning from scratch.
