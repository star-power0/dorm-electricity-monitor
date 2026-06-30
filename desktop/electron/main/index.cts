import { app, BrowserWindow, Menu, Tray, ipcMain, nativeImage, shell } from 'electron'
import { spawn } from 'node:child_process'
import path = require('node:path')
import fs = require('node:fs')

const desktopRoot = path.resolve(__dirname, '..', '..')
const repoRoot = path.resolve(desktopRoot, '..')
const runtimeRoot = app.isPackaged ? process.resourcesPath : repoRoot
const dataRoot = app.isPackaged ? app.getPath('userData') : repoRoot
const pythonExecutable = path.join(runtimeRoot, '.venv', 'Scripts', 'python.exe')
const bundledConfigPath = path.join(runtimeRoot, 'config.json')
const bundledExampleConfigPath = path.join(runtimeRoot, 'config.example.json')
const runtimeConfigPath = path.join(dataRoot, 'config.json')
const appIconPath = app.isPackaged
  ? path.join(process.resourcesPath, 'icon.png')
  : path.join(desktopRoot, 'build', 'icon.png')

let mainWindow: InstanceType<typeof BrowserWindow> | null = null
let tray: InstanceType<typeof Tray> | null = null
let checkTimer: NodeJS.Timeout | null = null
let isChecking = false
let isQuitting = false
let latestState: MonitorState | null = null

type BridgeResponse<T> = {
  ok: boolean
  data?: T
  error?: string
  traceback?: string
}

type MonitorState = {
  lastCheckAt?: string | null
  lastSuccessAt?: string | null
  lastError?: string | null
  failureCount?: number
  meters?: Record<string, { name: string; balance: number; energy: number; level: string; roomLabel?: string; collectedAt?: string }>
  logs?: string[]
}

type BootstrapBridgeData = {
  state: MonitorState
  config: RawConfig
}

type RawConfig = {
  checkIntervalMinutes?: number
}

function ensureRuntimeFiles() {
  fs.mkdirSync(dataRoot, { recursive: true })
  if (!fs.existsSync(runtimeConfigPath)) {
    if (fs.existsSync(bundledConfigPath)) {
      fs.copyFileSync(bundledConfigPath, runtimeConfigPath)
    } else if (fs.existsSync(bundledExampleConfigPath)) {
      fs.copyFileSync(bundledExampleConfigPath, runtimeConfigPath)
    }
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1220,
    height: 780,
    minWidth: 1040,
    minHeight: 680,
    title: '宿舍电费监控',
    icon: appIconPath,
    backgroundColor: '#0f172a',
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show()
  })

  mainWindow.on('close', (event: { preventDefault: () => void }) => {
    if (!isQuitting) {
      event.preventDefault()
      mainWindow?.hide()
    }
  })

  const devUrl = process.env.VITE_DEV_SERVER_URL
  if (devUrl) {
    void mainWindow.loadURL(devUrl)
  } else {
    void mainWindow.loadFile(path.join(__dirname, '..', '..', 'dist', 'index.html'))
  }
}

function createTray() {
  const icon = nativeImage.createFromPath(appIconPath).resize({ width: 18, height: 18 })
  tray = new Tray(icon)
  tray.setToolTip('宿舍电费监控')
  tray.on('click', showMainWindow)
  updateTrayMenu()
}

function updateTrayMenu() {
  if (!tray) return
  const summary = latestState ? stateSummary(latestState) : '等待检查'
  tray.setToolTip(`宿舍电费监控\n${summary}`)
  tray.setImage(nativeImage.createFromPath(appIconPath).resize({ width: 18, height: 18 }))
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: summary, enabled: false },
      { type: 'separator' },
      { label: '显示主界面', click: showMainWindow },
      { label: isChecking ? '正在查询…' : '立即查询', enabled: !isChecking, click: () => void runScheduledCheck() },
      { type: 'separator' },
      {
        label: '退出',
        click: () => {
          isQuitting = true
          app.quit()
        },
      },
    ]),
  )
}

function showMainWindow() {
  if (!mainWindow) createWindow()
  mainWindow?.show()
  mainWindow?.focus()
}

