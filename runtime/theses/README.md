# runtime/theses — scorecards de tese por ticker

Diretório canônico para teses falsificáveis cross-session, criado em
2026-09-03 para reconciliar a arquitetura documentada com o disco (o caminho
era citado no CLAUDE.md e na skill `tese-tracker`, mas nunca existiu).

## O que vai aqui

Um arquivo `runtime/theses/<TICKER>.json` por tese viva/morta, no formato do
contrato da skill `tese-tracker` (`pilares`, `invalidacao`, `conviction`,
`catalysts`, `revisoes`). Tese morta nunca é apagada — histórico é o ativo.

## Como uma tese nasce hoje

1. O operador invoca a skill `tese-tracker` (triggers: "tese", "scorecard",
   "a tese ainda vale") com um ticker.
2. A skill carrega `runtime/theses/<TICKER>.json` ou cria a partir do
   relatório mais recente em `runtime/reports/<TICKER>-<data>.md` (não inventa
   pilares fora do relatório).
3. Atualiza o checkpoint canônico `.f51/checkpoints/latest.json` com o status
   da tese (viva/morta/atualizada).

## Estado real (2026-09-03)

Nenhuma tese materializada em disco ainda: convicções do dia-a-dia vivem em
`.f51/checkpoints/latest.json` (última sessão) e nas evidências por turno em
`runs/evidence/<run_id>`; o relatório de sistema consolidado está em
`runtime/reports/relatorio-final-sistema.html`. Este diretório passa a ser o
lar dos scorecards a partir daqui.
