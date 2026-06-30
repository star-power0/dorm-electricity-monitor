# 宿舍电费监控

一个 Windows 本地桌面程序，用来监控宿舍照明和空调电费余额。

## 当前定位

当前版本定位非常明确：

- 面向 **用户本人已经绑定的单宿舍场景**
- 使用 `openId` 查询当前宿舍下的照明与空调电表
- 通过邮箱或 PushPlus 发送余额提醒
- 以本地桌面工具方式运行，不提供云端账号系统

> 当前版本不提供全校宿舍统一监控，也不鼓励扫描别人的宿舍。

## 当前架构

当前项目采用：

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
- PushPlus 提醒
- 收件人可视化编辑
- 设置页敏感项解锁后可编辑
- 首次启动引导
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

### 关键字段

```json
{
  "openId": "ofDET4ypS5bH***za_8CI",
  "notifyChannel": "email",
  "email": {
    "smtpHost": "smtp.qq.com",
    "smtpPort": 465,
    "sender": "your_qq_mail@qq.com",
    "password": "你的SMTP授权码",
    "recipients": [
      "your_qq_mail@qq.com"
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

### `openId` 是什么

`openId` 用来标识你在对应微信小程序中的当前用户身份与绑定场景。

在这个项目里，它的作用是：

- 查询你当前已经绑定的宿舍电表
- 区分照明 `type=1` 与空调 `type=2`

它看起来通常会像这样：

```text
ofDET4ypS5bH***za_8CI
```

或者你在文档、截图里应该只展示打码后的形式：

```text
ofDET4ypS5bH***za_8CI
```

### 如何获取 `openId`

当前项目默认不替你抓取 `openId`，你需要自己从微信小程序的合法调试过程中获取。

一种常见流程是使用 Reqable：

1. 在电脑安装 Reqable。
2. 按 Reqable 提示安装并信任 HTTPS 证书。
3. 开启 Reqable 的调试 / 代理能力。
4. 打开微信，并进入你本人正在使用的海大电费相关小程序。
5. 进入电费页面，分别点一次照明和空调余额查询。
6. 回到 Reqable 请求列表，筛选或搜索 `hainanu`、`weixinEle`、`getEleInfo` 等关键词。
7. 打开对应请求，查看 query/body 参数里的 `openId`。
8. 复制 `openId`，填入本项目设置页的“敏感配置”。

注意：

- `openId` 不是宿舍号
- `openId` 不是楼栋号
- `openId` 不是邮箱账号
- 只使用你本人已绑定宿舍产生的请求参数
- 不要把真实 `openId` 提交到 Git 仓库、issue、截图或聊天记录里

### SMTP 授权码是什么

SMTP 是邮箱服务商提供给第三方客户端发送邮件的协议。本工具通过 SMTP 发送余额提醒。

如果你选择邮箱提醒，`password` 填的不是邮箱登录密码，而是 **SMTP 授权码**。

以 QQ 邮箱为例，常见配置是：

- `smtpHost`: `smtp.qq.com`
- `smtpPort`: `465`
- `useSsl`: `true`

### 如何获取 QQ 邮箱 SMTP 授权码

通常流程如下：

1. 登录 QQ 邮箱网页端。
2. 进入“设置”或“账户”相关页面。
3. 找到 POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV 服务设置。
4. 开启 SMTP 或 IMAP/SMTP 服务。
5. 按页面提示验证身份并生成授权码。
6. 把生成的授权码填到本项目的 `password` 字段里。
7. 保存配置后，点击桌面程序顶部“测试邮件”确认能收到邮件。

参考页面：

- QQ 邮箱帮助：https://service.mail.qq.com/detail/0/75

### 多收件人支持

可以写成数组：

```json
"recipients": ["a@qq.com", "b@outlook.com"]
```

也可以写成逗号分隔字符串：

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
.venv\Scripts\python.exe -m dorm_electricity_monitor.bridge bootstrap
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

## 隐私与使用边界

开源前请先阅读：

- [PRIVACY.md](./PRIVACY.md)
- [DISCLAIMER.md](./DISCLAIMER.md)
- [OPEN_SOURCE_NOTICE.md](./OPEN_SOURCE_NOTICE.md)

最关键的边界是：

- 当前项目只面向你自己已经绑定的宿舍
- 不要用它扫描别人的宿舍
- 不要把真实 `openId`、邮箱账号或 SMTP 授权码公开提交

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
