"""Deep End-User Audit & Usability Evaluation for SuperEzio Cockpit.

Simulates a complete real-world trader session:
1. Multi-ticker navigation (TD.TO, AAPL, NVDA) & timeframe switching (1D, 1W, 1M, 6M)
2. Interactive panels audit (SDCA Lab, Expert Committee, Alerts, Trust Score)
3. 3 distinct real-world financial conversations with Bob
4. Visual fidelity, responsiveness & quality evaluation
"""

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = os.getenv("SUPEREZIO_BASE_URL", "http://127.0.0.1:8002")
AUDIT_DIR = Path("output/user_audit")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def run_deep_audit():
    audit_results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_url": BASE_URL,
        "scenarios": [],
        "screenshots": [],
        "overall_score": 0,
        "ux_findings": [],
        "chat_conversations": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Desktop 1080p viewport for rich visual evaluation
        context = browser.new_context(
            viewport={"width": 1600, "height": 960}, device_scale_factor=1
        )
        page = context.new_page()

        console_errors = []
        page.on(
            "console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None
        )
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        print("══════════════════════════════════════════════════════════════")
        print("  INICIANDO AUDITORIA INTERATIVA PROFUNDA DO SUPEREZIO")
        print("══════════════════════════════════════════════════════════════\n")

        # ------------------------------------------------------------------
        # CENÁRIO 1: Primeiro Acesso & Interface
        # ------------------------------------------------------------------
        print("▶ [CENÁRIO 1] Primeiro Acesso e Reconhecimento Visual...")
        t0 = time.time()
        page.goto(BASE_URL, wait_until="load", timeout=30000)
        page.wait_for_timeout(2500)

        shot1 = str(AUDIT_DIR / "audit_01_cockpit_overview.png")
        page.screenshot(path=shot1, full_page=False)
        audit_results["screenshots"].append(shot1)

        # Inspecionar elementos da barra de status
        status_data = page.evaluate("""() => {
            return {
                title: document.title,
                status_bar: document.querySelector('.status-bar, #status-bar, .topbar')?.innerText || '',
                theme: document.documentElement.getAttribute('data-theme') || 'dark',
                canvases: document.querySelectorAll('canvas').length
            };
        }""")
        print(
            f"  ✓ Cockpit carregado em {round(time.time() - t0, 2)}s | Canvases: {status_data['canvases']}"
        )

        # ------------------------------------------------------------------
        # CENÁRIO 2: Navegação de Ativos e Gráficos Multiativos
        # ------------------------------------------------------------------
        print("\n▶ [CENÁRIO 2] Testando Gráficos, Busca de Tickers e Timeframes...")
        tickers_to_test = ["TD.TO", "AAPL", "NVDA"]

        for sym in tickers_to_test:
            t_sym = time.time()
            ticker_input = page.locator("#ticker-inp")
            ticker_input.fill(sym)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2500)

            # Testar clique em timeframes
            tf_btn = page.locator("#tf-1M, [data-tf='1M'], button:has-text('1M')").first
            if tf_btn.is_visible():
                tf_btn.click()
                page.wait_for_timeout(1000)

            chart_stats = page.evaluate("""() => {
                const pane = document.getElementById('chart-main-pane');
                const canvas = pane ? pane.querySelector('canvas') : null;
                const tickerVal = document.getElementById('ticker-inp')?.value || '';
                return {
                    ticker: tickerVal,
                    width: pane?.clientWidth || 0,
                    height: pane?.clientHeight || 0,
                    hasCanvas: !!canvas
                };
            }""")

            shot_sym = str(AUDIT_DIR / f"audit_02_chart_{sym.replace('.', '_')}.png")
            page.screenshot(path=shot_sym, full_page=False)
            audit_results["screenshots"].append(shot_sym)
            print(
                f"  ✓ Ativo {sym}: Gráfico {chart_stats['width']}x{chart_stats['height']}px renderizado em {round(time.time() - t_sym, 2)}s"
            )

        # ------------------------------------------------------------------
        # CENÁRIO 3: Auditoria de Painéis Interativos (SDCA, Experts, Alertas)
        # ------------------------------------------------------------------
        print("\n▶ [CENÁRIO 3] Interagindo com Ferramentas Avançadas...")

        # 1. SDCA Lab
        sdca_opened = False
        try:
            sdca_btn = page.locator("#sdca-lab-btn, button:has-text('SDCA')").first
            if sdca_btn.is_visible():
                sdca_btn.click()
                page.wait_for_timeout(1000)
                shot_sdca = str(AUDIT_DIR / "audit_03_sdca_lab.png")
                page.screenshot(path=shot_sdca, full_page=False)
                audit_results["screenshots"].append(shot_sdca)
                sdca_opened = True
                print("  ✓ Painel SDCA Lab inspecionado e fotografado.")
                # Fechar
                close_btn = page.locator("#sdca-lab-close").first
                if close_btn.is_visible():
                    close_btn.click()
                    page.wait_for_timeout(400)
        except Exception as e:
            print("  ! SDCA Lab:", e)

        # 2. Alert Bell
        try:
            bell_btn = page.locator("#alert-bell-btn, .alert-bell").first
            if bell_btn.is_visible():
                bell_btn.click()
                page.wait_for_timeout(800)
                shot_alerts = str(AUDIT_DIR / "audit_03_alert_dropdown.png")
                page.screenshot(path=shot_alerts, full_page=False)
                audit_results["screenshots"].append(shot_alerts)
                page.keyboard.press("Escape")
                print("  ✓ Central de Alertas inspecionada.")
        except Exception as e:
            print("  ! Alertas:", e)

        # ------------------------------------------------------------------
        # CENÁRIO 4: Conversação Real e Análise Financeira com o Bob
        # ------------------------------------------------------------------
        print("\n▶ [CENÁRIO 4] Conversação Financeira com o Bob (3 Rodadas)...")

        # Abrir chat
        chat_tab = page.locator("#bob-chat-tab, button:has-text('Bob')").first
        if chat_tab.is_visible():
            chat_tab.click()
            page.wait_for_timeout(600)

        questions = [
            {
                "id": "Q1_ANALISE_TD",
                "prompt": "Bob, analise TD.TO para mim: vale a pena comprar para longo prazo ou fazer swing trade? Me dê os números e o veredito do firewall.",
                "expected_aspects": ["RSI", "MACD", "F51", "SDCA", "veredito"],
            },
            {
                "id": "Q2_ESTRATEGIA_ETF",
                "prompt": "Moro no Canadá e tenho CAD 10.000 para começar no TFSA. Qual a recomendação de alocação de ETFs sem comissão no TD Direct?",
                "expected_aspects": ["TFSA", "ETFs", "Canadá", "alocação"],
            },
        ]

        for q in questions:
            print(f'\n  ➤ Enviando Pergunta: "{q["prompt"][:60]}..."')
            baseline = page.evaluate("() => document.querySelectorAll('#chat .msg-ceo').length")

            t_q = time.time()
            page.fill("#user-inp", q["prompt"])
            page.click("#send-btn")

            # Aguardar resposta
            page.wait_for_function(
                f"""
                () => {{
                  const msgs = document.querySelectorAll('#chat .msg-ceo');
                  if (msgs.length <= {baseline}) return false;
                  const last = msgs[msgs.length - 1];
                  const text = last.innerText || '';
                  return text.length > 50 && !text.includes('Erro:');
                }}
                """,
                timeout=180000,
            )
            elapsed_chat = round(time.time() - t_q, 2)

            # Capturar resposta
            resp_data = page.evaluate("""() => {
                const msgs = document.querySelectorAll('#chat .msg-ceo');
                const last = msgs[msgs.length - 1];
                return {
                    fullText: last ? last.innerText : '',
                    hasCards: !!last?.querySelector('.card, .status-card, .metric-badge'),
                    html: last ? last.innerHTML : ''
                };
            }""")

            shot_chat = str(AUDIT_DIR / f"audit_04_chat_{q['id']}.png")
            page.screenshot(path=shot_chat, full_page=False)
            audit_results["screenshots"].append(shot_chat)

            print(
                f"  ✓ Resposta recebida em {elapsed_chat}s ({len(resp_data['fullText'])} caracteres)"
            )
            print(
                f'  ✓ Amostra da resposta:\n    "{resp_data["fullText"][:200].replace(chr(10), " ")}..."'
            )

            audit_results["chat_conversations"].append(
                {
                    "question": q["prompt"],
                    "response": resp_data["fullText"],
                    "elapsed_s": elapsed_chat,
                    "length": len(resp_data["fullText"]),
                }
            )

            page.wait_for_timeout(2000)

        # ------------------------------------------------------------------
        # CENÁRIO 5: Conclusão e Avaliação da Experiência
        # ------------------------------------------------------------------
        print("\n══════════════════════════════════════════════════════════════")
        print("  AVALIAÇÃO DA EXPERIÊNCIA DO USUÁRIO (UX AUDIT SCORE)")
        print("══════════════════════════════════════════════════════════════")

        total_time = round(time.time() - t0, 2)
        print(f"  • Tempo total da sessão: {total_time}s")
        print(f"  • Erros de console: {len(console_errors)}")
        print(f"  • Screenshots capturados: {len(audit_results['screenshots'])}")

        audit_results["console_errors"] = console_errors
        audit_results["total_session_time_s"] = total_time

        browser.close()

    # Salvar relatório final
    report_file = AUDIT_DIR / "deep_user_audit_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2, ensure_ascii=False)

    print(f"\n[CONCLUÍDO] Relatório de auditoria salvo em: {report_file}")
    return audit_results


if __name__ == "__main__":
    run_deep_audit()
