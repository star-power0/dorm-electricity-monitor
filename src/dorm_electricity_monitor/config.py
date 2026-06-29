from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import os
import sys
from typing import Any


APP_NAME = "宿舍电费监控"
API_URL = "https://sdxt.hainanu.edu.cn/scanQRWaterCtrl_redis_hndx1/service/weixinEle/getEleInfo"


def app_dir() -> Path:
    override = os.environ.get("DORM_MONITOR_APP_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


DEFAULT_CONFIG_PATH = app_dir() / "config.json"
STATE_PATH = app_dir() / "state.json"


@dataclass(frozen=True)
class MeterConfig:
    name: str
    type: int


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    sender: str
    password: str
    recipients: list[str]
    use_ssl: bool


@dataclass(frozen=True)
class SecurityConfig:
    admin_password: str


@dataclass(frozen=True)
class AppConfig:
    open_id: str
    notify_channel: str
    pushplus_token: str
    email: EmailConfig
    security: SecurityConfig
    check_interval_minutes: int
    warning_threshold: float
    critical_threshold: float
    notify_on_recovery: bool
    daily_heartbeat: bool
    heartbeat_time: str
    remind_every_checks: int
    meters: list[MeterConfig]


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    meters = [MeterConfig(name=item["name"], type=int(item["type"])) for item in data["meters"]]
    email_data = data.get("email", {})
    recipients_raw = email_data.get("recipients", email_data.get("recipient", []))
    if isinstance(recipients_raw, str):
        recipients = [part.strip() for part in recipients_raw.split(",") if part.strip()]
    else:
        recipients = [str(part).strip() for part in recipients_raw if str(part).strip()]
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
        security=SecurityConfig(
            admin_password=str((data.get("security") or {}).get("adminPassword", "123456")).strip(),
        ),
        check_interval_minutes=int(data.get("checkIntervalMinutes", 30)),
        warning_threshold=float(data.get("warningThreshold", 10)),
        critical_threshold=float(data.get("criticalThreshold", 5)),
        notify_on_recovery=bool(data.get("notifyOnRecovery", True)),
        daily_heartbeat=bool(data.get("dailyHeartbeat", False)),
        heartbeat_time=str(data.get("heartbeatTime", "22:00")),
        remind_every_checks=int(data.get("remindEveryChecks", 3)),
        meters=meters,
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
            "logs": [],
            "lastHeartbeatDate": None,
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "lastCheckAt": None,
            "lastSuccessAt": None,
            "lastError": "状态文件损坏，已临时重置读取结果。",
            "failureCount": 0,
            "meters": {},
            "alerts": {},
            "logs": [],
            "lastHeartbeatDate": None,
        }


def write_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
