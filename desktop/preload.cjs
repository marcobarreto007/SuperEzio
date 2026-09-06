const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('superEzioSetup', {
  save: (settings) => ipcRenderer.invoke('settings:save', settings)
});
