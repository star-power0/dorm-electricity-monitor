export type Level = 'normal' | 'warning' | 'critical'

export type EmailTemplateKey = 'test' | 'warning' | 'critical' | 'recovery' | 'failure'

export type EmailTemplate = {
  subject: string
  body: string
}

export type MeterState = {
  name: string
  roomLabel?: string
  buildingLabel?: string
  balance: number
  energy: number
  collectedAt?: string
  level: Level
}

export type RotationState = {
  cursor?: number
  activeAssignee?: number
  armed?: boolean
}

export type MonitorState = {
  lastCheckAt?: string | null
  lastSuccessAt?: string | null
  lastError?: string | null
  failureCount?: number
  meters?: Record<string, MeterState>
  alerts?: Record<string, unknown>
  rotationState?: Record<string, RotationState>
  logs?: string[]
  lastHeartbeatDate?: string | null
}

export type RawConfig = {
  openId: string
  notifyChannel: string
  pushplusToken: string
  email: {
    smtpHost: string
    smtpPort: number
    sender: string
    password: string
    recipients: string[] | string
    useSsl: boolean
  }
  emailTemplates: Record<EmailTemplateKey, EmailTemplate>
  rotationMembers: string[]
  security: {
    adminPassword: string
  }
  checkIntervalMinutes: number
  warningThreshold: number
  criticalThreshold: number
  notifyOnRecovery: boolean
  dailyHeartbeat: boolean
  heartbeatTime: string
  remindEveryChecks: number
  meters: Array<{ name: string; type: number }>
  onboardingCompleted: boolean
  privacyConsentVersion: string
  privacyConsentedAt: string
}

export type RuntimeInfo = {
  appRoot: string
  pythonExecutable: string
  packaged: boolean
  configExists: boolean
  autostart: {
    openAtLogin: boolean
  }
}

export type BootstrapData = {
  state: MonitorState
  config: RawConfig
  runtime: RuntimeInfo
}

export type MonitorApi = {
  bootstrap: () => Promise<BootstrapData>
  getState: () => Promise<MonitorState>
  checkOnce: () => Promise<MonitorState>
  getConfig: () => Promise<RawConfig>
  saveConfig: (config: RawConfig) => Promise<RawConfig>
  sendTestMail: () => Promise<{ sent: boolean; channel: string }>
  setAutostart: (enabled: boolean) => Promise<{ openAtLogin: boolean }>
  getRuntimeInfo: () => Promise<RuntimeInfo>
  openExternal: (url: string) => Promise<boolean>
  onStateUpdated: (listener: (state: MonitorState) => void) => () => void
}

declare global {
  interface Window {
    monitorApi: MonitorApi
  }
}
