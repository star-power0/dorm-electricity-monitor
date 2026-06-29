from __future__ import annotations

from datetime import datetime
from typing import Callable
import traceback

from .config import AppConfig, now_text, read_state, write_state
from .electricity import ElectricityClient, MeterReading
from .notifier import MultiNotifier

StatusCallback = Callable[[dict], None]


def level_for_balance(balance: float, warning: float, critical: float) -> str:
    if balance < critical:
        return "critical"
    if balance < warning:
        return "warning"
    return "normal"


def title_for_level(level: str) -> str:
    if level == "critical":
        return "宿舍电费余额告急"
    if level == "warning":
        return "宿舍电费余额偏低"
    return "宿舍电费监控恢复正常"


def message_for_reading(reading: MeterReading, level: str, config: AppConfig) -> str:
    if level == "critical":
        return (
            f"{reading.room_label}\n\n"
            f"当前余额只剩 {reading.balance:.2f} 元，已经低于 {config.critical_threshold:g} 元。\n"
            "请尽快充值，避免临时断电。\n\n"
            f"剩余电量：{reading.energy:.2f} 度\n"
            f"采集时间：{reading.collected_at}"
        )
    if level == "warning":
        return (
            f"{reading.room_label}\n\n"
            f"当前余额 {reading.balance:.2f} 元，已经低于 {config.warning_threshold:g} 元。\n"
            "建议今天顺手充一下。\n\n"
            f"剩余电量：{reading.energy:.2f} 度\n"
            f"采集时间：{reading.collected_at}"
        )
    return (
        f"{reading.room_label}\n\n"
        f"当前余额 {reading.balance:.2f} 元，已经回到安全范围。\n"
        f"剩余电量：{reading.energy:.2f} 度\n"
        f"采集时间：{reading.collected_at}"
    )


class MonitorEngine:
    def __init__(self, config: AppConfig, callback: StatusCallback | None = None) -> None:
        self.config = config
        self.client = ElectricityClient(config)
        self.notifier = MultiNotifier(config)
        self.callback = callback

    def check_once(self) -> dict:
        state = read_state()
        state.setdefault("logs", [])
        state["lastCheckAt"] = now_text()
        notifications_sent: list[str] = []
        try:
            readings = self.client.get_all()
            state["lastSuccessAt"] = now_text()
            state["lastError"] = None
            state["failureCount"] = 0
            state.setdefault("meters", {})
            state.setdefault("alerts", {})

            for reading in readings:
                self._store_reading(state, reading)
                note = self._handle_alert(state, reading)
                if note:
                    notifications_sent.append(note)

            self._handle_daily_heartbeat(state, readings)
            self._append_log(state, self._build_success_log(readings, notifications_sent))
        except Exception as exc:
            state["failureCount"] = int(state.get("failureCount") or 0) + 1
            state["lastError"] = f"{exc}\n{traceback.format_exc(limit=3)}"
            self._append_log(state, f"{now_text()} 查询失败：{exc}")
            if state["failureCount"] == 3:
                self.notifier.send(
                    "电费监控暂时查不到余额",
                    "已经连续 3 次查询失败。请检查电脑网络、接口状态或配置文件。",
                )
        write_state(state)
        if self.callback:
            self.callback(state)
        return state

    def _store_reading(self, state: dict, reading: MeterReading) -> None:
        level = level_for_balance(
            reading.balance,
            self.config.warning_threshold,
            self.config.critical_threshold,
        )
        state["meters"][str(reading.type)] = {
            "name": reading.name,
            "roomLabel": reading.room_label,
            "buildingLabel": reading.building_label,
            "balance": reading.balance,
            "energy": reading.energy,
            "collectedAt": reading.collected_at,
            "level": level,
        }

    def _handle_alert(self, state: dict, reading: MeterReading) -> str | None:
        key = str(reading.type)
        previous = state.setdefault("alerts", {}).get(key, {})
        previous_level = previous.get("level", "normal")
        previous_count = int(previous.get("repeatCount", 0) or 0)
        level = level_for_balance(
            reading.balance,
            self.config.warning_threshold,
            self.config.critical_threshold,
        )

        should_notify = False
        action_text = None
        repeat_count = 1

        if level == "normal":
            if previous_level != "normal" and self.config.notify_on_recovery:
                should_notify = True
                action_text = f"{reading.name} 已恢复正常，发送恢复提醒"
            repeat_count = 0
        else:
            if level != previous_level:
                should_notify = True
                repeat_count = 1
                action_text = f"{reading.name} 进入{self._level_cn(level)}，已发送提醒"
            else:
                repeat_count = previous_count + 1
                if repeat_count >= self.config.remind_every_checks:
                    should_notify = True
                    action_text = f"{reading.name} 持续{self._level_cn(level)}，第 {repeat_count} 次检查再次提醒"
                    repeat_count = 0
                else:
                    action_text = f"{reading.name} 仍为{self._level_cn(level)}，本次未重复发送"

        if should_notify:
            self.notifier.send(title_for_level(level), message_for_reading(reading, level, self.config))

        state["alerts"][key] = {
            "level": level,
            "lastSeenAt": now_text(),
            "repeatCount": repeat_count,
            "lastNotifiedAt": now_text() if should_notify else previous.get("lastNotifiedAt"),
        }
        return action_text

    def _handle_daily_heartbeat(self, state: dict, readings: list[MeterReading]) -> None:
        if not self.config.daily_heartbeat or not self.notifier.enabled:
            return
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        hour_minute = now.strftime("%H:%M")
        if hour_minute < self.config.heartbeat_time or state.get("lastHeartbeatDate") == today:
            return
        lines = ["电费监控正常运行。", ""]
        for reading in readings:
            lines.append(f"{reading.room_label}：{reading.balance:.2f} 元，{reading.energy:.2f} 度")
        self.notifier.send("宿舍电费监控正常", "\n".join(lines))
        state["lastHeartbeatDate"] = today

    def _append_log(self, state: dict, line: str) -> None:
        logs = state.setdefault("logs", [])
        logs.insert(0, line)
        del logs[50:]

    def _build_success_log(self, readings: list[MeterReading], notifications_sent: list[str]) -> str:
        summary = "；".join([f"{reading.name} {reading.balance:.2f} 元" for reading in readings])
        if notifications_sent:
            return f"{now_text()} 查询成功：{summary}。{"；".join(notifications_sent)}"
        return f"{now_text()} 查询成功：{summary}。未触发提醒。"

    def _level_cn(self, level: str) -> str:
        return {"warning": "偏低", "critical": "告急", "normal": "正常"}.get(level, level)
