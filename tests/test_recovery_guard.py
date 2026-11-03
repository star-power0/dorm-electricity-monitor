"""Regression tests for the 2026-11-03 false-recovery incident.

Usage:
    python tests/test_recovery_guard.py [package_parent]

package_parent is the directory that contains ``dorm_electricity_monitor/``
(default: <repo>/src). Point it at a pristine copy of monitor.py to see the
tests fail, and at src/ to see them pass.
"""

from __future__ import annotations

import copy
import sys
from datetime import datetime
from pathlib import Path

package_parent = (
    Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "src"
)
sys.path.insert(0, str(package_parent))

from dorm_electricity_monitor import monitor  # noqa: E402
from dorm_electricity_monitor.config import (  # noqa: E402
    AppConfig,
    EmailConfig,
    MeterConfig,
    SecurityConfig,
)
from dorm_electricity_monitor.electricity import MeterReading  # noqa: E402

MEMBERS = ["黄泼", "黄志强", "柯子晶", "李嘉哲"]
ROOM = "5号楼 516 室 · 空调"
BUILDING = "5号楼 空调"


def make_config() -> AppConfig:
    return AppConfig(
        open_id="test-open-id",
        notify_channel="email",
        pushplus_token="",
        email=EmailConfig(
            smtp_host="smtp.qq.com",
            smtp_port=465,
            sender="test@qq.com",
            password="x",
            recipients=["a@qq.com"],
            use_ssl=True,
        ),
        email_templates={},
        security=SecurityConfig(admin_password="pw"),
        check_interval_minutes=30,
        warning_threshold=10,
        critical_threshold=5,
        notify_on_recovery=True,
        daily_heartbeat=False,
        heartbeat_time="22:00",
        remind_every_checks=3,
        holiday_mode=False,
        meters=[MeterConfig(name="空调", type=2, enabled=True)],
        rotation_members=list(MEMBERS),
    )


class FakeClient:
    def __init__(self) -> None:
        self.queue: list[list[MeterReading]] = []

    def get_all(self) -> list[MeterReading]:
        return self.queue.pop(0)


class FakeNotifier:
    def __init__(self) -> None:
        self.templates: list[tuple[str, dict]] = []
        self.plain: list[str] = []

    @property
    def enabled(self) -> bool:
        return True

    def send_template(self, template_key: str, variables: dict) -> None:
        self.templates.append((template_key, variables))

    def send(self, title: str, content: str) -> None:
        self.plain.append(title)


def incident_seed() -> dict:
    """State right after the 08:46 warning on 2026-11-03 (cursor 10 = 柯子晶)."""
    return {
        "lastCheckAt": "2026-11-03 09:16:06",
        "lastSuccessAt": "2026-11-03 09:16:06",
        "lastError": None,
        "failureCount": 0,
        "meters": {
            "2": {
                "name": "空调",
                "roomLabel": ROOM,
                "buildingLabel": BUILDING,
                "balance": 9.89,
                "energy": 16.22,
                "collectedAt": "2026-11-03 09:16:05",
                "level": "warning",
            }
        },
        "alerts": {
            "2": {
                "level": "warning",
                "lastSeenAt": "2026-11-03 09:16:06",
                "repeatCount": 1,
                "lastNotifiedAt": "2026-11-03 08:46:08",
            }
        },
        "rotationState": {"2": {"cursor": 10, "activeAssignee": 10, "armed": True}},
        "logs": [],
        "lastHeartbeatDate": None,
    }


