import sys
sys.path.insert(0, 'src')

tests = [
    ('f51', 'F51Engine'),
    ('f51', 'Graph'),
    ('f51', 'Node'),
    ('f51', 'Context'),
    ('f51', 'NodeResult'),
    ('core.pipeline', 'create_pipeline'),
    ('core.math', 'sigmoid'),
    ('core.math', 'rsi'),
    ('core.math', 'macd'),
]

for modname, sym in tests:
    try:
        mod = __import__(modname, fromlist=[sym])
        if hasattr(mod, sym):
            print(f'OK: from {modname} import {sym}')
        else:
            print(f'QUEBRADO: {modname} nao tem {sym!r}')
    except Exception as e:
        print(f'QUEBRADO: {modname} -> {e}')
