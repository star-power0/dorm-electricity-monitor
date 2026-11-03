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


# Reading validation: the upstream occasionally serves stale or cross-record
# cache data (2026-11-03: 9.89 -> fake 20.27 for 3 checks -> 8.84), which used
# to trigger a false recovery mail and advance the rotation cursor. Readings
# that fail these checks are rejected before they touch alerts or state.
STALE_COLLECTION_MINUTES = 60
PRICE_RATIO_TOLERANCE = 0.10


def parse_collect_time(text: str) -> datetime | None:
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def reading_issues(previous: dict | None, reading: MeterReading, now: datetime) -> list[str]:
    """Return reasons to ignore this reading; an empty list means it is trustworthy."""
    issues: list[str] = []
    collected = parse_collect_time(reading.collected_at)
    prev_collected = None
    if previous and previous.get("collectedAt"):
        prev_collected = parse_collect_time(str(previous["collectedAt"]))
    if collected is not None:
        lag_minutes = (now - collected).total_seconds() / 60
        if lag_minutes > STALE_COLLECTION_MINUTES:
            issues.append(f"采集时间滞后 {int(lag_minutes)} 分钟")
        if prev_collected is not None and collected < prev_collected:
            issues.append("采集时间早于上一次有效读数（疑似旧缓存）")
    if previous:
        prev_room = str(previous.get("roomLabel") or "")
        if prev_room and reading.room_label != prev_room:
            issues.append(f"房间信息变化（{reading.room_label}）")
        prev_balance = float(previous.get("balance") or 0)
        prev_energy = float(previous.get("energy") or 0)
        if prev_balance >= 1 and prev_energy >= 1 and reading.balance >= 1 and reading.energy >= 1:
            prev_price = prev_balance / prev_energy
            price = reading.balance / reading.energy
            if abs(price - prev_price) / prev_price > PRICE_RATIO_TOLERANCE:
                issues.append(f"金额电量比异常（{price:.3f} vs {prev_price:.3f} 元/度）")
    if reading.balance >= 1 and reading.energy <= 0:
        issues.append("有余额但电量为 0")
    return issues


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
        if not self.config.enabled_meters:
            state["lastError"] = None
            state["failureCount"] = 0
            self._append_log(state, f"{now_text()} 未查询：照明与空调均已关闭")
            write_state(state)
            if self.callback:
                self.callback(state)
            return state
        try:
            readings = self.client.get_all()
            state.setdefault("meters", {})
            state.setdefault("alerts", {})

            # Reject implausible readings before they can touch alerts, state
            # or the rotation cursor; only accepted readings drive any of it.
            accepted: list[MeterReading] = []
            rejected: list[str] = []
            for reading in readings:
                issues = reading_issues(
                    state["meters"].get(str(reading.type)), reading, datetime.now()
                )
                if issues:
                    rejected.append(
                        f"{reading.name} {reading.balance:.2f} 元（{'；'.join(issues)}）"
                    )
                    continue
                accepted.append(reading)
                self._store_reading(state, reading)
                note = self._handle_alert(state, reading)
                if note:
                    notifications_sent.append(note)

            if accepted:
                state["lastSuccessAt"] = now_text()
                state["lastError"] = None
                state["failureCount"] = 0
                self._handle_daily_heartbeat(state, accepted)
                self._append_log(state, self._build_success_log(accepted, notifications_sent))
                if rejected:
                    self._append_log(
                        state, f"{now_text()} 读数存疑已忽略：{'；'.join(rejected)}"
                    )
            else:
                # No usable data this round: treat it as a failed check so a
                # persistently bad feed still raises the failure notification.
                state["failureCount"] = int(state.get("failureCount") or 0) + 1
                state["lastError"] = "读数存疑：" + ("；".join(rejected) or "未返回任何读数")
                self._append_log(state, f"{now_text()} 查询失败：{state['lastError']}")
                if state["failureCount"] == 3:
                    self.notifier.send_template(
                        "failure",
                        build_template_variables(
                            self.config,
                            {
                                "failureCount": state["failureCount"],
                                "error": state["lastError"],
                                "time": now_text(),
                            },
                        ),
                    )
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
        pending_recovery = bool(previous.get("pendingRecovery"))
        stored_level = level
        current_cursor = int(rotation.get("cursor", 0) or 0)
        active_assignee = int(rotation.get("activeAssignee", current_cursor) or 0)
        next_assignee = rotation_member_for(self.config, current_cursor + 1)

        if level == "normal":
            if pending_recovery:
                # Second consecutive good reading: the recovery is real, now
                # send the mail and advance the rotation cursor.
                pending_recovery = False
                repeat_count = 0
                if rotation.get("armed"):
                    rotation["armed"] = False
                    rotation["cursor"] = current_cursor + 1
                    rotation["activeAssignee"] = rotation["cursor"]
                if self.config.notify_on_recovery:
                    should_notify = True
                    action_text = f"{reading.name} 已恢复正常，发送恢复提醒"
            elif previous_level != "normal":
                # First good reading after an alert: hold the recovery until
                # the next check confirms it, so a single anomalous reading
                # cannot fake a payment or skip a roommate's turn.
                pending_recovery = True
                repeat_count = previous_count
                stored_level = previous_level
                action_text = f"{reading.name} 余额回升至 {reading.balance:.2f} 元，待下轮读数确认"
            else:
                repeat_count = 0
        else:
            pending_recovery = False  # bounced back before confirmation
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
            "level": stored_level,
            "lastSeenAt": now_text(),
            "repeatCount": repeat_count,
            "lastNotifiedAt": now_text() if should_notify else previous.get("lastNotifiedAt"),
            "pendingRecovery": pending_recovery,
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
