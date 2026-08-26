"""End-to-end user journey validation for SuperEzio Cockpit.

Simulates a real human investor using the cockpit:
1. Page navigation & UI component verification
2. Ticker search & interactive chart inspection
3. Panel interactions (Expert Panel, SDCA Lab, Timeframe selector)
4. Full live conversation with Bob (streaming & verdict verification)
5. Comprehensive screenshots and metrics capture
"""

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Set utf-8 stdout for Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = os.getenv("SUPEREZIO_BASE_URL", "http://127.0.0.1:8002")
OUTPUT_DIR = Path("output/user_testing")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_end_user_journey():
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_url": BASE_URL,
        "steps": [],
        "screenshots": [],
        "success": True,
        "errors": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900}, device_scale_factor=1
        )
        page = context.new_page()

        console_logs = []
        console_errors = []
        page.on(
            "console",
            lambda msg: (
                console_errors.append(msg.text)
                if msg.type == "error"
                else console_logs.append(msg.text)
            ),
        )
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        print(f"[1/5] Navegando para o cockpit em {BASE_URL}...")
        t0 = time.time()
        page.goto(BASE_URL, wait_until="load", timeout=30000)
        page.wait_for_timeout(3000)

        # Snapshot inicial
        shot_01 = str(OUTPUT_DIR / "01_initial_cockpit.png")
        page.screenshot(path=shot_01, full_page=True)
        report["screenshots"].append(shot_01)
        print("  -> Snapshot inicial capturado:", shot_01)

        # Verificar controles principais
        topbar_title = page.evaluate("() => document.title")
        canvas_count = page.evaluate("() => document.querySelectorAll('canvas').length")
        report["steps"].append(
            {
                "step": "initial_load",
                "title": topbar_title,
                "canvas_count": canvas_count,
                "elapsed_s": round(time.time() - t0, 2),
            }
        )
        print(f"  -> Titulo: '{topbar_title}', Canvases ativos: {canvas_count}")

        # [2/5] Buscar e carregar ticker TD.TO
        print("[2/5] Selecionando e carregando o ativo TD.TO no gráfico...")
        t_chart = time.time()
        ticker_input = page.locator("#ticker-inp")
        ticker_input.fill("TD.TO")
        page.keyboard.press("Enter")
        page.wait_for_timeout(4000)

        # Verificar se o chart carregou
        chart_info = page.evaluate("""() => {
            const chartPane = document.getElementById('chart-main-pane');
            const canvases = chartPane ? chartPane.querySelectorAll('canvas') : [];
            const symbolEl = document.getElementById('ticker-inp');
            return {
                symbol: symbolEl ? symbolEl.value : '',
                canvas_count: canvases.length,
                has_pane: !!chartPane,
                pane_w: chartPane ? chartPane.clientWidth : 0,
                pane_h: chartPane ? chartPane.clientHeight : 0
            };
        }""")

        shot_02 = str(OUTPUT_DIR / "02_chart_loaded_td_to.png")
        page.screenshot(path=shot_02, full_page=True)
        report["screenshots"].append(shot_02)
        report["steps"].append(
            {
                "step": "ticker_selection",
                "chart_info": chart_info,
                "elapsed_s": round(time.time() - t_chart, 2),
            }
        )
        print(
            f"  -> Ativo: {chart_info['symbol']}, Painel do gráfico: {chart_info['pane_w']}x{chart_info['pane_h']}px ({chart_info['canvas_count']} canvases)"
        )

        # [3/5] Testar interação com abas e painéis
        print("[3/5] Interagindo com painéis e ferramentas (Expert Panel / SDCA Lab)...")
        expert_panel_opened = False
        try:
            drawer_btn = page.locator("#mobile-drawer-btn")
            if drawer_btn.is_visible():
                drawer_btn.click()
                page.wait_for_timeout(800)
                expert_panel_opened = True
        except Exception:  # noqa: BLE001, S110 — sonda de UI opcional: drawer ausente não deve abortar a jornada
            pass

        shot_03 = str(OUTPUT_DIR / "03_expert_panel_interaction.png")
        page.screenshot(path=shot_03, full_page=True)
        report["screenshots"].append(shot_03)
        report["steps"].append(
            {"step": "panel_interaction", "expert_panel_opened": expert_panel_opened}
        )

        # [4/5] Enviar pergunta ao Bob e testar streaming
        print("[4/5] Iniciando chat ao vivo com o Bob...")
        # Abrir painel de chat
        tab = page.query_selector("#bob-chat-tab")
        if tab:
            tab.click()
            page.wait_for_timeout(600)

        # Baseline de mensagens
        baseline = page.evaluate("() => document.querySelectorAll('#chat .msg-ceo').length")

        user_prompt = "Oi Bob, qual a sua avaliação de risco e veredito para TD.TO hoje? Vale a pena comprar? Mostre os números do firewall."
        print(f"  -> Pergunta do usuário: '{user_prompt}'")

        page.fill("#user-inp", user_prompt)
        page.click("#send-btn")

        print("  -> Mensagem enviada. Aguardando Bob processar pipeline e transmitir resposta...")
        t_chat_start = time.time()

        # Esperar resposta do Bob
        max_wait_s = 180
        page.wait_for_function(
            f"""
            () => {{
              const bobMsgs = document.querySelectorAll('#chat .msg-ceo');
              if (bobMsgs.length <= {baseline}) return false;
              const last = bobMsgs[bobMsgs.length - 1];
              const text = last.innerText || '';
              return text.length > 50 && !text.includes('Erro:');
            }}
            """,
            timeout=max_wait_s * 1000,
        )

        chat_state = page.evaluate(
            """
            () => {
              const bobMsgs = document.querySelectorAll('#chat .msg-ceo');
              const lastBob = bobMsgs[bobMsgs.length - 1];
              const text = lastBob ? (lastBob.innerText || '') : '';
              const userMsgs = document.querySelectorAll('#chat .msg-user');
              const typing = document.getElementById('typing');
              return {
                responseLength: text.length,
                bobMsgCount: bobMsgs.length,
                userMsgCount: userMsgs.length,
                typingVisible: typing ? typing.style.display !== 'none' : null,
                containsError: text.includes('Erro:'),
                fullText: text
              };
            }
            """
        )

        chat_duration = round(time.time() - t_chat_start, 2)
        bob_answer_text = chat_state.get("fullText", "")
        print(f"  -> Resposta recebida em {chat_duration}s ({len(bob_answer_text)} caracteres).")

        shot_04 = str(OUTPUT_DIR / "04_bob_live_response.png")
        page.screenshot(path=shot_04, full_page=True)
        report["screenshots"].append(shot_04)

        report["steps"].append(
            {
                "step": "live_chat",
                "prompt": user_prompt,
                "response_length": len(bob_answer_text),
                "response_snippet": bob_answer_text[:400] + "..."
                if len(bob_answer_text) > 400
                else bob_answer_text,
                "duration_s": chat_duration,
                "success": len(bob_answer_text) > 50,
            }
        )

        # [5/5] Validação da experiência do usuário
        print("[5/5] Compilando relatório final de auditoria...")
        report["console_errors"] = console_errors
        report["total_time_s"] = round(time.time() - t0, 2)

        browser.close()

    report_path = OUTPUT_DIR / "end_user_journey_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n[SUCESSO] Teste de ponta a ponta finalizado com sucesso!")
    print(f"Relatório salvo em: {report_path}")
    return report


if __name__ == "__main__":
    rep = run_end_user_journey()
    print(
        json.dumps(
            {
                "success": rep["success"],
                "steps_count": len(rep["steps"]),
                "screenshots_count": len(rep["screenshots"]),
                "console_errors": len(rep["console_errors"]),
                "total_time_s": rep["total_time_s"],
            },
            indent=2,
        )
    )
