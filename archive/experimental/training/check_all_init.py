import ast, os

total_all = 0
broken_all = 0
files_with_broken = []

for root, dirs, files in os.walk('src'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f != '__init__.py': continue
        path = os.path.join(root, f)
        try:
            with open(path, encoding='utf-8') as fh:
                content = fh.read()
                tree = ast.parse(content)
        except:
            continue

        has_all = False
        all_ok = True
        missing = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '__all__':
                        has_all = True
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant):
                                    name = elt.value
                                    found = False
                                    # Check function/class defs
                                    for n in ast.iter_child_nodes(tree):
                                        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name:
                                            found = True; break
                                        if isinstance(n, ast.Assign):
                                            for t in n.targets:
                                                if isinstance(t, ast.Name) and t.id == name:
                                                    found = True; break
                                        if isinstance(n, ast.Import):
                                            for alias in n.names:
                                                imported_name = alias.asname or alias.name
                                                if imported_name == name or imported_name.split('.')[0] == name:
                                                    found = True; break
                                        if isinstance(n, ast.ImportFrom):
                                            for alias in n.names:
                                                imported_name = alias.asname or alias.name
                                                if imported_name == name:
                                                    found = True; break
                                    if not found:
                                        all_ok = False
                                        missing.append(name)

        if has_all:
            total_all += 1
            if not all_ok:
                broken_all += 1
                files_with_broken.append((path, missing))

print(f'__init__.py com __all__: {total_all}')
print(f'__init__.py com __all__ quebrado (simbolos nao encontrados no AST): {broken_all}')
print()

# Check if symbols are actually importable despite AST check
# Many __all__ symbols come from re-exports (imports from submodules)
import sys
sys.path.insert(0, 'src')

for path, missing in files_with_broken:
    modpath = path.replace('\\', '/').replace('src/', '').replace('/__init__.py', '').replace('/', '.')
    print(f'--- {modpath} ---')
    for sym in missing[:8]:
        try:
            mod = __import__(modpath, fromlist=[sym])
            if hasattr(mod, sym):
                print(f'  OK (importavel): {sym}')
            else:
                print(f'  QUEBRADO (nao importavel): {sym}')
        except Exception as e:
            print(f'  QUEBRADO (erro): {sym} -> {e}')
    if len(missing) > 8:
        print(f'  ... +{len(missing)-8} more')
