from dorm_electricity_monitor.config import load_config
from dorm_electricity_monitor.notifier import MultiNotifier

notifier = MultiNotifier(load_config())
notifier.send(
    "宿舍电费监控测试邮件",
    "这是一封测试邮件。\n\n如果你能收到，说明 QQ 邮箱提醒已经配置成功。",
)
print("Test email sent.")