def reading(
    balance: float,
    energy: float,
    mon_time: str | None = None,
    room: str = ROOM,
) -> MeterReading:
    return MeterReading(
        name="空调",
        type=2,
        room_label=room,
        building_label=BUILDING,
        balance=balance,
        energy=energy,
        collected_at=mon_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


class Runner:
    """Run one engine against a seeded state and capture the written state."""

    def __init__(self, state: dict) -> None:
        self.state = copy.deepcopy(state)
        self.engine = monitor.MonitorEngine(make_config())
        self.engine.client = FakeClient()
        self.engine.notifier = FakeNotifier()
        monitor.read_state = lambda: copy.deepcopy(self.state)
        monitor.write_state = lambda new_state: setattr(
            self, "state", copy.deepcopy(new_state)
        )

    def check(self, *readings: MeterReading) -> dict:
        self.engine.client.queue.append(list(readings))
        return self.engine.check_once()

    @property
    def templates(self) -> list[tuple[str, dict]]:
        return self.engine.notifier.templates

    @property
    def rotation(self) -> dict:
        return self.state["rotationState"]["2"]

    @property
    def alert(self) -> dict:
        return self.state["alerts"]["2"]

    @property
    def meter(self) -> dict:
        return self.state["meters"]["2"]


def test_01_stale_cache_reading_is_rejected() -> None:
    """The 2026-11-03 fake 20.27 must not trigger recovery or cursor advance."""
    runner = Runner(incident_seed())
    stale = reading(20.27, 33.26, mon_time="2026-11-01 20:00:00")
    runner.check(stale)
    assert runner.templates == [], f"stale reading sent mail: {runner.templates}"
    assert runner.rotation["cursor"] == 10, "cursor advanced on stale reading"
    assert runner.alert["level"] == "warning", "alert level overwritten by stale reading"
    assert runner.meter["balance"] == 9.89, "stale balance stored as truth"
    assert runner.state["failureCount"] == 1, "rejected reading not counted as failure"
    assert any("读数存疑" in line for line in runner.state["logs"]), (
        "rejection not visible in logs"
    )


def test_02_recovery_waits_for_confirmation() -> None:
    """A real recharge keeps data accepted but defers mail and cursor advance."""
    runner = Runner(incident_seed())
    runner.check(reading(55.49, 91.06))  # first good reading after alert
    assert runner.meter["balance"] == 55.49, "legit recharge was wrongly rejected"
    assert runner.templates == [], "recovery mail sent before confirmation"
    assert runner.rotation["cursor"] == 10, "cursor advanced before confirmation"
    assert runner.rotation["armed"] is True, "disarmed before confirmation"

    runner.check(reading(55.17, 90.52))  # second good reading confirms
    recovery_mails = [t for t in runner.templates if t[0] == "recovery"]
    assert len(recovery_mails) == 1, f"expected 1 recovery mail, got {runner.templates}"
    assert recovery_mails[0][1]["rotationAssignee"] == "柯子晶", (
        "recovery mail credits the wrong person"
    )
    assert runner.rotation["cursor"] == 11, "cursor not advanced after confirmation"
    assert runner.rotation["armed"] is False, "still armed after confirmed recovery"


def test_03_bounce_before_confirmation_changes_nothing() -> None:
    """Balance dips back to warning before the confirming reading: no mail."""
    runner = Runner(incident_seed())
    runner.check(reading(15.00, 24.60))  # pending recovery
    runner.check(reading(9.00, 14.77))  # bounce back to warning
    assert runner.templates == [], f"bounce produced mail: {runner.templates}"
    assert runner.rotation["cursor"] == 10, "cursor moved during bounced recovery"
    assert runner.rotation["armed"] is True, "lost armed flag during bounce"
    assert runner.alert["level"] == "warning", "alert level lost during bounce"
    assert "pendingRecovery" not in runner.alert or not runner.alert["pendingRecovery"], (
        "pending recovery flag not cleared after bounce"
    )


def test_04_money_energy_ratio_glitch_is_rejected() -> None:
    """Money jumps without matching energy: same timestamp, impossible ratio."""
    runner = Runner(incident_seed())
    runner.check(reading(20.27, 16.22))  # money doubled, energy unchanged
    assert runner.templates == [], "inconsistent reading sent mail"
    assert runner.rotation["cursor"] == 10, "cursor advanced on inconsistent reading"
    assert runner.meter["balance"] == 9.89, "inconsistent balance stored"
    assert runner.state["failureCount"] == 1, "inconsistent reading not counted"


def test_05_room_change_is_rejected() -> None:
    """A record for another room must never drive this room's alerts."""
    runner = Runner(incident_seed())
    runner.check(reading(20.27, 33.26, room="5号楼 517 室 · 空调"))
    assert runner.templates == [], "other-room reading sent mail"
    assert runner.rotation["cursor"] == 10, "cursor advanced on other-room reading"
    assert runner.meter["roomLabel"] == ROOM, "room label overwritten"


def test_06_money_without_energy_is_rejected() -> None:
    """Balance >= 1 with zero remaining energy is internally impossible."""
    runner = Runner(incident_seed())
    runner.check(reading(20.27, 0.0))
    assert runner.meter["balance"] == 9.89, "money-without-energy stored"
    assert runner.state["failureCount"] == 1, "not counted as failure"


def test_07_three_rejected_rounds_send_failure_mail() -> None:
    """A persistently bad feed still surfaces through the failure template."""
    runner = Runner(incident_seed())
    stale = reading(20.27, 33.26, mon_time="2026-11-01 20:00:00")
    for _ in range(3):
        runner.check(stale)
    failure_mails = [t for t in runner.templates if t[0] == "failure"]
    assert len(failure_mails) == 1, f"expected 1 failure mail, got {runner.templates}"
    assert runner.rotation["cursor"] == 10, "cursor advanced during failure streak"


def test_08_normal_flow_still_works() -> None:
    """Warning entry and repeat reminders must keep working as before."""
    seed = incident_seed()
    seed["alerts"]["2"] = {
        "level": "normal",
        "lastSeenAt": "2026-11-03 08:16:06",
        "repeatCount": 0,
        "lastNotifiedAt": None,
    }
    seed["rotationState"]["2"] = {"cursor": 10, "activeAssignee": 10, "armed": False}
    seed["meters"]["2"].update({"balance": 11.48, "energy": 18.83, "level": "normal"})
    runner = Runner(seed)
    runner.check(reading(9.89, 16.22))  # crosses into warning
    warning_mails = [t for t in runner.templates if t[0] == "warning"]
    assert len(warning_mails) == 1, f"warning entry mail missing: {runner.templates}"
    assert warning_mails[0][1]["rotationAssignee"] == "柯子晶"
    assert runner.rotation["armed"] is True
    assert runner.rotation["cursor"] == 10, "cursor must not move on warning entry"

    for _ in range(2):  # repeat counting, no mail yet
        runner.check(reading(9.50, 15.58))
    assert len(runner.templates) == 1, "repeat reminder fired too early"
    runner.check(reading(9.20, 15.09))  # third check -> repeat reminder
    assert len(runner.templates) == 2, "repeat reminder did not fire on interval"


TESTS = [
    test_01_stale_cache_reading_is_rejected,
    test_02_recovery_waits_for_confirmation,
    test_03_bounce_before_confirmation_changes_nothing,
    test_04_money_energy_ratio_glitch_is_rejected,
    test_05_room_change_is_rejected,
    test_06_money_without_energy_is_rejected,
    test_07_three_rejected_rounds_send_failure_mail,
    test_08_normal_flow_still_works,
]


def main() -> int:
    failed = []
    for test in TESTS:
        try:
            test()
        except AssertionError as exc:
            failed.append((test.__name__, str(exc)))
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - report, keep running
            failed.append((test.__name__, repr(exc)))
            print(f"ERROR {test.__name__}: {exc!r}")
        else:
            print(f"PASS {test.__name__}")
    print(f"\n{len(TESTS) - len(failed)}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
