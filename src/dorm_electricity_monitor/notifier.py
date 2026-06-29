from __future__ import annotations

from email.message import EmailMessage
import smtplib

import requests

from .config import AppConfig


class PushPlusNotifier:
    def __init__(self, token: str) -> None:
        self.token = token.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def send(self, title: str, content: str) -> None:
        if not self.enabled:
            return
        response = requests.post(
            "https://www.pushplus.plus/send",
            json={
                "token": self.token,
                "title": title,
                "content": content,
                "template": "txt",
            },
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") not in (200, "200"):
            raise RuntimeError(f"PushPlus 推送失败：{payload}")


class EmailNotifier:
    def __init__(self, smtp_host: str, smtp_port: int, sender: str, password: str, recipients: list[str], use_ssl: bool = True) -> None:
        self.smtp_host = smtp_host.strip()
        self.smtp_port = smtp_port
        self.sender = sender.strip()
        self.password = password.strip()
        self.recipients = recipients
        self.use_ssl = use_ssl

    @property
    def enabled(self) -> bool:
        return all([self.smtp_host, self.smtp_port, self.sender, self.password, self.recipients])

    def send(self, title: str, content: str) -> None:
        if not self.enabled:
            return
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        message.set_content(content)

        if self.use_ssl:
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.login(self.sender, self.password)
                server.send_message(message)
        else:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(self.sender, self.password)
                server.send_message(message)


class MultiNotifier:
    def __init__(self, config: AppConfig) -> None:
        self.channel = config.notify_channel
        self.pushplus = PushPlusNotifier(config.pushplus_token)
        self.email = EmailNotifier(
            smtp_host=config.email.smtp_host,
            smtp_port=config.email.smtp_port,
            sender=config.email.sender,
            password=config.email.password,
            recipients=config.email.recipients,
            use_ssl=config.email.use_ssl,
        )

    @property
    def enabled(self) -> bool:
        if self.channel == "pushplus":
            return self.pushplus.enabled
        if self.channel == "email":
            return self.email.enabled
        return self.pushplus.enabled or self.email.enabled

    def send(self, title: str, content: str) -> None:
        if self.channel == "pushplus":
            self.pushplus.send(title, content)
            return
        if self.channel == "email":
            self.email.send(title, content)
            return
        if self.email.enabled:
            self.email.send(title, content)
        elif self.pushplus.enabled:
            self.pushplus.send(title, content)
