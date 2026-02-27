const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // App controls
  minimize: () => ipcRenderer.invoke('app:minimize'),
  maximize: () => ipcRenderer.invoke('app:maximize'),
  close: () => ipcRenderer.invoke('app:close'),
  quit: () => ipcRenderer.invoke('app:quit'),
  getAppConfig: () => ipcRenderer.invoke('app:get-config'),
  getConfig: () => ipcRenderer.invoke('app:get-config'),
  openExternal: (url) => {
    // Only allow http/https URLs to prevent file:// or javascript: exploits
    if (typeof url === 'string' && /^https?:\/\//i.test(url)) {
      return ipcRenderer.invoke('app:open-external', url);
    }
    return Promise.reject(new Error('Only http/https URLs allowed'));
  },
  getPath: (name) => ipcRenderer.invoke('app:get-path', name),
  restartServices: () => ipcRenderer.invoke('app:restart-services'),

  // Wizard IPC
  testLLM: (config) => ipcRenderer.invoke('wizard:test-llm', config),
  saveConfig: (config) => ipcRenderer.invoke('wizard:save-config', config),
  completeSetup: () => ipcRenderer.invoke('wizard:complete-setup'),

  // Stripe IPC
  getStripeConfig: () => ipcRenderer.invoke('stripe:get-config'),
  saveStripeKeys: (keys) => ipcRenderer.invoke('stripe:save-keys', keys),

  // SMTP IPC
  getSmtpConfig: () => ipcRenderer.invoke('smtp:get-config'),
  saveSmtpConfig: (config) => ipcRenderer.invoke('smtp:save-config', config),

  // Agent Purchase Approval
  showPurchaseApproval: (data) => ipcRenderer.invoke('agent:purchase-approval', data),

  // Windows Sandbox
  sandbox: {
    checkAvailable: () => ipcRenderer.invoke('sandbox:check-available'),
    launch: (config) => ipcRenderer.invoke('sandbox:launch', config),
    stop: () => ipcRenderer.invoke('sandbox:stop'),
    isRunning: () => ipcRenderer.invoke('sandbox:is-running'),
    requestCapture: () => ipcRenderer.invoke('sandbox:request-capture'),
    getThumbnail: () => ipcRenderer.invoke('sandbox:get-thumbnail'),
    focus: () => ipcRenderer.invoke('sandbox:focus'),
    focusOgenti: () => ipcRenderer.invoke('sandbox:focus-ogenti'),
  },

  // Events
  on: (channel, callback) => {
    const validChannels = ['service-status', 'backend-log', 'runtime-log'];
    if (validChannels.includes(channel)) {
      const wrappedCallback = (_, data) => callback(data);
      // Store reference for removal
      callback._wrappedCallback = wrappedCallback;
      ipcRenderer.on(channel, wrappedCallback);
    }
  },
  removeListener: (channel, callback) => {
    // Use stored wrapped reference so the correct listener is removed
    const wrapped = callback._wrappedCallback || callback;
    ipcRenderer.removeListener(channel, wrapped);
  },
});
