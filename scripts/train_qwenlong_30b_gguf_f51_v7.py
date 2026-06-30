"""F51 Nitro LoRA v7 — Treinamento nativo via llama-finetune-qlora.exe.

PRÉ-REQUISITOS (já cumpridos):
  ✅ llama.cpp compilado com MSVC + CUDA
  ✅ llama-finetune-qlora.exe funcional
  ✅ Modelo Bob Core local quantizado (Q4_K_M)
  ✅ Dados de treino em JSONL

USO:
  python scripts\train_bob_core_gguf_f51_v7.py
"""

import os, sys, json, subprocess
from pathlib import Path
from datetime import datetime

# === Config ===
ROOT = Path(__file__).parent.parent
LLAMA_CPP = Path(r"C:\llama.cpp")
FINETUNE_EXE = LLAMA_CPP / "build" / "bin" / "llama-finetune-qlora.exe"
GGUF_MODEL = LLAMA_CPP / "models" / "bob-core-local.gguf"
TRAIN_DATA = ROOT / "temp_gguf_workspace" / "train_finance.jsonl"
OUTPUT_DIR = ROOT / "models" / "bob_lora_bob_core_f51"
LORA_OUT = OUTPUT_DIR / "lora_f51_v7.gguf"

# === Training Hyperparams (F51 Nitro) ===
TRAINING_CONFIG = {
    "lora_rank": 64,           # 10k ex — rank alto para capturar diversidade
    "lora_alpha": 128,         # alpha = 2x rank
    "learning_rate": 3e-5,     # LR baixa com dataset grande (evita overfit)
    "epochs": 3,               # 10k ex — 3 epochs bastam
    "batch_size": 4,           # batch maior com mais dados
    "ctx_size": 3072,          # exemplos longos com multi-tool chains
    "threads": 8,              # CPU threads
    "val_split": 0.05,         # 5% validacao (500 ex)
    "freeze_layers": 0,        # train all layers
    "save_every": 1,           # checkpoint a cada epoch
}


def check_prerequisites():
    """Verifica se tudo está pronto."""
    print("=" * 60)
    print("  F51 Nitro LoRA v7 — Pre-flight Check")
    print("=" * 60)

    checks = []

    # 1. Binario
    if FINETUNE_EXE.exists():
        print(f"  ✅ llama-finetune-qlora.exe: {FINETUNE_EXE}")
        checks.append(True)
    else:
        print(f"  ❌ llama-finetune-qlora.exe NAO ENCONTRADO: {FINETUNE_EXE}")
        checks.append(False)

    # 2. Modelo
    if GGUF_MODEL.exists():
        size_gb = GGUF_MODEL.stat().st_size / (1024**3)
        print(f"  ✅ Modelo GGUF: {GGUF_MODEL.name} ({size_gb:.1f} GB)")
        checks.append(True)
    else:
        print(f"  ❌ Modelo NAO ENCONTRADO: {GGUF_MODEL}")
        print(f"     -> Rode a quantizacao primeiro: --allow-requantize Q4_K_M")
        checks.append(False)

    # 3. Dados
    if TRAIN_DATA.exists():
        with open(TRAIN_DATA, "r", encoding="utf-8") as f:
            lines = f.readlines()
        print(f"  ✅ Dados de treino: {len(lines)} exemplos ({TRAIN_DATA.stat().st_size} bytes)")
        checks.append(True)
    else:
        print(f"  ❌ Dados NAO ENCONTRADOS: {TRAIN_DATA}")
        checks.append(False)

    # 4. CUDA
    try:
        result = subprocess.run(
            [str(FINETUNE_EXE), "--version"],
            capture_output=True, text=True, timeout=10
        )
        if "CUDA" in result.stderr or "CUDA" in result.stdout:
            print("  ✅ CUDA detectado")
        else:
            print("  ⚠️ CUDA pode nao estar disponivel")
        checks.append(True)
    except Exception as e:
        print(f"  ⚠️ Nao foi possivel verificar CUDA: {e}")
        checks.append(True)  # non-fatal

    print()
    if all(checks):
        print("  🟢 TUDO PRONTO para F51 Nitro LoRA training!")
        return True
    else:
        print("  🔴 Corrija os erros acima antes de continuar.")
        return False


