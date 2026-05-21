"""
F51 SFT Conversion Pipeline
Converts downloaded HF datasets into unified JSONL SFT format.
Target: 500 MB of premium fraud/finance training data.
"""

import pandas as pd
import json
import os
import hashlib
import random

RAW = r"C:\Users\marco\Desktop\F51_Datasets\raw_downloads"
OUT = r"C:\Users\marco\Desktop\F51_Datasets\sft_output"
os.makedirs(OUT, exist_ok=True)

random.seed(42)
ALL_ENTRIES = []

# ============================================================
# SYSTEM PROMPTS by domain
# ============================================================
SYSTEMS = {
    "fraud_transaction": "You are a defensive financial fraud risk analyst. You analyze transaction data and identify fraud patterns, money laundering signals, and account takeover indicators. Output structured risk assessments with clear reasoning.",
    "fraud_document": "You are a forensic financial document analyst. You examine corporate filings, financial statements, and regulatory documents for indicators of fraud, misrepresentation, and accounting irregularities. Output detailed analysis with specific evidence.",
    "fraud_phishing": "You are an email security analyst specializing in phishing and social engineering detection. You analyze email content for phishing indicators, impersonation attempts, and malicious intent. Output structured threat assessments.",
    "fraud_social": "You are a social media fraud and disinformation analyst. You analyze social media content for fraud schemes, deception tactics, manipulation techniques, and scam patterns. Output structured analysis identifying specific tactics and risk levels.",
    "finance_qa": "You are a financial analyst specializing in quantitative analysis of corporate financial reports. You analyze financial tables, earnings reports, and regulatory filings to answer precise quantitative questions. Output answers with step-by-step calculations and reasoning.",
    "finance_sentiment": "You are a financial sentiment analyst. You analyze financial news headlines, microblogs, and corporate communications for sentiment, market impact, and entity-level analysis. Output structured sentiment assessments with confidence scores.",
}


def make_entry(
    domain, category, difficulty, system_key, user_content, assistant_content, metadata=None
):
    """Create a standard F51 SFT entry."""
    entry = {
        "domain": domain,
        "category": category,
        "difficulty": difficulty,
        "messages": [
            {"role": "system", "content": SYSTEMS.get(system_key, SYSTEMS["fraud_transaction"])},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ],
    }
    if metadata:
        entry["metadata"] = metadata
    return entry


def estimate_tokens(text):
    """Rough token estimate: ~4 chars per token."""
    return len(str(text)) // 4


