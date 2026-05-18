const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const fs = require('fs');

let mainWindow = null;
let backendProcess = null;

const isDev = !app.isPackaged;
const pythonDist = isDev
  ? path.join(__dirname, 'python-dist')
  : path.join(process.resourcesPath, 'python-dist');

function getBackendExe() {
  const ext = process.platform === 'win32' ? '.exe' : '';
  return path.join(pythonDist, `avscraper-backend${ext}`);
}

function getAppDataDir() {
  return path.join(app.getPath('userData'), 'appdata');
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = require('net').createServer();
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on('error', reject);
  });
}

function waitForServer(port, maxRetries = 30) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      http.get(`http://127.0.0.1:${port}/`, (res) => {
        resolve(port);
      }).on('error', () => {
        attempts++;
        if (attempts >= maxRetries) {
          reject(new Error('Backend server did not start'));
        } else {
          setTimeout(check, 500);
        }
      });
    };
    check();
  });
}

async function startBackend() {
  const port = await findFreePort();
  const exe = getBackendExe();
  const appDataDir = getAppDataDir();

  fs.mkdirSync(appDataDir, { recursive: true });

  backendProcess = spawn(exe, [], {
    env: {
      ...process.env,
      FLASK_PORT: String(port),
      AV_DESKTOP: '1',
      AV_APPDATA: appDataDir,
      AV_CONFIG: path.join(appDataDir, 'config.yaml'),
    },
    cwd: pythonDist,
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.on('error', (err) => {
    dialog.showErrorBox('Backend Error', `Failed to start backend: ${err.message}`);
    app.quit();
  });

  try {
    await waitForServer(port);
  } catch (e) {
    dialog.showErrorBox('Startup Error', 'Backend server failed to start. Check that all dependencies are included.');
    app.quit();
    return;
  }

  return port;
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'AV Scraper',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(`http://127.0.0.1:${port}`);
  mainWindow.on('closed', () => { mainWindow = null; });
}

app.whenReady().then(async () => {
  if (!fs.existsSync(getBackendExe())) {
    dialog.showErrorBox('Missing Backend', `Backend executable not found at:\n${getBackendExe()}\n\nRun build.py first.`);
    app.quit();
    return;
  }

  const port = await startBackend();
  createWindow(port);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow(port);
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
