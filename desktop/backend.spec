# Build from repository root: python -m PyInstaller desktop/backend.spec --noconfirm
from pathlib import Path

root = Path(SPECPATH).parent
src = root / "src"
# Enumerate our modules without importing them (imports can initialize services).
hidden = []
for path in src.rglob("*.py"):
    parts = list(path.relative_to(src).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    if parts:
        hidden.append(".".join(parts))
hidden += ["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
           "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
           "passlib.handlers.bcrypt", "scripts.mangala_daily_scan"]

a = Analysis(
    [str(root / "scripts" / "desktop_backend.py")],
    pathex=[str(src), str(root)],
    binaries=[],
    datas=[(str(root / name), name) for name in ("frontend", "templates")]
        + [(str(p), "config") for p in (root / "config").glob("*")
           if p.is_file() and p.name != "mission_context.json"]
        + [(str(root / "desktop" / "defaults" / "mission_context.json"), "config")],
    hiddenimports=hidden,
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["torch", "transformers", "sentence_transformers", "peft", "faiss",
              "llama_cpp", "tensorflow", "keras", "jax", "PyQt5", "PyQt6",
              "PySide6", "tkinter", "pytest", "playwright", "IPython",
              "notebook", "jupyter", "matplotlib", "numba"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SuperEzioBackend",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=True, icon=str(root / "superezio.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name="SuperEzioBackend")