# ============================================================
# 1. CiferAI Fraud Detection (Tabular -> Fraud Analysis)
# ============================================================
def convert_ciferai(sample_fraud=30000, sample_nofraud=50000):
    """Sample from 21M rows, balance fraud/non-fraud, convert to analysis prompts."""
    print("\n[1/6] Converting CiferAI Fraud Detection...")
    path = os.path.join(RAW, "cifer_fraud_detection__default__train.parquet")
    df = pd.read_parquet(path)

    fraud_df = df[df["isFraud"] == 1]
    nofraud_df = df[df["isFraud"] == 0]

    print(f"  Fraud: {len(fraud_df):,}, Non-fraud: {len(nofraud_df):,}")

    # Sample
    fraud_sample = fraud_df.sample(n=min(sample_fraud, len(fraud_df)), random_state=42)
    nofraud_sample = nofraud_df.sample(n=min(sample_nofraud, len(nofraud_df)), random_state=42)

    entries = []
    for _, row in fraud_sample.iterrows():
        user_msg = (
            f"Transaction data:\n"
            f"  step: {row['step']}\n"
            f"  type: {row['type']}\n"
            f"  amount: {row['amount']:.2f}\n"
            f"  origin_balance_before: {row['oldbalanceOrg']:.2f}\n"
            f"  origin_balance_after: {row['newbalanceOrig']:.2f}\n"
            f"  destination_balance_before: {row['oldbalanceDest']:.2f}\n"
            f"  destination_balance_after: {row['newbalanceDest']:.2f}\n\n"
            f"Analyze this transaction for fraud risk. Identify all suspicious signals, "
            f"assess the risk level, and recommend action."
        )

        # Generate structured analysis from the features
        signals = []
        risk = "low"
        action = "allow"

        # Rule-based signal detection
        if row["amount"] > 200000:
            signals.append(f"High-value transaction: {row['amount']:.2f} exceeds typical threshold")
            risk = "medium"
        if row["type"] in ("TRANSFER", "CASH_OUT"):
            signals.append(f"{row['type']} transaction type is commonly used in fraud schemes")
            risk = "medium"
        if row["oldbalanceOrg"] > 0 and row["newbalanceOrig"] == 0 and row["amount"] > 50000:
            signals.append("Full account drain detected: entire balance transferred out")
            risk = "high"
        if row["newbalanceDest"] == 0 and row["amount"] > 0:
            signals.append(
                "Destination balance inconsistency: funds not reflected in destination account"
            )
            risk = "high"
        if row["oldbalanceDest"] == 0 and row["newbalanceDest"] == 0 and row["amount"] > 1000:
            signals.append(
                "Zero-balance destination account receiving transfer: possible mule account"
            )
            risk = "high"
        if row["amount"] > 500000:
            signals.append("Amount exceeds regulatory reporting threshold")
            risk = "high"
        if row["isFlaggedFraud"]:
            signals.append("Transaction flagged by automated system")
            risk = "high"

        if not signals:
            signals.append("No suspicious signals detected")
            risk = "low"
            action = "allow"

        if risk == "high":
            action = "block and escalate to fraud investigation team"
            difficulty = "hard"
        elif risk == "medium":
            action = "flag for manual review"
            difficulty = "medium"
        else:
            action = "allow through standard processing"
            difficulty = "easy"

        signals_text = "\n".join(f"  - {s}" for s in signals)
        assistant_msg = (
            f"Fraud Risk Assessment:\n\n"
            f"Risk Level: {risk.upper()}\n\n"
            f"Signals Detected:\n{signals_text}\n\n"
            f"Analysis: This {row['type']} transaction for {row['amount']:.2f} shows "
            f"{'multiple' if len(signals) > 2 else 'some' if len(signals) > 1 else 'no'} "
            f"fraud indicators. "
            f"{'The combination of full balance drain, destination inconsistency, and transaction type pattern is strongly indicative of fraud.' if risk == 'high' else ''}"
            f"{'Moderate concern due to transaction characteristics; manual review recommended.' if risk == 'medium' else ''}"
            f"{'Transaction appears routine with no anomalous patterns.' if risk == 'low' else ''}\n\n"
            f"Recommended Action: {action}\n\n"
            f"Transaction Type Risk Context: {row['type']} transactions account for a "
            f"{'significant' if row['type'] in ('TRANSFER', 'CASH_OUT') else 'moderate'} "
            f"portion of fraud cases. The balance pattern "
            f"{'is consistent with' if risk == 'high' else 'does not match'} known fraud signatures."
        )

        entries.append(
            make_entry(
                domain="fraud",
                category="transaction_risk",
                difficulty=difficulty,
                system_key="fraud_transaction",
                user_content=user_msg,
                assistant_content=assistant_msg,
                metadata={
                    "source": "CiferAI/Cifer-Fraud-Detection-Dataset-AF",
                    "isFraud": int(row["isFraud"]),
                },
            )
        )

    # Non-fraud sample (smaller, for balance)
    for _, row in nofraud_sample.iterrows():
        user_msg = (
            f"Transaction data:\n"
            f"  step: {row['step']}\n"
            f"  type: {row['type']}\n"
            f"  amount: {row['amount']:.2f}\n"
            f"  origin_balance_before: {row['oldbalanceOrg']:.2f}\n"
            f"  origin_balance_after: {row['newbalanceOrig']:.2f}\n"
            f"  destination_balance_before: {row['oldbalanceDest']:.2f}\n"
            f"  destination_balance_after: {row['newbalanceDest']:.2f}\n\n"
            f"Analyze this transaction. Is there any fraud risk? Justify your assessment."
        )

        assistant_msg = (
            f"Fraud Risk Assessment:\n\n"
            f"Risk Level: LOW\n\n"
            f"Signals Detected:\n"
            f"  - No suspicious signals detected\n\n"
            f"Analysis: This {row['type']} transaction for {row['amount']:.2f} appears legitimate. "
            f"Balance changes are consistent with the transaction type. "
            f"No anomalous patterns detected in origin or destination account behavior.\n\n"
            f"Recommended Action: Allow through standard processing."
        )

        entries.append(
            make_entry(
                domain="fraud",
                category="transaction_risk",
                difficulty="easy",
                system_key="fraud_transaction",
                user_content=user_msg,
                assistant_content=assistant_msg,
                metadata={"source": "CiferAI/Cifer-Fraud-Detection-Dataset-AF", "isFraud": 0},
            )
        )

    print(f"  Converted: {len(entries)} entries")
    return entries


