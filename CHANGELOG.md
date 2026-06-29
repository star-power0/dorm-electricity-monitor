# CHANGELOG

## 2026-06-29

- 新增 `src/dorm_electricity_monitor/bridge.py`，为 Electron 提供 `get-state`、`check-once`、`get-config`、`save-config`、`send-test-mail` 桥接命令。
- 调整 `src/dorm_electricity_monitor/config.py`，支持通过 `DORM_MONITOR_APP_DIR` 覆盖配置与状态目录，便于桌面壳统一管理运行目录。
- 新建 `desktop/`，引入 Electron + React + TypeScript + Vite 桌面端工程。
- 新增 Electron 主进程、preload 与 IPC 调度，接入托盘、自启动、定时检查与 Python 子进程调用。
- 新增总览、通知、设置三页桌面 UI，替换默认 Vite 页面。
- 新增 `scripts/run_desktop_dev.bat` 与 `scripts/build_desktop.bat`，用于开发与打包 Electron 桌面版。
- 删除旧 `PySide6` 桌面壳、旧 `PyInstaller` 打包脚本与相关启动/自启脚本，只保留 Python 核心逻辑与 Electron 桌面版。
- 删除旧 `.venv` 并按最小依赖重建运行时，清掉旧桌面栈历史污染。
- 修复 Electron 打包后前端资源绝对路径导致的黑屏问题。
- 修复 Electron 主进程/preload 被 ESM 方式加载导致的黑屏问题，改为 `.cts` 编译输出 `.cjs`，并让打包入口指向 `dist-electron/main/index.cjs`。
- 新增应用图标与托盘图标打包资源，修复默认图标与托盘白块问题。
- 更新 `README.md`，补充 Electron 架构、启动方式、桥接命令与打包说明。
- 清理旧 PyInstaller spec、Python `__pycache__` 与未使用的 Vite 模板资源。
- 新增 Python bridge `bootstrap` 命令，启动阶段一次性读取本地状态与配置。
- 优化 Electron 启动链路，首屏先显示历史状态，真实联网查询延迟后台执行，减少启动阻塞。
- 更新 Electron 打包过滤规则，排除 Python 缓存和旧字节码残留。

- 重做 Electron 主界面布局与视觉体系，改为浅色仪表盘风格，压缩侧栏、重排状态摘要、电表卡片、健康状态与日志区域，改善信息层级和组件尺寸。

- 再次优化总览页布局，改为 12 栅格信息流：状态摘要与运行指标同排、电表占主区域、最近记录改为底部侧卡，减少大面积空白并压缩卡片尺寸。

- 按用户反馈继续压缩总览与设置页：电表改为上下排列，最近记录改为卡片内部滚动，设置页移除重复启动区并压缩表单高度，尽量避免整页滚动。

## 2026-06-28

- 创建 Windows 本地宿舍电费监控项目。
- 接入海南大学电费接口，支持照明 `type=1` 与空调 `type=2`。
- 新增 10 元普通提醒、5 元强提醒与阈值阶段去重逻辑。
- 新增 PushPlus 微信推送支持。
- 新增 QQ 邮箱 SMTP 提醒支持，并将默认通知通道改为邮箱。
- 重构为 PySide6 桌面程序，提供总览、收件人、设置三页界面。
- 新增托盘常驻、Windows 系统通知、最近日志与监控健康状态展示。
- 新增应用单独密码解锁设置，敏感配置默认锁定。
- 新增同一阈值阶段每 3 次检查重复提醒一次的规则。
