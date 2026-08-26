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
        """Calcula expressão matemática ou financeira com segurança via AST.

        Suporta operações aritméticas básicas e funções financeiras:
          sharpe(ret, vol)     -> ret/vol (anualizado)
          kelly(win_p, wl_r)   -> fração de Kelly
          position(capital, risk_pct, stop_pct) -> tamanho da posição
          var_95(returns_csv)  -> VaR 95% de uma lista de retornos
          max_dd(equity_csv)   -> máximo drawdown de uma curva
          vol(returns_csv)     -> volatilidade anualizada
        """
        import ast
        import math
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
        safe_funcs = {
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sqrt": math.sqrt,
            "log": math.log,
            "exp": math.exp,
        }

        def _parse_csv(s: str) -> list[float]:
            return [float(x.strip()) for x in s.split(",") if x.strip()]

        def _sharpe(ret: float, vol: float) -> float:
            return ret / vol if vol != 0 else 0.0

        def _kelly(win_p: float, wl_r: float) -> float:
            if wl_r <= 0:
                return 0.0
            f = (win_p * wl_r - (1 - win_p)) / wl_r
            return max(0.0, min(1.0, f))

        def _position(capital: float, risk_pct: float, stop_pct: float) -> float:
            risk_amount = capital * (risk_pct / 100)
            return risk_amount / (stop_pct / 100) if stop_pct > 0 else 0.0

        def _var95(returns_csv: str) -> float:
            r = sorted(_parse_csv(returns_csv))
            idx = int(0.05 * len(r))
            return r[max(0, idx)]

        def _maxdd(equity_csv: str) -> float:
            eq = _parse_csv(equity_csv)
            peak = eq[0]
            max_dd = 0.0
            for v in eq:
                peak = max(peak, v)
                dd = (v - peak) / peak if peak != 0 else 0
                max_dd = min(max_dd, dd)
            return max_dd

        def _vol(returns_csv: str) -> float:
            r = _parse_csv(returns_csv)
            if len(r) < 2:
                return 0.0
            mean = sum(r) / len(r)
            var = sum((x - mean) ** 2 for x in r) / (len(r) - 1)
            return math.sqrt(var) * math.sqrt(252)

        finance_funcs = {
            "sharpe": _sharpe,
            "kelly": _kelly,
            "position": _position,
            "var_95": _var95,
            "max_dd": _maxdd,
            "vol": _vol,
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
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                name = node.func.id
                args = [eval_node(a) for a in node.args]
                if name in safe_funcs:
                    return safe_funcs[name](*args)
                if name in finance_funcs:
                    return finance_funcs[name](*args)
                raise ValueError(f"funcao nao permitida: {name}")
            raise ValueError("expressao nao permitida")

        try:
            tree = ast.parse(expression, mode="eval")
            result = eval_node(tree)
            if isinstance(result, float):
                result = round(result, 6)
            return f"Resultado: {result}"
        except Exception as e:
            return f"Erro: {e}"

    registry.register(
        name="calculate",
        func=calculate,
        desc="Calcula expressão matemática/financeira. Suporta: + - * / ** sqrt log exp abs round min max, e funções financeiras: sharpe(ret,vol) kelly(win_p,wl_r) position(capital,risk%,stop%) var_95('r1,r2,...') max_dd('e1,e2,...') vol('r1,r2,...')",
        schema={
            "expression": "string, expressão como 'kelly(0.6, 2.0)' ou 'position(10000, 2, 15)' ou 'sharpe(0.12, 0.25)'"
        },
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

    Decisao de auditoria (docs/audit/phase7_idempotency_security_repro.md,
    achado 7.2): o exec() em `execute_python` (abaixo) foi revisado e
    mantido, nao removido, porque ja possui defesa em profundidade:
    (1) desabilitado por default via env var opt-in; (2) AST validator
    bloqueia import/from-import, acesso a qualquer atributo dunder e uma
    blocklist de builtins/metodos perigosos (eval, exec, open, os, sys,
    subprocess, getattr, etc); (3) __builtins__ restrito passado ao exec()
    (sem __import__, open, getattr...). Provado com testes em
    tests/test_custom_tools.py::test_execute_python_blocks_known_sandbox_escapes
    contra os bypasses classicos (walk de __class__.__bases__.__subclasses__,
    __globals__ de closures, __import__, eval/exec/open/getattr diretos).
    Se algum desses testes falhar apos uma mudanca aqui, a mudanca introduziu
    uma regressao de sandbox e nao deve ser commitada.
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
        from contextlib import redirect_stderr, redirect_stdout

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
            # "type": type,  # REMOVED — sandbox escape vector via type.__subclasses__()
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
                exec(code, {"__builtins__": safe_builtins})  # nosec: B102 — sandboxed with restricted builtins
            output = stdout.getvalue()
            error = stderr.getvalue()
            if error:
                return f"Stderr:\n{error}\n\nStdout:\n{output}"
            return output if output else "(código executado sem output)"
        except Exception as e:
            return f"Erro: {e}"

    return execute_python
