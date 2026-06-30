import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import type { EmailTemplateKey, Level, MeterState, MonitorState, RawConfig, RuntimeInfo } from './types'

const navItems = [
  { key: 'dashboard', label: '总览', eyebrow: 'Overview' },
  { key: 'notify', label: '通知', eyebrow: 'Notify' },
  { key: 'settings', label: '设置', eyebrow: 'Settings' },
] as const

const templateItems: Array<{ key: EmailTemplateKey; label: string; hint: string }> = [
  { key: 'test', label: '测试邮件', hint: '点击顶部“测试邮件”时发送' },
  { key: 'warning', label: '余额偏低提醒', hint: '余额低于普通阈值时发送' },
  { key: 'critical', label: '余额告急提醒', hint: '余额低于强提醒阈值时发送' },
  { key: 'recovery', label: '恢复正常提醒', hint: '余额恢复安全范围时发送' },
  { key: 'failure', label: '查询失败提醒', hint: '连续 3 次查询失败时发送' },
]

const defaultEmailTemplates: RawConfig['emailTemplates'] = {
  test: {
    subject: '[{appName}] 测试邮件 {time}',
    body: '这是一封来自 {appName} 的测试邮件。\n\n发送时间：{time}\n通知通道：{channel}\n当前收件人：{recipients}\n\n如果你能收到这封邮件，说明当前通知链路可用。',
  },
  warning: {
    subject: '[{appName}] {meterName} 余额偏低：{balance} 元',
    body: '{roomLabel}\n\n当前余额 {balance} 元，已经低于普通提醒阈值 {warningThreshold} 元。\n本轮请 {rotationAssignee} 交费。\n\n剩余电量：{energy} 度\n采集时间：{collectedAt}',
  },
  critical: {
    subject: '[{appName}] {meterName} 余额告急：{balance} 元',
    body: '{roomLabel}\n\n当前余额只剩 {balance} 元，已经低于强提醒阈值 {criticalThreshold} 元。\n本轮请 {rotationAssignee} 立刻交费。\n\n请尽快充值，避免临时断电。\n\n剩余电量：{energy} 度\n采集时间：{collectedAt}',
  },
  recovery: {
    subject: '[{appName}] {meterName} 已恢复正常',
    body: '{roomLabel}\n\n当前余额 {balance} 元，已经回到安全范围。\n本轮 {rotationAssignee} 已完成交费，下一次会轮到下一位。\n\n剩余电量：{energy} 度\n采集时间：{collectedAt}',
  },
  failure: {
    subject: '[{appName}] 连续查询失败提醒',
    body: '{appName} 已连续 {failureCount} 次查询失败。\n\n错误信息：{error}\n发生时间：{time}\n\n请检查电脑网络、接口状态或配置文件。',
  },
}

const previewVariables: Record<string, string> = {
  appName: '宿舍电费监控',
  channel: 'email',
  recipients: 'REDACTED_RECIPIENT@qq.com',
  meterName: '空调',
  roomLabel: '5号楼 516 室 · 空调',
  buildingLabel: '5号楼 空调',
  balance: '4.82',
  energy: '8.16',
  collectedAt: '2026-06-29 20:30:00',
  warningThreshold: '10.00',
  criticalThreshold: '5.00',
  level: 'critical',
  time: '2026-06-29 20:30:00',
  failureCount: '3',
  error: '网络连接超时',
}

const privacyConsentVersion = '2026-06-30'
const openIdPreview = 'ofDET4ypS5bH***za_8CI'
const smtpHelpLink = 'https://service.mail.qq.com/detail/0/75'

type PageKey = (typeof navItems)[number]['key']
type NotifyTab = 'recipients' | 'templates'
type SettingsTab = 'runtime' | 'sensitive'

type Toast = {
  id: number
  type: 'success' | 'error' | 'info'
  text: string
}

const levelText: Record<Level, string> = {
  normal: '正常',
  warning: '偏低',
  critical: '告急',
}

