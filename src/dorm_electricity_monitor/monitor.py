from __future__ import annotations

from datetime import datetime
from typing import Callable
import traceback

from .config import AppConfig, now_text, read_state, write_state
from .electricity import ElectricityClient, MeterReading
from .notifier import MultiNotifier, build_template_variables, build_variables_for_meter

StatusCallback = Callable[[dict], None]


def level_for_balance(balance: float, warning: float, critical: float) -> str:
    if balance < critical:
        return "critical"
    if balance < warning:
        return "warning"
    return "normal"


def rotation_state_for(state: dict, meter_key: str) -> dict:
    rotation_state = state.setdefault("rotationState", {})
    current = rotation_state.get(meter_key)
    if not isinstance(current, dict):
        current = {"cursor": 0, "activeAssignee": 0, "armed": False}
        rotation_state[meter_key] = current
    current.setdefault("cursor", 0)
    current.setdefault("activeAssignee", 0)
    current.setdefault("armed", False)
    return current


def rotation_member_for(config: AppConfig, cursor: int) -> str:
    members = config.rotation_members or ["A", "B", "C", "D"]
    return members[cursor % len(members)] if members else ""


def repeat_interval_for(config: AppConfig) -> int:
    return max(1, int(config.remind_every_checks or 1))


class MonitorEngine:
    def __init__(self, config: AppConfig, callback: StatusCallback | None = None) -> None:
        self.config = config
        self.client = ElectricityClient(config)
        self.notifier = MultiNotifier(config)
        self.callback = callback

    def check_once(self) -> dict:
        state = read_state()
        if self.config.holiday_mode:
            return state
        state.setdefault("logs", [])
        state.setdefault("rotationState", {})
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
                self.notifier.send_template(
                    "failure",
                    build_template_variables(
                        self.config,
                        {
                            "failureCount": state["failureCount"],
                            "error": exc,
                            "time": now_text(),
                        },
                    ),
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
        rotation = rotation_state_for(state, key)
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
        current_cursor = int(rotation.get("cursor", 0) or 0)
        active_assignee = int(rotation.get("activeAssignee", current_cursor) or 0)
        next_assignee = rotation_member_for(self.config, current_cursor + 1)

        if level == "normal":
            if previous_level != "normal" and self.config.notify_on_recovery:
                should_notify = True
                action_text = f"{reading.name} 已恢复正常，发送恢复提醒"
            repeat_count = 0
            if rotation.get("armed"):
                rotation["armed"] = False
                rotation["cursor"] = current_cursor + 1
                rotation["activeAssignee"] = rotation["cursor"]
        else:
            if not rotation.get("armed"):
                rotation["armed"] = True
                rotation["activeAssignee"] = current_cursor
                active_assignee = current_cursor
                should_notify = True
                action_text = f"{reading.name} 进入{self._level_cn(level)}，已发送提醒"
                repeat_count = 0
            elif previous_level != level:
                should_notify = True
                action_text = f"{reading.name} 进入{self._level_cn(level)}，已发送提醒"
                repeat_count = 0
            else:
                repeat_count = previous_count + 1
                if repeat_count >= repeat_interval_for(self.config):
                    should_notify = True
                    action_text = f"{reading.name} 持续{self._level_cn(level)}，累计 {repeat_interval_for(self.config)} 次检查再次提醒"
                    repeat_count = 0

        assignee = rotation_member_for(self.config, active_assignee)
        payload = build_variables_for_meter(
            self.config,
            reading,
            level,
            {
                "time": now_text(),
                "rotationAssignee": assignee,
                "nextRotationAssignee": next_assignee,
                "rotationCursor": current_cursor,
            },
        )
        if should_notify:
            template_key = "recovery" if level == "normal" else level
            self.notifier.send_template(template_key, payload)

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
            notes = "；".join(notifications_sent)
            return f"{now_text()} 查询成功：{summary}。{notes}"
        return f"{now_text()} 查询成功：{summary}。未触发提醒。"

    def _level_cn(self, level: str) -> str:
        return {"warning": "偏低", "critical": "告急", "normal": "正常"}.get(level, level)
