"""SuperEzio Eval Pipeline - GLM Judge -> Local Guidance.

Fluxo:
  1. Carrega questÃµes de data/eval_questions.jsonl
  2. Envia cada questÃ£o ao SuperEzio via /task/submit (NDJSON stream)
  3. GLM (via glm_proxy :8899) avalia qualidade de cada resposta
  4. Gera orientacao local priorizada a partir das avaliacoes
  5. Salva relatÃ³rio completo em reports/

Uso:
  python scripts/eval_pipeline.py                  # full run (25 questÃµes)
  python scripts/eval_pipeline.py --limit 5        # sÃ³ 5 pra testar
  python scripts/eval_pipeline.py --ids eval_001 eval_005  # especÃ­ficas
"""

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# Ensure project root is on path before importing core
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.config import load_env_once

load_env_once()

# â”€â”€ Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_FILE = PROJECT_ROOT / "data" / "eval_questions.jsonl"
REPORTS_DIR = PROJECT_ROOT / "reports"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

SUPEREZIO_URL = os.getenv("SUPEREZIO_EVAL_URL", "http://127.0.0.1:8002")
GLM_URL = os.getenv("GLM_EVAL_URL", "http://127.0.0.1:8899")
GLM_MODEL = os.getenv("GLM_EVAL_MODEL", "GLM-5.1")


TIMEOUT_SUPEREZIO = 120
TIMEOUT_GLM = 90
CONCURRENCY = 3  # paralelismo das questÃµes

# â”€â”€ GLM Judge Prompt â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
GLM_JUDGE_SYSTEM = """VocÃª Ã© um juiz de qualidade de um assistente financeiro AI chamado SuperEzio.

Seu trabalho Ã© avaliar respostas financeiras com RIGOR TÃ‰CNICO. Seja severo â€” se a resposta for fraca, genÃ©rica ou inventar dados, EXPLICITE.

CRITÃ‰RIOS (cada um de 0 a 10):

1. **Accuracy (AcurÃ¡cia)**: Os fatos estÃ£o corretos? NÃ£o inventou nÃºmeros, yields, valuations?
   - 0-3: Dados inventados ou completamente errados
   - 4-6: Alguns acertos, mas com imprecisÃµes
   - 7-10: Dados precisos e verificÃ¡veis com evidence_id rastreÃ¡vel

2. **Completeness (Completeza)**: Cobriu todos os aspectos relevantes da pergunta?
   - 0-3: Ignorou a pergunta ou respondeu algo irrelevante
   - 4-6: Parcial â€” cobriu alguns pontos mas faltaram outros crÃ­ticos
   - 7-10: Cobertura completa com anÃ¡lise multi-Ã¢ngulo

3. **Hallucination**: Inventou dados, citaÃ§Ãµes, nÃºmeros, autoridades ou eventos que nÃ£o existem?
   - 0-3: AlucinaÃ§Ã£o grave (inventou preÃ§os, tickers, eventos)
   - 4-6: AlucinaÃ§Ã£o menor (extrapolou sem evidÃªncia)
   - 7-10: Zero alucinaÃ§Ã£o â€” tudo baseado em dados fornecidos

4. **Structure (Estrutura)**: Usa markdown, JSON, ferramentas adequadamente?
   - 0-3: Texto bagunÃ§ado, sem estrutura
   - 4-6: Estrutura bÃ¡sica mas poderia ser muito melhor
   - 7-10: Estrutura impecÃ¡vel com sections, bullet points, tool calls bem formatadas

5. **Usefulness (Utilidade)**: A resposta Ã© acionÃ¡vel para um investidor real?
   - 0-3: GenÃ©rico, sem recomendaÃ§Ã£o ou conclusÃ£o clara
   - 4-6: Ãštil mas falta convicÃ§Ã£o ou direÃ§Ã£o
   - 7-10: Altamente acionÃ¡vel com veredito claro e prÃ³ximo passo

Retorne APENAS um JSON com este formato exato:
{
  "overall_score": 0-100,
  "scores": {
    "accuracy": 0-10,
    "completeness": 0-10,
    "hallucination": 0-10,
    "structure": 0-10,
    "usefulness": 0-10
  },
  "critical_issues": ["problema 1", "problema 2"],
  "strengths": ["ponto forte 1"],
  "verdict": "PASS|FAIL|WARN",
  "notes": "comentÃ¡rio tÃ©cnico conciso"
}"""

