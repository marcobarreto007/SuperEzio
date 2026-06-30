#!/usr/bin/env python
"""Vast.ai RTX 5090 checker"""

from vastai.sync import SyncClient
from vastai.data.query import Query

client = SyncClient()
q = Query({
    'gpu_filter': {'gpu_name': 'rtx5090', 'gpu_ram': {'min': 24}},
    'rental': {'rental_type': 'interruptible', 'min_duration': 86400}
})

print("Buscando RTX 5090 interruptíveis...")
offers = client.search(q, limit=10)

print(f"\n{len(offers)} ofertas encontradas:\n")
for o in offers[:5]:
    print(f"ID: {o.id}")
    print(f"GPU: {o.gpu_name}")
    print(f"VRAM: {o.gpu_ram} GB")
    print(f"Preço: ${o.price}/hr")
    print(f"Host ID: {o.host_id}")
    print(f"Reliability: {o.reliability}%")
    print(f"Disk: {o.disk_storage} GB")
    print("---")
