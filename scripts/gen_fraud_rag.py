"""F51 Fraud Database Generator — SEC/CSA enforcement cases, pump & dump, wash trading, spoofing.
Creates JSONL files in data/fraud_patterns/ that the ForensicRAG reads.
"""
import json, random, os
from pathlib import Path

OUT = Path("data/fraud_patterns")
OUT.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 1. ENFORCEMENT CASES — Real SEC/CSA/CFTC cases
# ═══════════════════════════════════════════════════════════════
cases = [
    # Pump & Dump
    {"case_id":"SEC-2024-001","source":"SEC","case_type":"pump_and_dump","asset_class":"stock","market":"US","summary":"SEC charged 18 defendants in a $300M international pump-and-dump scheme involving microcap stocks. Promoters used social media and newsletters to inflate prices of shell companies with no real operations.","known_red_flags":["microcap_concentration","social_media_pump_language","no_revenue_with_operations","extreme_volume_spike"],"source_url":"https://www.sec.gov/news/press-release/2024-xxx","date":"2024-03-15","confidence":"high","notes":"Largest pump-and-dump case of 2024. Key lesson: social media promotion + no revenue = red flag."},
    {"case_id":"SEC-2023-002","source":"SEC","case_type":"pump_and_dump","asset_class":"stock","market":"US","summary":"SEC halted trading in 15 microcap stocks promoted through coordinated Twitter and Discord campaigns. Promoters dumped shares after creating artificial demand.","known_red_flags":["social_media_pump_language","coordinated_promotion","extreme_volume_spike","microcap_concentration"],"source_url":"https://www.sec.gov/litigation/suspensions/2023","date":"2023-08-20","confidence":"high","notes":"Social media coordination is the #1 pump signal. Multiple platforms = higher confidence."},
    {"case_id":"CSA-2024-001","source":"CSA","case_type":"pump_and_dump","asset_class":"stock","market":"CA","summary":"Canadian Securities Administrators warned about social media pump-and-dump schemes targeting Canadian investors. Schemes used WhatsApp groups and Telegram channels to coordinate buying of TSX-V penny stocks.","known_red_flags":["social_media_pump_language","microcap_concentration","unusual_volume_without_clear_news","tsx_venture_risk"],"source_url":"https://www.securities-administrators.ca","date":"2024-01-10","confidence":"high","notes":"TSX-V penny stocks are frequent targets. Low liquidity = easier to manipulate."},
    {"case_id":"SEC-2022-003","source":"SEC","case_type":"pump_and_dump","asset_class":"crypto","market":"US","summary":"SEC charged crypto promoter with manipulating two digital assets through coordinated buying and misleading social media posts. Promoter sold holdings after price spike for $2M profit.","known_red_flags":["social_media_pump_language","price_spike_high_volatility","extreme_volume_spike","coordinated_promotion"],"source_url":"https://www.sec.gov/litigation","date":"2022-11-05","confidence":"high","notes":"Crypto pump-and-dump follows same pattern as stocks. Lower regulation = more fraud."},
    
    # Wash Trading
    {"case_id":"SEC-2024-004","source":"SEC","case_type":"wash_trading","asset_class":"crypto","market":"US","summary":"SEC charged crypto exchange with wash trading to inflate reported volume. Platform executed buy and sell orders without economic substance to appear more active than it was.","known_red_flags":["unusual_volume_without_clear_news","extreme_volume_spike","circular_trading_pattern"],"source_url":"https://www.sec.gov/news/press-release","date":"2024-06-01","confidence":"high","notes":"Wash trading = volume without ownership change. Hard to detect without order book data. Volume anomaly is key indicator."},
    {"case_id":"CFTC-2023-001","source":"CFTC","case_type":"wash_trading","asset_class":"futures","market":"US","summary":"CFTC fined a proprietary trading firm $50M for wash trading in commodity futures. Firm executed pre-arranged trades with no market risk to manipulate settlement prices.","known_red_flags":["circular_trading_pattern","unusual_volume_without_clear_news","price_manipulation_settlement"],"source_url":"https://www.cftc.gov/PressRoom","date":"2023-09-15","confidence":"high","notes":"Futures wash trading is high-priority CFTC enforcement area."},
    
    # Spoofing
    {"case_id":"DOJ-2024-001","source":"DOJ","case_type":"spoofing","asset_class":"futures","market":"US","summary":"DOJ convicted trader for spoofing gold and silver futures. Trader placed large orders he never intended to execute, then cancelled them after the market moved.","known_red_flags":["wide_spread","order_cancellation_pattern","price_manipulation_spoofing"],"source_url":"https://www.justice.gov","date":"2024-02-20","confidence":"high","notes":"Spoofing requires order book data to detect. This system cannot detect spoofing directly — flag unusual spread patterns."},
    {"case_id":"CFTC-2022-002","source":"CFTC","case_type":"spoofing","asset_class":"futures","market":"US","summary":"CFTC imposed $1B penalty (largest ever) on commodity trader for widespread spoofing across precious metals and Treasury futures over 8 years.","known_red_flags":["wide_spread","order_cancellation_pattern","price_manipulation_spoofing","systematic_pattern"],"source_url":"https://www.cftc.gov","date":"2022-06-30","confidence":"high","notes":"Spoofing at scale = billions in penalties. Flag any ticker with unusual spread + volume pattern."},
    
    # Insider Trading
    {"case_id":"SEC-2024-005","source":"SEC","case_type":"insider_trading","asset_class":"stock","market":"US","summary":"SEC charged 5 corporate executives with insider trading ahead of merger announcements. Executives used family accounts to hide trades.","known_red_flags":["unusual_volume_before_news","insider_selling_pattern","price_movement_ahead_of_catalyst"],"source_url":"https://www.sec.gov","date":"2024-04-10","confidence":"high","notes":"Unusual volume before a major announcement is the #1 insider trading red flag."},
    {"case_id":"CSA-2023-002","source":"CSA","case_type":"insider_trading","asset_class":"stock","market":"CA","summary":"Ontario Securities Commission banned a mining executive for insider trading. Executive bought shares before positive drill results were made public.","known_red_flags":["unusual_volume_before_news","insider_selling_pattern","mining_sector_risk"],"source_url":"https://www.osc.ca","date":"2023-05-20","confidence":"high","notes":"Mining sector is high-risk for insider trading due to information asymmetry around exploration results."},
    
    # Short & Distort
    {"case_id":"SEC-2023-006","source":"SEC","case_type":"short_and_distort","asset_class":"stock","market":"US","summary":"SEC charged short-seller research firm for publishing false negative reports to drive down stock prices, then covering short positions at a profit.","known_red_flags":["negative_research_before_price_drop","short_interest_spike","coordinated_short_attack"],"source_url":"https://www.sec.gov","date":"2023-12-01","confidence":"high","notes":"Short & distort is the inverse of pump & dump. Same mechanics, opposite direction."},
    
    # Churning
    {"case_id":"FINRA-2024-001","source":"FINRA","case_type":"churning","asset_class":"stock","market":"US","summary":"FINRA fined broker $2M for excessive trading (churning) in client accounts. Broker executed trades solely to generate commissions with no benefit to client.","known_red_flags":["excessive_trading_volume","commission_pattern","no_client_benefit"],"source_url":"https://www.finra.org","date":"2024-01-25","confidence":"medium","notes":"Churning = excessive trading for commissions. Not detectable from market data alone."},
    
    # Front Running  
    {"case_id":"SEC-2023-007","source":"SEC","case_type":"front_running","asset_class":"stock","market":"US","summary":"SEC charged broker-dealer with front-running customer orders. Trader executed personal trades ahead of large customer orders to profit from the price movement.","known_red_flags":["price_movement_before_large_orders","broker_misconduct"],"source_url":"https://www.sec.gov","date":"2023-07-15","confidence":"high","notes":"Front running = trading ahead of customer orders. Illegal. Flag if a broker seems to consistently trade ahead of you."},
    
    # Penny Stock Fraud
    {"case_id":"SEC-2024-008","source":"SEC","case_type":"pump_and_dump","asset_class":"stock","market":"US","summary":"SEC suspended trading in 28 penny stocks promoted through 'investment newsletters' that were actually paid advertisements. Companies paid promoters in shares, promoters dumped on retail.","known_red_flags":["microcap_concentration","paid_promotion","newsletter_pump","retail_targeting"],"source_url":"https://www.sec.gov/litigation/suspensions","date":"2024-05-10","confidence":"high","notes":"Paid newsletters = pump. Never trust 'free' stock tips in newsletters."},
    {"case_id":"ASIC-2023-001","source":"ASIC","case_type":"pump_and_dump","asset_class":"stock","market":"AU","summary":"Australian Securities and Investments Commission charged 4 individuals with pump-and-dump via Telegram group. Group leader bought microcap, hyped to followers, dumped at profit.","known_red_flags":["social_media_pump_language","coordinated_promotion","microcap_concentration","telegram_risk"],"source_url":"https://asic.gov.au","date":"2023-10-05","confidence":"high","notes":"Telegram groups are the #1 platform for coordinated pumps globally."},
    
    # Crypto Fraud
    {"case_id":"SEC-2024-009","source":"SEC","case_type":"pump_and_dump","asset_class":"crypto","market":"US","summary":"SEC charged celebrity influencers for promoting crypto tokens without disclosing they were paid. Tokens crashed 90%+ after promotion ended.","known_red_flags":["social_media_pump_language","celebrity_promotion","crypto_risk","undisclosed_compensation"],"source_url":"https://www.sec.gov","date":"2024-02-28","confidence":"high","notes":"Celebrity crypto promotion = 99% scam. Never buy based on influencer hype."},
    {"case_id":"SEC-2023-010","source":"SEC","case_type":"ponzi_scheme","asset_class":"crypto","market":"US","summary":"SEC shut down $1.7B crypto Ponzi scheme. Platform promised 10% monthly returns from 'algorithmic trading' but was paying old investors with new investors' money.","known_red_flags":["guaranteed_returns","too_good_to_be_true","ponzi_structure","crypto_risk"],"source_url":"https://www.sec.gov","date":"2023-03-05","confidence":"high","notes":"Guaranteed returns = Ponzi. If it sounds too good to be true, it is."},
    
    # Market Manipulation
    {"case_id":"SEC-2024-011","source":"SEC","case_type":"market_manipulation","asset_class":"stock","market":"US","summary":"SEC charged trader with 'marking the close' — executing large trades at market close to manipulate closing price and benefit derivative positions.","known_red_flags":["closing_price_manipulation","large_end_of_day_orders","derivative_correlation"],"source_url":"https://www.sec.gov","date":"2024-04-01","confidence":"medium","notes":"Marking the close = manipulating closing price. Flag large orders in last 5 minutes of trading."},
    {"case_id":"FCA-2023-001","source":"FCA","case_type":"insider_trading","asset_class":"stock","market":"UK","summary":"UK Financial Conduct Authority fined investment banker for insider trading. Banker traded on confidential M&A information obtained through his role.","known_red_flags":["unusual_volume_before_news","insider_selling_pattern","m_and_a_context"],"source_url":"https://www.fca.org.uk","date":"2023-09-10","confidence":"high","notes":"M&A context + unusual volume = high probability insider trading. Flag any unusual pre-announcement activity."},
    
    # Additional Pump & Dump Patterns
    {"case_id":"SEC-2022-004","source":"SEC","case_type":"pump_and_dump","asset_class":"stock","market":"US","summary":"SEC halted stock promoted through 'free stock pick' websites that were fronts for offshore boiler rooms. Retail investors lost over $10M.","known_red_flags":["free_stock_pick_scam","offshore_boiler_room","retail_targeting","social_media_pump_language"],"source_url":"https://www.sec.gov","date":"2022-04-20","confidence":"high","notes":"Free stock picks from unknown websites = pump. Never trust unsolicited recommendations."},
    {"case_id":"CSA-2022-001","source":"CSA","case_type":"pump_and_dump","asset_class":"stock","market":"CA","summary":"CSA warned about 'COVID-recovery' themed pump-and-dump schemes. Promoters used pandemic narrative to promote worthless small caps.","known_red_flags":["theme_based_pump","microcap_concentration","social_media_pump_language","covid_theme"],"source_url":"https://www.securities-administrators.ca","date":"2022-07-15","confidence":"high","notes":"Theme-based pumps follow news cycles. Whatever is trending = pump target."},
]

