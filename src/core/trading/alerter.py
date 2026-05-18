"""Email alerter — sends trade alerts via SMTP."""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    from_addr: str = ""
    to_addrs: list[str] | None = None
    enabled: bool = False

    def __post_init__(self):
        if not self.smtp_host:
            self.smtp_host = os.getenv("SMTP_HOST", "")
        if not self.smtp_user:
            self.smtp_user = os.getenv("SMTP_USER", "")
        if not self.smtp_pass:
            self.smtp_pass = os.getenv("SMTP_PASS", "")
        if not self.from_addr:
            self.from_addr = os.getenv("SMTP_FROM", "")
        if not self.to_addrs:
            raw = os.getenv("SMTP_TO", "")
            self.to_addrs = [a.strip() for a in raw.split(",") if a.strip()] if raw else []


class EmailAlerter:
    """Sends email alerts for trade events."""

    def __init__(self, config: EmailConfig | None = None):
        self.config = config or EmailConfig()

    def send_trade_alert(
        self,
        subject: str,
        body: str,
    ) -> bool:
        if not self.config.enabled:
            logger.debug("Email alerts disabled — skipping send")
            return False

        if not self.config.to_addrs:
            logger.warning("No recipients configured for email alerts")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[SuperEzio] {subject}"
        msg["From"] = self.config.from_addr
        msg["To"] = ", ".join(self.config.to_addrs)
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.starttls()
                if self.config.smtp_user and self.config.smtp_pass:
                    server.login(self.config.smtp_user, self.config.smtp_pass)
                server.sendmail(
                    self.config.from_addr,
                    self.config.to_addrs,
                    msg.as_string(),
                )
            logger.info("Email alert sent: %s", subject)
            return True
        except Exception as exc:
            logger.error("Failed to send email alert: %s", exc)
            return False

    def send_approval_request(
        self,
        request_id: str,
        symbol: str,
        side: str,
        qty: float,
        risk_amount: float,
        reason: str = "",
    ) -> bool:
        body = (
            f"Trade Approval Request\n"
            f"{'=' * 40}\n"
            f"Request ID: {request_id}\n"
            f"Symbol:     {symbol}\n"
            f"Side:       {side.upper()}\n"
            f"Quantity:   {qty}\n"
            f"Risk:       ${risk_amount:,.2f}\n"
        )
        if reason:
            body += f"Reason:     {reason}\n"
        return self.send_trade_alert(
            subject=f"Approval Required: {side.upper()} {qty} {symbol}",
            body=body,
        )

    def send_kill_switch_alert(self, reason: str, daily_pnl: float) -> bool:
        body = (
            f"Kill Switch Activated\n"
            f"{'=' * 40}\n"
            f"Reason:    {reason}\n"
            f"Daily PnL: ${daily_pnl:,.2f}\n"
            f"\nAll trading has been halted."
        )
        return self.send_trade_alert(subject="Kill Switch Activated", body=body)


class LogAlerter:
    """Fallback alerter that just logs — used when email is not configured."""

    def __init__(self, config: EmailConfig | None = None):
        self.config = config or EmailConfig()

    def send_trade_alert(self, subject: str, body: str) -> bool:
        logger.info("[ALERT] %s\n%s", subject, body)
        return True

    def send_approval_request(
        self,
        request_id: str,
        symbol: str,
        side: str,
        qty: float,
        risk_amount: float,
        reason: str = "",
    ) -> bool:
        logger.info(
            "[APPROVAL] %s %s %s x%.0f risk=$%.2f id=%s",
            side.upper(),
            symbol,
            reason,
            qty,
            risk_amount,
            request_id,
        )
        return True

    def send_kill_switch_alert(self, reason: str, daily_pnl: float) -> bool:
        logger.info("[KILL_SWITCH] reason=%s daily_pnl=%.2f", reason, daily_pnl)
        return True