def train():
    """Executa o treinamento F51 Nitro LoRA."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(FINETUNE_EXE),
        "--model", str(GGUF_MODEL),
        "--train-file", str(TRAIN_DATA),
        "--lora-out", str(LORA_OUT),
        "--lora-rank", str(TRAINING_CONFIG["lora_rank"]),
        "--lora-alpha", str(TRAINING_CONFIG["lora_alpha"]),
        "--learning-rate", str(TRAINING_CONFIG["learning_rate"]),
        "--epochs", str(TRAINING_CONFIG["epochs"]),
        "--batch-size", str(TRAINING_CONFIG["batch_size"]),
        "--ctx-size", str(TRAINING_CONFIG["ctx_size"]),
        "--threads", str(TRAINING_CONFIG["threads"]),
        "--val-split", str(TRAINING_CONFIG["val_split"]),
        "--freeze-layers", str(TRAINING_CONFIG["freeze_layers"]),
        "--save-every", str(TRAINING_CONFIG["save_every"]),
    ]

    print("=" * 60)
    print("  F51 Nitro LoRA v7 — Training")
    print("=" * 60)
    print(f"  Modelo:    {GGUF_MODEL.name}")
    print(f"  LoRA rank: {TRAINING_CONFIG['lora_rank']}, alpha: {TRAINING_CONFIG['lora_alpha']}")
    print(f"  LR:        {TRAINING_CONFIG['learning_rate']}")
    print(f"  Epochs:    {TRAINING_CONFIG['epochs']}")
    print(f"  Batch:     {TRAINING_CONFIG['batch_size']}")
    print(f"  Saida:     {LORA_OUT}")
    print()
    print(f"  Comando: {' '.join(cmd)}")
    print()

    start = datetime.now()
    print(f"  🚀 Iniciando treino as {start.strftime('%H:%M:%S')}...")
    print()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(LLAMA_CPP / "build" / "bin"),
            check=False,
        )
        elapsed = datetime.now() - start

        if result.returncode == 0 and LORA_OUT.exists():
            size_mb = LORA_OUT.stat().st_size / (1024**2)
            print()
            print("=" * 60)
            print(f"  ✅ F51 NITRO LORA TREINADA COM SUCESSO!")
            print(f"  Tempo:    {elapsed}")
            print(f"  Tamanho:  {size_mb:.1f} MB")
            print(f"  Arquivo:  {LORA_OUT}")
            print("=" * 60)
            print()
            print("  Para usar com llama.cpp:")
            print(f'  llama-cli.exe -m "{GGUF_MODEL}" --lora "{LORA_OUT}" -p "Analise PETR4" -t 16')
            return True
        else:
            print()
            print(f"  ❌ Treino falhou (exit code {result.returncode})")
            if result.stdout:
                print(f"  stdout: {result.stdout[-500:]}")
            if result.stderr:
                print(f"  stderr: {result.stderr[-500:]}")
            return False

    except KeyboardInterrupt:
        print("\n  ⚠️ Treino interrompido pelo usuario")
        return False
    except Exception as e:
        print(f"\n  ❌ Erro: {e}")
        return False


def main():
    if not check_prerequisites():
        sys.exit(1)

    input("\n  Pressione ENTER para iniciar o treino F51 Nitro LoRA...")

    success = train()

    # Atualiza checkpoint
    checkpoint_path = ROOT / ".f51" / "checkpoints" / "train_qwenlong_checkpoint.json"
    checkpoint = {
        "timestamp": datetime.now().isoformat(),
        "task": "train_bob_core_gguf_f51_v7",
        "status": "completed" if success else "failed",
        "method": "llama-finetune-qlora (native GGUF QLoRA)",
        "config": TRAINING_CONFIG,
        "artifacts": {
            "gguf_model": str(GGUF_MODEL),
            "train_data": str(TRAIN_DATA),
            "lora_output": str(LORA_OUT),
        },
    }

    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)

    print(f"\n  Checkpoint salvo: {checkpoint_path}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
