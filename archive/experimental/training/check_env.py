import os
import re

read_vars = set()
for root, dirs, files in os.walk('src'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if not f.endswith('.py'): continue
        path = os.path.join(root, f)
        try:
            with open(path, encoding='utf-8', errors='ignore') as fh:
                content = fh.read()
        except:
            continue
        for m in re.finditer(r'os\.getenv\(\s*[\'"]([^\'"]+)[\'"]\s*\)', content):
            read_vars.add(m.group(1))
        for m in re.finditer(r'os\.environ(?:\.get)?\[\s*[\'"]([^\'"]+)[\'"]\s*\]', content):
            read_vars.add(m.group(1))

print('Env vars lidas pelo codigo:')
for v in sorted(read_vars):
    print(f'  {v}')

env_example = '.env.example'
if os.path.exists(env_example):
    with open(env_example, encoding='utf-8') as fh:
        doc_content = fh.read()
    doc_vars = set(re.findall(r'^([A-Z_][A-Z0-9_]*)=', doc_content, re.MULTILINE))
    missing_doc = read_vars - doc_vars
    if missing_doc:
        print(f'\nVARs lidas mas NAO documentadas: {missing_doc}')
    else:
        print('\nOK - todas vars documentadas')
    unused_doc = doc_vars - read_vars
    if unused_doc:
        print(f'VARs documentadas mas NAO lidas: {unused_doc}')
else:
    print('\n.env.example nao encontrado')
