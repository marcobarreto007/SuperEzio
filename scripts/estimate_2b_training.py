#!/usr/bin/env python
"""Estimativa de custo para treinar modelo 2B do zero"""

# Parâmetros
params = 2e9  # 2B parâmetros
tokens_per_param = 20  # regra de polegar: 20 tokens por parâmetro
total_tokens = params * tokens_per_param
seq_len = 2048
total_sequences = total_tokens / seq_len

# Hardware: opções vast.ai
gpu_options = [
    {'name': 'RTX 4090', 'vram': 24, 'price': 0.35, 'tflops': 83},
    {'name': 'RTX 5090', 'vram': 32, 'price': 0.58, 'tflops': 100},
    {'name': 'RTX A6000', 'vram': 48, 'price': 0.40, 'tflops': 38},
]

# Estimativa de throughput (otimista)
# Assume 50k tokens/segundo em GPU moderna
tokens_per_second = 50000
tokens_per_hour = tokens_per_second * 3600
hours_needed = total_tokens / tokens_per_hour

print('=== Estimativa Treinamento 2B do Zero ===')
print(f'Modelo: 2B parâmetros')
print(f'Tokens: {total_tokens/1e9:.1f}B tokens')
print(f'Throughput: {tokens_per_second/1000:.0f}k tokens/s')
print(f'Tempo estimado: {hours_needed:.1f} horas ({hours_needed/24:.1f} dias)')
print()

print('=== Custo por GPU ===')
print(f"{'GPU':<15} {'VRAM':<6} {'$/h':<6} {'Custo 24h':<10} {'Custo Total':<12}")
print('-' * 55)

for gpu in gpu_options:
    daily = gpu['price'] * 24
    total = gpu['price'] * hours_needed
    print(f"{gpu['name']:<15} {gpu['vram']}GB  ${gpu['price']:<5.2f} ${daily:<9.2f} ${total:<11.2f}")

print()
print('=== Notas ===')
print('- Estimativa otimista (hardware moderno, bem configurado)')
print('- Não inclui: validação, checkpointing, data loading overhead')
print('- Preços vast.ai interruptible/spot (podem variar)')
