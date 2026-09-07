from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import copy
import json
import os
import sys
from typing import Any


APP_NAME = "宿舍电费监控"
API_URL = "https://sdxt.hainanu.edu.cn/scanQRWaterCtrl_redis_hndx1/service/weixinEle/getEleInfo"


DEFAULT_EMAIL_TEMPLATES = {
    "test": {
        "subject": "[{appName}] 测试邮件 {time}",
        "body": (
            "这是一封来自 {appName} 的测试邮件。\n\n"
            "发送时间：{time}\n"
            "通知通道：{channel}\n"
            "当前收件人：{recipients}\n\n"
            "如果你能收到这封邮件，说明当前通知链路可用。"
        ),
    },
    "warning": {
        "subject": "[{appName}] {meterName} 余额偏低：{balance} 元",
        "body": (
            "{roomLabel}\n\n"
            "当前余额 {balance} 元，已经低于普通提醒阈值 {warningThreshold} 元。\n"
            "本轮请 {rotationAssignee} 交费。\n\n"
            "剩余电量：{energy} 度\n"
            "采集时间：{collectedAt}"
        ),
    },
    "critical": {
        "subject": "[{appName}] {meterName} 余额告急：{balance} 元",
        "body": (
            "{roomLabel}\n\n"
            "当前余额只剩 {balance} 元，已经低于强提醒阈值 {criticalThreshold} 元。\n"
            "本轮请 {rotationAssignee} 立刻交费。\n\n"
            "请尽快充值，避免临时断电。\n\n"
            "剩余电量：{energy} 度\n"
            "采集时间：{collectedAt}"
        ),
    },
    "recovery": {
        "subject": "[{appName}] {meterName} 已恢复正常",
        "body": (
            "{roomLabel}\n\n"
            "当前余额 {balance} 元，已经回到安全范围。\n"
            "本轮 {rotationAssignee} 已完成交费，下一轮请 {nextRotationAssignee} 负责。\n\n"
            "剩余电量：{energy} 度\n"
            "采集时间：{collectedAt}"
        ),
    },
    "failure": {
        "subject": "[{appName}] 连续查询失败提醒",
        "body": (
            "{appName} 已连续 {failureCount} 次查询失败。\n\n"
            "错误信息：{error}\n"
            "发生时间：{time}\n\n"
            "请检查电脑网络、接口状态或配置文件。"
        ),
    },
}


DEFAULT_ROTATION_MEMBERS = ["A", "B", "C", "D"]


@dataclass(frozen=True)
class MeterConfig:
    name: str
    type: int
    enabled: bool = True


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    sender: str
    password: str
    recipients: list[str]
    use_ssl: bool


@dataclass(frozen=True)
class EmailTemplate:
    subject: str
    body: str


@dataclass(frozen=True)
class SecurityConfig:
    admin_password: str


@dataclass(frozen=True)
class AppConfig:
    open_id: str
    notify_channel: str
    pushplus_token: str
    email: EmailConfig
    email_templates: dict[str, EmailTemplate]
    security: SecurityConfig
    check_interval_minutes: int
    warning_threshold: float
    critical_threshold: float
    notify_on_recovery: bool
    daily_heartbeat: bool
    heartbeat_time: str
    remind_every_checks: int
    holiday_mode: bool
    meters: list[MeterConfig]
    rotation_members: list[str]

    @property
    def enabled_meters(self) -> list[MeterConfig]:
        return [meter for meter in self.meters if meter.enabled]