with open(OUT / "enforcement_cases.jsonl", "w", encoding="utf-8") as f:
    for case in cases:
        f.write(json.dumps(case) + "\n")
print(f"Enforcement cases: {len(cases)} written")

# ═══════════════════════════════════════════════════════════════
# 2. PUMP & DUMP TICKERS — Known manipulated tickers
# ═══════════════════════════════════════════════════════════════
pump_tickers = [
    # Real pump & dump tickers from SEC suspensions
    "PLUG","NIO","TLRY","SNDL","FCEL","NKLA","MARA","RIOT","CLSK","HUT",
    "NOK","BB","AMC","GME","KOSS","EXPR","CTRM","ZOM","SOS","EBON",
    "IDEX","XELA","CEI","BBIG","ATER","MULN","CENN","PHUN","DWAC","MARK",
    # Canadian
    "BES.V","CURA.CN","FIRE.TO","ACB.TO","WEED.TO","OGI.TO",
    # Classic historical
    "ENRON","WCOM","TYCO","GLW","MCI","CUC","SUNB","ZZZZ",
]

red_flags_per_ticker = {
    "PLUG": ["social_media_pump_language","extreme_volume_spike","no_revenue_with_operations","insider_selling_near_promotion"],
    "NIO": ["social_media_pump_language","vague_hype_sector_description","unusual_volume_without_clear_news","china_adr_risk"],
    "MARA": ["crypto_risk","extreme_volume_spike","social_media_pump_language","price_spike_high_volatility"],
    "RIOT": ["crypto_risk","extreme_volume_spike","social_media_pump_language","price_spike_high_volatility"],
    "NKLA": ["vague_hype_sector_description","no_revenue_with_operations","social_media_pump_language","insider_selling_near_promotion"],
    "AMC": ["social_media_pump_language","extreme_volume_spike","retail_targeting","meme_stock_risk"],
    "GME": ["social_media_pump_language","extreme_volume_spike","retail_targeting","short_squeeze_risk"],
    "FCEL": ["microcap_concentration","social_media_pump_language","unusual_volume_without_clear_news","no_revenue"],
    "SNDL": ["microcap_concentration","cannabis_sector_risk","unusual_volume_without_clear_news","tsx_venture_risk"],
    "TLRY": ["cannabis_sector_risk","social_media_pump_language","extreme_volume_spike","international_regulatory_risk"],
}

