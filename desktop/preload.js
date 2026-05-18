const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('avscraper', {
  platform: process.platform,
  isDesktop: true,
  quit: () => ipcRenderer.send('quit'),
  openFolder: (folderPath) => ipcRenderer.send('open-folder', folderPath),
});