# ============================================================
# 2. amitkedia Financial Fraud (Filings -> Document Fraud Analysis)
# ============================================================
def convert_amitkedia():
    print("\n[2/6] Converting amitkedia Financial Fraud...")
    path = os.path.join(RAW, "financial_fraud_amitkedia__default__train.parquet")
    df = pd.read_parquet(path)

    entries = []
    for _, row in df.iterrows():
        filing_text = str(row["Fillings"])[:8000]  # Truncate very long filings
        is_fraud = str(row["Fraud"]).lower() == "yes"

        user_msg = (
            f"Analyze the following financial filing for indicators of fraud, "
            f"misrepresentation, or accounting irregularities:\n\n"
            f"--- FILING TEXT ---\n{filing_text}\n--- END ---\n\n"
            f"Provide a structured analysis identifying any red flags, "
            f"accounting concerns, or compliance issues."
        )

        if is_fraud:
            difficulty = "hard"
            assistant_msg = (
                "Fraud Analysis of Financial Filing:\n\n"
                "Fraud Determination: YES — Indicators Present\n\n"
                "Red Flags Identified:\n"
                "  1. The filing contains language patterns consistent with obfuscation of material facts.\n"
                "  2. Multiple restatements and amendments suggest prior reporting deficiencies.\n"
                "  3. Complex entity structures and related-party transactions present opacity risks.\n"
                "  4. Non-standard accounting treatments noted in the filing language.\n\n"
                "Risk Assessment: HIGH — This filing exhibits multiple characteristics associated "
                "with fraudulent financial reporting. The pattern of amendments, complexity of "
                "transactions, and disclosure language warrant further forensic investigation.\n\n"
                "Recommended Actions:\n"
                "  - Engage forensic accounting team for full review\n"
                "  - Cross-reference with regulatory filings and auditor communications\n"
                "  - Examine related-party transactions and off-balance-sheet items\n"
                "  - Review management discussion for inconsistencies with financial data"
            )
        else:
            difficulty = "medium"
            assistant_msg = (
                "Fraud Analysis of Financial Filing:\n\n"
                "Fraud Determination: NO — No Material Indicators\n\n"
                "Assessment: The filing was reviewed for common fraud indicators including:\n"
                "  - Unusual disclosure language or obfuscation\n"
                "  - Inconsistencies with standard accounting practices\n"
                "  - Red flags in related-party transaction disclosures\n"
                "  - Patterns associated with earnings management\n\n"
                "No material fraud indicators were identified in this filing. "
                "The disclosure language and structure appear consistent with standard "
                "regulatory filing requirements.\n\n"
                "Risk Level: LOW — Routine monitoring sufficient."
            )

        entries.append(
            make_entry(
                domain="fraud",
                category="document_fraud",
                difficulty=difficulty,
                system_key="fraud_document",
                user_content=user_msg,
                assistant_content=assistant_msg,
                metadata={"source": "amitkedia/Financial-Fraud-Dataset", "isFraud": is_fraud},
            )
        )

    print(f"  Converted: {len(entries)} entries")
    return entries


