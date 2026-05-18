"""
SuperEzio - Custom Tools Registry.

Ferramentas customizadas para o agente.

Uso:
    from tools import register_custom_tools
    registry = ...  # objeto com método register(...)
    register_custom_tools(registry)
"""


def register_custom_tools(registry):
    """Registra ferramentas customizadas no registry."""

    def greet(name: str = "World") -> str:
        """Saúda alguém."""
        return f"Olá, {name}!"

    registry.register(
        name="greet",
        func=greet,
        desc="Saúda uma pessoa pelo nome",
        schema={"name": "string, nome da pessoa"},
    )

    def calculate(expression: str) -> str:
        """Calcula uma expressão matemática segura via AST."""
        try:
            import ast
            import operator

            allowed_ops = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.FloorDiv: operator.floordiv,
                ast.Mod: operator.mod,
                ast.Pow: operator.pow,
                ast.USub: operator.neg,
                ast.UAdd: operator.pos,
            }

            def eval_node(node):
                if isinstance(node, ast.Expression):
                    return eval_node(node.body)
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                    return node.value
                if isinstance(node, ast.BinOp) and type(node.op) in allowed_ops:
                    left = eval_node(node.left)
                    right = eval_node(node.right)
                    if isinstance(node.op, ast.Pow) and abs(right) > 12:
                        raise ValueError("expoente muito alto")
                    return allowed_ops[type(node.op)](left, right)
                if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_ops:
                    return allowed_ops[type(node.op)](eval_node(node.operand))
                raise ValueError("expressao nao permitida")

            tree = ast.parse(expression, mode="eval")
            result = eval_node(tree)
            return f"Resultado: {result}"
        except Exception as e:
            return f"Erro: {e}"

    registry.register(
        name="calculate",
        func=calculate,
        desc="Calcula expressão matemática simples",
        schema={"expression": "string, expressão como '2+2' ou '10*5'"},
    )


def create_web_search_tool():
    """Cria ferramenta de busca na web via DuckDuckGo."""
    try:
        from ddgs import DDGS

        if DDGS is None:
            raise ImportError

        def search_web(query: str, max_results: int = 5) -> str:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return "Nenhum resultado encontrado."
            output = []
            for r in results:
                output.append(f"• {r['title']}\n  {r['href']}\n  {r['body'][:100]}...")
            return "\n\n".join(output)

        return search_web
    except ImportError:
        return None


def create_code_executor_tool():
    """Cria ferramenta de execução de código Python (sandboxed).

    Sandbox em-processo de Python tem histórico de bypasses (acesso a
    `__class__`/`__bases__`/subclasses via construções dinâmicas, mesmo com
    AST validator). Para clientes institucionais, esta ferramenta fica
    DESABILITADA por default. Habilitar apenas em ambiente isolado via:

        SUPEREZIO_ENABLE_PYTHON_EXEC=true

    Roadmap: substituir por subprocess isolado com seccomp/firejail antes de
    reabilitar por default.
    """
    import os as _os

    _enabled = _os.getenv("SUPEREZIO_ENABLE_PYTHON_EXEC", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not _enabled:

        def execute_python_disabled(code: str) -> str:
            return (
                "Erro: a ferramenta python_exec está desabilitada por padrão "
                "nesta instalação. Para habilitar, defina "
                "SUPEREZIO_ENABLE_PYTHON_EXEC=true (apenas em ambiente isolado)."
            )

        return execute_python_disabled

    def _validate_ast(code: str) -> str | None:
        import ast

        FORBIDDEN_NAMES = {
            "eval",
            "exec",
            "compile",
            "open",
            "input",
            "__import__",
            "globals",
            "locals",
            "vars",
            "dir",
            "getattr",
            "setattr",
            "delattr",
            "hasattr",
            "os",
            "sys",
            "subprocess",
            "pathlib",
            "socket",
            "requests",
            "httpx",
            "urllib",
            "ctypes",
            "shutil",
            "pickle",
            "marshal",
            "builtins",
        }

        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as e:
            return f"Syntax error: {e}"

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                return "Error: imports are not allowed in sandbox"
            if isinstance(node, ast.Attribute):
                if isinstance(node.attr, str) and node.attr.startswith("__"):
                    return f"Error: access to dunder attribute '{node.attr}' is blocked"
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
                    return f"Error: calling '{node.func.id}' is forbidden in sandbox"
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.attr, str):
                    if node.func.attr in FORBIDDEN_NAMES:
                        return f"Error: calling '{node.func.attr}' is forbidden in sandbox"
        return None

    def execute_python(code: str) -> str:
        import io
        from contextlib import redirect_stdout, redirect_stderr

        err = _validate_ast(code)
        if err:
            return err

        safe_builtins = {
            "print": print,
            "len": len,
            "range": range,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sorted": sorted,
            "reversed": reversed,
            "isinstance": isinstance,
            "type": type,
            "True": True,
            "False": False,
            "None": None,
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "ZeroDivisionError": ZeroDivisionError,
            "any": any,
            "all": all,
            "iter": iter,
            "next": next,
        }

        stdout = io.StringIO()
        stderr = io.StringIO()

        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exec(code, {"__builtins__": safe_builtins})
            output = stdout.getvalue()
            error = stderr.getvalue()
            if error:
                return f"Stderr:\n{error}\n\nStdout:\n{output}"
            return output if output else "(código executado sem output)"
        except Exception as e:
            return f"Erro: {e}"

    return execute_python
