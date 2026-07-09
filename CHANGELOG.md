# CHANGELOG

## 2026-07-09

- 修复低余额持续期间每轮查询都发送提醒的问题，改为首次触发后按 `remindEveryChecks` 节奏重复提醒。
- 修复余额恢复提醒里的轮值人错位问题，恢复邮件显示本轮完成人，并补充下一轮负责人变量。
- 新增假期模式，开启后冻结当前状态，暂停后台轮询、手动查询和邮件发送。

## 2026-06-30

- 新增首次启动引导层：补充单宿舍定位、隐私边界、`openId` 准备说明与 SMTP 授权码说明，并把完成状态持久化到配置。
- 设置页新增 `openId` 编辑入口，以及 `openId` / SMTP 授权码帮助卡，降低普通用户配置门槛。
- 总览页新增开源与隐私边界提示卡，支持随时重新查看首次引导。
- 配置结构新增 `onboardingCompleted`、`privacyConsentVersion`、`privacyConsentedAt` 兼容字段，旧配置可无痛升级。
- 重写 `README.md`，补齐 `openId` 是什么、如何获取、SMTP 授权码是什么、如何填写等用户说明。
- 新增 `PRIVACY.md`、`DISCLAIMER.md`、`OPEN_SOURCE_NOTICE.md`，补齐开源发布所需的隐私、免责声明和边界说明。
- 收窄 `OPEN_SOURCE_ROADMAP.md`：当前主线明确保持单宿舍产品化，不再把多宿舍或全校扫描作为近期方向。
- 修正隐私与引导交互：隐私确认去掉读秒，勾选后即可进入引导；顶部“首次引导”按钮强制打开分步引导。
- 重做页面布局收口：总览页移除大块隐私说明卡，设置页拆为“基础运行 / 敏感配置”页签，敏感配置只保留短提示与帮助链接，减少小窗口遮挡。
- 修复右下角提示条驻留问题：为每条 toast 增加独立 ID、关闭按钮、定时清理和淡出动画，并清理旧开发进程后用生产构建验证。
- 优化隐私确认与引导按钮响应：隐私确认和完成引导先切换界面，再后台保存配置，减少点击后的卡顿感。
- 升级隐私与首次引导文案：补充非官方关系、数据保存范围、Reqable 获取 openId 的步骤、SMTP 授权码解释和测试邮件验证流程。
- 同步升级 `README.md`、`PRIVACY.md`、`DISCLAIMER.md`、`OPEN_SOURCE_NOTICE.md` 的隐私、抓包边界、SMTP 和开源说明。
- 调整外链打开方式：QQ 邮箱 SMTP 帮助通过 Electron `shell.openExternal` 调用系统默认浏览器打开，避免在应用内打开造成卡顿。
- 细化隐私弹窗免责声明，明确本工具是本地辅助查询，不是盗取、扫描或官方系统；并去掉隐私页中 `openId` 的代码反引号展示。
- 完成一轮视觉抛光：升级字体栈与数字显示，统一金额/时间的等宽数字表现，收紧卡片阴影、状态标签、按钮和日志区视觉节奏，在不改变功能与布局逻辑的前提下提升整体质感。
- 修正总览页首屏收口：保持整页不滚动，仅允许“最近记录”卡内部滚动；同时压缩摘要区与指标卡高度，并重做电表余额卡布局，消除底部截断与大面积空白问题。
- 继续压缩通知页邮件模板工作台：收紧页签、模板列表、编辑区与预览区的纵向密度，修复全屏与非全屏下模板内容轻微突出的问题。

## 2026-06-30

- 整理项目结构：删除临时 Electron 探针文件、旧 release 产物与历史备份目录，收紧仓库内非源码内容。
- 精简桌面端依赖：移除未再使用的 `png-to-ico` 开发包。
- 统一启动文档：保留 `scripts\run_desktop_dev.bat` 为推荐入口，`scripts\run.bat` 改为兼容转发壳，并同步更新 README 的安装、启动、打包说明。
- 新增 `OPEN_SOURCE_ROADMAP.md`，记录 UI 第二轮美化、隐私协议与首次引导、多宿舍监控可行性和分阶段路线，避免后续讨论遗忘。

## 2026-06-29

- 修复桌面端构建链路：将 Vite 配置切到 ESM 文件 `vite.config.mts`，并让 Electron TypeScript 编译同时覆盖 `.mts` / `.cts` 入口，恢复 `npm run build` 所需的模块解析一致性。
- 新增宿舍电费轮值前端展示：总览页电表卡片显示当前轮值人，通知页轮值卡片显示照明/空调各自独立的当前轮转状态。
- 调整默认邮件模板文案，明确写出“本轮请 {rotationAssignee} 交费 / 立刻交费”，恢复提醒改为提示本轮已完成且下次轮到下一位。
- 同步更新 `config.json` 与 `config.example.json` 默认模板内容，避免界面默认值、示例配置与 Python 后端文案不一致。

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
- 新增 `desktop/scripts/start-electron.cjs`，启动前主动清除全局 `ELECTRON_RUN_AS_NODE` 污染，避免 `npm start` / `dev:electron` 被错误降级成 Node 模式。
- 新增应用图标与托盘图标打包资源，修复默认图标与托盘白块问题。
- 更新 `README.md`，补充 Electron 架构、启动方式、桥接命令与打包说明。
- 清理旧 PyInstaller spec、Python `__pycache__` 与未使用的 Vite 模板资源。
- 新增 Python bridge `bootstrap` 命令，启动阶段一次性读取本地状态与配置。
- 优化 Electron 启动链路，首屏先显示历史状态，真实联网查询延迟后台执行，减少启动阻塞。
- 更新 Electron 打包过滤规则，排除 Python 缓存和旧字节码残留。

- 重做 Electron 主界面布局与视觉体系，改为浅色仪表盘风格，压缩侧栏、重排状态摘要、电表卡片、健康状态与日志区域，改善信息层级和组件尺寸。

- 再次优化总览页布局，改为 12 栅格信息流：状态摘要与运行指标同排、电表占主区域、最近记录改为底部侧卡，减少大面积空白并压缩卡片尺寸。

- 新增邮件模板配置与编辑能力，测试邮件、普通提醒、强提醒、恢复提醒和故障提醒统一走模板渲染。
- 桌面端通知页改为页内标签布局，支持收件人与邮件模板分开管理。
- 邮件模板页增加应用密码解锁、模板列表、双栏编辑区、变量提示和预览。
- `config.example.json` 补充默认模板示例，方便直接修改文案。

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