def app_dir() -> Path:
    override = os.environ.get("DORM_MONITOR_APP_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


DEFAULT_CONFIG_PATH = app_dir() / "config.json"
STATE_PATH = app_dir() / "state.json"


def default_email_templates() -> dict[str, dict[str, str]]:
    return copy.deepcopy(DEFAULT_EMAIL_TEMPLATES)


def normalize_email_templates(data: Any) -> dict[str, dict[str, str]]:
    defaults = default_email_templates()
    if not isinstance(data, dict):
        return defaults
    for key, template in defaults.items():
        incoming = data.get(key)
        if not isinstance(incoming, dict):
            continue
        defaults[key] = {
            "subject": str(incoming.get("subject", template["subject"])),
            "body": str(incoming.get("body", template["body"])),
        }
    return defaults


def normalize_rotation_members(data: Any) -> list[str]:
    if isinstance(data, str):
        members = [part.strip() for part in data.split(",") if part.strip()]
    elif isinstance(data, list):
        members = [str(item).strip() for item in data if str(item).strip()]
    else:
        members = []
    return members or DEFAULT_ROTATION_MEMBERS.copy()


def normalize_raw_config(data: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(data)
    normalized["emailTemplates"] = normalize_email_templates(normalized.get("emailTemplates"))
    normalized["rotationMembers"] = normalize_rotation_members(normalized.get("rotationMembers"))
    normalized["onboardingCompleted"] = bool(normalized.get("onboardingCompleted", False))
    normalized["privacyConsentVersion"] = str(normalized.get("privacyConsentVersion", "")).strip()
    normalized["privacyConsentedAt"] = str(normalized.get("privacyConsentedAt", "")).strip()
    normalized["holidayMode"] = bool(normalized.get("holidayMode", False))
    normalized["meters"] = [
        {
            **item,
            "name": str(item.get("name", "")).strip(),
            "type": int(item.get("type", 0)),
            "enabled": bool(item.get("enabled", True)),
        }
        for item in normalized.get("meters", [])
        if isinstance(item, dict)
    ]
    return normalized


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = normalize_raw_config(raw)
    meters = [
        MeterConfig(
            name=item["name"],
            type=int(item["type"]),
            enabled=bool(item.get("enabled", True)),
        )
        for item in data["meters"]
    ]
    email_data = data.get("email", {})
    recipients_raw = email_data.get("recipients", email_data.get("recipient", []))
    if isinstance(recipients_raw, str):
        recipients = [part.strip() for part in recipients_raw.split(",") if part.strip()]
    else:
        recipients = [str(part).strip() for part in recipients_raw if str(part).strip()]
    templates = {
        key: EmailTemplate(subject=value["subject"], body=value["body"])
        for key, value in data["emailTemplates"].items()
    }
    return AppConfig(
        open_id=str(data["openId"]).strip(),
        notify_channel=str(data.get("notifyChannel", "email")).strip().lower(),
        pushplus_token=str(data.get("pushplusToken", "")).strip(),
        email=EmailConfig(
            smtp_host=str(email_data.get("smtpHost", "smtp.qq.com")).strip(),
            smtp_port=int(email_data.get("smtpPort", 465)),
            sender=str(email_data.get("sender", "")).strip(),
            password=str(email_data.get("password", "")).strip(),
            recipients=recipients,
            use_ssl=bool(email_data.get("useSsl", True)),
        ),
        email_templates=templates,
        security=SecurityConfig(
            admin_password=str((data.get("security") or {}).get("adminPassword", "")).strip(),
        ),
        check_interval_minutes=int(data.get("checkIntervalMinutes", 30)),
        warning_threshold=float(data.get("warningThreshold", 10)),
        critical_threshold=float(data.get("criticalThreshold", 5)),
        notify_on_recovery=bool(data.get("notifyOnRecovery", True)),
        daily_heartbeat=bool(data.get("dailyHeartbeat", False)),
        heartbeat_time=str(data.get("heartbeatTime", "22:00")),
        remind_every_checks=int(data.get("remindEveryChecks", 3)),
        holiday_mode=bool(data.get("holidayMode", False)),
        meters=meters,
        rotation_members=normalize_rotation_members(data.get("rotationMembers")),
    )


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "lastCheckAt": None,
            "lastSuccessAt": None,
            "lastError": None,
            "failureCount": 0,
            "meters": {},
            "alerts": {},
            "rotationState": {},
            "logs": [],
            "lastHeartbeatDate": None,
        }
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise json.JSONDecodeError("state must be an object", path.as_posix(), 0)
        state.setdefault("rotationState", {})
        return state
    except json.JSONDecodeError:
        return {
            "lastCheckAt": None,
            "lastSuccessAt": None,
            "lastError": "状态文件损坏，已临时重置读取结果。",
            "failureCount": 0,
            "meters": {},
            "alerts": {},
            "rotationState": {},
            "logs": [],
            "lastHeartbeatDate": None,
        }


def write_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