# ============================================================
# 3. Phishing Email Dataset (Email -> Phishing Detection)
# ============================================================
def convert_phishing():
    print("\n[3/6] Converting Phishing Email Dataset...")
    path = os.path.join(RAW, "phishing_email_zefang__default__train.parquet")
    df = pd.read_parquet(path)
    df = df.dropna(subset=["Email Text"])

    # Separate phishing and safe
    phishing = df[df["Email Type"] == "Phishing Email"]
    safe = df[df["Email Type"] == "Safe Email"]

    # Balance: use all phishing, sample safe to 2x
    safe_sample = safe.sample(n=min(len(phishing) * 2, len(safe)), random_state=42)
    combined = pd.concat([phishing, safe_sample])

    entries = []
    for _, row in combined.iterrows():
        email_text = str(row["Email Text"])[:6000]
        is_phishing = row["Email Type"] == "Phishing Email"

        user_msg = (
            f"Analyze the following email for phishing indicators, social engineering tactics, "
            f"and security threats:\n\n"
            f"--- EMAIL ---\n{email_text}\n--- END ---\n\n"
            f"Provide a structured phishing threat assessment."
        )

        if is_phishing:
            difficulty = "medium"
            assistant_msg = (
                "Phishing Threat Assessment:\n\n"
                "Verdict: PHISHING — Threat Detected\n\n"
                "Indicators Identified:\n"
                "  1. Deceptive content aiming to manipulate recipient into action\n"
                "  2. Social engineering tactics designed to create urgency or fear\n"
                "  3. Impersonation or authority exploitation patterns\n"
                "  4. Request for sensitive information or credential harvesting\n\n"
                "Threat Level: MEDIUM-HIGH\n\n"
                "Tactics Used: Spear phishing, social engineering, impersonation\n\n"
                "Recommendation: Block sender domain, flag for security team review, "
                "add to phishing threat feed. Do not engage with sender."
            )
        else:
            difficulty = "easy"
            assistant_msg = (
                "Phishing Threat Assessment:\n\n"
                "Verdict: LEGITIMATE — No Phishing Detected\n\n"
                "Assessment: This email does not exhibit common phishing characteristics:\n"
                "  - No urgency or fear manipulation\n"
                "  - No credential harvesting attempts\n"
                "  - No suspicious links or attachment vectors\n"
                "  - Content consistent with legitimate communication\n\n"
                "Threat Level: LOW — No action required."
            )

        entries.append(
            make_entry(
                domain="fraud",
                category="phishing_detection",
                difficulty=difficulty,
                system_key="fraud_phishing",
                user_content=user_msg,
                assistant_content=assistant_msg,
                metadata={
                    "source": "zefang-liu/phishing-email-dataset",
                    "is_phishing": is_phishing,
                },
            )
        )

    print(
        f"  Converted: {len(entries)} entries (from {len(phishing)} phishing + {len(safe_sample)} safe)"
    )
    return entries


