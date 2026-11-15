const input = document.querySelector('#url');
const error = document.querySelector('#error');
const recent = document.querySelector('#recent');
const list = document.querySelector('#recentList');
const scanButton = document.querySelector('#scan');
const key = 'autorip.server.urls';

function urls() {
  try {
    const values = JSON.parse(localStorage.getItem(key) || '[]');
    if (!Array.isArray(values)) return [];
    const result = [];
    for (const value of values) {
      if (typeof value === 'string' && !result.includes(value)) result.push(value);
      if (result.length === 5) break;
    }
    return result;
  }
  catch { return []; }
}
function render() {
  const items = urls();
  recent.hidden = !items.length;
  list.replaceChildren();
  items.forEach(value => {
    const li = document.createElement('li');
    const button = document.createElement('button');
    button.textContent = value;
    button.onclick = () => { input.value = value; connect(value); };
    li.appendChild(button);
    list.appendChild(li);
  });
}
function parseServerUrl(value) {
  const text = value.trim();
  if (!text || /[?#]/.test(text)) throw new Error('query-fragment');
  const url = new URL(text);
  if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash) throw new Error('invalid-url');
  return url;
}
function connect(value = input.value) {
  error.textContent = '';
  let url;
  try { url = parseServerUrl(value); }
  catch {
    error.textContent = 'Informe um endereço HTTP(S) válido, sem usuário, senha, query ou fragmento.';
    return false;
  }
  const clean = url.href.replace(/\/$/, '');
  const items = [clean, ...urls().filter(x => x !== clean)].slice(0, 5);
  try { localStorage.setItem(key, JSON.stringify(items)); }
  catch { /* O histórico é opcional; falha de armazenamento não impede conexão. */ }
  location.replace(`${clean}/`);
  return true;
}

async function scanQr() {
  if (scanButton.disabled) return;
  error.textContent = '';
  scanButton.disabled = true;
  try {
    const { BarcodeFormat, BarcodeScanner } = await loadScanner();
    const supported = await BarcodeScanner.isSupported();
    if (!supported.supported) {
      error.textContent = 'Este dispositivo não tem câmera compatível para ler QR.';
      return;
    }
    let permission = await BarcodeScanner.checkPermissions();
    if (permission.camera !== 'granted') permission = await BarcodeScanner.requestPermissions();
    if (permission.camera !== 'granted') {
      error.textContent = 'Permissão da câmera negada. Autorize a câmera nas configurações ou informe o endereço manualmente.';
      return;
    }
    const result = await BarcodeScanner.scan({ formats: [BarcodeFormat.QrCode] });
    const value = result.barcodes?.find(barcode => barcode.format === BarcodeFormat.QrCode && barcode.rawValue)?.rawValue;
    if (!value) return; // Leitura cancelada ou sem QR: permanecer na tela.
    let url;
    try { url = parseServerUrl(value); }
    catch {
      error.textContent = 'O QR não contém um endereço HTTP(S) válido. São aceitos apenas URLs sem usuário, senha, query ou fragmento.';
      return;
    }
    input.value = url.href;
    connect(url.href);
  } catch (cause) {
    const message = String(cause?.message || cause || '');
    if (/cancel|dismiss|canceled/i.test(message)) return;
    error.textContent = 'Não foi possível abrir a câmera. Você ainda pode informar o endereço manualmente.';
  } finally {
    scanButton.disabled = false;
  }
}

let scanner;
function loadScanner() {
  if (!scanner) {
    scanner = import('@capacitor-mlkit/barcode-scanning').catch(error => {
      scanner = null;
      throw error;
    });
  }
  return scanner;
}

document.querySelector('#connect').onclick = () => connect();
input.addEventListener('keydown', event => { if (event.key === 'Enter') connect(); });
scanButton.onclick = scanQr;
render();