function App() {
  const [page, setPage] = useState<PageKey>('dashboard')
  const [state, setState] = useState<MonitorState | null>(null)
  const [config, setConfig] = useState<RawConfig | null>(null)
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null)
  const [checking, setChecking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<Toast | null>(null)
  const toastTimerRef = useRef<number | null>(null)
  const [recipientDraft, setRecipientDraft] = useState('')
  const [settingsUnlocked, setSettingsUnlocked] = useState(false)
  const [unlockPassword, setUnlockPassword] = useState('')
  const [templateUnlocked, setTemplateUnlocked] = useState(false)
  const [templatePassword, setTemplatePassword] = useState('')
  const [notifyTab, setNotifyTab] = useState<NotifyTab>('recipients')
  const [settingsTab, setSettingsTab] = useState<SettingsTab>('runtime')
  const [rotationDraft, setRotationDraft] = useState('')
  const [activeTemplate, setActiveTemplate] = useState<EmailTemplateKey>('test')
  const [privacyVisible, setPrivacyVisible] = useState(false)
  const [privacyChecked, setPrivacyChecked] = useState(false)
  const [onboardingVisible, setOnboardingVisible] = useState(false)
  const [onboardingStep, setOnboardingStep] = useState(0)

  useEffect(() => {
    void bootstrap()
    const dispose = window.monitorApi.onStateUpdated((nextState) => {
      setState(nextState)
    })
    return () => {
      dispose()
      if (toastTimerRef.current !== null) {
        window.clearTimeout(toastTimerRef.current)
      }
    }
  }, [])

  function showToast(nextToast: Omit<Toast, 'id'>) {
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current)
    }
    const toastWithId = { ...nextToast, id: Date.now() }
    setToast(toastWithId)
    toastTimerRef.current = window.setTimeout(() => {
      setToast((current) => (current?.id === toastWithId.id ? null : current))
      toastTimerRef.current = null
    }, 3200)
  }

  const meters = useMemo(
    () => Object.entries(state?.meters || {}).map(([key, m]) => ({ ...m, key })),
    [state],
  )
  const status = useMemo(() => getOverallStatus(state), [state])
  const meterAssignees = useMemo(() => {
    const members = config?.rotationMembers?.length ? config.rotationMembers : ['A', 'B', 'C', 'D']
    return Object.fromEntries(
      Object.entries(state?.rotationState || {}).map(([k, rs]) => [
        k,
        members[(rs.activeAssignee ?? 0) % members.length],
      ]),
    )
  }, [state, config])
  const rotationSummary = useMemo(() => {
    const members = config?.rotationMembers?.length ? config.rotationMembers : ['A', 'B', 'C', 'D']
    return Object.entries(state?.rotationState || {}).map(([key, rs]) => ({
      key,
      label: state?.meters?.[key]?.name ?? key,
      assignee: members[(rs.activeAssignee ?? 0) % members.length],
      armed: rs.armed ?? false,
    }))
  }, [state, config])
  const pageTitle = navItems.find((item) => item.key === page)?.label || '总览'

  async function bootstrap() {
    try {
      const data = await window.monitorApi.bootstrap()
      setState(data.state)
      const normalizedConfig = normalizeConfig(data.config)
      setConfig(normalizedConfig)
      setRotationDraft((normalizedConfig.rotationMembers || []).join(', '))
      setRuntime(data.runtime)
      setPrivacyVisible(!normalizedConfig.privacyConsentedAt)
      setOnboardingVisible(Boolean(normalizedConfig.privacyConsentedAt) && !normalizedConfig.onboardingCompleted)
      setOnboardingStep(0)
    } catch (error) {
      showError(error)
    }
  }

  async function runCheck() {
    setChecking(true)
    try {
      const nextState = await window.monitorApi.checkOnce()
      setState(nextState)
      showToast({ type: 'success', text: '查询完成，状态已刷新。' })
    } catch (error) {
      showError(error)
    } finally {
      setChecking(false)
    }
  }

  async function saveConfig(nextConfig = config) {
    if (!nextConfig) return
    setSaving(true)
    try {
      const saved = await window.monitorApi.saveConfig(nextConfig)
      setConfig(normalizeConfig(saved))
      setRuntime(await window.monitorApi.getRuntimeInfo())
      showToast({ type: 'success', text: '配置已保存，并已更新后台定时任务。' })
    } catch (error) {
      showError(error)
    } finally {
      setSaving(false)
    }
  }

  async function saveRecipients() {
    await saveConfig()
  }

  async function saveTemplates() {
    await saveConfig()
    setTemplateUnlocked(false)
    setTemplatePassword('')
  }

  async function saveSettings() {
    await saveConfig()
    setSettingsUnlocked(false)
    setUnlockPassword('')
  }

  async function acceptPrivacy() {
    if (!config) return
    if (!privacyChecked) {
      showToast({ type: 'error', text: '请先勾选确认框，再继续。' })
      return
    }
    const nextConfig = {
      ...config,
      privacyConsentVersion,
      privacyConsentedAt: new Date().toISOString(),
    }
    setConfig(normalizeConfig(nextConfig))
    setPrivacyVisible(false)
    setOnboardingStep(0)
    setOnboardingVisible(true)
    void saveConfig(nextConfig)
  }

  async function completeOnboarding() {
    if (!config) return
    if (!config.openId.trim()) {
      showToast({ type: 'error', text: '请先填写 openId，再完成首次引导。' })
      closeOverlaysAndGo('settings')
      return
    }
    if (config.notifyChannel === 'email') {
      const recipients = normalizeRecipients(config.email.recipients)
      if (!config.email.sender.trim() || !config.email.password.trim() || !recipients.length) {
        showToast({ type: 'error', text: '邮箱提醒模式下，请先补齐发件邮箱、SMTP 授权码和至少一个收件人。' })
        closeOverlaysAndGo('settings')
        return
      }
    }
    const nextConfig = {
      ...config,
      onboardingCompleted: true,
      privacyConsentVersion,
      privacyConsentedAt: config.privacyConsentedAt || new Date().toISOString(),
    }
    setConfig(normalizeConfig(nextConfig))
    setOnboardingVisible(false)
    setOnboardingStep(0)
    setPage('dashboard')
    showToast({ type: 'success', text: '首次引导已完成，后续可在设置页继续修改参数。' })
    void saveConfig(nextConfig)
  }

  function closeOverlaysAndGo(nextPage: PageKey, nextStep = 0) {
    setPrivacyVisible(false)
    setOnboardingVisible(false)
    setOnboardingStep(nextStep)
    if (nextPage === 'settings') {
      setSettingsTab(nextStep === 0 ? 'runtime' : 'sensitive')
    }
    setPage(nextPage)
  }

  function openPrivacy() {
    setOnboardingVisible(false)
    setPrivacyChecked(Boolean(config?.privacyConsentedAt))
    setPrivacyVisible(true)
  }

  function openOnboarding(startStep = 0) {
    setPrivacyVisible(false)
    setOnboardingStep(startStep)
    setOnboardingVisible(true)
  }

  function openSmtpHelp() {
    void window.monitorApi.openExternal(smtpHelpLink)
  }

  function reopenOnboarding() {
    openOnboarding(0)
  }

  async function sendTestMail() {
    try {
      await window.monitorApi.sendTestMail()
      showToast({ type: 'success', text: '测试邮件已发送。' })
    } catch (error) {
      showError(error)
    }
  }

  async function toggleAutostart(enabled: boolean) {
    try {
      const autostart = await window.monitorApi.setAutostart(enabled)
      const nextRuntime = await window.monitorApi.getRuntimeInfo()
      setRuntime({ ...nextRuntime, autostart })
      showToast({ type: 'success', text: enabled ? '已设置开机自启动。' : '已关闭开机自启动。' })
    } catch (error) {
      showError(error)
    }
  }

  function updateConfig(patch: Partial<RawConfig>) {
    if (!config) return
    setConfig({ ...config, ...patch })
  }

  function updateEmail(patch: Partial<RawConfig['email']>) {
    if (!config) return
    setConfig({ ...config, email: { ...config.email, ...patch } })
  }

  function updateRotationMembers(value: string) {
    if (!config) return
    const members = value.split(',').map((item) => item.trim()).filter(Boolean)
    setRotationDraft(value)
    setConfig({ ...config, rotationMembers: members })
  }

  function updateTemplate(key: EmailTemplateKey, patch: Partial<RawConfig['emailTemplates'][EmailTemplateKey]>) {
    if (!config) return
    setConfig({
      ...config,
      emailTemplates: {
        ...config.emailTemplates,
        [key]: {
          ...config.emailTemplates[key],
          ...patch,
        },
      },
    })
  }

  function restoreTemplate(key: EmailTemplateKey) {
    if (!config) return
    setConfig({ ...config, emailTemplates: { ...config.emailTemplates, [key]: defaultEmailTemplates[key] } })
    showToast({ type: 'info', text: '已恢复当前模板默认内容，保存后生效。' })
  }

  function addRecipient() {
    if (!config) return
    const mail = recipientDraft.trim()
    if (!mail) return
    const recipients = normalizeRecipients(config.email.recipients)
    if (recipients.includes(mail)) {
      setRecipientDraft('')
      return
    }
    updateEmail({ recipients: [...recipients, mail] })
    setRecipientDraft('')
  }

  function removeRecipient(mail: string) {
    if (!config) return
    updateEmail({ recipients: normalizeRecipients(config.email.recipients).filter((item) => item !== mail) })
  }

  function unlockSettings() {
    if (!config) return
    if (unlockPassword === config.security.adminPassword) {
      setSettingsUnlocked(true)
      setUnlockPassword('')
      showToast({ type: 'success', text: '敏感设置已解锁。' })
      return
    }
    showToast({ type: 'error', text: '应用密码不正确。' })
  }

  function unlockTemplates() {
    if (!config) return
    if (templatePassword === config.security.adminPassword) {
      setTemplateUnlocked(true)
      setTemplatePassword('')
      showToast({ type: 'success', text: '邮件模板已解锁。' })
      return
    }
    showToast({ type: 'error', text: '应用密码不正确。' })
  }

  function showError(error: unknown) {
    showToast({ type: 'error', text: error instanceof Error ? error.message : String(error) })
  }

  return (
    <main className="app-shell">
      {privacyVisible && config && (
        <PrivacyOverlay
          checked={privacyChecked}
          setChecked={setPrivacyChecked}
          acceptPrivacy={() => void acceptPrivacy()}
          closeOverlay={() => setPrivacyVisible(false)}
          initialConsent={Boolean(config.privacyConsentedAt)}
        />
      )}
      {onboardingVisible && config && (
        <OnboardingOverlay
          config={config}
          step={onboardingStep}
          setStep={setOnboardingStep}
          completeOnboarding={() => void completeOnboarding()}
          closeOverlay={() => setOnboardingVisible(false)}
          goSettings={() => closeOverlaysAndGo('settings', 1)}
          goNotify={() => closeOverlaysAndGo('notify', 2)}
          openPrivacy={openPrivacy}
          openSmtpHelp={openSmtpHelp}
        />
      )}
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">电</div>
          <div>
            <h1>宿舍电费监控</h1>
            <p>Hainan University</p>
          </div>
        </div>

        <nav className="nav-list">
          {navItems.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${page === item.key ? 'active' : ''}`}
              onClick={() => setPage(item.key)}
              type="button"
            >
              <span>{item.label}</span>
              <small>{item.eyebrow}</small>
            </button>
          ))}
        </nav>

        <div className={`sidebar-status ${status.level}`}>
          <span>{status.label}</span>
          <strong>{status.title}</strong>
          <p>{status.detail}</p>
        </div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">{pageTitle}</p>
            <h2>{page === 'dashboard' ? status.title : pageTitle}</h2>
          </div>
          <div className="top-actions">
            <button className="secondary" type="button" onClick={openPrivacy}>隐私说明</button>
            <button className="secondary" type="button" onClick={reopenOnboarding}>首次引导</button>
            <button className="secondary" type="button" onClick={sendTestMail}>测试邮件</button>
            <button type="button" onClick={runCheck} disabled={checking}>{checking ? '查询中…' : '立即查询'}</button>
          </div>
        </header>

        {page === 'dashboard' && <Dashboard state={state} meters={meters} runtime={runtime} status={status} meterAssignees={meterAssignees} />}
        {page === 'notify' && config && (
          <NotifyPage
            config={config}
            setConfig={setConfig}
            recipientDraft={recipientDraft}
            setRecipientDraft={setRecipientDraft}
            addRecipient={addRecipient}
            removeRecipient={removeRecipient}
            save={notifyTab === 'templates' ? saveTemplates : saveRecipients}
            saving={saving}
            notifyTab={notifyTab}
            setNotifyTab={setNotifyTab}
            templateUnlocked={templateUnlocked}
            templatePassword={templatePassword}
            setTemplatePassword={setTemplatePassword}
            unlockTemplates={unlockTemplates}
            activeTemplate={activeTemplate}
            setActiveTemplate={setActiveTemplate}
            updateTemplate={updateTemplate}
            restoreTemplate={restoreTemplate}
            rotationDraft={rotationDraft}
            setRotationDraft={updateRotationMembers}
            rotationSummary={rotationSummary}
          />
        )}
        {page === 'settings' && config && (
          <SettingsPage
            config={config}
            runtime={runtime}
            updateConfig={updateConfig}
            updateEmail={updateEmail}
            save={saveSettings}
            saving={saving}
            settingsUnlocked={settingsUnlocked}
            unlockPassword={unlockPassword}
            setUnlockPassword={setUnlockPassword}
            unlockSettings={unlockSettings}
            toggleAutostart={toggleAutostart}
            settingsTab={settingsTab}
            setSettingsTab={setSettingsTab}
            openSmtpHelp={openSmtpHelp}
          />
        )}
      </section>

      {toast && (
        <div
          className={`toast ${toast.type}`}
          key={toast.id}
          onAnimationEnd={() => setToast((current) => (current?.id === toast.id ? null : current))}
        >
          <span>{toast.text}</span>
          <button className="toast-close" type="button" onClick={() => setToast(null)}>×</button>
        </div>
      )}
    </main>
  )
}

function Dashboard({ state, meters, runtime, status, meterAssignees }: { state: MonitorState | null; meters: (MeterState & { key: string })[]; runtime: RuntimeInfo | null; status: ReturnType<typeof getOverallStatus>; meterAssignees: Record<string, string> }) {
  const totalBalance = meters.reduce((sum, meter) => sum + Number(meter.balance || 0), 0)
  return (
    <div className="dashboard-grid">
      <section className={`summary-card ${status.level}`}>
        <div>
          <p className="eyebrow">Current Status</p>
          <h3>{status.title}</h3>
          <p>{status.detail}</p>
        </div>
        <div className="summary-number">
          <span>总余额</span>
          <strong>{totalBalance.toFixed(2)}</strong>
          <small>元</small>
        </div>
      </section>

      <section className="status-strip">
        <Metric label="最近检查" value={state?.lastCheckAt || '--'} />
        <Metric label="连续失败" value={`${state?.failureCount || 0} 次`} />
        <Metric label="后台自启" value={runtime?.autostart.openAtLogin ? '已开启' : '未开启'} />
        <Metric label="配置文件" value={runtime?.configExists ? '正常' : '未找到'} />
      </section>

      <section className="meter-section">
        <div className="section-title compact">
          <div>
            <p className="eyebrow">Meters</p>
            <h3>电表余额</h3>
          </div>
          <span className="section-note">最近成功 {state?.lastSuccessAt || '--'}</span>
        </div>
        <div className="meter-grid">
          {meters.map((meter) => <MeterCard key={meter.key} meter={meter} assignee={meterAssignees[meter.key]} />)}
          {!meters.length && <div className="empty-card">暂无余额数据，点击立即查询刷新。</div>}
        </div>
      </section>

      <section className="card logs-card">
        <div className="section-title compact">
          <div>
            <p className="eyebrow">Timeline</p>
            <h3>最近记录</h3>
          </div>
        </div>
        <div className="timeline">
          {(state?.logs || []).map((line, index) => (
            <div className="timeline-item" key={`${line}-${index}`}>
              <span></span>
              <p>{line}</p>
            </div>
          ))}
          {!(state?.logs || []).length && <p className="muted">暂无记录。</p>}
        </div>
      </section>
    </div>
  )
}

function MeterCard({ meter, assignee }: { meter: MeterState; assignee?: string }) {
  const location = getMeterLocation(meter)

  return (
    <article className={`meter-card ${meter.level}`}>
      <div className="meter-card-body">
        <div className="meter-copy">
          {location && <span className="meter-location">{location}</span>}
          <h3>{meter.name}</h3>
          <div className="meter-meta">
            <span>剩余电量 {Number(meter.energy || 0).toFixed(2)} 度</span>
            {assignee && <span className="meter-assignee">本轮：{assignee}</span>}
          </div>
        </div>
        <div className="meter-side">
          <strong className="meter-level">{levelText[meter.level]}</strong>
          <div className="balance"><strong>{Number(meter.balance || 0).toFixed(2)}</strong><small>元</small></div>
          <span className="meter-time">采集 {meter.collectedAt || '--'}</span>
        </div>
      </div>
    </article>
  )
}

type NotifyPageProps = {
  config: RawConfig
  setConfig: (config: RawConfig) => void
  recipientDraft: string
  setRecipientDraft: (value: string) => void
  addRecipient: () => void
  removeRecipient: (mail: string) => void
  save: () => void
  saving: boolean
  notifyTab: NotifyTab
  setNotifyTab: (tab: NotifyTab) => void
  templateUnlocked: boolean
  templatePassword: string
  setTemplatePassword: (value: string) => void
  unlockTemplates: () => void
  activeTemplate: EmailTemplateKey
  setActiveTemplate: (key: EmailTemplateKey) => void
  updateTemplate: (key: EmailTemplateKey, patch: Partial<RawConfig['emailTemplates'][EmailTemplateKey]>) => void
  restoreTemplate: (key: EmailTemplateKey) => void
  rotationDraft: string
  setRotationDraft: (value: string) => void
  rotationSummary: Array<{ key: string; label: string; assignee: string; armed: boolean }>
}

function NotifyPage(props: NotifyPageProps) {
  const recipients = normalizeRecipients(props.config.email.recipients)
  const activeItem = templateItems.find((item) => item.key === props.activeTemplate) || templateItems[0]
  const template = props.config.emailTemplates[props.activeTemplate]
  const subjectPreview = renderTemplatePreview(template.subject)
  const bodyPreview = renderTemplatePreview(template.body)

  return (
    <div className="stack-page notify-page">
      <div className="page-tabs">
        <button className={props.notifyTab === 'recipients' ? 'active' : ''} type="button" onClick={() => props.setNotifyTab('recipients')}>收件人</button>
        <button className={props.notifyTab === 'templates' ? 'active' : ''} type="button" onClick={() => props.setNotifyTab('templates')}>邮件模板</button>
      </div>

      {props.notifyTab === 'recipients' && (
        <div className="notify-grid">
          <div className="notify-column">
            <section className="card split-card notify-channel-card">
              <div>
                <p className="eyebrow">Channel</p>
                <h3>通知通道</h3>
                <p className="muted">当前使用 {props.config.notifyChannel === 'email' ? '邮箱提醒' : 'PushPlus'}，提醒规则由 Python 核心逻辑判断。</p>
              </div>
              <select
                value={props.config.notifyChannel}
                onChange={(event) => props.setConfig({ ...props.config, notifyChannel: event.target.value })}
              >
                <option value="email">Email</option>
                <option value="pushplus">PushPlus</option>
              </select>
            </section>

            <section className="card notify-card">
              <div className="section-title">
                <div>
                  <p className="eyebrow">Recipients</p>
                  <h3>收件人</h3>
                </div>
                <button type="button" onClick={props.save} disabled={props.saving}>{props.saving ? '保存中…' : '保存收件人'}</button>
              </div>
              <div className="recipient-row compact-row">
                <input value={props.recipientDraft} onChange={(event) => props.setRecipientDraft(event.target.value)} placeholder="输入邮箱地址" />
                <button type="button" onClick={props.addRecipient}>添加</button>
              </div>
              <div className="recipient-list scroll-panel">
                {recipients.map((mail) => (
                  <div className="recipient-item" key={mail}>
                    <span>{mail}</span>
                    <button className="ghost" type="button" onClick={() => props.removeRecipient(mail)}>删除</button>
                  </div>
                ))}
                {!recipients.length && <p className="muted">还没有收件人。</p>}
              </div>
            </section>
          </div>

          <section className="card notify-card rotation-card">
            <div className="section-title">
              <div>
                <p className="eyebrow">Rotation</p>
                <h3>轮值名单</h3>
              </div>
              <button type="button" onClick={props.save} disabled={props.saving}>{props.saving ? '保存中…' : '保存轮值'}</button>
            </div>
            <div className="recipient-row compact-row">
              <input value={props.rotationDraft} onChange={(event) => props.setRotationDraft(event.target.value)} placeholder="A, B, C, D" />
            </div>
            <p className="muted">可直接填写真人名字；这里只决定邮件里写谁处理，不影响群发收件人。</p>
            <div className="recipient-list scroll-panel">
              {props.rotationSummary.map((item) => (
                <div className="recipient-item rotation-item" key={item.key}>
                  <div>
                    <strong>{item.label}</strong>
                    <p className="muted">当前轮到 {item.assignee}</p>
                  </div>
                  <small className={`rotation-flag ${item.armed ? 'armed' : ''}`}>{item.armed ? '本轮告警处理中' : '等待下一轮告警'}</small>
                </div>
              ))}
              {!props.rotationSummary.length && <p className="muted">暂无轮值状态，先执行一次查询。</p>}
            </div>
          </section>
        </div>
      )}

      {props.notifyTab === 'templates' && !props.templateUnlocked && (
        <section className="card template-lock-card">
          <div>
            <p className="eyebrow">Locked</p>
            <h3>解锁邮件模板</h3>
            <p className="muted">邮件主题和正文会直接影响正式提醒内容，需要应用密码解锁后编辑。</p>
          </div>
          <div className="unlock-row">
            <input type="password" value={props.templatePassword} onChange={(event) => props.setTemplatePassword(event.target.value)} placeholder="应用密码" />
            <button type="button" onClick={props.unlockTemplates}>解锁</button>
          </div>
        </section>
      )}

      {props.notifyTab === 'templates' && props.templateUnlocked && (
        <section className="template-layout">
          <aside className="template-list card">
            <p className="eyebrow">Templates</p>
            <h3>邮件类型</h3>
            <div className="template-buttons">
              {templateItems.map((item) => (
                <button
                  className={props.activeTemplate === item.key ? 'active' : ''}
                  key={item.key}
                  type="button"
                  onClick={() => props.setActiveTemplate(item.key)}
                >
                  <span>{item.label}</span>
                  <small>{item.hint}</small>
                </button>
              ))}
            </div>
          </aside>

          <section className="card template-editor">
            <div className="section-title">
              <div>
                <p className="eyebrow">Editor</p>
                <h3>{activeItem.label}</h3>
                <p className="muted">支持用花括号插入变量，例如 {'{balance}'}、{'{time}'}。</p>
              </div>
              <div className="template-actions">
                <button className="secondary" type="button" onClick={() => props.restoreTemplate(props.activeTemplate)}>恢复默认</button>
                <button type="button" onClick={() => { void props.save(); props.setTemplatePassword(''); }} disabled={props.saving}>{props.saving ? '保存中…' : '保存模板'}</button>
              </div>
            </div>

            <div className="template-workbench">
              <div className="template-form">
                <TextField label="邮件主题" value={template.subject} onChange={(value) => props.updateTemplate(props.activeTemplate, { subject: value })} />
                <TextAreaField label="邮件正文" value={template.body} onChange={(value) => props.updateTemplate(props.activeTemplate, { body: value })} />
              </div>

              <div className="template-preview">
                <p className="eyebrow">Preview</p>
                <h4>{subjectPreview}</h4>
                <pre>{bodyPreview}</pre>
              </div>
            </div>
          </section>
        </section>
      )}
    </div>
  )
}

function PrivacyOverlay(props: {
  checked: boolean
  setChecked: (value: boolean) => void
  acceptPrivacy: () => void
  closeOverlay: () => void
  initialConsent: boolean
}) {
  return (
    <div className="onboarding-backdrop">
      <section className="onboarding-panel onboarding-panel-narrow">
        <div className="section-title compact">
          <div>
            <p className="eyebrow">Privacy</p>
            <h3>隐私与使用边界</h3>
          </div>
          {props.initialConsent && (
            <button className="ghost" type="button" onClick={props.closeOverlay}>稍后再看</button>
          )}
        </div>
        <div className="stack-page">
          <article className="card onboarding-card">
            <h3>在进入软件前，请确认以下使用边界</h3>
            <ul className="bullet-list muted">
              <li>本工具是本地桌面辅助程序，不是学校或微信小程序的官方服务。</li>
              <li>当前版本只支持用户本人已经在小程序中绑定的单宿舍电表，不提供全校扫描、他人宿舍查询或批量枚举能力。</li>
              <li>openId、发件邮箱、SMTP 授权码、收件人和本地查询状态默认只保存在当前电脑的配置目录中。</li>
              <li>邮箱提醒依赖你自行开启 SMTP 服务并提供授权码；SMTP 授权码不是邮箱登录密码，请不要公开提交。</li>
              <li>学校接口、小程序参数和邮箱服务策略可能变化，余额数据以官方缴费平台实际显示为准。</li>
            </ul>
            <label className="consent-row consent-box">
              <input type="checkbox" checked={props.checked} onChange={(event) => props.setChecked(event.target.checked)} />
              <span>我已阅读并理解上述隐私、数据保存方式与使用边界。</span>
            </label>
          </article>
          <div className="inline-actions onboarding-footer">
            <button type="button" disabled={!props.checked} onClick={props.acceptPrivacy}>
              我已阅读并同意，继续进入引导
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}

function OnboardingOverlay(props: {
  config: RawConfig
  step: number
  setStep: (value: number) => void
  completeOnboarding: () => void
  closeOverlay: () => void
  goSettings: () => void
  goNotify: () => void
  openPrivacy: () => void
  openSmtpHelp: () => void
}) {
  const isLastStep = props.step === 2
  return (
    <div className="onboarding-backdrop">
      <section className="onboarding-panel onboarding-panel-narrow">
        <div className="section-title compact">
          <div>
            <p className="eyebrow">Welcome</p>
            <h3>首次启动引导</h3>
            <p className="muted">步骤 {props.step + 1} / 3</p>
          </div>
          <button className="ghost" type="button" onClick={props.closeOverlay}>稍后再看</button>
        </div>

        <div className="step-dots" aria-hidden="true">
          {[0, 1, 2].map((step) => <span key={step} className={step === props.step ? 'active' : ''}></span>)}
        </div>

        {props.step === 0 && (
          <article className="card onboarding-card">
            <p className="eyebrow">Step 1</p>
            <h3>获取并填写 openId</h3>
            <p className="muted">openId 是小程序接口里识别当前微信用户与已绑定宿舍关系的参数，通常是一串较长的字母数字，例如：</p>
            <code className="inline-code">{openIdPreview}</code>
            <ul className="bullet-list muted">
              <li>安装 Reqable 并信任 HTTPS 证书。</li>
              <li>打开小程序后点一次照明和空调查询。</li>
              <li>在请求里找到 `openId`，填到敏感配置。</li>
            </ul>
            <div className="inline-actions onboarding-footer">
              <button className="secondary" type="button" onClick={props.openPrivacy}>返回隐私说明</button>
              <button type="button" onClick={props.goSettings}>去敏感配置填写</button>
              <button type="button" onClick={() => props.setStep(1)}>下一步</button>
            </div>
          </article>
        )}

        {props.step === 1 && (
          <article className="card onboarding-card">
            <p className="eyebrow">Step 2</p>
            <h3>配置邮箱 SMTP 授权码</h3>
            <p className="muted">SMTP 是邮箱提供给第三方客户端发送邮件的协议。本工具填写的是“授权码”，不是邮箱登录密码。</p>
            <ul className="bullet-list muted">
              <li>登录 QQ 邮箱，开启 SMTP 或 IMAP/SMTP 服务。</li>
              <li>按页面提示生成授权码。</li>
              <li>在敏感配置里填写发件邮箱、服务器、端口和授权码。</li>
              <li>保存后点击顶部“测试邮件”验证链路。</li>
            </ul>
            <div className="inline-actions">
              <button className="link-button" type="button" onClick={props.openSmtpHelp}>查看 QQ 邮箱 SMTP 帮助</button>
            </div>
            <div className="inline-actions onboarding-footer">
              <button className="secondary" type="button" onClick={() => props.setStep(0)}>上一步</button>
              <button type="button" onClick={props.goSettings}>去敏感配置填写</button>
              <button type="button" onClick={() => props.setStep(2)}>下一步</button>
            </div>
          </article>
        )}

        {props.step === 2 && (
          <article className="card onboarding-card">
            <p className="eyebrow">Step 3</p>
            <h3>确认配置并开始使用</h3>
            <p className="muted">完成引导前建议确认三件事：`openId` 已填写、通知收件人已添加、邮箱提醒链路已通过测试邮件验证。后续仍可在设置页继续修改。</p>
            <ul className="bullet-list muted">
              <li>openId 当前状态：{props.config.openId ? '已填写' : '未填写'}</li>
              <li>邮箱收件人：{normalizeRecipients(props.config.email.recipients).length ? '已填写' : '未填写'}</li>
              <li>隐私同意：已记录</li>
            </ul>
            <div className="inline-actions onboarding-footer">
              <button className="secondary" type="button" onClick={() => props.setStep(1)}>上一步</button>
              <button className="secondary" type="button" onClick={props.goNotify}>去通知页补收件人</button>
              <button type="button" onClick={props.completeOnboarding}>{isLastStep ? '完成引导' : '继续'}</button>
            </div>
          </article>
        )}
      </section>
    </div>
  )
}

function SettingsPage(props: {
  config: RawConfig
  runtime: RuntimeInfo | null
  updateConfig: (patch: Partial<RawConfig>) => void
  updateEmail: (patch: Partial<RawConfig['email']>) => void
  save: () => void
  saving: boolean
  settingsUnlocked: boolean
  unlockPassword: string
  setUnlockPassword: (value: string) => void
  unlockSettings: () => void
  toggleAutostart: (enabled: boolean) => void
  settingsTab: SettingsTab
  setSettingsTab: (tab: SettingsTab) => void
  openSmtpHelp: () => void
}) {
  return (
    <div className="stack-page settings-page settings-page-wide">
      <div className="page-tabs settings-tabs">
        <button className={props.settingsTab === 'runtime' ? 'active' : ''} type="button" onClick={() => props.setSettingsTab('runtime')}>基础运行</button>
        <button className={props.settingsTab === 'sensitive' ? 'active' : ''} type="button" onClick={() => props.setSettingsTab('sensitive')}>敏感配置</button>
      </div>

      {props.settingsTab === 'runtime' && (
        <section className="card form-card form-card-compact">
          <div className="section-title">
            <div>
              <p className="eyebrow">Monitor</p>
              <h3>基础运行参数</h3>
            </div>
            <label className="switch-line compact-switch">
              <input type="checkbox" checked={Boolean(props.runtime?.autostart.openAtLogin)} onChange={(event) => props.toggleAutostart(event.target.checked)} />
              开机自启动
            </label>
          </div>
          <div className="form-grid">
            <NumberField label="检查间隔（分钟）" value={props.config.checkIntervalMinutes} onChange={(value) => props.updateConfig({ checkIntervalMinutes: value })} />
            <NumberField label="普通提醒阈值" value={props.config.warningThreshold} onChange={(value) => props.updateConfig({ warningThreshold: value })} />
            <NumberField label="强提醒阈值" value={props.config.criticalThreshold} onChange={(value) => props.updateConfig({ criticalThreshold: value })} />
            <NumberField label="重复提醒间隔" value={props.config.remindEveryChecks} onChange={(value) => props.updateConfig({ remindEveryChecks: value })} />
          </div>
          <p className="muted compact-note">这里只放运行参数。`openId`、发件邮箱和 SMTP 授权码都放在“敏感配置”页签里。</p>
          <div className="save-row">
            <button type="button" onClick={() => { void props.save() }} disabled={props.saving}>{props.saving ? '保存中…' : '保存基础参数'}</button>
          </div>
        </section>
      )}

      {props.settingsTab === 'sensitive' && (
        <section className="card form-card form-card-compact sensitive-panel">
          <div className="section-title section-title-top">
            <div>
              <p className="eyebrow">Security</p>
              <h3>敏感配置</h3>
              <p className="muted">先输入应用密码解锁，再查看或修改 `openId`、发件邮箱和 SMTP 授权码。</p>
            </div>
            {!props.settingsUnlocked && (
              <div className="unlock-row unlock-row-wide">
                <input type="password" value={props.unlockPassword} onChange={(event) => props.setUnlockPassword(event.target.value)} placeholder="应用密码" />
                <button type="button" onClick={props.unlockSettings}>解锁</button>
              </div>
            )}
          </div>

          <div className="form-grid">
            <div className="field field-span-2">
              <span>openId</span>
              <input
                type={props.settingsUnlocked ? 'text' : 'password'}
                value={props.config.openId}
                disabled={!props.settingsUnlocked}
                onChange={(event) => props.updateConfig({ openId: event.target.value })}
                placeholder={props.settingsUnlocked ? '输入 openId' : '未解锁时默认隐藏'}
              />
            </div>
            <TextField label="发件邮箱" value={props.config.email.sender} disabled={!props.settingsUnlocked} onChange={(value) => props.updateEmail({ sender: value })} />
            <TextField label="SMTP 服务器" value={props.config.email.smtpHost} disabled={!props.settingsUnlocked} onChange={(value) => props.updateEmail({ smtpHost: value })} />
            <NumberField label="SMTP 端口" value={props.config.email.smtpPort} disabled={!props.settingsUnlocked} onChange={(value) => props.updateEmail({ smtpPort: value })} />
            <TextField label="SMTP 授权码" type="password" value={props.config.email.password} disabled={!props.settingsUnlocked} onChange={(value) => props.updateEmail({ password: value })} />
          </div>

          <div className="sensitive-links muted">
            <span>需要帮助：</span>
            <button className="link-button" type="button" onClick={props.openSmtpHelp}>QQ 邮箱 SMTP 帮助</button>
            <span>·</span>
            <span>openId 来自你自己抓到的小程序请求参数，不是宿舍号。</span>
          </div>

          <div className="save-row">
            <button type="button" onClick={() => { void props.save(); props.setUnlockPassword(''); }} disabled={props.saving}>{props.saving ? '保存中…' : '保存敏感配置'}</button>
          </div>
        </section>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>
}

function NumberField({ label, value, onChange, disabled }: { label: string; value: number; onChange: (value: number) => void; disabled?: boolean }) {
  return <label className="field"><span>{label}</span><input type="number" value={value} disabled={disabled} onChange={(event) => onChange(Number(event.target.value))} /></label>
}

function TextField({ label, value, onChange, disabled, type = 'text' }: { label: string; value: string; onChange: (value: string) => void; disabled?: boolean; type?: string }) {
  return <label className="field"><span>{label}</span><input type={type} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} /></label>
}

function TextAreaField({ label, value, onChange, disabled }: { label: string; value: string; onChange: (value: string) => void; disabled?: boolean }) {
  return <label className="field"><span>{label}</span><textarea value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} /></label>
}

function getOverallStatus(state: MonitorState | null) {
  if (!state) return { level: 'idle', label: '等待', title: '读取本地状态', detail: '应用正在读取本地状态。' }
  if (state.lastError) return { level: 'critical', label: '失败', title: '查询失败', detail: state.lastError.split('\n')[0] }
  const levels = Object.values(state.meters || {}).map((meter) => meter.level)
  if (levels.includes('critical')) return { level: 'critical', label: '告急', title: '余额告急', detail: '已有电表余额低于强提醒阈值。' }
  if (levels.includes('warning')) return { level: 'warning', label: '偏低', title: '余额偏低', detail: '已有电表余额低于普通提醒阈值。' }
  if (levels.length) return { level: 'normal', label: '正常', title: '运行正常', detail: '所有电表余额处于安全范围。' }
  return { level: 'idle', label: '等待', title: '等待首次查询', detail: '点击立即查询获取最新余额。' }
}

function normalizeRecipients(value: RawConfig['email']['recipients']) {
  if (Array.isArray(value)) return value
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function getMeterLocation(meter: MeterState) {
  const roomLabel = (meter.roomLabel || '').trim()
  if (!roomLabel) return ''
  const suffix = `· ${meter.name}`
  return roomLabel.endsWith(suffix) ? roomLabel.slice(0, -suffix.length).trim() : roomLabel
}

function normalizeConfig(config: RawConfig) {
  return {
    ...config,
    onboardingCompleted: Boolean(config.onboardingCompleted),
    privacyConsentVersion: config.privacyConsentVersion || '',
    privacyConsentedAt: config.privacyConsentedAt || '',
    email: { ...config.email, recipients: normalizeRecipients(config.email.recipients) },
    emailTemplates: { ...defaultEmailTemplates, ...(config.emailTemplates || {}) },
  }
}

function renderTemplatePreview(template: string) {
  return template.replace(/\{([A-Za-z][A-Za-z0-9]*)\}/g, (match, key: string) => previewVariables[key] || match)
}

export default App
