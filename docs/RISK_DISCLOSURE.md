# SuperEzio - Risk Disclosure

## Not Financial Advice

SuperEzio is an educational and analytical tool. It is not a financial advisor, broker, or registered investment recommendation engine. It does not:

- Execute trades or transmit orders to any broker.
- Provide personalized investment advice.
- Guarantee any return, profit, or outcome.
- Replace a licensed financial professional.

## Safe Actions Only

The system is constrained to five bounded actions:

| Action | Meaning |
|--------|---------|
| STUDY_MORE | Insufficient data for a conclusion |
| WATCHLIST | Worth monitoring, no action recommended |
| WAIT | Conditions unfavorable for entry |
| SMALL_POSITION | Evidence supports only a limited allocation |
| AVOID | Red flags or insufficient evidence for involvement |

The system should not output BUY, SELL, ALL_IN, leverage instructions, options strategies, or speculative pressure language.

## Known Limitations

1. Data gaps: missing fundamentals, delayed prices, or rate-limited APIs can produce incomplete analysis.
2. Model latency: analysis depends on external cloud model APIs; complex requests can take noticeably longer and response time varies with network and provider load.
3. Market coverage: primary coverage is US and Canadian equities. Other markets may have weaker data.
4. No execution: the system analyzes; it does not connect to brokers for trading.
5. Language: English financial prompts are the best-tested path.

## Privacy And External Providers

The final CEO synthesis runs on external cloud model APIs (official DeepSeek HTTPS API by default). All model inference — CEO synthesis, expert sub-analysis, judge, and auditor — is performed by external providers; the optional Z.ai GLM-5.3 path, when configured, is also external.

Runtime data (journals, logs, theses) is kept on local disk (DISK ONLY), but prompts and analysis context are sent to the configured model provider. Do not claim that no data ever leaves the machine.

Market-data providers for price, profile, fundamentals, and catalysts are configured separately. The operator controls which providers are active through API keys and environment variables.

## Regulatory

This software is not registered with any financial regulatory authority, including the SEC, FINRA, OSC, or CVM. It is a research and analysis tool. Users are responsible for compliance with applicable laws in their jurisdiction.

## Limitation Of Liability

This software is provided as is, without warranty of any kind. The authors and distributors assume no liability for financial losses, trading decisions, or investment outcomes resulting from use of this software.
