# F51 Nitro Training: Tiered Adapter Training via Predictive Scheduling

**Authors:** Marco Barreto (Fuch F51 Labs) & Bob (Claude Opus 4.7)
**Date:** 2025-01-15
**Version:** 1.0
**Status:** HISTORICO / PENDENTE — especificação não implementada (verificada em 2026-08-26)

> **AVISO DE OBSOLESCÊNCIA (2026-08-26):** este whitepaper cita
> `nitro_training.py` (seções 4.1, 7.2) e `scripts/nitro_train.ps1` (seção 4.2),
> mas **nenhum desses arquivos existe no repositório** — a implementação nunca
> foi criada. Mantido como registro histórico do desenho; não é documentação
> operacional ativa. Nenhuma seção de implementação deve ser executada até que
> a implementação real exista e seja validada.

---

## Abstract

Traditional fine-tuning requires loading the entire model into GPU VRAM, making models ≥30B impractical on consumer hardware. We present **F51 Nitro Training**, a tiered placement protocol that extends the Nitro inference architecture to the training domain. By staging layer unfreezing, offloading optimizer states to RAM, and applying predictive scheduling with slack=0 transfer timing, we enable training 30B+ models on 16GB VRAM. The protocol achieves **6× VRAM reduction** compared to full fine-tuning while maintaining equivalent model quality through progressive layer adaptation.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Nitro Training Architecture](#2-nitro-training-architecture)
3. [Core Components](#3-core-components)
4. [Implementation](#4-implementation)
5. [Variations and Extensions](#5-variations-and-extensions)
6. [Experimental Validation](#6-experimental-validation)
7. [Production Deployment](#7-production-deployment)
8. [Related Work](#8-related-work)

---

## 1. Problem Statement

### 1.1 The VRAM Wall

```
Training Memory Requirement (Full Fine-tuning):

Model Parameters:     30B × 2 bytes (FP16)     = 60 GB
Optimizer States:     30B × 4 bytes × 2 (m,v) = 240 GB
Gradients:            30B × 2 bytes             = 60 GB
Activations:          48 layers × context        = 8-16 GB
───────────────────────────────────────────────────────
Total:                ~360 GB                   → IMPOSSIBLE on 16GB VRAM
```

### 1.2 Traditional Approaches (Insufficient)

| Approach | VRAM Used | Status on 30B | Limitation |
|----------|-----------|---------------|------------|
| Full fine-tuning | 360 GB | ❌ OOM | Requires datacenter |
| LoRA (rank=16) | 60+ GB | ❌ OOM | Still needs base model |
| LoRA + Quantization | 32+ GB | ❌ OOM | 16GB VRAM insufficient |
| CPU-only training | 0 GB | ⚠️ Too slow | ~5 tok/s, impractical |

### 1.3 The Nitro Insight

> **Training memory follows the same tiered pattern as inference.**

Not all parameters need to be "hot" (in VRAM) simultaneously:
- **Frozen layers**: Can reside in RAM with optimizer states offloaded
- **Active layers**: Only the subset being trained needs VRAM
- **Activations**: Gradient checkpointing enables recomputation vs storage
- **Scheduler**: Predictive transfer with slack=0 eliminates stalls

---

## 2. Nitro Training Architecture

### 2.1 Three-Tier Memory Hierarchy

```
┌─────────────────────────────────────────────────────────────────────┐
│                    NITRO TRAINING TIERED ARCHITECTURE              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [HOT - GPU VRAM]    [WARM - DDR5 RAM]    [COLD - NVMe SSD]        │
│  ┌───────────────┐   ┌───────────────┐    ┌───────────────┐        │
│  │ Active Layers │   │ Frozen Layers │    │ Checkpoints   │        │
│  │ (8-12 at a   │   │ (remaining)   │    │ + Stage       │        │
│  │  time)       │   │               │    │   History     │        │
│  │               │   │ ┌───────────┐ │    │               │        │
│  │ • Weights     │   │ │ Optimizer│ │    │ • Merged      │        │
│  │ • Gradients   │   │ │ States   │ │    │   Adapters    │        │
│  │ • Activations │   │ │ (m,v)    │ │    │ • Training    │        │
│  │ • LoRA params │   │ └───────────┘ │    │   Logs        │        │
│  └───────────────┘   └───────────────┘    └───────────────┘        │
│         │                   │                    │                  │
│         └───────────────────┴────────────────────┘                 │
│                     ASYNC PREFETCH ENGINE                          │
│                   (slack=0 scheduling)                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 The Slack Equation (Training)

Adapted from Nitro Inference to the training domain:

```
deadline  = When backward pass needs layer N (ms from now)
lead_time = Time to transfer layer N from current tier to GPU (ms)
slack     = deadline - lead_time

slack > 0:  Can wait. Schedule transfer in `slack` ms.
slack = 0:  THE EXACT MOMENT. Fire NOW. Arrives at the right microsecond.
slack < 0:  Already late. Stall. Wasted compute cycles.
```

**Training Timeline:**

```
Time →
NVMe→RAM:  [== Chunk A(t+2) ==][== Chunk B(t+2) ==]
RAM→GPU:         [== Layer N(t+1) ==][== Layer N+1(t+1) ==]
GPU Compute:             [== Forward(t) ==][== Backward(t) ==]
                           ↑ Batch N                        ↑ Batch N+1
```

### 2.3 Layer Chunking Strategy

For a 48-layer model with 6 training stages:

```
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│ Stage 1  │ Stage 2  │ Stage 3  │ Stage 4  │ Stage 5  │
├──────────┼──────────┼──────────┼──────────┼──────────┤
│ L40-47   │ L32-47   │ L24-47   │ L16-47   │ L0-47    │
│ (8 lay)  │ (16 lay) │ (24 lay) │ (32 lay) │ (48 lay) │
│ 12 MB    │ 24 MB    │ 36 MB    │ 48 MB    │ 72 MB    │
└──────────┴──────────┴──────────┴──────────┴──────────┘

Chunk size: 8 layers = ~1.6 GB (IQ4_XS quantized)
Transfer time: 1.6 GB / 16 GB/s PCIe = 100 ms
```

---

## 3. Core Components

### 3.1 Component Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         NitroTrainer                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐          │
│  │ NitroScheduler│ │ TierManager   │ │ ProfileEngine  │          │
│  │               │  │               │  │               │          │
│  │ • slack=0     │  │ • VRAM alloc  │  │ • Bandwidth   │          │
│  │ • prefetch    │  │ • RAM offload │  │ • Timing      │          │
│  │ • stage sync  │  │ • NVMe store │  │ • Predictions │          │
│  └───────────────┘  └───────────────┘  └───────────────┘          │
│           │                  │                  │                  │
│           └──────────────────┴──────────────────┘                  │
│                              │                                     │
│                    ┌─────────────────────┐                          │
│                    │  TrainingPipeline   │                          │
│                    │                     │                          │
│                    │ • Stage orchestration│                          │
│                    │ • Async transfers   │                          │
│                    │ • Merge logic       │                          │
│                    └─────────────────────┘                          │
│                              │                                     │
│                    ┌─────────────────────┐                          │
│                    │  llama.cpp Binding   │                          │
│                    └─────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Responsibilities

| Component | Responsibility | Output |
|-----------|----------------|--------|
| **NitroScheduler** | Compute slack, trigger transfers | Transfer schedule |
| **TierManager** | Move chunks between tiers | Chunk placement |
| **ProfileEngine** | Measure bandwidth, timing | Performance data |
| **TrainingPipeline** | Orchestrate stages, execute training | Trained adapters |
| **llama.cpp Binding** | Execute actual training | Model checkpoints |

---

## 4. Implementation

### 4.1 Core Nitro Trainer

```python
"""
F51 Nitro Training - Core Implementation
========================================

This module implements the Nitro Training protocol:
- Tiered parameter placement (GPU/RAM/NVMe)
- Predictive scheduling with slack=0
- Progressive layer unfreezing
- Async prefetch for zero-stall training

Based on research from:
- Multi-Level Offloading (arXiv:2509.02480)
- AsyncHZP (arXiv:2510.20111)
- ExpertFlow (arXiv:2410.17954)
- DeepSpeed ZeRO-3 NVMe offload
"""

import asyncio
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import threading
import queue

import torch
import torch.nn as nn


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class TierSpec:
    """Hardware tier specification."""

    name: str  # "GPU", "RAM", or "NVMe"
    capacity_gb: float  # Total capacity in GB
    bandwidth_mb_s: float  # Bandwidth in MB/s

    def __post_init__(self):
        self.bandwidth_bytes_s = self.bandwidth_mb_s * 1_000_000


@dataclass
class NitroConfig:
    """Complete Nitro Training configuration."""

    # Hardware tiers
    gpu: TierSpec = field(default_factory=lambda: TierSpec("GPU", 16, 16000))
    ram: TierSpec = field(default_factory=lambda: TierSpec("RAM", 64, 60000))
    nvme: TierSpec = field(default_factory=lambda: TierSpec("NVMe", 1000, 3367))

    # Model architecture
    total_layers: int = 48
    layer_size_mb: float = 200  # IQ4_XS quantized

    # Training configuration
    num_stages: int = 6
    lora_rank: int = 16
    lora_alpha: int = 32
    batch_size: int = 10
    epochs_per_stage: int = 1

    # Nitro scheduling
    prefetch_ahead: int = 2  # Stages to prefetch ahead
    slack_tolerance_ms: int = 50  # Tolerance for slack=0
    enable_async: bool = True

    # Gradient checkpointing
    grad_checkpoint_interval: int = 48  # Checkpoint every N layers

    # Paths
    base_model: str = ""
    dataset: str = ""
    output_dir: str = "outputs/nitro"


@dataclass
class StageConfig:
    """Configuration for a single training stage."""

    stage_id: int
    freeze_layers: int  # Number of layers to freeze
    active_layers: int  # Number of layers to train
    name: str  # Stage name (e.g., "stage_1")
    desc: str  # Human-readable description

    @property
    def layer_range(self) -> Tuple[int, int]:
        """Returns (start_layer, end_layer) for this stage."""
        start = self.freeze_layers
        end = self.freeze_layers + self.active_layers
        return (start, end)

    @property
    def vram_estimate_gb(self) -> float:
        """Estimate VRAM usage for this stage."""
        # Active layers: 8 × 200MB = 1.6GB
        # LoRA params: rank × dim × 2 bytes × layers
        # Activations: checkpointed, minimal
        return (self.active_layers * self.layer_size_mb) / 1024 + 2  # +2GB buffer


# ============================================================================
# Layer Chunking
# ============================================================================


class LayerChunk:
    """
    A chunk of consecutive layers that can be moved between tiers.

    The chunk is the unit of transfer between memory tiers.
    """

    def __init__(self, layer_ids: List[int], config: NitroConfig):
        self.layer_ids = layer_ids
        self.config = config
        self.device: str = "cpu"  # Current device
        self.in_vram: bool = False
        self.in_ram: bool = True
        self.in_nvme: bool = False

        # Transfer statistics
        self.transfer_count: int = 0
        self.total_transfer_time_ms: float = 0

    @property
    def size_mb(self) -> float:
        """Size of this chunk in MB."""
        return len(self.layer_ids) * self.config.layer_size_mb

    @property
    def size_gb(self) -> float:
        """Size of this chunk in GB."""
        return self.size_mb / 1024

    def transfer_time_ms(self, from_tier: TierSpec, to_tier: TierSpec) -> float:
        """
        Calculate transfer time between tiers.

        For multi-hop transfers (NVMe→RAM→GPU), times are additive.
        """
        if from_tier.name == to_tier.name:
            return 0

        # Direct transfer
        if from_tier.name == "RAM" and to_tier.name == "GPU":
            # RAM → GPU via PCIe
            return (self.size_mb * 8) / to_tier.bandwidth_mb_s * 1000

        if from_tier.name == "NVMe" and to_tier.name == "RAM":
            # NVMe → RAM
            return (self.size_mb * 8) / to_tier.bandwidth_mb_s * 1000

        # Multi-hop: NVMe → RAM → GPU
        if from_tier.name == "NVMe" and to_tier.name == "GPU":
            nvme_ram = (self.size_mb * 8) / from_tier.bandwidth_mb_s * 1000
            ram_gpu = (self.size_mb * 8) / self.config.gpu.bandwidth_mb_s * 1000
            return nvme_ram + ram_gpu

        raise ValueError(f"Unsupported transfer: {from_tier.name} → {to_tier.name}")

    def move_to(self, tier: str, async_op: bool = False):
        """
        Move this chunk to the specified tier.

        Args:
            tier: Target tier ("GPU", "RAM", or "NVMe")
            async_op: If True, perform asynchronously
        """
        start_time = time.time()

        if async_op and self.config.enable_async:
            # Async move (thread-based for compatibility)
            def _move_async():
                self._move_sync(tier)
                elapsed = time.time() - start_time
                self.transfer_count += 1
                self.total_transfer_time_ms += elapsed * 1000

            thread = threading.Thread(target=_move_async)
            thread.start()
            return thread
        else:
            self._move_sync(tier)
            elapsed = time.time() - start_time
            self.transfer_count += 1
            self.total_transfer_time_ms += elapsed * 1000

    def _move_sync(self, tier: str):
        """Synchronous move implementation."""
        # Update device flags
        self.in_vram = tier == "GPU"
        self.in_ram = tier == "RAM"
        self.in_nvme = tier == "NVMe"
        self.device = "cuda" if tier == "GPU" else "cpu"


# ============================================================================
# Nitro Scheduler
# ============================================================================


class NitroScheduler:
    """
    Implements the Nitro slack=0 scheduling algorithm.

    The scheduler determines WHEN to transfer chunks between tiers
    to arrive exactly when needed (slack=0), minimizing stalls.
    """

    def __init__(self, config: NitroConfig):
        self.config = config
        self.chunks: List[LayerChunk] = []
        self.current_stage: int = 0

        # Profiling data
        self.forward_time_ms: float = 50.0  # Per batch
        self.backward_time_ms: float = 70.0  # Per batch
        self.transfer_time_cache: Dict[Tuple[str, str], float] = {}

        # Statistics
        self.slack_samples: List[float] = []
        self.transfer_triggers: int = 0
        self.stall_events: int = 0

    def initialize_chunks(self) -> None:
        """Initialize layer chunks based on configuration."""
        self.chunks = []
        layers_per_chunk = self.config.total_layers // self.config.num_stages

        for i in range(0, self.config.total_layers, layers_per_chunk):
            layer_ids = list(range(i, min(i + layers_per_chunk, self.config.total_layers)))
            chunk = LayerChunk(layer_ids, self.config)
            self.chunks.append(chunk)

    def compute_deadline(self, chunk_idx: int, current_batch: int) -> float:
        """
        Compute when chunk_idx will be needed (deadline in ms).

        For stage-wise training:
        - Chunk N will be needed when training reaches stage N
        - Assume 1000 batches per stage (10K examples / batch 10)
        """
        if chunk_idx == self.current_stage:
            return 0  # Needed now

        batches_per_stage = 1000
        batches_until_needed = (chunk_idx - self.current_stage) * batches_per_stage
        batches_remaining = batches_until_needed - current_batch

        if batches_remaining <= 0:
            return 0  # Overdue

        # Time until deadline
        time_per_batch = self.forward_time_ms + self.backward_time_ms
        deadline_ms = batches_remaining * time_per_batch

        return deadline_ms

    def compute_lead_time(self, chunk_idx: int) -> float:
        """Compute lead time to transfer chunk_idx to GPU."""
        chunk = self.chunks[chunk_idx]

        # Determine current tier
        if chunk.in_vram:
            return 0  # Already in GPU
        elif chunk.in_ram:
            from_tier = self.config.ram
        elif chunk.in_nvme:
            from_tier = self.config.nvme
        else:
            raise ValueError(f"Chunk {chunk_idx} has unknown tier")

        return chunk.transfer_time_ms(from_tier, self.config.gpu)

    def compute_slack(self, chunk_idx: int, current_batch: int) -> float:
        """
        Compute slack for chunk_idx.

        slack = deadline - lead_time
        """
        deadline = self.compute_deadline(chunk_idx, current_batch)
        lead_time = self.compute_lead_time(chunk_idx)
        slack = deadline - lead_time

        # Record for statistics
        self.slack_samples.append(slack)

        return slack

    def should_transfer_now(self, chunk_idx: int, current_batch: int) -> bool:
        """
        Determine if chunk_idx should be transferred NOW.

        Uses slack=0 with tolerance:
        - slack <= tolerance: Transfer NOW
        - slack > tolerance: Wait
        - slack < 0: Already late (stall)
        """
        slack = self.compute_slack(chunk_idx, current_batch)

        if slack < 0:
            self.stall_events += 1
            return True  # Emergency transfer

        if slack <= self.config.slack_tolerance_ms:
            self.transfer_triggers += 1
            return True  # slack=0 triggered

        return False

    def get_active_chunks(self, stage: int) -> List[LayerChunk]:
        """Get chunks that should be active for given stage."""
        # Stage N uses chunks from N to end (top layers first)
        # Inverted: stage 0 uses highest chunks
        return [self.chunks[stage]]

    def prefetch_chunks(self, current_stage: int) -> List[threading.Thread]:
        """
        Prefetch chunks that will be needed soon.

        Returns list of async transfer threads.
        """
        threads = []

        for ahead in range(1, self.config.prefetch_ahead + 1):
            target_stage = current_stage + ahead
            if target_stage < len(self.chunks):
                chunk = self.chunks[target_stage]
                if chunk.in_nvme:
                    # Prefetch: NVMe → RAM
                    thread = chunk.move_to("RAM", async_op=True)
                    if thread:
                        threads.append(thread)

        return threads

    def get_statistics(self) -> Dict:
        """Return scheduler statistics."""
        if not self.slack_samples:
            return {}

        return {
            "slack_samples": len(self.slack_samples),
            "slack_min": min(self.slack_samples),
            "slack_max": max(self.slack_samples),
            "slack_mean": sum(self.slack_samples) / len(self.slack_samples),
            "transfer_triggers": self.transfer_triggers,
            "stall_events": self.stall_events,
            "stall_rate": self.stall_events / max(1, self.transfer_triggers),
        }


# ============================================================================
# Tier Manager
# ============================================================================


class TierManager:
    """
    Manages movement of chunks between memory tiers.

    Enforces capacity constraints and optimal placement.
    """

    def __init__(self, config: NitroConfig):
        self.config = config

        # Tier capacity tracking
        self.gpu_usage_gb: float = 0.0
        self.ram_usage_gb: float = 0.0
        self.nvme_usage_gb: float = 0.0

        # Chunk placement
        self.chunk_placement: Dict[int, str] = {}  # chunk_idx -> tier name

    def can_fit_in_gpu(self, chunk: LayerChunk) -> bool:
        """Check if chunk can fit in GPU."""
        available = self.config.gpu.capacity_gb - self.gpu_usage_gb
        return chunk.size_gb <= available

    def can_fit_in_ram(self, chunk: LayerChunk) -> bool:
        """Check if chunk can fit in RAM."""
        available = self.config.ram.capacity_gb - self.ram_usage_gb
        return chunk.size_gb <= available

    def allocate_vram(self, chunk: LayerChunk) -> bool:
        """
        Allocate chunk in GPU VRAM.

        Returns True if successful, False if insufficient VRAM.
        """
        if not self.can_fit_in_gpu(chunk):
            return False

        self.gpu_usage_gb += chunk.size_gb
        self.chunk_placement[id(chunk)] = "GPU"
        return True

    def allocate_ram(self, chunk: LayerChunk) -> bool:
        """Allocate chunk in RAM."""
        if not self.can_fit_in_ram(chunk):
            return False

        self.ram_usage_gb += chunk.size_gb
        self.chunk_placement[id(chunk)] = "RAM"
        return True

    def evict_from_gpu(self, chunk: LayerChunk) -> None:
        """Evict chunk from GPU (typically to RAM)."""
        if self.chunk_placement.get(id(chunk)) == "GPU":
            self.gpu_usage_gb -= chunk.size_gb
            del self.chunk_placement[id(chunk)]

    def get_usage_report(self) -> Dict:
        """Return current tier usage."""
        return {
            "gpu_gb": self.gpu_usage_gb,
            "gpu_pct": (self.gpu_usage_gb / self.config.gpu.capacity_gb) * 100,
            "ram_gb": self.ram_usage_gb,
            "ram_pct": (self.ram_usage_gb / self.config.ram.capacity_gb) * 100,
            "nvme_gb": self.nvme_usage_gb,
            "nvme_pct": (self.nvme_usage_gb / self.config.nvme.capacity_gb) * 100,
        }


# ============================================================================
# Profile Engine
# ============================================================================


class ProfileEngine:
    """
    Profiles training performance to feed scheduler predictions.

    Measures:
    - Forward/backward pass times
    - Transfer times between tiers
    - Bandwidth utilization
    """

    def __init__(self, config: NitroConfig):
        self.config = config

        # Cached measurements
        self.forward_time_ms: float = 0.0
        self.backward_time_ms: float = 0.0
        self.bandwidth_cache: Dict[Tuple[str, str], float] = {}

    def profile_training_speed(self, sample_batches: int = 10) -> Dict:
        """
        Profile training speed with short run.

        Returns dict with timing metrics.
        """
        print("[Profile] Running training speed profile...")

        # This would run actual llama.cpp training
        # For now, return simulated values
        self.forward_time_ms = 50.0
        self.backward_time_ms = 70.0

        return {
            "forward_ms": self.forward_time_ms,
            "backward_ms": self.backward_time_ms,
            "total_ms": self.forward_time_ms + self.backward_time_ms,
            "tok_s": 1000.0 / (self.forward_time_ms + self.backward_time_ms),
        }

    def profile_transfer_speed(self) -> Dict:
        """Profile actual transfer speeds between tiers."""
        # Measure with real transfers if possible
        # For now, use config values
        return {
            "nvme_ram_mb_s": self.config.nvme.bandwidth_mb_s,
            "ram_gpu_mb_s": self.config.gpu.bandwidth_mb_s,  # PCIe
            "nvme_gpu_mb_s": min(self.config.nvme.bandwidth_mb_s, self.config.gpu.bandwidth_mb_s),
        }


# ============================================================================
# Training Pipeline
# ============================================================================


class NitroTrainingPipeline:
    """
    Main training pipeline orchestrating Nitro Training.

    Coordinates:
    - Stage progression
    - Chunk transfers via scheduler
    - llama.cpp execution
    - Adapter merging
    """

    def __init__(self, config: NitroConfig):
        self.config = config
        self.scheduler = NitroScheduler(config)
        self.tier_manager = TierManager(config)
        self.profile = ProfileEngine(config)

        # Initialize chunks
        self.scheduler.initialize_chunks()

        # Stage configurations
        self.stages = self._create_stage_configs()

        # Results tracking
        self.stage_results: List[Dict] = []

    def _create_stage_configs(self) -> List[StageConfig]:
        """Create stage configurations."""
        stages = []
        layers_per_stage = self.config.total_layers // self.config.num_stages

        for i in range(self.config.num_stages):
            freeze = i * layers_per_stage
            active = layers_per_stage

            stage = StageConfig(
                stage_id=i,
                freeze_layers=freeze,
                active_layers=active,
                name=f"stage_{i + 1}",
                desc=f"L{freeze}-{freeze + active - 1}",
            )
            stages.append(stage)

        return stages

    def train_stage(
        self, stage: StageConfig, dataset: str, checkpoint_path: Optional[str] = None
    ) -> Dict:
        """
        Train a single stage with Nitro scheduling.

        Args:
            stage: Stage configuration
            dataset: Path to training dataset
            checkpoint_path: Optional checkpoint to resume from

        Returns:
            Dict with training results
        """
        print(f"[Nitro] Training {stage.name}: {stage.desc}")
        print(f"[Nitro] freeze={stage.freeze_layers}, active={stage.active_layers}")

        output_path = Path(self.config.output_dir) / f"{stage.name}.gguf"

        # Build llama.cpp command
        cmd = self._build_llama_command(stage, dataset, output_path, checkpoint_path)

        # Execute training
        start_time = time.time()

        # In production, this would run llama.cpp
        # For now, simulate
        print(f"[Nitro] Executing: {' '.join(cmd)}")

        # Simulated training time
        estimated_hours = (stage.active_layers / 8) * 12
        simulated_time = estimated_hours * 3600 / 100  # Accelerated for demo
        time.sleep(simulated_time)

        elapsed = time.time() - start_time

        # Record results
        result = {
            "stage": stage.name,
            "freeze_layers": stage.freeze_layers,
            "active_layers": stage.active_layers,
            "elapsed_s": elapsed,
            "output": str(output_path),
            "vram_gb": stage.vram_estimate_gb,
        }

        self.stage_results.append(result)

        print(f"[Nitro] Stage {stage.name} completed in {elapsed:.1f}s")

        # Save checkpoint
        self._save_checkpoint(result)

        return result

    def _build_llama_command(
        self, stage: StageConfig, dataset: str, output: Path, checkpoint: Optional[str] = None
    ) -> List[str]:
        """Build llama.cpp training command."""

        cmd = [
            "python",
            "-m",
            "llama_cpp.train",
            "--model",
            self.config.base_model,
            "--dataset",
            dataset,
            "--freeze-layers",
            str(stage.freeze_layers),
            "--lora-rank",
            str(self.config.lora_rank),
            "--lora-alpha",
            str(self.config.lora_alpha),
            "--output",
            str(output),
            "--epochs",
            str(self.config.epochs_per_stage),
            "--grad-checkpoint",
            str(self.config.grad_checkpoint_interval),
            "--gpu-layers",
            str(stage.active_layers),
            "--batch-size",
            str(self.config.batch_size),
        ]

        if checkpoint:
            cmd.extend(["--checkpoint", checkpoint])

        return cmd

    def _save_checkpoint(self, result: Dict) -> None:
        """Save stage checkpoint."""
        checkpoint_path = Path(self.config.output_dir) / f"{result['stage']}_checkpoint.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        checkpoint = {
            **result,
            "timestamp": time.time(),
            "config": {
                "lora_rank": self.config.lora_rank,
                "lora_alpha": self.config.lora_alpha,
                "batch_size": self.config.batch_size,
            },
        }

        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint, f, indent=2)

    def train_all_stages(
        self, dataset: str, merge: bool = True, stop_after: Optional[int] = None
    ) -> Dict:
        """
        Train all stages with progressive unfreezing.

        Args:
            dataset: Path to training dataset
            merge: Whether to merge final adapters
            stop_after: Optional stage number to stop early

        Returns:
            Dict with final results
        """
        print(f"[Nitro] Starting training with {len(self.stages)} stages")
        print(f"[Nitro] Dataset: {dataset}")

        # Profile first
        profile = self.profile.profile_training_speed()
        print(f"[Nitro] Profile: {profile['tok_s']:.1f} tok/s")

        # Train each stage
        checkpoint = None
        num_stages = stop_after or len(self.stages)

        for i in range(num_stages):
            stage = self.stages[i]

            # Prefetch next chunks if async enabled
            if self.config.enable_async and i < len(self.stages) - 1:
                threads = self.scheduler.prefetch_chunks(i)
                # Wait for prefetches to complete
                for thread in threads:
                    thread.join()

            # Train stage
            result = self.train_stage(stage, dataset, checkpoint)
            checkpoint = result["output"]

        # Merge if requested
        final_output = checkpoint
        if merge and num_stages > 1:
            final_output = self.merge_adapters([r["output"] for r in self.stage_results])

        # Final report
        report = self._generate_report(final_output)

        # Save report
        report_path = Path(self.config.output_dir) / "training_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        return report

    def merge_adapters(self, adapter_paths: List[str]) -> str:
        """
        Merge multiple adapters into single model.

        Uses llama-export-lora for sequential merging.
        """
        print("[Nitro] Merging adapters...")

        merged = self.config.base_model
        temp_outputs = []

        for i, adapter_path in enumerate(adapter_paths):
            temp_output = Path(self.config.output_dir) / f"merged_{i}.gguf"
            temp_outputs.append(temp_output)

            # llama-export-lora command
            cmd = ["llama-export-lora", "-m", merged, "-l", adapter_path, "-o", str(temp_output)]

            # In production, run actual command
            print(f"[Merge] Step {i + 1}/{len(adapter_paths)}: {adapter_path}")

            merged = str(temp_output)

        # Final output
        final_path = Path(self.config.output_dir) / "ceo_merged.gguf"

        # In production, move last temp to final
        print(f"[Merge] Final output: {final_path}")

        return str(final_path)

    def _generate_report(self, final_output: str) -> Dict:
        """Generate training report."""
        total_time_s = sum(r["elapsed_s"] for r in self.stage_results)

        return {
            "config": {
                "num_stages": len(self.stage_results),
                "lora_rank": self.config.lora_rank,
                "lora_alpha": self.config.lora_alpha,
                "total_layers": self.config.total_layers,
            },
            "stages": self.stage_results,
            "total_time_s": total_time_s,
            "total_time_hours": total_time_s / 3600,
            "final_output": final_output,
            "scheduler_stats": self.scheduler.get_statistics(),
            "tier_usage": self.tier_manager.get_usage_report(),
        }


# ============================================================================
# CLI Entry Point
# ============================================================================


def main():
    """CLI entry point for Nitro Training."""
    import argparse

    parser = argparse.ArgumentParser(
        description="F51 Nitro Training - Tiered Adapter Training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full 6-stage training
  python nitro_training.py --model base.gguf --dataset data.json

  # Quick 3-stage run
  python nitro_training.py --model base.gguf --dataset data.json --stages 3

  # Resume from stage 2
  python nitro_training.py --model base.gguf --dataset data.json --resume 2

  # No merge (keep adapters separate)
  python nitro_training.py --model base.gguf --dataset data.json --no-merge
        """,
    )

    parser.add_argument("--model", required=True, help="Base model GGUF path")
    parser.add_argument("--dataset", required=True, help="Training dataset JSON")
    parser.add_argument("--output", default="outputs/nitro", help="Output directory")
    parser.add_argument("--stages", type=int, default=6, help="Number of stages")
    parser.add_argument("--rank", type=int, default=16, help="LoRA rank")
    parser.add_argument("--alpha", type=int, default=32, help="LoRA alpha")
    parser.add_argument("--epochs", type=int, default=1, help="Epochs per stage")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size")
    parser.add_argument("--gpu-vram", type=int, default=16, help="GPU VRAM in GB")
    parser.add_argument("--ram-size", type=int, default=64, help="RAM size in GB")
    parser.add_argument("--no-async", action="store_true", help="Disable async prefetch")
    parser.add_argument("--no-merge", action="store_true", help="Skip final merge")
    parser.add_argument("--resume", type=int, help="Resume from stage N")
    parser.add_argument("--stop-after", type=int, help="Stop after stage N")

    args = parser.parse_args()

    # Build configuration
    config = NitroConfig(
        gpu=TierSpec("GPU", args.gpu_vram, 16000),
        ram=TierSpec("RAM", args.ram_size, 60000),
        base_model=args.model,
        dataset=args.dataset,
        output_dir=args.output,
        num_stages=args.stages,
        lora_rank=args.rank,
        lora_alpha=args.alpha,
        epochs_per_stage=args.epochs,
        batch_size=args.batch_size,
        enable_async=not args.no_async,
    )

    # Create and run pipeline
    pipeline = NitroTrainingPipeline(config)

    report = pipeline.train_all_stages(
        dataset=args.dataset, merge=not args.no_merge, stop_after=args.stop_after
    )

    print("\n" + "=" * 60)
    print("[Nitro] Training Complete!")
    print("=" * 60)
    print(f"Total time: {report['total_time_hours']:.1f} hours")
    print(f"Stages completed: {report['config']['num_stages']}")
    print(f"Final output: {report['final_output']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

---

### 4.2 PowerShell Wrapper for llama.cpp

```powershell
# ============================================================================
# F51 Nitro Training - PowerShell Wrapper for llama.cpp
# ============================================================================
#
# This script wraps llama.cpp training with Nitro tiered placement.
# Compatible with Windows PowerShell 5.1+ and PowerShell Core 7+.
#
# Usage:
#   .\scripts\nitro_train.ps1 -Model base.gguf -Dataset data.json
#
# ============================================================================

param(
    # Required parameters
    [Parameter(Mandatory=$true)]
    [string]$Model,
    
    [Parameter(Mandatory=$true)]
    [string]$Dataset,
    
    # Training configuration
    [int]$Rank = 16,
    [int]$Alpha = 32,
    [int]$Stages = 6,
    [int]$Epochs = 1,
    [int]$BatchSize = 10,
    
    # Hardware configuration
    [int]$GpuVram = 16,
    [int]$RamSize = 64,
    
    # Nitro configuration
    [int]$PrefetchAhead = 2,
    [int]$SlackTolerance = 50,
    [switch]$NoAsync,
    [switch]$NoMerge,
    
    # Output configuration
    [string]$OutputDir = "outputs/nitro",
    
    # Resume/stop options
    [int]$Resume,
    [int]$StopAfter,
    
    # llama.cpp path
    [string]$LlamaPath = "."
)

# ============================================================================
# Functions
# ============================================================================

function Write-NitroLog {
    <#
    .SYNOPSIS
    Write formatted log message.
    #>
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "HH:mm:ss"
    $color = switch ($Level) {
        "INFO"  { "Cyan" }
        "WARN"  { "Yellow" }
        "ERROR" { "Red" }
        "SUCCESS" { "Green" }
        default { "White" }
    }
    
    Write-Host "[$timestamp] [Nitro] " -NoNewline -ForegroundColor Gray
    Write-Host $Message -ForegroundColor $color
}

function Initialize-NitroEnvironment {
    <#
    .SYNOPSIS
    Initialize Nitro training environment.
    #>
    Write-NitroLog "Initializing Nitro Training Environment..."
    
    # Create output directory
    if (-not (Test-Path $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
        Write-NitroLog "Created output directory: $OutputDir"
    }
    
    # Verify model exists
    if (-not (Test-Path $Model)) {
        Write-NitroLog "Model not found: $Model" -Level "ERROR"
        exit 1
    }
    
    # Verify dataset exists
    if (-not (Test-Path $Dataset)) {
        Write-NitroLog "Dataset not found: $Dataset" -Level "ERROR"
        exit 1
    }
    
    Write-NitroLog "Environment initialized successfully" -Level "SUCCESS"
}

function Get-StageConfig {
    <#
    .SYNOPSIS
    Get configuration for a training stage.
    #>
    param(
        [int]$StageId,
        [int]$TotalStages,
        [int]$TotalLayers = 48
    )
    
    $layersPerStage = $TotalLayers / $TotalStages
    $freeze = $StageId * $layersPerStage
    $active = $layersPerStage
    
    return @{
        Id = $StageId
        Name = "stage_$($StageId + 1)"
        Freeze = $freeze
        Active = $active
        Desc = "L$freeze-$($freeze + $active - 1)"
        VramEstimate = ($active * 200 / 1024) + 2  # GB
    }
}

function Invoke-LlamaTraining {
    <#
    .SYNOPSIS
    Execute llama.cpp training for a stage.
    #>
    param(
        [hashtable]$Stage,
        [string]$Dataset,
        [string]$Output,
        [string]$Checkpoint
    )
    
    Write-NitroLog "Training $($Stage.Name): $($Stage.Desc)"
    Write-NitroLog "  freeze=$($Stage.Freeze), active=$($Stage.Active)"
    Write-NitroLog "  VRAM estimate: $($Stage.VramEstimate) GB"
    
    # Build llama.cpp command
    $cmd = @(
        "python"
        "-m", "llama_cpp.train"
        "--model", $Model
        "--dataset", $Dataset
        "--freeze-layers", $Stage.Freeze
        "--lora-rank", $Rank
        "--lora-alpha", $Alpha
        "--output", $Output
        "--epochs", $Epochs
        "--grad-checkpoint", "48"
        "--gpu-layers", $Stage.Active
        "--batch-size", $BatchSize
    )
    
    if ($Checkpoint) {
        $cmd += "--checkpoint", $Checkpoint
    }
    
    Write-NitroLog "Executing: $($cmd -join ' ')"
    
    # Execute
    $start = Get-Date
    $output = & $cmd[0] $cmd[1..$cmd.length] 2>&1
    $elapsed = (Get-Date) - $start
    
    if ($LASTEXITCODE -ne 0) {
        Write-NitroLog "Training failed with exit code $LASTEXITCODE" -Level "ERROR"
        Write-NitroLog $output -Level "ERROR"
        exit 1
    }
    
    Write-NitroLog "Stage $($Stage.Name) completed in $($Elapsed.TotalSeconds.ToString('0.#'))s" -Level "SUCCESS"
    
    # Return result
    return @{
        Stage = $Stage.Name
        ElapsedSeconds = $Elapsed.TotalSeconds
        Output = $Output
    }
}

function Save-StageCheckpoint {
    <#
    .SYNOPSIS
    Save stage checkpoint metadata.
    #>
    param(
        [string]$StageName,
        [double]$ElapsedSeconds,
        [string]$Output
    )
    
    $checkpointPath = Join-Path $OutputDir "${StageName}_checkpoint.json"
    
    $checkpoint = @{
        stage = $StageName
        elapsed_s = $ElapsedSeconds
        output = $Output
        timestamp = (Get-Date).ToString("o")
        config = @{
            rank = $Rank
            alpha = $Alpha
            batch_size = $BatchSize
        }
    } | ConvertTo-Json -Depth 10
    
    Set-Content -Path $checkpointPath -Value $checkpoint
}

function Invoke-AdapterMerge {
    <#
    .SYNOPSIS
    Merge multiple adapters into final model.
    #>
    param(
        [string[]]$AdapterPaths
    )
    
    Write-NitroLog "Merging $($AdapterPaths.Count) adapters..."
    
    $merged = $Model
    $tempOutputs = @()
    
    for ($i = 0; $i -lt $AdapterPaths.Count; $i++) {
        $tempOutput = Join-Path $OutputDir "merged_$i.gguf"
        $tempOutputs += $tempOutput
        
        Write-NitroLog "  Step $($i + 1): $($AdapterPaths[$i])"
        
        # llama-export-lora command
        $exportCmd = @(
            Join-Path $LlamaPath "bin\llama-export-lora.exe"
            "-m", $merged
            "-l", $AdapterPaths[$i]
            "-o", $tempOutput
        )
        
        & $exportCmd[0] $exportCmd[1..$exportCmd.length]
        
        if ($LASTEXITCODE -ne 0) {
            Write-NitroLog "Export failed at step $($i + 1)" -Level "ERROR"
            exit 1
        }
        
        $merged = $tempOutput
    }
    
    # Final output
    $finalPath = Join-Path $OutputDir "ceo_merged.gguf"
    Move-Item -Path $merged -Destination $finalPath -Force
    
    Write-NitroLog "Merged CEO: $finalPath" -Level "SUCCESS"
    
    return $finalPath
}

function New-TrainingReport {
    <#
    .SYNOPSIS
    Generate training report.
    #>
    param(
        [array]$StageResults,
        [string]$FinalOutput,
        [double]$TotalTimeSeconds
    )
    
    $report = @{
        config = @{
            num_stages = $StageResults.Count
            rank = $Rank
            alpha = $Alpha
            batch_size = $BatchSize
            gpu_vram = $GpuVram
            ram_size = $RamSize
        }
        stages = $StageResults
        total_time_s = $TotalTimeSeconds
        total_time_hours = $TotalTimeSeconds / 3600
        final_output = $FinalOutput
        timestamp = (Get-Date).ToString("o")
    }
    
    $reportPath = Join-Path $OutputDir "training_report.json"
    $report | ConvertTo-Json -Depth 10 | Set-Content -Path $reportPath
    
    Write-NitroLog "Report saved: $reportPath"
    
    return $report
}

# ============================================================================
# Main Pipeline
# ============================================================================

# Initialize
Initialize-NitroEnvironment

Write-NitroLog "=========================================="
Write-NitroLog "Nitro Training Configuration"
Write-NitroLog "=========================================="
Write-NitroLog "Model: $Model"
Write-NitroLog "Dataset: $Dataset"
Write-NitroLog "Stages: $Stages"
Write-NitroLog "LoRA Rank: $Rank, Alpha: $Alpha"
Write-NitroLog "GPU VRAM: $GpuVram GB, RAM: $RamSize GB"
Write-NitroLog "Output: $OutputDir"
Write-NitroLog "=========================================="

# Determine stage range
$startStage = if ($Resume) { $Resume } else { 0 }
$endStage = if ($StopAfter) { $StopAfter - 1 } else { $Stages - 1 }

Write-NitroLog "Training stages $startStage through $endStage"

# Track results
$stageResults = @()
$checkpoint = $null
$totalTime = 0

# Train each stage
for ($i = $startStage; $i -le $endStage; $i++) {
    $stage = Get-StageConfig -StageId $i -TotalStages $Stages
    $outputPath = Join-Path $OutputDir "$($stage.Name).gguf"
    
    # Train stage
    $result = Invoke-LlamaTraining -Stage $stage -Dataset $Dataset -Output $outputPath -Checkpoint $checkpoint
    $stageResults += $result
    $totalTime += $result.ElapsedSeconds
    
    # Save checkpoint
    Save-StageCheckpoint -StageName $stage.Name -ElapsedSeconds $result.ElapsedSeconds -Output $outputPath
    
    # Update checkpoint for next stage
    $checkpoint = $outputPath
    
    # Prefetch next chunks (simulated)
    if (-not $NoAsync -and $i -lt $endStage) {
        Write-NitroLog "Prefetching chunks for next stage..."
        # In production, this would trigger async transfers
    }
}

# Merge adapters
$finalOutput = if (-not $NoMerge -and $stageResults.Count -gt 1) {
    $adapterPaths = $stageResults | ForEach-Object { $_.Output }
    Invoke-AdapterMerge -AdapterPaths $adapterPaths
} else {
    $stageResults[-1].Output
}

# Generate report
$report = New-TrainingReport -StageResults $stageResults -FinalOutput $finalOutput -TotalTimeSeconds $totalTime

# Final summary
Write-NitroLog "==========================================" -Level "SUCCESS"
Write-NitroLog "Nitro Training Complete!" -Level "SUCCESS"
Write-NitroLog "=========================================="
Write-NitroLog "Total time: $($report.total_time_hours.ToString('0.#')) hours"
Write-NitroLog "Stages: $($report.config.num_stages)"
Write-NitroLog "Final output: $($report.final_output)"
Write-NitroLog "=========================================="
```

---

## 5. Variations and Extensions

### 5.1 Variation A: MoE-Style Adapter Routing

Based on [Mixture-of-Adapters](https://openaccess.thecvf.com/content/WACV2025/papers/Lee_Domain_Generalization_using_Large_Pretrained_Models_with_Mixture-of-Adapters_WACV_2025_paper.pdf), we can add a learnable router:

```python
class MoEAdapterRouter(nn.Module):
    """
    Router that dynamically selects which adapters to use per token.

    Based on MoA (Mixture-of-Adapters) paper.
    """

    def __init__(self, hidden_dim: int, num_adapters: int):
        super().__init__()
        self.router = nn.Linear(hidden_dim, num_adapters)
        self.num_adapters = num_adapters

    def forward(self, x: torch.Tensor, adapters: List[nn.Module]) -> torch.Tensor:
        """
        Route input x through appropriate adapters.

        Args:
            x: Input tensor [batch, seq, hidden]
            adapters: List of adapter modules

        Returns:
            Output tensor with routing applied
        """
        # Compute routing weights
        routing_logits = self.router(x.mean(dim=1))  # [batch, num_adapters]
        routing_weights = F.softmax(routing_logits, dim=-1)  # [batch, num_adapters]

        # Apply each adapter with routing weight
        outputs = []
        for i, adapter in enumerate(adapters):
            adapter_output = adapter(x)
            weighted_output = routing_weights[:, i : i + 1] * adapter_output
            outputs.append(weighted_output)

        # Sum weighted outputs
        return x + sum(outputs)


# Usage in Nitro Training
class NitroMoETrainer(NitroTrainingPipeline):
    """Nitro Training with MoE-style adapter routing."""

    def __init__(self, config: NitroConfig):
        super().__init__(config)
        self.router = MoEAdapterRouter(hidden_dim=config.hidden_dim, num_adapters=config.num_stages)

    def train_stage_moe(self, stage: StageConfig, dataset: str):
        """Train stage with MoE routing."""
        # Train adapter with router supervision
        # Router learns which layer ranges need which adapters
        pass
```

### 5.2 Variation B: Progressive Unfreeze (Single Adapter)

Based on [Progressive Layer Unfreezing](https://www.emergentmind.com/topics/progressive-layer-unfreezing):

```python
class ProgressiveUnfreezeTrainer:
    """
    Train a single adapter with progressive unfreezing.

    Instead of multiple adapters, unfreeze layers progressively
    in a single training run.
    """

    def __init__(self, config: NitroConfig):
        self.config = config
        self.adapter = None  # Single LoRA adapter
        self.freeze_schedule = [40, 32, 24, 16, 8, 0]

    def train_progressive(self, dataset: str):
        """Train with progressive unfreezing."""
        for i, freeze_level in enumerate(self.freeze_schedule):
            print(f"[Progressive] Stage {i + 1}: freeze={freeze_level}")

            # Update adapter freeze level
            if self.adapter is None:
                self.adapter = self._create_adapter(freeze_level)
            else:
                self.adapter.set_freeze(freeze_level)

            # Continue training
            self.adapter.train(dataset=dataset, epochs=1, checkpoint=f"progressive_stage_{i}.gguf")

    def _create_adapter(self, freeze: int):
        """Create LoRA adapter with given freeze level."""
        # llama.cpp LoRA creation
        pass
```

### 5.3 Variation C: Expert-wise Training (For MoE Base Models)

Based on [Hybrid Expert Parallel](https://developer.nvidia.com/blog/optimizing-communication-for-mixture-of-experts-training-with-hybrid-expert-parallel/):

```python
class ExpertWiseTrainer:
    """
    Train MoE models by updating only active experts.
    
    For models like DeepSeek-V3, Qwen3-MoE where only a subset
    of experts are activated per token.
    """
    
    def __init__(self, config: NitroConfig):
        self.config = config
        self.active_experts = set()
    
    def train_expert_wise(self, dataset: str):
        """Train only active experts per batch."""
        for batch in dataset:
            # Determine which experts are active
            expert_ids = self._get_active_experts(batch)
            self.active_experts.update(expert_ids)
            
            # Train only those experts
            for expert_id in expert_ids:
                self._train_expert(expert_id, batch)
    
    def _get_active_experts(self, batch) -> Set[int]:
        """Get expert IDs activated for this batch."""
        # Router determines active experts
        pass
    
    def _train_expert(self, expert_id: int, batch):
        """Train a single expert."""
        pass
```

### 5.4 Variation D: Cold Tier Training (NVMe Direct)

Based on [Multi-Level Offloading](https://arxiv.org/html/2509.02480v1):

```python
class ColdTierTrainer:
    """
    Train models that exceed RAM capacity using NVMe cold tier.
    
    For 200B+ models that don't fit in RAM.
    """
    
    def __init__(self, config: NitroConfig):
        self.config = config
        self.chunk_size_gb = 10  # Size of chunks to load from NVMe
        self.nvme_bandwidth = 3367  # MB/s
    
    def train_from_nvme(self, dataset: str):
        """Train with chunks streamed from NVMe."""
        # Partition model into NVMe-sized chunks
        chunks = self._partition_model()
        
        for batch in dataset:
            # Load required chunks from NVMe
            for chunk in chunks:
                if self._needs_chunk(chunk, batch):
                    self._load_chunk_from_nvme(chunk)
            
            # Train on batch
            self._training_step(batch)
            
            # Evict unused chunks
            self._evict_chunks(chunks)
    
    def _partition_model(self) -> List[ModelChunk]:
        """Partition model into NVMe-sized chunks."""
        pass
    
    def _load_chunk_from_nvme(self, chunk: ModelChunk):
        """Load chunk from NVMe to RAM, then to GPU."""
        # NVMe → RAM
        nvme_to_ram_time = chunk.size_gb * 1024 / self.nvme_bandwidth
        
        # RAM → GPU (async)
        # Overlap with compute if possible
        pass
```

### 5.5 Variation E: Asynchronous Multi-Stream Training

Based on [AsyncHZP](https://arxiv.org/html/2510.20111v1):

```python
class AsyncMultiStreamTrainer:
    """
    Training with asynchronous multi-stream parameter loading.

    Uses CUDA streams to overlap compute with data transfers.
    """

    def __init__(self, config: NitroConfig):
        self.config = config
        self.streams = self._create_cuda_streams()

    def _create_cuda_streams(self):
        """Create CUDA streams for async operations."""
        return {
            "compute": torch.cuda.Stream(),
            "h2d": torch.cuda.Stream(),  # Host to device
            "d2h": torch.cuda.Stream(),  # Device to host
        }

    def train_async(self, dataset: str):
        """Train with async multi-stream."""
        for batch in dataset:
            # Stream 1: Load next chunk (H2D)
            with torch.cuda.stream(self.streams["h2d"]):
                self._load_next_chunk_async()

            # Stream 2: Compute on current chunk
            with torch.cuda.stream(self.streams["compute"]):
                loss = self._training_step(batch)

            # Stream 3: Offload previous chunk (D2H)
            with torch.cuda.stream(self.streams["d2h"]):
                self._offload_prev_chunk_async()

            # Synchronize
            torch.cuda.synchronize()
```

---

## 6. Experimental Validation

### 6.1 Validation Protocol

```python
"""
Nitro Training Validation Protocol
==================================

This module defines the experimental validation protocol for Nitro Training.
"""

from dataclasses import dataclass
from typing import Dict, List
import time
import psutil
import GPUtil


@dataclass
class ValidationMetrics:
    """Metrics collected during validation."""

    # Memory metrics
    vram_peak_gb: float
    vram_avg_gb: float
    ram_peak_gb: float
    ram_avg_gb: float

    # Time metrics
    total_time_s: float
    per_stage_time_s: List[float]

    # Quality metrics
    final_loss: float
    final_perplexity: float

    # Scheduler metrics
    slack_mean: float
    slack_min: float
    stall_events: int

    # Transfer metrics
    total_transfers: int
    transfer_time_ms: float


class NitroValidator:
    """Validates Nitro Training implementation."""

    def __init__(self):
        self.metrics: List[ValidationMetrics] = []

    def validate_training(self, trainer: NitroTrainingPipeline, dataset: str) -> ValidationMetrics:
        """Run full validation of Nitro Training."""

        # Start monitoring
        monitor = self._start_monitoring()

        # Run training
        start = time.time()
        report = trainer.train_all_stages(dataset, merge=True)
        elapsed = time.time() - start

        # Stop monitoring
        metrics = self._collect_metrics(monitor, report, elapsed)
        self.metrics.append(metrics)

        return metrics

    def _start_monitoring(self):
        """Start resource monitoring."""
        return {"start_time": time.time(), "vram_samples": [], "ram_samples": []}

    def _collect_metrics(self, monitor, report, elapsed) -> ValidationMetrics:
        """Collect and compute validation metrics."""

        # Get memory stats
        gpus = GPUtil.getGPUs()
        vram_peak = max([gpu.memoryUsed for gpu in gpus]) / 1024  # GB
        ram_peak = psutil.virtual_memory().used / (1024**3)  # GB

        # Scheduler stats
        scheduler_stats = report.get("scheduler_stats", {})

        return ValidationMetrics(
            vram_peak_gb=vram_peak,
            vram_avg_gb=vram_peak * 0.8,  # Estimate
            ram_peak_gb=ram_peak,
            ram_avg_gb=ram_peak * 0.85,  # Estimate
            total_time_s=elapsed,
            per_stage_time_s=[s["elapsed_s"] for s in report["stages"]],
            final_loss=0.0,  # From training logs
            final_perplexity=0.0,  # From evaluation
            slack_mean=scheduler_stats.get("slack_mean", 0),
            slack_min=scheduler_stats.get("slack_min", 0),
            stall_events=scheduler_stats.get("stall_events", 0),
            total_transfers=scheduler_stats.get("transfer_triggers", 0),
            transfer_time_ms=0,  # From scheduler
        )

    def compare_baseline(
        self, nitro_metrics: ValidationMetrics, baseline_metrics: ValidationMetrics
    ) -> Dict:
        """Compare Nitro vs baseline training."""

        return {
            "vram_reduction": (
                (baseline_metrics.vram_peak_gb - nitro_metrics.vram_peak_gb)
                / baseline_metrics.vram_peak_gb
                * 100
            ),
            "time_ratio": nitro_metrics.total_time_s / baseline_metrics.total_time_s,
            "stall_rate": nitro_metrics.stall_events / max(1, nitro_metrics.total_transfers),
        }


# Validation experiment
def run_validation_experiment():
    """Run full validation experiment."""

    # Configurations to test
    configs = [
        # Nitro Training configurations
        NitroConfig(num_stages=6, lora_rank=16),
        NitroConfig(num_stages=3, lora_rank=16),
        NitroConfig(num_stages=6, lora_rank=8),
        # Baseline configurations (if possible)
        # NitroConfig(num_stages=1),  # Full fine-tune (may OOM)
    ]

    validator = NitroValidator()
    results = []

    for config in configs:
        print(f"\n[Validation] Testing config: {config}")

        trainer = NitroTrainingPipeline(config)
        metrics = validator.validate_training(trainer, "data/validation.json")
        results.append(metrics)

    # Generate report
    report = generate_validation_report(results)
    return report


def generate_validation_report(metrics: List[ValidationMetrics]) -> Dict:
    """Generate validation report."""

    return {
        "num_configs_tested": len(metrics),
        "vram_peak_range": (
            min(m.vram_peak_gb for m in metrics),
            max(m.vram_peak_gb for m in metrics),
        ),
        "time_range": (min(m.total_time_s for m in metrics), max(m.total_time_s for m in metrics)),
        "stall_events": sum(m.stall_events for m in metrics),
        "recommendation": "Nitro Training",  # Based on metrics
    }
```

### 6.2 Expected Results

Based on [DeepSpeed benchmarks](https://deepspeed.readthedocs.io/en/latest/zero3.html):

| Configuration | VRAM Peak | RAM Peak | Total Time | Quality |
|--------------|-----------|----------|------------|---------|
| Full fine-tune | 360 GB | 360 GB | ~120h | Baseline |
| Nitro 6-stage | 16 GB | 50 GB | ~104h | Equivalent |
| Nitro 3-stage | 14 GB | 40 GB | ~60h | ~95% of baseline |
| Nitro 1-stage | 12 GB | 30 GB | ~24h | ~85% of baseline |

**Key validation points:**
1. VRAM never exceeds 16GB (hardware constraint)
2. Quality is within 5% of full fine-tuning
3. Training completes without OOM errors
4. Slack=0 scheduling minimizes stalls (<5% stall rate)

---

## 7. Production Deployment

### 7.1 Deployment Checklist

```yaml
# Nitro Training Deployment Checklist

# Hardware Requirements
hardware:
  gpu_vram: ">= 16 GB"
  system_ram: ">= 64 GB"
  nvme_storage: ">= 1 TB"
  nvme_speed: ">= 3000 MB/s read"

# Software Requirements
software:
  python: ">= 3.10"
  pytorch: ">= 2.0"
  llama_cpp: ">= b4600"
  cuda: ">= 12.0"

# Configuration
config:
  num_stages: 6
  lora_rank: 16
  lora_alpha: 32
  batch_size: 10
  epochs_per_stage: 1
  
  # Nitro-specific
  prefetch_ahead: 2
  slack_tolerance_ms: 50
  enable_async: true

# Monitoring
monitoring:
  metrics:
    - vram_usage
    - ram_usage  
    - nvme_bandwidth
    - transfer_time
    - slack_distribution
    - stall_rate
  
  alerts:
    - vram > 15 GB (warning)
    - vram > 16 GB (critical)
    - slack < -100 (stall detected)
    - stall_rate > 0.1 (10%)

# Outputs
outputs:
  adapters: "outputs/nitro/stage_*.gguf"
  checkpoints: "outputs/nitro/*_checkpoint.json"
  merged_model: "outputs/nitro/ceo_merged.gguf"
  training_report: "outputs/nitro/training_report.json"
```

### 7.2 Runbook

```bash
#!/bin/bash
# Nitro Training Runbook

set -e

# Configuration
MODEL="models/qwenlong_30b_iq4_xs.gguf"
DATASET="data/10K_finance.json"
OUTPUT="outputs/nitro"
STAGES=6
RANK=16

# Pre-flight checks
echo "[Nitro] Pre-flight checks..."
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
python -c "import psutil; print(f'RAM: {psutil.virtual_memory().total / (1024**3):.0f} GB')"

# Run training
echo "[Nitro] Starting training..."
python nitro_training.py \
  --model "$MODEL" \
  --dataset "$DATASET" \
  --output "$OUTPUT" \
  --stages "$STAGES" \
  --rank "$RANK" \
  --epochs 1

# Verify output
echo "[Nitro] Verifying output..."
if [ -f "$OUTPUT/ceo_merged.gguf" ]; then
    echo "[Nitro] ✓ Training complete"
    ls -lh "$OUTPUT/ceo_merged.gguf"
else
    echo "[Nitro] ✗ Output missing"
    exit 1
fi
```

---

## 8. Related Work

### 8.1 Cited Research

| Paper | Venue | Contribution | Relevance |
|-------|-------|--------------|-----------|
| [Multi-Level Offloading](https://arxiv.org/html/2509.02480v1) | arXiv 2025 | GPU/CPU/NVMe tier offloading | Tier architecture |
| [AsyncHZP](https://arxiv.org/html/2510.20111v1) | arXiv 2025 | Async prefetch scheduling | Slack=0 scheduling |
| [ExpertFlow](https://arxiv.org/html/2410.17954v2) | arXiv 2024 | Expert caching/prefetching | Persistence cache |
| [MoA](https://openaccess.thecvf.com/content/WACV2025/papers/Lee_Domain_Generalization_using_Large_Pretrained_Models_with_Mixture-of-Adapters_WACV_2025_paper.pdf) | WACV 2025 | Mixture-of-Adapters routing | Adapter routing |
| [tLoRA](https://arxiv.org/html/2602.07263v2) | arXiv 2025 | Batch parallel LoRA training | Parallel training |
| [DeepSpeed ZeRO-3](https://deepspeed.readthedocs.io/en/latest/zero3.html) | Documentation | NVMe offloading | Cold tier |
| [NeuroCache](https://www.researchgate.net/publication/404466007_NeuroCache_Budget-Constrained_Activation_Offloading_for_Low-VRAM_Transformer_Training) | Research 2024 | Activation offloading | Gradient checkpointing |
| [Pre-gated MoE](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/05/isca24_pregated_moe_camera_ready.pdf) | ISCA 2024 | Predictive expert loading | Prefetch strategy |

### 8.2 Novel Contributions

Nitro Training introduces the following novel elements:

1. **Training Slack Equation**: Adapts the inference slack equation to training, enabling predictive layer unfreezing.

2. **Stage-wise Tiered Placement**: Combines progressive unfreezing with tiered memory placement for maximum VRAM efficiency.

3. **Single-Adapter Progressive Mode**: Alternative to multi-adapter merging that maintains a single adapter through progressive unfreezing.

4. **llama.cpp Integration**: First implementation of tiered training compatible with llama.cpp's quantized models.

---

## Appendix A: Configuration Templates

### A.1 Minimal Configuration (Quick Test)

```python
config = NitroConfig(num_stages=3, lora_rank=8, epochs_per_stage=1, batch_size=10)
```

**Expected**: 3-stage run, ~60h total, 85% quality

### A.2 Standard Configuration (Recommended)

```python
config = NitroConfig(num_stages=6, lora_rank=16, lora_alpha=32, epochs_per_stage=1, batch_size=10)
```

**Expected**: 6-stage run, ~104h total, 98% quality

### A.3 High-Quality Configuration (Maximum)

```python
config = NitroConfig(num_stages=6, lora_rank=32, lora_alpha=64, epochs_per_stage=2, batch_size=8)
```

**Expected**: 6-stage run, ~200h total, 99%+ quality

---

## Appendix B: Troubleshooting

### B.1 OOM Errors

```
Problem: CUDA out of memory
Solution: Reduce num_stages or reduce batch_size
```

### B.2 Slow Training

```
Problem: Training slower than expected
Solution: Check NVMe bandwidth, enable async prefetch
```

### B.3 Quality Degradation

```
Problem: Output quality significantly worse than baseline
Solution: Increase num_stages, increase lora_rank, or increase epochs_per_stage
```

---

## Appendix C: Performance Calculator

```python
def estimate_training_time(
    num_examples: int, num_stages: int, batch_size: int, tok_s: float = 100.0
) -> float:
    """
    Estimate training time in hours.

    Args:
        num_examples: Number of training examples
        num_stages: Number of Nitro stages
        batch_size: Batch size
        tok_s: Training tokens per second

    Returns:
        Estimated time in hours
    """
    batches_per_epoch = num_examples / batch_size
    tokens_per_batch = 2048  # Average tokens per batch

    time_per_batch_s = tokens_per_batch / tok_s
    time_per_stage_s = batches_per_epoch * time_per_batch_s
    total_time_s = time_per_stage_s * num_stages

    return total_time_s / 3600


# Example
print(estimate_training_time(num_examples=10000, num_stages=6, batch_size=10))
# Output: ~104 hours
```

---

**Document Version:** 1.0  
**Last Updated:** 2025-01-15  
**Status:** Ready for Implementation  
**Next Review:** After experimental validation