# ============================================================
# 4. MultiAgentFraudBench (Social -> Deception Analysis)
# ============================================================
def convert_multiagent():
    print("\n[4/6] Converting MultiAgentFraudBench...")
    entries = []

    for split_name in ["balanced", "full"]:
        fname = f"multiagent_fraud_bench__{split_name}__train.parquet"
        path = os.path.join(RAW, fname)
        if not os.path.exists(path):
            print(f"  SKIP {fname}: not found")
            continue

        df = pd.read_parquet(path)
        print(f"  {split_name}: {len(df)} rows")

        for _, row in df.iterrows():
            content = str(row["content"])
            category = str(row["category"])
            deception = str(row["deception_type"])
            tactics = str(row["manipulation_tactics"])

            user_msg = (
                f"Analyze this social media content for fraud, deception, or scam indicators:\n\n"
                f'--- CONTENT ---\n"{content}"\n--- END ---\n\n'
                f"Context: This was posted in a category related to '{category}'.\n"
                f"Identify deception types, manipulation tactics, risk level, and victim profile."
            )

            # Difficulty based on category
            if "investment" in category.lower() or "securities" in category.lower():
                difficulty = "hard"
            elif "phishing" in category.lower() or "impersonation" in category.lower():
                difficulty = "medium"
            else:
                difficulty = "medium"

            assistant_msg = (
                f"Fraud Content Analysis:\n\n"
                f"Category: {category}\n"
                f"Deception Type: {deception}\n"
                f"Manipulation Tactics: {tactics}\n\n"
                f"Risk Level: {'HIGH' if 'investment' in category.lower() or 'securities' in category.lower() else 'MEDIUM'}\n\n"
                f"Analysis:\n"
                f"This content employs {deception.lower()} to manipulate targets. "
                f"The primary psychological levers are {tactics.lower()}. "
                f"{'Financial fraud is the likely objective, targeting victims with promises of unrealistic returns.' if 'investment' in category.lower() else ''}"
                f"{'The scam exploits trust and authority to obtain sensitive information or payments.' if 'impersonation' in category.lower() or 'phishing' in category.lower() else ''}"
                f"{'Consumer fraud pattern: non-delivery of goods/services after payment.' if 'product' in category.lower() or 'consumer' in category.lower() else ''}\n\n"
                f"Victim Profile: {'Retail investors seeking quick returns, financially vulnerable individuals' if 'investment' in category.lower() else 'General consumers, elderly or less tech-savvy individuals' if 'consumer' in category.lower() else 'General social media users susceptible to social engineering'}\n\n"
                f"Recommended Countermeasures:\n"
                f"  1. Platform content moderation flag: {deception}\n"
                f"  2. User education on {tactics} recognition\n"
                f"  3. Block known scam patterns and report to relevant authorities"
            )

            entries.append(
                make_entry(
                    domain="fraud",
                    category="social_fraud",
                    difficulty=difficulty,
                    system_key="fraud_social",
                    user_content=user_msg,
                    assistant_content=assistant_msg,
                    metadata={
                        "source": "ninty-seven/MultiAgentFraudBench",
                        "category": category,
                        "deception_type": deception,
                        "manipulation_tactics": tactics,
                    },
                )
            )

    print(f"  Converted: {len(entries)} entries")
    return entries


# ============================================================
# 5. ConvFinQA (Financial Tables -> Q&A)
# ============================================================
def convert_convfinqa():
    print("\n[5/6] Converting ConvFinQA...")
    entries = []

    for split_name in ["train", "validation"]:
        fname = f"convfinqa__ConvFinQA__{split_name}.parquet"
        path = os.path.join(RAW, fname)
        if not os.path.exists(path):
            print(f"  SKIP {fname}: not found")
            continue

        df = pd.read_parquet(path)
        # Only rows with qa field populated
        df = df.dropna(subset=["qa"])
        print(f"  {split_name}: {len(df)} rows with Q&A")

        for _, row in df.iterrows():
            qa = row["qa"]
            question = str(qa.get("question", ""))
            answer = str(qa.get("answer", ""))
            explanation = str(qa.get("explanation", ""))
            program = str(qa.get("program", ""))

            # Build table context (handle numpy arrays and lists)
            pre_raw = row.get("pre_text")
            if pre_raw is not None and len(pre_raw) > 0:
                pre_text = " ".join(str(t) for t in pre_raw)[:3000]
            else:
                pre_text = ""
            post_raw = row.get("post_text")
            if post_raw is not None and len(post_raw) > 0:
                post_text = " ".join(str(t) for t in post_raw)[:3000]
            else:
                post_text = ""

            user_msg = (
                f"Financial Document Context:\n{pre_text}\n\n"
                f"Additional Context:\n{post_text}\n\n"
                f"Question: {question}\n\n"
                f"Answer this financial question using the provided document context. "
                f"Show your calculations step by step. Be numerically precise."
            )

            # Determine difficulty from computation steps
            steps_arr = qa.get("steps", [])
            num_steps = len(steps_arr) if hasattr(steps_arr, "__len__") else 0
            if num_steps >= 3:
                difficulty = "hard"
            elif num_steps == 2:
                difficulty = "medium"
            else:
                difficulty = "easy"

            assistant_msg = (
                f"Answer: {answer}\n\n"
                f"Calculation:\n"
                f"{'  ' + program if program else '  Direct computation from financial data'}\n\n"
                f"{'Explanation: ' + explanation if explanation else ''}\n\n"
                f"The answer was derived by {'a multi-step computation from the financial tables and document text' if num_steps >= 2 else 'direct extraction/computation from the provided financial data'}."
            )

            entries.append(
                make_entry(
                    domain="finance",
                    category="financial_qa",
                    difficulty=difficulty,
                    system_key="finance_qa",
                    user_content=user_msg,
                    assistant_content=assistant_msg,
                    metadata={
                        "source": "AdaptLLM/ConvFinQA",
                        "split": split_name,
                        "num_steps": num_steps,
                        "program": program,
                    },
                )
            )

    print(f"  Converted: {len(entries)} entries")
    return entries


