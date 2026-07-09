from __future__ import annotations

from pathlib import Path
import json
import sys
import traceback
from typing import Any

from .config import DEFAULT_CONFIG_PATH, load_config, normalize_raw_config, now_text, read_state
from .monitor import MonitorEngine
from .notifier import MultiNotifier, build_template_variables


def _print_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()


def _load_raw_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    return normalize_raw_config(json.loads(path.read_text(encoding="utf-8")))


def _save_raw_config(data: dict[str, Any], path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    normalized = normalize_raw_config(data)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    load_config(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _command_bootstrap() -> dict[str, Any]:
    return {
        "state": read_state(),
        "config": _load_raw_config(),
    }


def _command_get_state() -> dict[str, Any]:
    return read_state()


def _command_check_once() -> dict[str, Any]:
    config = load_config()
    engine = MonitorEngine(config)
    return engine.check_once()


def _command_get_config() -> dict[str, Any]:
    return _load_raw_config()


def _command_save_config() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("missing config payload")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("config payload must be an object")
    return _save_raw_config(data)


def _command_send_test_mail() -> dict[str, Any]:
    config = load_config()
    if config.holiday_mode:
        raise RuntimeError("假期模式已开启，请先关闭假期模式。")
    notifier = MultiNotifier(config)
    notifier.send_template("test", build_template_variables(config, {"time": now_text()}))
    return {"sent": True, "channel": config.notify_channel}


COMMANDS = {
    "bootstrap": _command_bootstrap,
    "get-state": _command_get_state,
    "check-once": _command_check_once,
    "get-config": _command_get_config,
    "save-config": _command_save_config,
    "send-test-mail": _command_send_test_mail,
}


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        _print_json({
            "ok": False,
            "error": "missing command",
            "availableCommands": list(COMMANDS.keys()),
        })
        return 1

    command = args[0]
    handler = COMMANDS.get(command)
    if handler is None:
        _print_json({
            "ok": False,
            "error": f"unknown command: {command}",
            "availableCommands": list(COMMANDS.keys()),
        })
        return 1

    try:
        data = handler()
    except Exception as exc:  # pragma: no cover
        _print_json(
            {
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=6),
            }
        )
        return 1

    _print_json({"ok": True, "data": data})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
