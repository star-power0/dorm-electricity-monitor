import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('monitorApi', {
  bootstrap: () => ipcRenderer.invoke('monitor:bootstrap'),
  getState: () => ipcRenderer.invoke('monitor:get-state'),
  checkOnce: () => ipcRenderer.invoke('monitor:check-once'),
  getConfig: () => ipcRenderer.invoke('monitor:get-config'),
  saveConfig: (config: unknown) => ipcRenderer.invoke('monitor:save-config', config),
  sendTestMail: () => ipcRenderer.invoke('monitor:send-test-mail'),
  setAutostart: (enabled: boolean) => ipcRenderer.invoke('monitor:set-autostart', enabled),
  getRuntimeInfo: () => ipcRenderer.invoke('monitor:get-runtime-info'),
  openExternal: (url: string) => ipcRenderer.invoke('monitor:open-external', url),
  onStateUpdated: (listener: (state: unknown) => void) => {
    const handler = (_event: unknown, state: unknown) => listener(state)
    ipcRenderer.on('monitor:state-updated', handler)
    return () => ipcRenderer.removeListener('monitor:state-updated', handler)
  },
})