# ============================================================
# 6. FiQA Sentiment (Financial Headlines -> Sentiment Analysis)
# ============================================================
def convert_fiqa():
    print("\n[6/6] Converting FiQA Sentiment...")
    entries = []

    for split_name in ["train", "test", "valid"]:
        fname = f"fiqa_sentiment__default__{split_name}.parquet"
        path = os.path.join(RAW, fname)
        if not os.path.exists(path):
            print(f"  SKIP {fname}: not found")
            continue

        df = pd.read_parquet(path)
        print(f"  {split_name}: {len(df)} rows")

        for _, row in df.iterrows():
            sentence = str(row["sentence"])
            target = str(row["target"])
            aspect = str(row["aspect"])
            score = float(row["score"])

            # Convert score to label
            if score > 0.2:
                sentiment = "positive"
                sentiment_label = "POSITIVE"
                difficulty = "easy"
            elif score < -0.2:
                sentiment = "negative"
                sentiment_label = "NEGATIVE"
                difficulty = "easy"
            else:
                sentiment = "neutral"
                sentiment_label = "NEUTRAL"
                difficulty = "easy"

            user_msg = (
                f"Analyze the sentiment of this financial text:\n\n"
                f'"{sentence}"\n\n'
                f"Entity: {target}\n"
                f"Aspect: {aspect}\n\n"
                f"Provide sentiment classification with confidence score and entity-level analysis."
            )

            assistant_msg = (
                f"Financial Sentiment Analysis:\n\n"
                f'Text: "{sentence}"\n'
                f"Entity: {target}\n"
                f"Aspect: {aspect}\n\n"
                f"Sentiment: {sentiment_label}\n"
                f"Sentiment Score: {score:.3f} (range: -1.0 to +1.0)\n\n"
                f"Analysis: This text expresses a {sentiment} sentiment toward {target} "
                f"regarding {aspect}. "
                f"{'The positive tone suggests favorable market conditions or corporate developments.' if sentiment == 'positive' else ''}"
                f"{'The negative tone indicates concerning developments or market headwinds.' if sentiment == 'negative' else ''}"
                f"{'The neutral tone reflects balanced or factual reporting without strong directional bias.' if sentiment == 'neutral' else ''}\n\n"
                f"Market Impact: {'Potentially favorable for entity valuation' if sentiment == 'positive' else 'Potentially adverse for entity valuation' if sentiment == 'negative' else 'Limited directional impact expected'}"
            )

            entries.append(
                make_entry(
                    domain="finance",
                    category="sentiment_analysis",
                    difficulty=difficulty,
                    system_key="finance_sentiment",
                    user_content=user_msg,
                    assistant_content=assistant_msg,
                    metadata={
                        "source": "TheFinAI/fiqa-sentiment-classification",
                        "split": split_name,
                        "score": score,
                        "target": target,
                        "aspect": aspect,
                    },
                )
            )

    print(f"  Converted: {len(entries)} entries")
    return entries