# Local guidance reference prompt.
LOCAL_GUIDANCE_SYSTEM = """VocÃª Ã© um arquiteto sÃªnior de sistemas AI financeiros revisando os resultados de uma avaliaÃ§Ã£o completa do pipeline SuperEzio.

O SuperEzio Ã© um assistente financeiro multiagente com:
- 12 experts financeiros (DeepSeek Chat V3 cloud)
- CEO local Qwen 3.6 merged GGUF, porta 8082
- Sem fallback cloud para veredito CEO final
- Pipeline: intent router â†’ data collection â†’ experts â†’ committee â†’ CEO â†’ resposta
- Componentes: Fraud RAG, Veracity Gate, Cost Guard, Memory, Crisis Math, PennyLab

Seu trabalho Ã© analisar as avaliaÃ§Ãµes do GLM Judge e fornecer ORIENTAÃ‡ÃƒO ACIONÃVEL de melhoria.

FORMATO DE RESPOSTA (markdown):
# SuperEzio Eval Run â€” OrientaÃ§Ã£o de Melhorias

## 1. DiagnÃ³stico Geral
- Score mÃ©dio: X/100
- Taxa de PASS: X% | FAIL: X% | WARN: X%
- Categorias mais fracas: [...]
- Componentes do pipeline que precisam de atenÃ§Ã£o: [...]

## 2. Problemas CrÃ­ticos (P0 â€” Corrigir Agora)
[Lista priorizada com gravidade, padrÃ£o observado e aÃ§Ã£o recomendada]

## 3. Melhorias Estruturais (P1 â€” Esta Sprint)
[Melhorias de mÃ©dio prazo nos componentes do pipeline]

## 4. OtimizaÃ§Ãµes (P2 â€” Backlog)
[Melhorias incrementais e ajustes finos]

## 5. RecomendaÃ§Ãµes TÃ©cnicas EspecÃ­ficas
- Arquivos a modificar
- MudanÃ§as sugeridas nos prompts
- Ajustes de parÃ¢metros
- Issues para abrir no GitHub

## 6. ConclusÃ£o
[Resumo executivo em 3-5 linhas]
"""


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Step 1: Carregar questÃµes
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def load_questions(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[FATAL] Dataset nÃ£o encontrado: {path}")
        sys.exit(1)
    questions = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        if line.strip():
            questions.append(json.loads(line))
    return questions


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Step 2: Enviar questÃ£o ao SuperEzio e coletar resposta
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
async def ask_superezio(question: str, session_id: str) -> dict[str, Any]:
    """Envia pergunta ao SuperEzio via /task/submit e coleta resposta NDJSON."""
    payload = {
        "from_agent": "eval_pipeline",
        "to_agent": "superezio",
        "type": "task_submit",
        "msg_id": str(uuid.uuid4()),
        "payload": {
            "message": question,
            "session_id": session_id,
            "memory_mode": "relevant_all",
            "rigor": "strict",
        },
    }

    chunks: list[str] = []
    events: list[dict] = []
    error = None
    start = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SUPEREZIO) as client:
            async with client.stream(
                "POST",
                f"{SUPEREZIO_URL}/task/submit",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status_code != 200:
                    error = f"HTTP {response.status_code}"
                else:
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            evt = json.loads(line)
                            events.append(evt)
                            if evt.get("type") == "CHUNK":
                                chunks.append(str(evt.get("content", "")))
                            elif evt.get("type") == "ERROR":
                                error = str(evt.get("detail", "Unknown"))
                        except json.JSONDecodeError:
                            pass
    except Exception as exc:
        error = str(exc)

    elapsed = time.monotonic() - start
    return {
        "question": question,
        "response": "".join(chunks),
        "events": events,
        "error": error,
        "elapsed_s": round(elapsed, 2),
        "chunk_count": len(chunks),
        "event_count": len(events),
    }


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Step 3: GLM avalia resposta do SuperEzio
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
async def glm_judge(question: str, response: str, expected_aspects: list[str]) -> dict:
    """GLM avalia a resposta do SuperEzio."""
    if not response or len(response) < 20:
        return {
            "overall_score": 0,
            "scores": {
                "accuracy": 0,
                "completeness": 0,
                "hallucination": 0,
                "structure": 0,
                "usefulness": 0,
            },
            "critical_issues": ["Resposta vazia ou muito curta"],
            "strengths": [],
            "verdict": "FAIL",
            "notes": "SuperEzio nÃ£o gerou resposta significativa",
            "error": "empty_response",
        }

    user_prompt = f"""PERGUNTA DO USUÃRIO:
{question}

ASPECTOS ESPERADOS NA RESPOSTA: {", ".join(expected_aspects)}

RESPOSTA DO SUPEREZIO:
{response[:8000]}

Avalie a resposta acima com RIGOR TÃ‰CNICO. Retorne APENAS o JSON."""

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_GLM) as client:
            r = await client.post(
                f"{GLM_URL}/v1/responses",
                json={
                    "model": GLM_MODEL,
                    "input": [
                        {"role": "system", "content": GLM_JUDGE_SYSTEM},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_output_tokens": 2048,
                    "temperature": 0.2,
                },
            )
            data = r.json()
            text = ""
            for output in data.get("output", []):
                for content in output.get("content", []):
                    if content.get("type") == "output_text":
                        text += content.get("text", "")

            # Extrair JSON da resposta (GLM pode adicionar markdown)
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(text[json_start:json_end])
            return {
                "raw": text,
                "error": "json_parse_failed",
                "overall_score": 0,
                "verdict": "ERROR",
            }
    except Exception as exc:
        return {"error": str(exc), "overall_score": 0, "verdict": "ERROR"}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Step 4: local guidance from GLM evaluations
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def local_guidance(eval_results: list[dict]) -> str:
    """Generate local prioritized guidance from GLM evaluation results."""
    summaries: list[str] = []
    total = len(eval_results)
    scores: list[int] = []
    verdicts: dict[str, int] = {"PASS": 0, "FAIL": 0, "WARN": 0, "ERROR": 0}
    category_fails: dict[str, list[str]] = {}
    all_critical: list[str] = []

    for r in eval_results:
        eval_data = r.get("evaluation", {})
        if isinstance(eval_data, str):
            continue
        s = eval_data.get("overall_score", 0)
        if isinstance(s, (int, float)):
            scores.append(int(s))
        v = eval_data.get("verdict", "ERROR")
        verdicts[v] = verdicts.get(v, 0) + 1

        cat = r.get("category", "unknown")
        if v in ("FAIL", "WARN"):
            category_fails.setdefault(cat, []).append(r["id"])

        for issue in eval_data.get("critical_issues", []):
            all_critical.append(f"[{r['id']}] {issue}")

        summaries.append(
            f"### {r['id']} ({r.get('category', '?')}) â€” Score: {s}/100 [{v}]\n"
            f"**Q:** {r['question'][:200]}\n"
            f"**A:** {r['response'][:500]}\n"
            f"**Scores:** {eval_data.get('scores', {})}\n"
            f"**Issues:** {eval_data.get('critical_issues', [])}\n"
            f"**Strengths:** {eval_data.get('strengths', [])}\n"
        )

    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    batch_summary = f"""RUN ID: {RUN_ID}
TOTAL QUESTÃ•ES: {total}
SCORE MÃ‰DIO: {avg_score}/100
PASS: {verdicts.get("PASS", 0)} | FAIL: {verdicts.get("FAIL", 0)} | WARN: {verdicts.get("WARN", 0)} | ERROR: {verdicts.get("ERROR", 0)}

TAXA DE APROVAÃ‡ÃƒO: {round(verdicts.get("PASS", 0) / max(total, 1) * 100, 1)}%

CATEGORIAS COM MAIS FALHAS:
{json.dumps({k: len(v) for k, v in category_fails.items()}, indent=2)}

TODOS OS PROBLEMAS CRÃTICOS:
{chr(10).join(all_critical[:50])}

AVALIAÃ‡Ã•ES DETALHADAS:
{chr(10).join(summaries)}"""

    worst_categories = sorted(
        ((category, len(ids)) for category, ids in category_fails.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    top_issues = all_critical[:10] or ["No critical issues reported by GLM."]

    return "\n".join(
        [
            "# SuperEzio Eval Run - Local Guidance",
            "",
            "## 1. Diagnostico Geral",
            f"- Score medio: {avg_score}/100",
            f"- PASS: {verdicts.get('PASS', 0)} | FAIL: {verdicts.get('FAIL', 0)} | WARN: {verdicts.get('WARN', 0)} | ERROR: {verdicts.get('ERROR', 0)}",
            f"- Categorias mais fracas: {worst_categories[:5]}",
            "",
            "## 2. Problemas Criticos",
            *[f"- {issue}" for issue in top_issues],
            "",
            "## 3. Proximo Patch Seguro",
            "- Corrigir primeiro respostas vazias, dados inventados, falta de evidence_id e rotas que pulam coleta de dados.",
            "- Reexecutar este script apos cada patch e comparar o score medio.",
            "",
            "## 4. Raw Summary",
            batch_summary[:3000],
        ]
    )


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Orchestrator
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
async def run_eval(questions: list[dict], semaphore: asyncio.Semaphore) -> list[dict]:
    """Executa avaliaÃ§Ã£o completa: SuperEzio â†’ GLM Judge."""
    results: list[dict] = []

    async def eval_one(q: dict) -> dict:
        async with semaphore:
            qid = q["id"]
            print(f"  [{qid}] Enviando: {q['question'][:80]}...")
            se_result = await ask_superezio(q["question"], f"eval_{qid}")
            if se_result["error"]:
                print(f"  [{qid}] âŒ SuperEzio error: {se_result['error']}")
            else:
                print(
                    f"  [{qid}] âœ… {se_result['chunk_count']} chunks em {se_result['elapsed_s']}s"
                )

            print(f"  [{qid}] GLM julgando...")
            evaluation = await glm_judge(
                q["question"], se_result["response"], q.get("expected_aspects", [])
            )
            score = evaluation.get("overall_score", "?")
            verdict = evaluation.get("verdict", "?")
            print(f"  [{qid}] ðŸ“Š Score: {score}/100 [{verdict}]")

            return {**q, **se_result, "evaluation": evaluation}

    tasks = [eval_one(q) for q in questions]
    results = await asyncio.gather(*tasks)
    return results


def save_report(results: list[dict], guidance: str):
    """Salva relatÃ³rio completo em Markdown."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"eval_run_{RUN_ID}.md"

    # Statistics
    total = len(results)
    scores = [
        r["evaluation"].get("overall_score", 0)
        for r in results
        if isinstance(r.get("evaluation"), dict)
    ]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    verdicts = {"PASS": 0, "FAIL": 0, "WARN": 0, "ERROR": 0}
    for r in results:
        v = (
            r.get("evaluation", {}).get("verdict", "ERROR")
            if isinstance(r.get("evaluation"), dict)
            else "ERROR"
        )
        verdicts[v] = verdicts.get(v, 0) + 1

    lines = [
        f"# SuperEzio Eval Run â€” {RUN_ID}",
        "",
        f"**QuestÃµes**: {total} | **Score MÃ©dio**: {avg_score}/100",
        f"**PASS**: {verdicts['PASS']} | **FAIL**: {verdicts['FAIL']} | **WARN**: {verdicts['WARN']} | **ERROR**: {verdicts['ERROR']}",
        f"**Taxa de AprovaÃ§Ã£o**: {round(verdicts['PASS'] / max(total, 1) * 100, 1)}%",
        "",
        "---",
        "",
        "## ðŸ” Resultados por QuestÃ£o",
        "",
    ]

    for r in results:
        eval_data = r.get("evaluation", {})
        if not isinstance(eval_data, dict):
            eval_data = {}
        lines.append(f"### {r['id']} â€” {r.get('category', '?')}")
        lines.append(
            f"- **Score**: {eval_data.get('overall_score', '?')}/100 [{eval_data.get('verdict', '?')}]"
        )
        lines.append(
            f"- **Tempo**: {r.get('elapsed_s', '?')}s | **Chunks**: {r.get('chunk_count', '?')}"
        )
        lines.append(f"- **Pergunta**: {r['question']}")
        lines.append(
            f"- **Resposta**: {r['response'][:500]}{'...' if len(r.get('response', '')) > 500 else ''}"
        )
        scores_detail = eval_data.get("scores", {})
        if scores_detail:
            lines.append(
                f"- **Scores**: A={scores_detail.get('accuracy', '?')} C={scores_detail.get('completeness', '?')} H={scores_detail.get('hallucination', '?')} S={scores_detail.get('structure', '?')} U={scores_detail.get('usefulness', '?')}"
            )
        issues = eval_data.get("critical_issues", [])
        if issues:
            lines.append(f"- **Problemas**: {'; '.join(issues)}")
        strengths = eval_data.get("strengths", [])
        if strengths:
            lines.append(f"- **Pontos Fortes**: {'; '.join(strengths)}")
        if r.get("error"):
            lines.append(f"- **Erro**: {r['error']}")
        lines.append("")

    lines += [
        "",
        "---",
        "",
        "## Orientacao Local",
        "",
        guidance,
        "",
        "---",
        "",
        f"*RelatÃ³rio gerado em {RUN_ID}*",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nðŸ“„ RelatÃ³rio salvo: {report_path}")
    return report_path


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Main
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def main():
    parser = argparse.ArgumentParser(description="SuperEzio Eval Pipeline")
    parser.add_argument("--limit", type=int, default=0, help="Limitar N questÃµes")
    parser.add_argument("--ids", nargs="*", default=[], help="IDs especÃ­ficos")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    args = parser.parse_args()

    print("=" * 60)
    print("  SuperEzio Eval Pipeline")
    print("  GLM Judge -> Local Guidance")
    print(f"  Run ID: {RUN_ID}")
    print("=" * 60)

    # Load questions
    all_qs = load_questions(QUESTIONS_FILE)
    if args.ids:
        questions = [q for q in all_qs if q["id"] in args.ids]
    elif args.limit:
        questions = all_qs[: args.limit]
    else:
        questions = all_qs

    print(f"\nðŸ“‹ {len(questions)} questÃµes carregadas")
    print(f"ðŸ”— SuperEzio: {SUPEREZIO_URL}")
    print(f"âš–ï¸  GLM Judge: {GLM_URL} ({GLM_MODEL})")
    print()

    # Check endpoints
    async def health_check():
        async with httpx.AsyncClient(timeout=5) as client:
            se_ok = False
            glm_ok = False
            try:
                r = await client.get(f"{SUPEREZIO_URL}/health")
                se_ok = r.status_code == 200
                print(f"  SuperEzio health: {'âœ…' if se_ok else 'âŒ'} ({r.status_code})")
            except Exception as e:
                print(f"  SuperEzio health: âŒ ({e})")
            try:
                r = await client.get(
                    f"{GLM_URL}/v1/responses",
                    json={"model": GLM_MODEL, "input": "ping"},
                )
                glm_ok = r.status_code in (200, 404, 405)  # aceita erro de mÃ©todo
                print(f"  GLM proxy: {'âœ…' if glm_ok else 'âŒ'} ({r.status_code})")
            except Exception as e:
                print(f"  GLM proxy: âŒ ({e})")
            return se_ok, glm_ok

    se_ok, glm_ok = asyncio.run(health_check())
    if not se_ok:
        print("\n[AVISO] SuperEzio parece offline. Continuando mesmo assim...")
    if not glm_ok:
        print("\n[AVISO] GLM Proxy parece offline. As avaliaÃ§Ãµes vÃ£o falhar.")

    print()

    # Run evaluation
    semaphore = asyncio.Semaphore(args.concurrency)
    results = asyncio.run(run_eval(questions, semaphore))

    # Summary
    scores = [
        r["evaluation"].get("overall_score", 0)
        for r in results
        if isinstance(r.get("evaluation"), dict)
    ]
    avg = round(sum(scores) / len(scores), 1) if scores else 0
    passed = sum(
        1
        for r in results
        if isinstance(r.get("evaluation"), dict) and r["evaluation"].get("verdict") == "PASS"
    )

    print(f"\n{'=' * 60}")
    print(f"  RESULTADO: {avg}/100 | {passed}/{len(results)} PASS")
    print(f"{'=' * 60}")

    # Local guidance
    print("\nGerando orientacao local...")
    guidance = local_guidance(results)

    # Save report
    report_path = save_report(results, guidance)
    json_path = report_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(
            {
                "run_id": RUN_ID,
                "avg_score": avg,
                "passed": passed,
                "total": len(results),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"ðŸ“„ JSON salvo: {json_path}")

    return 0 if avg >= 50 else 1


if __name__ == "__main__":
    sys.exit(main())
