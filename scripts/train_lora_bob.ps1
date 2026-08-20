# RETIRED: historical Bob 80B LoRA experiment.
# The active SuperEzio product is inference-only and uses Qwen3.8-27B through
# scripts\serve_agent_llamacpp.ps1. Training requires a separately reviewed
# training contract, dataset provenance, hardware profile, and output gate.

$ErrorActionPreference = "Stop"
Write-Error "RETIRED: scripts\train_lora_bob.ps1 is not an active or supported training entrypoint."
Write-Host "Use the inference runtime: powershell -ExecutionPolicy Bypass -File scripts\serve_agent_llamacpp.ps1 -Port 8080"
exit 2