async function runBridge<T>(command: string, payload?: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonExecutable, ['-m', 'dorm_electricity_monitor.bridge', command], {
      cwd: runtimeRoot,
      env: {
        ...process.env,
        PYTHONPATH: path.join(runtimeRoot, 'src'),
        DORM_MONITOR_APP_DIR: dataRoot,
        PYTHONIOENCODING: 'utf-8',
      },
      windowsHide: true,
    })

    let stdout = ''
    let stderr = ''
    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (chunk) => {
      stdout += chunk
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk
    })
    child.on('error', reject)
    child.on('close', () => {
      try {
        const response = JSON.parse(stdout || '{}') as BridgeResponse<T>
        if (response.ok) {
          resolve(response.data as T)
          return
        }
        reject(new Error(response.error || stderr || 'Python bridge failed'))
      } catch (error) {
        reject(error instanceof Error ? error : new Error(String(error)))
      }
    })

    if (payload !== undefined) {
      child.stdin.write(JSON.stringify(payload))
    }
    child.stdin.end()
  })
}

async function getConfig(): Promise<RawConfig> {
  return runBridge<RawConfig>('get-config')
}

async function runScheduledCheck() {
  if (isChecking) return latestState
  isChecking = true
  updateTrayMenu()
  try {
    latestState = await runBridge<MonitorState>('check-once')
    mainWindow?.webContents.send('monitor:state-updated', latestState)
    return latestState
  } finally {
    isChecking = false
    updateTrayMenu()
  }
}

async function scheduleChecks(options: { config?: RawConfig; runImmediately?: boolean } = {}) {
  if (checkTimer) clearInterval(checkTimer)
  const config = options.config || await getConfig().catch(() => ({ checkIntervalMinutes: 30 }))
  const minutes = Math.max(5, Number(config.checkIntervalMinutes || 30))
  checkTimer = setInterval(() => {
    void runScheduledCheck()
  }, minutes * 60 * 1000)
  if (options.runImmediately) {
    setTimeout(() => {
      void runScheduledCheck()
    }, 4000)
  }
}

function stateSummary(state: MonitorState) {
  if (state.lastError) return '查询失败，请查看详情'
  const meters = Object.values(state.meters || {})
  if (!meters.length) return '等待检查'
  return meters.map((meter) => `${meter.name} ${Number(meter.balance || 0).toFixed(2)} 元`).join(' · ')
}

function runtimeInfo() {
  return {
    appRoot: runtimeRoot,
    pythonExecutable,
    autostart: app.getLoginItemSettings(),
    packaged: app.isPackaged,
    configExists: fs.existsSync(path.join(dataRoot, 'config.json')),
  }
}

function registerIpc() {
  ipcMain.handle('monitor:bootstrap', async () => {
    const data = await runBridge<BootstrapBridgeData>('bootstrap')
    latestState = data.state
    updateTrayMenu()
    void scheduleChecks({ config: data.config, runImmediately: true })
    return { ...data, runtime: runtimeInfo() }
  })
  ipcMain.handle('monitor:get-state', async () => {
    latestState = await runBridge<MonitorState>('get-state')
    updateTrayMenu()
    return latestState
  })
  ipcMain.handle('monitor:check-once', async () => runScheduledCheck())
  ipcMain.handle('monitor:get-config', async () => getConfig())
  ipcMain.handle('monitor:save-config', async (_event: unknown, config: RawConfig) => {
    const saved = await runBridge<RawConfig>('save-config', config)
    await scheduleChecks()
    return saved
  })
  ipcMain.handle('monitor:send-test-mail', async () => runBridge('send-test-mail'))
  ipcMain.handle('monitor:set-autostart', (_event: unknown, enabled: boolean) => {
    app.setLoginItemSettings({ openAtLogin: enabled, path: process.execPath })
    return app.getLoginItemSettings()
  })
  ipcMain.handle('monitor:get-runtime-info', () => ({
    appRoot: runtimeRoot,
    pythonExecutable,
    autostart: app.getLoginItemSettings(),
    packaged: app.isPackaged,
    configExists: fs.existsSync(path.join(dataRoot, 'config.json')),
  }))
  ipcMain.handle('monitor:open-external', async (_event: unknown, url: string) => {
    await shell.openExternal(url)
    return true
  })
}

app.whenReady().then(() => {
  app.setAppUserModelId('cn.hainanu.dorm-electricity-monitor')
  ensureRuntimeFiles()
  registerIpc()
  createTray()
  createWindow()
})

app.on('activate', showMainWindow)
app.on('window-all-closed', () => {
})
