import asyncio
import httpx
import json
import time

QUESTIONS = [
    "What is heavier: 1 kg of feathers or 1 kg of steel?",
    "If you drop a yellow hat in the Red Sea, what does it become?",
    "A plane crashes on the border of the US and Canada. Where do they bury the survivors?",
    "How many months have 28 days?",
    "I have branches, but no fruit, trunk or leaves. What am I?",
    "If there are 3 apples and you take away 2, how many apples do you have?",
    "Before Mount Everest was discovered, what was the highest mountain in the world?",
    "What goes up but never comes down?",
    "Some months have 31 days. How many have 28?",
    "Which is correct: 'The yolk of the egg is white' or 'The yolk of the egg are white'?",
    "If you're running in a race and you pass the person in second place, what place are you in?",
    "How many animals of each species did Moses take on the Ark?",
    "A rooster lays an egg on the roof of a barn. Which way does it roll?",
    "How much dirt is in a hole that is 2 meters wide, 3 meters long, and 4 meters deep?",
    "If it takes 8 men 10 hours to build a wall, how long would it take 4 men to build it?",
    "Is it legal for a man in California to marry his widow's sister?",
    "What has a head and a tail but no body?",
    "Mary's father has five daughters: 1. Nana, 2. Nene, 3. Nini, 4. Nono. What is the name of the fifth daughter?",
    "Imagine you are in a dark room. How do you get out?",
    "What gets wetter as it dries?"
]

async def run_tests():
    url = "http://127.0.0.1:8002/task/submit"
    
    print(f"=== Running 20 Trick Questions Test ===")
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        success_count = 0
        for i, q in enumerate(QUESTIONS):
            print(f"\n[Q{i+1}/20] {q}")
            payload = {
                "from": "user",
                "to": "orchestrator",
                "type": "TASK.SUBMIT",
                "payload": {
                    "message": f"Answer concisely: {q}",
                    "session_id": "quality_gate_trick_test"
                }
            }
            try:
                start_time = time.time()
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code == 200:
                        chunks = []
                        async for line in response.aiter_lines():
                            if line:
                                try:
                                    data = json.loads(line)
                                    if data.get("type") == "CHUNK":
                                        chunks.append(data.get("content", ""))
                                    elif data.get("type") == "ERROR":
                                        print(f"  [!] ERROR event: {data.get('detail')}", flush=True)
                                except json.JSONDecodeError:
                                    pass
                        
                        full_answer = "".join(chunks).strip()
                        elapsed = time.time() - start_time
                        print(f"  [+] Response ({elapsed:.2f}s): {full_answer[:200]}...", flush=True)
                        if full_answer and "MODEL_MISSING" not in full_answer:
                            success_count += 1
                        else:
                            print(f"  [-] Failed: Empty or Missing Model response", flush=True)
                    else:
                        print(f"  [-] Failed with status {response.status_code}", flush=True)
                        
            except Exception as e:
                print(f"  [!] Exception: {str(e)}", flush=True)
                
        print(f"\n=== Test Completed: {success_count}/20 passed ===", flush=True)

if __name__ == "__main__":
    asyncio.run(run_tests())
