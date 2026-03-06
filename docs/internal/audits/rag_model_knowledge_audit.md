# RAG and Model Knowledge Audit

## Fraud RAG

- Loaded text patterns: 25
- Loaded pump symbols: 0
- Source files: 3
- Local HF fraud files: 53

## Macro RAG

- Series count: 4
- Last update: 2026-04-27T22:08:24.961698
- Canada context rows: 12

## Model Knowledge Files

- `data/intent_golden.jsonl`: 9 rows, assistant messages=0, categories={'uncategorized': 9}
- `data/intent_dataset.jsonl`: 593 rows, assistant messages=0, categories={'uncategorized': 593}
- `data/intent_eval.jsonl`: 148 rows, assistant messages=0, categories={'uncategorized': 148}
- `data/nurse_dataset.jsonl`: 1800 rows, assistant messages=1800, categories={'finance_knowledge': 600, 'agent_management': 600, 'persona': 600}
- `data/sensei_dataset.jsonl`: 750 rows, assistant messages=0, categories={'uncategorized': 750}
- `data/eval_questions.jsonl`: 25 rows, assistant messages=0, categories={'ticker_analysis': 5, 'risk_assessment': 2, 'macro': 2, 'etf': 1, 'fraud': 2, 'sentiment': 2, 'technical': 2, 'fixed_income': 2, 'portfolio': 1, 'esg': 1, 'edge_case': 2, 'multi_ticker': 1, 'crisis': 1, 'crypto': 1}

## Fraud RAG Sample

- [PATTERN_FOUND]: pump_and_dump | Padrão genérico: microcap com campanha de promoção em newsletters e redes sociais, seguido de spike de volume, alta de preço e venda de insiders/promoters. Empresa sem receita real ou com receita mínima. | microcap_concentration unusual_volume_without_clear_news vague_hype_sector_description no_revenue_with_operations social_media_pump_language insider_selling_near_promotion | Padrão documentado amplamente por SEC Investor Education, FINRA e CSA. Não representa caso específico. Operadores podem adicionar casos reais com source_url consultando https://www.sec.gov/divisions/enforce/enforcements.htm ou https://www.osc.ca/en/enforcement...
- [PATTERN_FOUND]: misleading_promotion | Padrão genérico: empresa com narrativa de crescimento em setor quente (IA, litio, cannabis, quantum, crypto) sem fundamentos operacionais correspondentes. Materiais de promoção não divulgam pagamento a promotores. Volume e preço sobem durante campanha, caem após. | vague_hype_sector_description no_revenue_with_operations microcap_concentration social_media_pump_language unusual_volume_without_clear_news | Padrão documentado pela SEC Section 17(b). Para investigação real, consultar: https://efts.sec.gov/LATEST/search-index?q=%22pump+and+dump%22&dateRange=custom...
- [PATTERN_FOUND]: microcap_fraud | Padrão genérico em mercado canadense: empresa listada no TSX Venture ou CSE com capitalização abaixo de $50M CAD, sem receita operacional, mudanças frequentes de nome ou ramo de negócio, diluição significativa de ações. Frequentemente associada a reverse mergers. | microcap_concentration no_revenue_with_operations vague_hype_sector_description heavy_dilution reverse_split_history frequent_name_changes | Padrão documentado pela OSC e CSA. Para casos específicos: https://www.osc.ca/en/enforcement/proceedings...

## Findings

- Intent dataset is now separated from model answer datasets.
- FraudRAG should load JSON/JSONL pattern files before any PennyLab RAG claims.
- Sensei-style data without assistant messages is not ready for supervised fine-tuning as chat completions.
- FiQA is useful for RAG QA evaluation, not for ticker-specific market claims.
