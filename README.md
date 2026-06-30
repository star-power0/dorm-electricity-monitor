# 宿舍电费监控

一个 Windows 本地桌面程序，用来监控宿舍照明和空调电费余额。

## 当前方向

当前项目现在采用：

- Electron 桌面壳
- React + TypeScript + Vite 前端界面
- Python 核心逻辑保留
- Electron 主进程负责托盘、自启动、定时检查
- Python 负责查余额、判定阈值、发送提醒、读写配置与状态

## 目录结构

- `src/dorm_electricity_monitor/`：Python 核心逻辑
- `src/dorm_electricity_monitor/bridge.py`：Electron 调用的 Python bridge
- `desktop/`：Electron + React 桌面界面
- `scripts/`：启动、打包、测试脚本

## 核心能力

- 托盘常驻
- 开机自启动
- 定时检查余额
- QQ 邮箱提醒
- 收件人可视化编辑
- 设置页敏感项解锁后可编辑
- 同一阈值阶段首次提醒，之后每累计 3 次检查再提醒一次

## 监控规则

- `< 10 元`：普通提醒
- `< 5 元`：强提醒
- 适用于照明和空调
- 余额恢复正常后，可选发送恢复提醒
- 连续 3 次查询失败时，会发送故障提醒

## 安装

一键初始化 Python 环境和桌面端依赖：

```bat
scripts\setup.bat
```

如果你只想单独安装桌面端依赖：

```bat
cd desktop
npm install
```

## 配置

编辑根目录 `config.json`。

关键字段：

```json
{
  "notifyChannel": "email",
  "email": {
    "smtpHost": "smtp.qq.com",
    "smtpPort": 465,
    "sender": "REDACTED_SENDER@qq.com",
    "password": "你的SMTP授权码",
    "recipients": [
      "REDACTED_RECIPIENT@qq.com"
    ],
    "useSsl": true
  },
  "security": {
    "adminPassword": "123456"
  },
  "checkIntervalMinutes": 30,
  "warningThreshold": 10,
  "criticalThreshold": 5,
  "remindEveryChecks": 3
}
```

多收件人支持：

```json
"recipients": ["a@qq.com", "b@outlook.com"]
```

或：

```json
"recipients": "a@qq.com,b@outlook.com"
```

## 启动

推荐开发入口：

```bat
scripts\run_desktop_dev.bat
```

兼容入口（等价转发到上面的脚本）：

```bat
scripts\run.bat
```

桌面目录内直接启动：

```bat
cd desktop
npm start
```

调试 Python 桥接：

```bat
.venv\Scripts\python.exe -m dorm_electricity_monitor.bridge get-state
.venv\Scripts\python.exe -m dorm_electricity_monitor.bridge check-once
```

测试邮件：

```bat
scripts\test_email.bat
```

## 打包

构建 Electron 桌面版：

```bat
scripts\build_desktop.bat
```

或在桌面目录内直接执行：

```bat
cd desktop
npm run dist
```

构建产物默认输出到：

```text
desktop\release
```


## 托盘与常驻逻辑

- 关闭主窗口不会退出，而是最小化到托盘
- 托盘菜单支持显示主界面、立即查询、退出
- Electron 主进程负责定时检查
- Python bridge 负责真正执行查询、提醒和状态落盘

## 当前已验证

- Python bridge `get-state` 正常
- Python bridge `check-once` 正常
- Python bridge `bootstrap` 正常
- 已重建最小 `.venv`，仅保留 `requests` 及其必要依赖
- 启动阶段已改为先显示本地历史状态，再延迟后台联网查询
- 前端构建产物已切换为相对资源路径
- Electron 主进程/preload 已改为 `.cts` 源文件并编译为 `.cjs` 入口，避免打包后 ESM 加载异常导致黑屏
- 启动入口已增加 `desktop/scripts/start-electron.cjs`，会主动清除全局 `ELECTRON_RUN_AS_NODE` 污染
- 已补应用图标与托盘图标资源链路

## 说明

当前发布包已经把 `.venv` 与 Python 核心逻辑一并打入 Electron 产物。首次启动会把 `config.json` 自动复制到用户数据目录，后续配置与状态都写在那里。
