"""
SuperEzio - Notification Engine
------------------------------
Gerencia o envio de alertas críticos (Telegram, Push, etc.).
"""

import requests
import os
import logging

logger = logging.getLogger(__name__)


class NotificationEngine:
    def __init__(self):
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def send_alert(self, message: str, level: str = "INFO"):
        """Envia um alerta para os canais configurados."""
        prefix = "🚨" if level in ["CRITICAL", "BLACK"] else "⚠️"
        formatted_msg = f"{prefix} [{level}] SuperEzio: {message}"

        # Log local
        logger.info(formatted_msg)

        # 1. Telegram Push (se configurado)
        if self.telegram_token and self.telegram_chat_id:
            try:
                url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                requests.post(
                    url,
                    json={
                        "chat_id": self.telegram_chat_id,
                        "text": formatted_msg,
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )
            except Exception as exc:
                logger.warning("Telegram alert failed: %s", exc)


notifier = NotificationEngine()
