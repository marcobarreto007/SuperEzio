import asyncio
import httpx
import json
import time
import sys

QUERIES = [
    {
        "name": "1. Dica genérica (Vague Request)",
        "message": "Me dê dicas de investimento. Como faço para ganhar dinheiro rápido?",
    },
    {
        "name": "2. Market Scan (Escopo específico)",
        "message": "Procure oportunidades de investimento no setor de tecnologia no Canadá (TSX).",
    },
    {
        "name": "3. Ticker Analysis (Análise Completa)",
        "message": "Analise a empresa NVDA detalhadamente. Verifique os dados fundamentais, os especialistas e me dê um veredito se vale a pena investir.",
    },
]

async def run_investment_test():
    url = "http://127.0.0.1:8002/task/submit"
    print("=== SuperEzio End-to-End Investment Test ===")
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        for i, q in enumerate(QUERIES):
            print(f"\n[{q['name']}]")
            print(f"User: {q['message']}")
            payload = {
                "from": "user",
                "to": "orchestrator",
                "type": "TASK.SUBMIT",
                "payload": {
                    "message": q["message"],
                    "session_id": f"investment_test_{i}"
                }
            }
            
            try:
                start_time = time.time()
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code == 200:
                        chunks = []
                        print("  [STREAM] ", end="", flush=True)
                        async for line in response.aiter_lines():
                            if line:
                                try:
                                    data = json.loads(line)
                                    msg_type = data.get("type")
                                    
                                    if msg_type == "CHUNK":
                                        content = data.get("content", "")
                                        chunks.append(content)
                                        # Print the chunk to see it live
                                        print(content, end="", flush=True)
                                    elif msg_type == "PIPELINE_STEP":
                                        step = data.get('step', '')
                                        status = data.get('status', '')
                                        if status == "completed":
                                            print(f"\n  [PIPELINE] {step} completed.", flush=True)
                                            print("  [STREAM] ", end="", flush=True)
                                    elif msg_type == "ERROR":
                                        print(f"\n  [!] ERROR: {data.get('detail')}", flush=True)
                                except json.JSONDecodeError:
                                    pass
                        
                        full_answer = "".join(chunks).strip()
                        elapsed = time.time() - start_time
                        print(f"\n  [+] Time: {elapsed:.2f}s", flush=True)
                    else:
                        print(f"\n  [-] HTTP {response.status_code} Error: {response.text}", flush=True)
                        
            except Exception as e:
                print(f"\n  [!] Exception: {str(e)}", flush=True)
                
        print("\n=== Test Finished ===")

if __name__ == "__main__":
    # Ensure UTF-8 output
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(run_investment_test())