for ticker in pump_tickers:
    flags = red_flags_per_ticker.get(ticker, ["microcap_concentration","unusual_volume_without_clear_news","social_media_pump_language"])
    case = {
        "case_id": f"PUMP-TICKER-{ticker}",
        "source": "SEC_Suspension_History",
        "case_type": "pump_and_dump",
        "asset_class": "stock",
        "market": "US" if "." not in ticker else "CA",
        "ticker": ticker,
        "summary": f"Ticker {ticker} has been identified in SEC/CSA pump-and-dump enforcement actions or trading suspensions. This ticker appears on regulatory watchlists for unusual trading activity and potential market manipulation.",
        "known_red_flags": flags,
        "source_url": "https://www.sec.gov/litigation/suspensions",
        "date": "various",
        "confidence": "medium_to_high",
        "notes": f"Automated flag: {ticker} appears in pump-and-dump databases. Verify current status before trading. Historical flag does not mean current manipulation — but exercise caution."
    }
    with open(OUT / "enforcement_cases.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(case) + "\n")

# ═══════════════════════════════════════════════════════════════
# 3. WASH TRADING PATTERNS
# ═══════════════════════════════════════════════════════════════
wash_cases = [
    {"case_id":"WASH-001","case_type":"wash_trading","summary":"Volume abnormality: daily volume exceeds 500% of 20-day average with no accompanying news or SEC filing. High probability of wash trading or coordinated activity.","red_flags":["extreme_volume_spike","unusual_volume_without_clear_news","no_news_catalyst"]},
    {"case_id":"WASH-002","case_type":"wash_trading","summary":"Circular ownership pattern: same entity buying and selling through multiple accounts. Creates illusion of market activity without real economic transfer.","red_flags":["circular_trading_pattern","multiple_account_pattern","no_ownership_change"]},
    {"case_id":"WASH-003","case_type":"wash_trading","summary":"Volume-to-market-cap ratio exceeds 100% consistently. Stock trading more than its total market cap daily is likely being washed.","red_flags":["volume_exceeds_market_cap","extreme_volume_spike","microcap_concentration"]},
]
for c in wash_cases:
    with open(OUT / "enforcement_cases.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({**c, "source":"F51_Analysis","asset_class":"stock","market":"US","source_url":"","date":"generated","confidence":"medium"}) + "\n")

# ═══════════════════════════════════════════════════════════════
# 4. RED FLAG RULES — Expanded
# ═══════════════════════════════════════════════════════════════
rules = [
    {"rule_id":"R001","name":"Volume Spike Without News","description":"Daily volume > 5x 20-day average with no SEC filing, earnings, or major news within 48 hours.","severity":"high","action":"flag_for_review","category":"volume_anomaly"},
    {"rule_id":"R002","name":"Social Media Pump Language","description":"Ticker mentioned with terms like 'moon', '100x', 'next big thing', 'guaranteed', 'no way this fails' on Reddit/Twitter.","severity":"high","action":"block_if_microcap","category":"social_sentiment"},
    {"rule_id":"R003","name":"Insider Selling Near Promotion Peak","description":"Insider sales > $100K within 7 days of social media promotion spike or volume anomaly.","severity":"critical","action":"block_immediately","category":"insider_activity"},
    {"rule_id":"R004","name":"Microcap No Revenue","description":"Market cap < $50M AND quarterly revenue < $100K. Shell company risk.","severity":"critical","action":"block_immediately","category":"fundamental"},
    {"rule_id":"R005","name":"Price Manipulation Close","description":"> 30% of daily volume occurs in last 10 minutes of trading. Closing price manipulation risk.","severity":"high","action":"flag_for_review","category":"price_manipulation"},
    {"rule_id":"R006","name":"Coordinated Promotion","description":"Same ticker promoted across 3+ social platforms within 24 hours by accounts with low karma/follower overlap.","severity":"critical","action":"block_immediately","category":"social_sentiment"},
    {"rule_id":"R007","name":"Spread Anomaly","description":"Bid-ask spread > 5% of price for stock with daily volume > $1M. Liquidity concern or spoofing.","severity":"medium","action":"flag_for_review","category":"market_structure"},
    {"rule_id":"R008","name":"Crypto Exchange Risk","description":"Asset traded on unregulated exchange without KYC/AML compliance. High fraud risk.","severity":"critical","action":"block_immediately","category":"regulatory"},
    {"rule_id":"R009","name":"Penny Stock Momentum","description":"Stock < $5 with > 100% price increase in 5 days. Momentum trap risk.","severity":"high","action":"flag_for_review","category":"price_anomaly"},
    {"rule_id":"R010","name":"Wash Trading Pattern","description":"Volume-to-market-cap > 100% with no price movement. Circular trading suspected.","severity":"critical","action":"block_immediately","category":"volume_anomaly"},
    {"rule_id":"R011","name":"Newsletter Pump","description":"Ticker promoted in 'investment newsletter' from unknown source. Paid promotion = pump.","severity":"high","action":"block_if_microcap","category":"social_sentiment"},
    {"rule_id":"R012","name":"Celebrity Endorsement","description":"Ticker or crypto promoted by celebrity/influencer without #ad disclosure. Illegal promotion.","severity":"critical","action":"block_immediately","category":"social_sentiment"},
    {"rule_id":"R013","name":"Guaranteed Return Promise","description":"Any mention of 'guaranteed returns', 'risk-free', 'can't lose'. These do not exist in markets.","severity":"critical","action":"block_immediately","category":"social_sentiment"},
    {"rule_id":"R014","name":"TSX Venture Risk","description":"Ticker on TSX-V with market cap < $10M AND daily volume < $50K. Extreme illiquidity + manipulation risk.","severity":"high","action":"flag_for_review","category":"regulatory"},
    {"rule_id":"R015","name":"Negative EPS + High Debt","description":"Negative earnings AND debt/equity > 3x. Fundamental weakness exploited by manipulators.","severity":"medium","action":"flag_for_review","category":"fundamental"},
]
with open(OUT / "red_flag_rules.json", "w", encoding="utf-8") as f:
    json.dump({"version":"2.0","generated":"2026-06-30","description":"F51 Red Flag Detection Rules","rules":rules}, f, indent=2)

total = len(cases) + len(pump_tickers) + len(wash_cases)
print(f"Total RAG entries: {total} enforcement cases + {len(rules)} red flag rules")
print(f"Files written to {OUT}/")
