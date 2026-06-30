from __future__ import annotations

from email.message import EmailMessage
import smtplib
from typing import Any

import requests

from .config import APP_NAME, AppConfig, MeterConfig, default_email_templates


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
        self.config = config
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

    def send_template(self, template_key: str, variables: dict[str, Any]) -> None:
        if self.channel == "pushplus":
            template = default_email_templates().get(template_key)
            if not template:
                raise ValueError(f"unknown template: {template_key}")
            title = render_template_text(template["subject"], variables)
            content = render_template_text(template["body"], variables)
            self.pushplus.send(title, content)
            return
        title, content = self.render_email_template(template_key, variables)
        self.send(title, content)

    def render_email_template(self, template_key: str, variables: dict[str, Any]) -> tuple[str, str]:
        template = self.config.email_templates.get(template_key)
        if not template:
            raise ValueError(f"unknown template: {template_key}")
        return (
            render_template_text(template.subject, variables),
            render_template_text(template.body, variables),
        )


def build_template_variables(config: AppConfig, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "appName": APP_NAME,
        "channel": config.notify_channel or "email",
        "recipients": ", ".join(config.email.recipients),
        "warningThreshold": format_decimal(config.warning_threshold),
        "criticalThreshold": format_decimal(config.critical_threshold),
        "meterName": "",
        "roomLabel": "",
        "buildingLabel": "",
        "balance": "",
        "energy": "",
        "collectedAt": "",
        "level": "",
        "time": "",
        "rotationAssignee": "",
        "rotationCursor": "",
    }
    if overrides:
        for key, value in overrides.items():
            data[key] = stringify_template_value(value)
    return data


def build_variables_for_meter(config: AppConfig, meter: MeterConfig | Any, level: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    data = build_template_variables(
        config,
        {
            "meterName": getattr(meter, "name", ""),
            "roomLabel": getattr(meter, "room_label", ""),
            "buildingLabel": getattr(meter, "building_label", ""),
            "balance": format_decimal(getattr(meter, "balance", "")),
            "energy": format_decimal(getattr(meter, "energy", "")),
            "collectedAt": getattr(meter, "collected_at", ""),
            "level": level,
        },
    )
    if extra:
        for key, value in extra.items():
            data[key] = stringify_template_value(value)
    return data


def render_template_text(template: str, variables: dict[str, Any]) -> str:
    safe_variables = {key: stringify_template_value(value) for key, value in variables.items()}
    try:
        return template.format_map(SafeFormatDict(safe_variables))
    except ValueError as exc:
        raise ValueError(f"模板格式错误：{exc}") from exc


class SafeFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def stringify_template_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def format_decimal(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return stringify_template_value(value)
