"""Bridge MIKE <-> SuperEzio (Fase 3).

Processo próprio, uvicorn em 127.0.0.1:8009. Coleta por polling + diff no Ezio,
publica no MIKE pelo canal de notificacao que ja existe, e aceita comando
allowlistado em POST /commands.

Nunca le .env, nunca persiste comando, nunca faz bind fora de loopback.
"""

__version__ = "0.1.0"
