const {app, BrowserWindow, Menu, ipcMain, safeStorage, dialog, shell} = require('electron');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const {pathToFileURL} = require('node:url');
const {validateSettings} = require('./settings.cjs');
const {provisionFromDotenv} = require('./autoprovision.cjs');
let window, backend, quitting = false, starting = false;
const setupURL = pathToFileURL(path.join(__dirname, 'setup.html')).href;
const smoke = process.argv.includes('--desktop-smoke');
if (process.env.SUPEREZIO_DESKTOP_TEST_DATA) app.setPath('userData', process.env.SUPEREZIO_DESKTOP_TEST_DATA);
if (!app.requestSingleInstanceLock()) app.quit();
app.on('second-instance', () => { if (window) { window.show(); window.focus(); } });
function stopBackend() { if (backend) { backend.removeAllListeners('exit'); backend.kill(); backend = null; } }
function makeWindow(setup = false) {
  const next = new BrowserWindow({width: 1480, height: 960, minWidth: 1180, minHeight: 720, show: false,
    title: 'SuperEzio — Trade e investimentos', backgroundColor: '#111820',
    webPreferences: {nodeIntegration: false, contextIsolation: true, sandbox: true,
      preload: setup ? path.join(__dirname, 'preload.cjs') : undefined}});
  next.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
  next.webContents.on('will-navigate', (event, url) => {
    if (url !== next.webContents.getURL()) event.preventDefault();
  });
  next.webContents.session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  next.once('ready-to-show', () => { if (!smoke) next.show(); });
  next.on('closed', () => { if (window === next) window = null; });
  const previous = window; window = next;
  if (previous) previous.destroy();
  return next;
}
function settingsPath() { return path.join(app.getPath('userData'), 'api-settings.enc'); }
function readSettings() {
  if (!fs.existsSync(settingsPath())) return null;
  if (!safeStorage.isEncryptionAvailable()) throw new Error('Proteção de credenciais do Windows indisponível.');
  return validateSettings(JSON.parse(safeStorage.decryptString(fs.readFileSync(settingsPath()))));
}
function persistSettings(settings) {
  if (!safeStorage.isEncryptionAvailable()) throw new Error('Proteção de credenciais do Windows indisponível.');
  const target = settingsPath(); fs.mkdirSync(path.dirname(target), {recursive: true});
  fs.writeFileSync(target + '.tmp', safeStorage.encryptString(JSON.stringify(settings)));
  fs.renameSync(target + '.tmp', target);
}
// ── Auto-provision (módulo puro em autoprovision.cjs): em dev lê o dotenv da
// raiz do repositório; no instalado, o do perfil do usuário. Sem tela manual
// quando as chaves já existem na máquina.
function dotenvDirs() {
  const dirs = [];
  if (!app.isPackaged) dirs.push(path.join(__dirname, '..')); // dev: raiz do repositório
  dirs.push(app.getPath('userData'));                          // instalado: perfil do usuário
  return dirs;
}
async function freePort() {
  return new Promise((resolve, reject) => { const server = net.createServer(); server.once('error', reject);
    server.listen(0, '127.0.0.1', () => { const port = server.address().port; server.close(() => resolve(port)); }); });
}
async function launch(settings) {
  if (starting) throw new Error('Inicialização já em andamento.');
  starting = true;
  try {
    stopBackend();
    const port = await freePort();
    const dataRoot = path.join(app.getPath('userData'), 'workspace');
    fs.mkdirSync(dataRoot, {recursive: true});
    let command, commandArgs, childCwd;
    const packagedExe = app.isPackaged ? path.join(process.resourcesPath, 'backend', 'SuperEzioBackend.exe') : null;
    const devExe = path.join(__dirname, '..', 'dist', 'desktop-backend', 'SuperEzioBackend', 'SuperEzioBackend.exe');
    if (packagedExe && fs.existsSync(packagedExe)) { command = packagedExe; commandArgs = []; childCwd = dataRoot; }
    else if (fs.existsSync(devExe)) { command = devExe; commandArgs = []; childCwd = dataRoot; }
    else if (!app.isPackaged) {
      // Dev sem PyInstaller: sobe o backend Python direto (cwd=src, quirk do repo).
      command = process.env.SUPEREZIO_PYTHON || 'python'; commandArgs = ['-m', 'agent_server.main'];
      childCwd = path.join(__dirname, '..', 'src');
    }
    else throw new Error('Backend não encontrado. Reinstale o SuperEzio.');
    const logPath = path.join(app.getPath('userData'), 'backend.log');
    const log = fs.openSync(logPath, 'a');
    const env = {...process.env, ...settings, SUPEREZIO_PORT: String(port), SUPEREZIO_HOST: '127.0.0.1',
      SUPEREZIO_DESKTOP_DATA_DIR: dataRoot, F51_TRADING_EXECUTION_FREEZE: '1',
      SUPEREZIO_LIVE_TRADING_DISABLED: '1', SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT: '0'};
    delete env.PYTHONPATH; delete env.PYTHONHOME;
    backend = spawn(command, commandArgs, {cwd: childCwd, env, windowsHide: true, stdio: ['ignore', log, log]});
    fs.closeSync(log);
    const child = backend;
    let failure;
    child.on('error', () => { failure = 'Não foi possível iniciar o backend.'; });
    child.on('exit', (code) => {
      failure = `Backend encerrou (${code}). Consulte Ajuda → Abrir logs.`;
      if (!starting && !quitting) dialog.showErrorBox('SuperEzio', failure);
    });
    const url = `http://127.0.0.1:${port}`;
    let ready = false;
    for (let i = 0; i < 120; i++) {
      if (failure) throw new Error(failure);
      try { const r = await fetch(`${url}/health`, {signal: AbortSignal.timeout(1500)});
        if (r.status === 200 || r.status === 503) { ready = true; break; } } catch {}
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    if (!ready) throw new Error('O backend demorou para iniciar. Consulte Ajuda → Abrir logs.');
    await makeWindow().loadURL(url);
    if (smoke) {
      const health = await (await fetch(`${url}/health`)).json();
      const check = await window.webContents.executeJavaScript(`({title:document.title,chat:!!document.querySelector('#chat'),node:typeof require})`);
      fs.writeFileSync(path.join(app.getPath('userData'), 'desktop-smoke.json'), JSON.stringify({health,check,packaged:app.isPackaged}));
      stopBackend(); app.exit(check.chat && check.node === 'undefined' ? 0 : 1);
    }
  } catch (error) { stopBackend(); throw error; }
  finally { starting = false; }
}
ipcMain.handle('settings:save', async (event, input) => {
  if (event.senderFrame.url !== setupURL) throw new Error('Origem não autorizada.');
  try {
    const settings = validateSettings(input);
    persistSettings(settings);
    await launch(settings); return {ok: true};
  } catch (error) { return {ok: false, error: error.message}; }
});
app.whenReady().then(async () => {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {label:'SuperEzio', submenu:[{label:'Configurar APIs', click:() => makeWindow(true).loadURL(setupURL)}, {role:'quit',label:'Sair'}]},
    {label:'Exibir',submenu:[{role:'reload',label:'Recarregar'},{role:'togglefullscreen',label:'Tela cheia'},{role:'resetzoom'},{role:'zoomin'},{role:'zoomout'}]},
    {label:'Ajuda',submenu:[{label:'Abrir logs',click:() => shell.openPath(app.getPath('userData'))},{label:'Sobre',click:() => dialog.showMessageBox({title:'SuperEzio',message:`SuperEzio ${app.getVersion()}`,detail:'Trade e assistente de investimento. Execução com dinheiro real bloqueada.'})}]}
  ]));
  try {
    // Sem chave salva: usa as do dotenv do projeto automaticamente — sem tela
    // (também no --desktop-smoke: o backend é fail-closed sem chave).
    let settings = readSettings() || provisionFromDotenv(dotenvDirs());
    if (settings && !smoke) persistSettings(settings);
    if (settings) await launch(settings); else await makeWindow(true).loadURL(setupURL);
  } catch (error) {
    if (smoke) { fs.writeFileSync(path.join(app.getPath('userData'),'desktop-smoke-error.txt'), error.message); app.exit(1); }
    else { dialog.showErrorBox('SuperEzio', error.message); makeWindow(true).loadURL(setupURL); }
  }
});
app.on('before-quit', () => { quitting = true; stopBackend(); });
app.on('will-quit', stopBackend);
app.on('window-all-closed', () => app.quit());