# ============================================================
# MAIN: Run all conversions, deduplicate, and save
# ============================================================
if __name__ == "__main__":
    all_entries = []

    all_entries.extend(convert_ciferai(sample_fraud=27000, sample_nofraud=350000))
    all_entries.extend(convert_amitkedia())
    all_entries.extend(convert_phishing())
    all_entries.extend(convert_multiagent())
    all_entries.extend(convert_convfinqa())
    all_entries.extend(convert_fiqa())

    print(f"\n{'=' * 60}")
    print(f"TOTAL ENTRIES: {len(all_entries):,}")

    # Deduplicate by user message hash
    seen = set()
    deduped = []
    for e in all_entries:
        h = hashlib.md5(e["messages"][1]["content"][:500].encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            deduped.append(e)
    dupes_removed = len(all_entries) - len(deduped)
    print(f"Duplicates removed: {dupes_removed}")
    print(f"Deduplicated total: {len(deduped):,}")

    # Shuffle
    random.shuffle(deduped)

    # Save full SFT file
    sft_path = os.path.join(OUT, "f51_sft_combined.jsonl")
    with open(sft_path, "w", encoding="utf-8") as f:
        for entry in deduped:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    sz_mb = os.path.getsize(sft_path) / (1024 * 1024)
    print(f"\nSaved: {sft_path}")
    print(f"Size: {sz_mb:.1f} MB")

    # Domain breakdown
    domains = {}
    for e in deduped:
        d = e["domain"]
        domains[d] = domains.get(d, 0) + 1

    print("\nDomain Breakdown:")
    for d, c in sorted(domains.items()):
        print(f"  {d}: {c:,}")

    # Category breakdown
    categories = {}
    for e in deduped:
        cat = f"{e['domain']}/{e['category']}"
        categories[cat] = categories.get(cat, 0) + 1
    print("\nCategory Breakdown:")
    for cat, c in sorted(categories.items()):
        print(f"  {cat}: {c:,}")

    # Difficulty breakdown
    diffs = {}
    for e in deduped:
        d = e["difficulty"]
        diffs[d] = diffs.get(d, 0) + 1
    print("\nDifficulty Breakdown:")
    for d, c in sorted(diffs.items()):
        print(f"  {d}: {c:,}")

    # Estimated tokens
    total_chars = sum(len(json.dumps(e, ensure_ascii=False)) for e in deduped)
    est_tokens = total_chars // 4
    print(f"\nEstimated tokens: {est_tokens:,}")
    print(f"Estimated size: {sz_mb:.1f} MB")

    # Save manifest
    manifest = {
        "total_entries": len(deduped),
        "duplicates_removed": dupes_removed,
        "size_mb": round(sz_mb, 2),
        "estimated_tokens": est_tokens,
        "domains": domains,
        "categories": categories,
        "difficulties": diffs,
        "sources": {
            "CiferAI": len(
                [e for e in deduped if "CiferAI" in str(e.get("metadata", {}).get("source", ""))]
            ),
            "amitkedia": len(
                [e for e in deduped if "amitkedia" in str(e.get("metadata", {}).get("source", ""))]
            ),
            "phishing_email": len(
                [e for e in deduped if "phishing" in str(e.get("metadata", {}).get("source", ""))]
            ),
            "MultiAgentFraudBench": len(
                [e for e in deduped if "MultiAgent" in str(e.get("metadata", {}).get("source", ""))]
            ),
            "ConvFinQA": len(
                [e for e in deduped if "ConvFinQA" in str(e.get("metadata", {}).get("source", ""))]
            ),
            "FiQA": len(
                [e for e in deduped if "fiqa" in str(e.get("metadata", {}).get("source", ""))]
            ),
        },
    }

    manifest_path = os.path.join(OUT, "sft_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nManifest: {manifest_path}")
