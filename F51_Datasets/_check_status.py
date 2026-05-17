import json
import os

train = r'C:\Users\marco\Desktop\F51-Dataset-Operacao\datasets\grok_transfusion\grok_transfusion_train.jsonl'
evalf = r'C:\Users\marco\Desktop\F51-Dataset-Operacao\datasets\grok_transfusion\grok_transfusion_eval.jsonl'
chk = r'C:\Users\marco\Desktop\F51-Dataset-Operacao\datasets\grok_transfusion\checkpoint_python.json'

tn = sum(1 for _ in open(train, encoding='utf-8')) if os.path.exists(train) else 0
en = sum(1 for _ in open(evalf, encoding='utf-8')) if os.path.exists(evalf) else 0
tm = os.path.getsize(train)/(1024*1024) if os.path.exists(train) else 0
em = os.path.getsize(evalf)/(1024*1024) if os.path.exists(evalf) else 0

if os.path.exists(chk):
    c = json.load(open(chk))
    new_entries = c['total_entries']
    cats = c.get('categories', {})
    diffs = c.get('difficulties', {})
    elapsed_h = c.get('elapsed_hours', 0)
    pt = c.get('total_prompt_tokens', 0)
    ct = c.get('total_completion_tokens', 0)
    cost = (pt/1e6*1.25) + (ct/1e6*2.50)
else:
    new_entries = 0; cats = {}; diffs = {}; elapsed_h = 0; cost = 0

py_train = 0; py_eval = 0
if os.path.exists(train):
    with open(train, encoding='utf-8') as f:
        for l in f:
            try:
                e = json.loads(l)
                if e.get('domain') == 'python':
                    py_train += 1
            except: pass
if os.path.exists(evalf):
    with open(evalf, encoding='utf-8') as f:
        for l in f:
            try:
                e = json.loads(l)
                if e.get('domain') == 'python':
                    py_eval += 1
            except: pass

lens = []
if os.path.exists(train):
    with open(train, encoding='utf-8') as f:
        for l in f:
            try:
                e = json.loads(l)
                if e.get('domain') == 'python':
                    lens.append(len(e['messages'][2]['content']))
            except: pass

total = tn + en
rate = new_entries / elapsed_h if elapsed_h > 0 else 0

print('=== TRANSFUSAO PYTHON ===')
print(f'Runtime: {elapsed_h:.1f}h')
print(f'Total entries: {total:,} (train={tn:,} / eval={en:,})')
print(f'Total size: {tm+em:.1f} MB')
print(f'New Python this run: {new_entries:,}')
print(f'Python all-time: {py_train+py_eval:,}')
print(f'Rate: {rate:.0f} e/h')
print(f'Cost: ${cost:.2f}')
if lens: print(f'Avg assistant: {sum(lens)/len(lens):.0f} chars')
print()
print('--- Categories ---')
for cat, n in sorted(cats.items(), key=lambda x: -x[1])[:12]:
    pct = n / max(new_entries, 1) * 100
    print(f'  {cat:30s} {n:6,} ({pct:.1f}%)')
print('\n--- Difficulty ---')
for d, n in sorted(diffs.items(), key=lambda x: -x[1]):
    pct = n / max(new_entries, 1) * 100
    print(f'  {d}: {n:,} ({pct:.1f}%)')
