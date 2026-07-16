/* ═══════════════════════════════════════════
   CTV — App Core: tabs, cameras, state, search
   ═══════════════════════════════════════════ */

const S = {
  session: { deployment: 'standalone', authenticated: true, is_admin: true, source_roots: [] },
  cameras: [],          // ordinamento corrente (persistito in localStorage)
  timeline: null,
  currentTime: null,
  zoomRange: null,
  gridCols: 2,          // auto-calcolato dal numero di camere
  gridRows: 1,
  gridLayout: 2,
  playing: false,
  speed: 1,
  loop: false,
  colorMap: {},
  rWidth: 0,
  activeTab: 'timeline',
  visibleCameraIds: [],
  selectedDate: null,
  editingCameraId: null,
  layoutMode: localStorage.getItem('ctv-layout') || 'auto',
  customCols: Number(localStorage.getItem('ctv-grid-cols') || 2),
  customRows: Number(localStorage.getItem('ctv-grid-rows') || 2),
  aspectMode: localStorage.getItem('ctv-aspect') || '4/3',
  page: 0,
  pageSize: 1,
  focusCameraId: null,
  hotspotPrimaryId: null,
  hotspotSideCols: 1,
  hotspotSideRows: 1,
  hotspotMobile: false,
  loadingPartitions: 0,
};

function isCompactViewport() {
  return window.matchMedia('(max-width: 760px), (max-width: 900px) and (max-height: 500px)').matches;
}

function useStackedMobileHotspot() {
  return window.matchMedia('(max-width: 760px) and (orientation: portrait)').matches;
}

const COLORS = ['#58a6ff','#3fb950','#f78166','#d2991d','#bc8cff','#f778ba','#39d2c0','#f97316',
                '#84cc16','#f43f5e','#6366f1','#14b8a6','#d946ef','#0ea5e9'];
function camColor(cid) {
  const idx = S.cameras.findIndex(c => c.id === cid);
  return COLORS[idx >= 0 ? idx % COLORS.length : Object.keys(S.colorMap).length % COLORS.length];
}

function visibleCameras() {
  return S.cameras.filter(camera => S.visibleCameraIds.includes(camera.id));
}

function displayedCameras() {
  const cameras = visibleCameras();
  if (S.focusCameraId) return cameras.filter(camera => camera.id === S.focusCameraId);
  const start = S.page * S.pageSize;
  const page = cameras.slice(start, start + S.pageSize);
  if (S.layoutMode === 'hotspot' && S.hotspotPrimaryId) {
    const primaryIndex = page.findIndex(camera => camera.id === S.hotspotPrimaryId);
    if (primaryIndex > 0) page.unshift(page.splice(primaryIndex, 1)[0]);
  }
  return page;
}

const _location = new URL(window.location.href);
_location.search = '';
_location.hash = '';
if (!_location.pathname.endsWith('/')) {
  const lastPart = _location.pathname.split('/').pop() || '';
  _location.pathname = lastPart.includes('.')
    ? _location.pathname.slice(0, _location.pathname.lastIndexOf('/') + 1)
    : _location.pathname + '/';
}
const APP_BASE = _location;

function appUrl(path) {
  return new URL(String(path).replace(/^\/+/, ''), APP_BASE).toString();
}

applyTranslations();
document.getElementById('language-select').addEventListener('change', event => setLanguage(event.target.value));

async function api(url, opts = {}) {
  if (opts.body && typeof opts.body === 'object') {
    opts.body = JSON.stringify(opts.body);
    opts.headers = { ...opts.headers, 'Content-Type': 'application/json' };
  }
  const res = await fetch(appUrl(url), opts);
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    let msg = body;
    try { const j = JSON.parse(body); msg = j.detail || body; } catch {}
    throw new Error(msg || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function escAttr(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function localizeMessage(message) {
  const value = String(message ?? '');
  const prefixes = [
    ['Sorgente non disponibile', t('cameras.sourceUnavailable')],
    ['Sorgente non leggibile', t('cameras.sourceUnreadable')],
  ];
  for (const [prefix, translated] of prefixes) {
    if (value === prefix) return translated;
    if (value.startsWith(prefix + ':')) return translated + value.slice(prefix.length);
  }
  return value;
}
function fmtTime(ts) { return new Date(ts * 1000).toLocaleString(ctvLocale()); }
function fmtTimeShort(ts) { return new Date(ts * 1000).toLocaleTimeString(ctvLocale(), {hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
function fmtTick(ts, step) {
  const d = new Date(ts * 1000);
  if (step >= 86400) return d.toLocaleDateString(ctvLocale(), {day:'numeric',month:'short'});
  if (step >= 3600) return String(d.getHours()).padStart(2,'0')+':00';
  if (step >= 60) return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
  return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')+':'+String(d.getSeconds()).padStart(2,'0');
}
function niceTickStep(range, width) {
  const rough = range / (width / 80);
  const steps = [1,2,5,10,15,30,60,120,300,600,900,1800,3600,7200,14400,43200,86400];
  for (const s of steps) if (s >= rough) return s;
  return 86400;
}

// ═══ Toast ═══
let _toastTimer;
function toast(msg, type) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.className = type || 'info';
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.className = ''; }, 3000);
}

// ═══ Tab switching ═══
function switchTab(name) {
  if (S.activeTab === name) return;
  // Esci dalla timeline → ferma tutto
  if (S.activeTab === 'timeline') stopPlayback();
  // Aggiorna UI
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelector(`.tab[data-tab="${name}"]`).classList.add('active');
  const view = document.getElementById('view-' + name);
  if (view) view.classList.add('active');
  S.activeTab = name;
  // Entra nella timeline → renderizza
  if (name === 'timeline') { renderTimeline(); renderPlayers(); updateCursor(); updateTimeDisplay(); }
}

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ═══ Camera order persistence ═══
function loadOrder() {
  try { return JSON.parse(localStorage.getItem('ctv-cam-order') || '[]'); }
  catch { return []; }
}
function saveOrder(ids) {
  localStorage.setItem('ctv-cam-order', JSON.stringify(ids));
}

function sortCamerasByOrder(cameras) {
  const order = loadOrder();
  const ordered = [];
  const byId = {};
  cameras.forEach(c => byId[c.id] = c);
  // Prima quelle nell'ordine salvato
  order.forEach(id => { if (byId[id]) { ordered.push(byId[id]); delete byId[id]; } });
  // Poi le nuove (non ancora nell'ordine) in fondo
  cameras.forEach(c => { if (byId[c.id]) ordered.push(c); });
  // Salva ordine aggiornato
  saveOrder(ordered.map(c => c.id));
  return ordered;
}

// ═══ Camera management ═══
async function loadCameras() {
  try { S.cameras = sortCamerasByOrder(await api('/api/cameras')); }
  catch(e) { toast(t('cameras.errorLoading'), 'error'); return; }
  const validIds = new Set(S.cameras.map(camera => camera.id));
  if (!S.visibleCameraIds.length) {
    try { S.visibleCameraIds = JSON.parse(localStorage.getItem('ctv-visible-cameras') || '[]'); }
    catch { S.visibleCameraIds = []; }
  }
  S.visibleCameraIds = S.visibleCameraIds.filter(id => validIds.has(id));
  if (!S.visibleCameraIds.length) S.visibleCameraIds = S.cameras.map(camera => camera.id);
  renderCamList();
  renderCameraFilter();
  updateGridLayout();
  renderViewerCameraList();
}

async function loadSession() {
  S.session = await api('/api/session');
  const isAdmin = Boolean(S.session.is_admin);
  document.querySelector('.tab[data-tab="cameras"]').hidden = !isAdmin;
  document.getElementById('view-cameras').hidden = !isAdmin;
  document.getElementById('btn-browse-source').hidden = !isAdmin || !S.session.source_roots?.length;
  const pathInput = document.getElementById('cam-path');
  pathInput.readOnly = S.session.deployment === 'homeassistant';
  if (!isAdmin && S.activeTab === 'cameras') switchTab('timeline');
}

function updateGridLayout() {
  const area = document.getElementById('player-area');
  const n = Math.max(1, visibleCameras().length);
  const width = Math.max(160, area.clientWidth - 8);
  const height = Math.max(90, area.clientHeight - 8);
  area.classList.toggle('fill', S.aspectMode === 'fill');
  area.classList.toggle('hotspot-layout', S.layoutMode === 'hotspot' && !S.focusCameraId);

  if (S.focusCameraId) {
    S.gridCols = 1; S.gridRows = 1;
  } else if (S.layoutMode === 'custom') {
    S.gridCols = S.customCols; S.gridRows = S.customRows;
  } else if (/^\d+x\d+$/.test(S.layoutMode)) {
    [S.gridCols, S.gridRows] = S.layoutMode.split('x').map(Number);
  } else if (S.layoutMode === 'hotspot') {
    S.gridCols = 2; S.gridRows = 1;
  } else {
    const ratio = aspectRatio();
    let best = { score: -1, cols: 1, rows: n };
    for (let cols = 1; cols <= Math.min(n, 8); cols++) {
      const rows = Math.ceil(n / cols);
      const cellW = Math.min(width / cols, (height / rows) * ratio);
      const score = cellW * (cellW / ratio) * n;
      if (score > best.score) best = { score, cols, rows };
    }
    S.gridCols = best.cols; S.gridRows = best.rows;
  }

  S.pageSize = S.layoutMode === 'hotspot' && !S.focusCameraId ? 9 : S.gridCols * S.gridRows;
  const pages = Math.max(1, Math.ceil(visibleCameras().length / S.pageSize));
  S.page = Math.min(S.page, pages - 1);
  document.getElementById('page-controls').hidden = pages <= 1 || Boolean(S.focusCameraId);
  document.getElementById('page-display').textContent = `${S.page + 1}/${pages}`;

  if (S.layoutMode === 'hotspot' && !S.focusCameraId) {
    const ratio = aspectRatio();
    const gap = 3;
    const pageCount = Math.min(S.pageSize, Math.max(0, visibleCameras().length - S.page * S.pageSize));
    const secondaryCount = Math.max(0, pageCount - 1);
    S.hotspotMobile = useStackedMobileHotspot();

    if (secondaryCount === 0) {
      S.hotspotSideCols = 0; S.hotspotSideRows = 1;
      const cellW = Math.floor(Math.min(width, height * ratio));
      const cellH = Math.floor(cellW / ratio);
      area.style.gridTemplateColumns = `${cellW}px`;
      area.style.gridTemplateRows = `${cellH}px`;
    } else if (S.hotspotMobile) {
      const sideCols = Math.min(2, secondaryCount);
      const sideRows = Math.ceil(secondaryCount / sideCols);
      const sideW = Math.floor((width - (sideCols - 1) * gap) / sideCols);
      const maxSideH = Math.max(42, Math.floor((height * 0.34 - (sideRows - 1) * gap) / sideRows));
      const sideH = Math.max(42, Math.min(Math.floor(sideW / ratio), maxSideH));
      const sideBlockH = sideRows * sideH + (sideRows - 1) * gap;
      const mainH = Math.max(80, Math.min(Math.floor(width / ratio), height - sideBlockH - gap));
      S.hotspotSideCols = sideCols; S.hotspotSideRows = sideRows;
      area.style.gridTemplateColumns = `repeat(${sideCols}, ${sideW}px)`;
      area.style.gridTemplateRows = `${mainH}px repeat(${sideRows}, ${sideH}px)`;
    } else {
      let best = null;
      // Fino a quattro camere preserva la gerarchia hotspot: una principale e una sola colonna laterale.
      const candidateColumns = secondaryCount <= 3
        ? [1]
        : Array.from({ length: secondaryCount }, (_, index) => index + 1);
      for (const sideCols of candidateColumns) {
        const sideRows = Math.ceil(secondaryCount / sideCols);
        const byHeight = (height - (sideRows - 1) * gap) / sideRows;
        const fixedWidth = ratio * (sideRows - 1) * gap + sideCols * gap;
        const byWidth = (width - fixedWidth) / (ratio * (sideRows + sideCols));
        const rowH = Math.floor(Math.min(byHeight, byWidth));
        if (rowH < 30) continue;
        const usedCells = secondaryCount + sideRows * sideRows;
        const score = rowH * rowH * usedCells;
        if (!best || score > best.score) best = { sideCols, sideRows, rowH, score };
      }
      best ||= { sideCols: 1, sideRows: secondaryCount, rowH: 40 };
      S.hotspotSideCols = best.sideCols; S.hotspotSideRows = best.sideRows;
      const sideW = Math.floor(best.rowH * ratio);
      const mainH = best.sideRows * best.rowH + (best.sideRows - 1) * gap;
      const mainW = Math.floor(mainH * ratio);
      area.style.gridTemplateColumns = `${mainW}px repeat(${best.sideCols}, ${sideW}px)`;
      area.style.gridTemplateRows = `repeat(${best.sideRows}, ${best.rowH}px)`;
    }
    area.style.setProperty('--cell-w', '100%');
    area.style.setProperty('--cell-h', '100%');
  } else {
    const ratio = aspectRatio();
    const cellW = Math.max(80, Math.floor(Math.min(width / S.gridCols, (height / S.gridRows) * ratio)));
    const cellH = Math.max(60, Math.floor(cellW / ratio));
    area.style.gridTemplateColumns = `repeat(${S.gridCols}, ${cellW}px)`;
    area.style.gridTemplateRows = `repeat(${S.gridRows}, ${cellH}px)`;
    area.style.setProperty('--cell-w', `${cellW}px`);
    area.style.setProperty('--cell-h', `${cellH}px`);
  }
  S.gridLayout = S.pageSize;
  applyHotspotCellPositions();
}

function applyHotspotCellPositions() {
  const cells = Array.from(document.querySelectorAll('#player-area .player-cell'));
  cells.forEach(cell => { cell.style.gridColumn = ''; cell.style.gridRow = ''; });
  if (S.layoutMode !== 'hotspot' || S.focusCameraId || !cells.length) return;
  if (S.hotspotMobile) {
    cells[0].style.gridColumn = `1 / span ${Math.max(1, S.hotspotSideCols)}`;
    cells[0].style.gridRow = '1';
    cells.slice(1).forEach((cell, index) => {
      cell.style.gridColumn = String(1 + (index % S.hotspotSideCols));
      cell.style.gridRow = String(2 + Math.floor(index / S.hotspotSideCols));
    });
    return;
  }
  cells[0].style.gridColumn = '1';
  cells[0].style.gridRow = `1 / span ${S.hotspotSideRows}`;
  cells.slice(1).forEach((cell, index) => {
    cell.style.gridColumn = String(2 + (index % S.hotspotSideCols));
    cell.style.gridRow = String(1 + Math.floor(index / S.hotspotSideCols));
  });
}

function aspectRatio() {
  if (S.aspectMode === '16/9') return 16 / 9;
  return 4 / 3;
}

function renderCamList() {
  const el = document.getElementById('cam-list');
  if (!S.session.is_admin) {
    el.innerHTML = '';
    return;
  }
  if (!S.cameras.length) {
    el.innerHTML = `<div class="empty-hint">${esc(t('cameras.noneConfigured'))}</div>`;
    return;
  }
  el.innerHTML = S.cameras.map((c, i) => `
    <div class="cam-item${S.editingCameraId === c.id ? ' selected' : ''}" draggable="true" data-id="${c.id}" data-idx="${i}"
         onclick="selectCamera(${c.id})"
         ondragstart="onCamDragStart(event)" ondragover="onCamDragOver(event)"
         ondragleave="onCamDragLeave(event)" ondrop="onCamDrop(event)" ondragend="onCamDragEnd(event)">
      <span class="drag-handle" aria-hidden="true">⠿</span>
      <span class="dot" style="background:${camColor(c.id)}" aria-hidden="true"></span>
      <span class="cam-main">
        <span class="name">${esc(c.name)}</span>
        <span class="cam-meta">${esc(c.source_path)}</span>
        <span class="cam-stats">${esc(cameraStats(c))}</span>
      </span>
      <span class="source-status ${escAttr(c.source_status)}" title="${escAttr(localizeMessage(c.source_error || ''))}">
        ${sourceStatusLabel(c)}
      </span>
      <button class="btn-icon" aria-label="${escAttr(t('cameras.scan', {name: c.name}))}" title="${escAttr(t('cameras.scan', {name: c.name}))}"
        onclick="event.stopPropagation();scanCam(${c.id})">↻</button>
      <button class="btn-icon" aria-label="${escAttr(t('cameras.remove', {name: c.name}))}" title="${escAttr(t('cameras.remove', {name: c.name}))}"
        onclick="event.stopPropagation();deleteCam(${c.id})">✕</button>
    </div>
  `).join('');
}

function renderCameraFilter() {
  const menu = document.getElementById('camera-filter-menu');
  const button = document.getElementById('btn-camera-filter');
  const selected = visibleCameras().length;
  button.textContent = `${t('tab.cameras')} ${selected}/${S.cameras.length}`;
  menu.innerHTML = S.cameras.map(camera => `
    <label class="camera-filter-option">
      <input type="checkbox" value="${camera.id}" ${S.visibleCameraIds.includes(camera.id) ? 'checked' : ''}>
      <span class="dot" style="background:${camColor(camera.id)}"></span>
      <span>${esc(camera.name)}</span>
    </label>
  `).join('') || `<div class="empty-hint">${esc(t('cameras.none'))}</div>`;
  menu.querySelectorAll('input').forEach(input => {
    input.addEventListener('change', () => toggleVisibleCamera(Number(input.value), input.checked));
  });
}

function renderViewerCameraList() {
  const list = document.getElementById('viewer-camera-list');
  list.innerHTML = S.cameras.map(camera => `
    <div class="viewer-camera-item${displayedCameras().some(item => item.id === camera.id) ? ' current' : ''}"
         data-camera-id="${camera.id}" title="${escAttr(t('cameras.focus'))}">
      <input type="checkbox" ${S.visibleCameraIds.includes(camera.id) ? 'checked' : ''}
             aria-label="${escAttr(t('cameras.show', {name: camera.name}))}">
      <span class="dot" style="background:${camColor(camera.id)}"></span>
      <span class="viewer-cam-name">${esc(camera.name)}</span>
      <span class="viewer-cam-state ${escAttr(camera.source_status)}">${camera.source_status === 'online' ? '●' : '○'}</span>
    </div>
  `).join('') || `<div class="empty-hint">${esc(t('cameras.none'))}</div>`;
  list.querySelectorAll('.viewer-camera-item').forEach(item => {
    const id = Number(item.dataset.cameraId);
    item.querySelector('input').addEventListener('change', event => {
      event.stopPropagation(); toggleVisibleCamera(id, event.target.checked);
    });
    item.addEventListener('click', event => { if (event.target.tagName !== 'INPUT') showCameraPage(id); });
    item.addEventListener('dblclick', event => { if (event.target.tagName !== 'INPUT') toggleCameraFocus(id); });
  });
}

function showCameraPage(id) {
  const index = visibleCameras().findIndex(camera => camera.id === id);
  if (index < 0) return;
  S.focusCameraId = null;
  S.page = Math.floor(index / S.pageSize);
  if (S.layoutMode === 'hotspot') S.hotspotPrimaryId = id;
  updateGridLayout(); renderPlayers(); renderViewerCameraList();
  if (isCompactViewport()) setSidebarCollapsed(true, false);
}

function promoteHotspotCamera(id) {
  if (S.layoutMode !== 'hotspot' || S.focusCameraId) return;
  S.hotspotPrimaryId = id;
  renderPlayers(); renderViewerCameraList();
}

function toggleCameraFocus(id) {
  S.focusCameraId = S.focusCameraId === id ? null : id;
  updateGridLayout(); renderPlayers(); renderViewerCameraList();
}

function toggleVisibleCamera(id, checked) {
  if (checked && !S.visibleCameraIds.includes(id)) S.visibleCameraIds.push(id);
  if (!checked) {
    if (S.visibleCameraIds.length === 1) {
      renderCameraFilter();
      toast(t('cameras.keepOneVisible'), 'error');
      return;
    }
    S.visibleCameraIds = S.visibleCameraIds.filter(cameraId => cameraId !== id);
  }
  localStorage.setItem('ctv-visible-cameras', JSON.stringify(S.visibleCameraIds));
  S.currentTime = null;
  S.zoomRange = null;
  renderCameraFilter();
  renderViewerCameraList();
  updateGridLayout();
  loadTimeline();
}

document.getElementById('btn-camera-filter').onclick = event => {
  event.stopPropagation();
  const menu = document.getElementById('camera-filter-menu');
  menu.classList.toggle('open');
  event.currentTarget.setAttribute('aria-expanded', String(menu.classList.contains('open')));
};
document.addEventListener('click', event => {
  if (!event.target.closest('#camera-filter-wrap')) {
    document.getElementById('camera-filter-menu').classList.remove('open');
    document.getElementById('btn-camera-filter').setAttribute('aria-expanded', 'false');
  }
});

document.getElementById('layout-select').value = S.layoutMode;
document.getElementById('aspect-select').value = S.aspectMode;
document.getElementById('grid-cols').value = S.customCols;
document.getElementById('grid-rows').value = S.customRows;
document.getElementById('custom-grid-controls').hidden = S.layoutMode !== 'custom';

document.getElementById('layout-select').onchange = event => {
  S.layoutMode = event.target.value; S.page = 0; S.focusCameraId = null;
  S.hotspotPrimaryId = null;
  localStorage.setItem('ctv-layout', S.layoutMode);
  document.getElementById('custom-grid-controls').hidden = S.layoutMode !== 'custom';
  updateGridLayout(); renderPlayers(); renderViewerCameraList();
};
document.getElementById('aspect-select').onchange = event => {
  S.aspectMode = event.target.value;
  localStorage.setItem('ctv-aspect', S.aspectMode);
  updateGridLayout(); renderPlayers();
};
function updateCustomGrid() {
  S.customCols = Math.max(1, Math.min(8, Number(document.getElementById('grid-cols').value) || 1));
  S.customRows = Math.max(1, Math.min(8, Number(document.getElementById('grid-rows').value) || 1));
  localStorage.setItem('ctv-grid-cols', S.customCols);
  localStorage.setItem('ctv-grid-rows', S.customRows);
  S.page = 0; updateGridLayout(); renderPlayers(); renderViewerCameraList();
}
document.getElementById('grid-cols').onchange = updateCustomGrid;
document.getElementById('grid-rows').onchange = updateCustomGrid;
document.getElementById('btn-page-prev').onclick = () => {
  S.page = Math.max(0, S.page - 1); updateGridLayout(); renderPlayers(); renderViewerCameraList();
};
document.getElementById('btn-page-next').onclick = () => {
  const pages = Math.ceil(visibleCameras().length / S.pageSize);
  S.page = Math.min(pages - 1, S.page + 1); updateGridLayout(); renderPlayers(); renderViewerCameraList();
};

function setSidebarCollapsed(collapsed, persist = true) {
  document.getElementById('viewer-sidebar').classList.toggle('collapsed', collapsed);
  if (persist) localStorage.setItem('ctv-sidebar-collapsed', collapsed ? '1' : '0');
  setTimeout(() => { updateGridLayout(); renderPlayers(); }, 170);
}
document.getElementById('btn-sidebar').onclick = () => {
  setSidebarCollapsed(!document.getElementById('viewer-sidebar').classList.contains('collapsed'));
};
document.getElementById('btn-sidebar-close').onclick = () => setSidebarCollapsed(true);
setSidebarCollapsed(
  isCompactViewport() || localStorage.getItem('ctv-sidebar-collapsed') === '1',
  false,
);

function sourceStatusLabel(camera) {
  if (camera.source_status === 'online') {
    const key = Number(camera.recordings_available) === 1 ? 'cameras.oneFile' : 'cameras.manyFiles';
    return t(key, {count: camera.recordings_available});
  }
  if (camera.source_status === 'scanning') return t('cameras.scanning');
  if (camera.source_status === 'offline') return t('cameras.offline');
  return t('cameras.notChecked');
}

function cameraStats(camera) {
  const parts = [];
  if (camera.source_error) parts.push(localizeMessage(camera.source_error));
  if (camera.recordings_missing) parts.push(t('cameras.unavailable', {count: camera.recordings_missing}));
  if (camera.last_scan_completed) parts.push(t('cameras.lastScan', {time: fmtTime(camera.last_scan_completed)}));
  return parts.join(' · ') || t('cameras.neverScanned');
}

async function scanCam(id) {
  try {
    const camera = S.cameras.find(item => item.id === id);
    if (camera?.indexing_mode === 'partitioned') {
      const range = selectedDayRange();
      if (!range) throw new Error(t('cameras.selectDayFirst'));
      const result = await api(
        `/api/timeline/prepare?from=${range[0]}&to=${range[1]}&cameras=${id}`,
        { method: 'POST' },
      );
      S.loadingPartitions += result.partitions || 0;
    } else {
      await api('/api/scan/' + id, { method: 'POST' });
    }
    if (camera) camera.source_status = 'scanning';
    renderCamList();
    document.getElementById('topbar-status').textContent = t('cameras.scanStarted');
  } catch(e) {
    toast(t('cameras.errorScan', {message: localizeMessage(e.message)}), 'error');
  }
}

// ═══ Drag & Drop ═══
let _dragSrcIdx = -1;

function onCamDragStart(e) {
  _dragSrcIdx = parseInt(e.currentTarget.dataset.idx);
  e.currentTarget.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', '');
}

function onCamDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  const tgt = e.currentTarget;
  if (!tgt.classList.contains('dragging')) tgt.classList.add('drag-over');
}

function onCamDragLeave(e) {
  e.currentTarget.classList.remove('drag-over');
}

function onCamDrop(e) {
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  const dstIdx = parseInt(e.currentTarget.dataset.idx);
  if (_dragSrcIdx === dstIdx || _dragSrcIdx < 0) return;

  // Sposta nell'array
  const item = S.cameras.splice(_dragSrcIdx, 1)[0];
  S.cameras.splice(dstIdx, 0, item);
  saveOrder(S.cameras.map(c => c.id));
  renderCamList();
  loadTimeline();
  renderPlayers();
}

function onCamDragEnd(e) {
  document.querySelectorAll('.cam-item').forEach(el => el.classList.remove('dragging', 'drag-over'));
  _dragSrcIdx = -1;
}

// ═══ Delete ═══
async function deleteCam(id) {
  if (!confirm(t('cameras.confirmRemove'))) return;
  try {
    await api('/api/cameras/' + id, { method: 'DELETE' });
    delete _playerCache[id];
    S.visibleCameraIds = S.visibleCameraIds.filter(cameraId => cameraId !== id);
    localStorage.setItem('ctv-visible-cameras', JSON.stringify(S.visibleCameraIds));
    if (S.editingCameraId === id) resetCameraForm();
    loadCameras(); loadTimeline();
    toast(t('cameras.removed'), 'info');
  } catch(e) {
    toast(t('cameras.errorGeneric', {message: localizeMessage(e.message)}), 'error');
  }
}

function selectCamera(id) {
  const camera = S.cameras.find(item => item.id === id);
  if (!camera) return;
  S.editingCameraId = id;
  document.getElementById('camera-form-title').textContent = t('cameras.edit');
  document.getElementById('cam-name').value = camera.name;
  document.getElementById('cam-path').value = camera.source_path;
  setCameraTimezone(camera.timezone);
  document.getElementById('cam-indexing-mode').value = camera.indexing_mode || 'partitioned';
  document.getElementById('cam-pattern').value = camera.directory_pattern || '{YYYY}/{MM}/{DD}';
  document.getElementById('btn-add-cam').textContent = t('cameras.save');
  document.getElementById('btn-cancel-edit').hidden = false;
  renderCamList();
}

function resetCameraForm() {
  S.editingCameraId = null;
  document.getElementById('camera-form-title').textContent = t('cameras.add');
  document.getElementById('cam-name').value = '';
  document.getElementById('cam-path').value = '';
  setCameraTimezone(DETECTED_TIMEZONE);
  document.getElementById('cam-indexing-mode').value = 'partitioned';
  document.getElementById('cam-pattern').value = '{YYYY}/{MM}/{DD}';
  document.getElementById('btn-add-cam').textContent = t('cameras.addAction');
  document.getElementById('btn-cancel-edit').hidden = true;
  renderCamList();
}

document.getElementById('btn-cancel-edit').onclick = resetCameraForm;

// ═══ Timeline loading ═══
function formatDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function selectedDayRange() {
  const value = S.selectedDate || document.getElementById('timeline-date').value;
  if (!value) return null;
  const [year, month, day] = value.split('-').map(Number);
  const start = new Date(year, month - 1, day).getTime() / 1000;
  const endDate = new Date(year, month - 1, day + 1);
  return [start, endDate.getTime() / 1000];
}

async function initializeTimelineDate() {
  const bounds = await api('/api/timeline/bounds');
  const date = bounds.last ? new Date(bounds.last * 1000) : new Date();
  S.selectedDate = formatDateInput(date);
  document.getElementById('timeline-date').value = S.selectedDate;
}

async function loadTimeline(from, to, prepare = true) {
  try {
    if (from == null || to == null) {
      const range = selectedDayRange();
      if (range) [from, to] = range;
    }
    const cameraQuery = S.visibleCameraIds.length ? S.visibleCameraIds.join(',') : '';
    if (prepare && from != null && to != null) {
      const result = await api(
        `/api/timeline/prepare?from=${from}&to=${to}&cameras=${cameraQuery}`,
        { method: 'POST' },
      );
      S.loadingPartitions = result.partitions || 0;
    }
    let url = '/api/timeline?';
    if (from != null) url += 'from=' + from + '&';
    if (to != null) url += 'to=' + to + '&';
    if (cameraQuery) url += 'cameras=' + cameraQuery;
    S.timeline = await api(url);
  } catch(e) { toast(t('cameras.errorTimeline'), 'error'); return; }
  if (!S.timeline || !S.timeline.cameras.length) {
    const range = selectedDayRange() || [0, 86400];
    S.timeline = { from: range[0], to: range[1], cameras: [] };
    S.currentTime = null;
    S.zoomRange = [...range];
    renderTimeline();
    renderPlayers();
    updateTimeDisplay();
    return;
  }
  // Ordina le camere della timeline secondo S.cameras
  const byId = {};
  S.timeline.cameras.forEach(c => byId[c.camera_id] = c);
  S.timeline.cameras = S.cameras.map(c => byId[c.id]).filter(Boolean);

  if (S.currentTime == null) {
    const starts = S.timeline.cameras.flatMap(camera => camera.segments.map(segment => segment.start_ts));
    if (starts.length) S.currentTime = Math.min(...starts);
  }
  if (!S.zoomRange) {
    if (isCompactViewport() && S.timeline.to - S.timeline.from > 6 * 3600) {
      const range = 6 * 3600;
      let from = Math.max(S.timeline.from, (S.currentTime ?? S.timeline.from) - 30 * 60);
      let to = from + range;
      if (to > S.timeline.to) { to = S.timeline.to; from = Math.max(S.timeline.from, to - range); }
      S.zoomRange = [from, to];
    } else {
      S.zoomRange = [S.timeline.from, S.timeline.to];
    }
  }
  updateGridLayout();
  renderTimeline();
  renderPlayers();
  updateTimeDisplay();
}

async function changeDay(delta) {
  const range = selectedDayRange();
  const date = new Date((range ? range[0] : Date.now() / 1000) * 1000);
  date.setDate(date.getDate() + delta);
  S.selectedDate = formatDateInput(date);
  document.getElementById('timeline-date').value = S.selectedDate;
  S.currentTime = null;
  S.zoomRange = null;
  stopPlayback();
  await loadTimeline();
}

document.getElementById('btn-day-prev').onclick = () => changeDay(-1);
document.getElementById('btn-day-next').onclick = () => changeDay(1);
document.getElementById('btn-today').onclick = () => {
  S.selectedDate = formatDateInput(new Date());
  document.getElementById('timeline-date').value = S.selectedDate;
  S.currentTime = null; S.zoomRange = null; stopPlayback(); loadTimeline();
};
document.getElementById('timeline-date').onchange = event => {
  S.selectedDate = event.target.value;
  S.currentTime = null; S.zoomRange = null; stopPlayback(); loadTimeline();
};

// ═══ Source browser ═══
let _sourceBrowserPath = null;

function closeSourceBrowser() {
  const overlay = document.getElementById('source-overlay');
  overlay.classList.remove('open');
  overlay.setAttribute('aria-hidden', 'true');
}

async function loadSourceDirectory(path) {
  try {
    const query = path ? `?path=${encodeURIComponent(path)}` : '';
    const data = await api('/api/sources/directories' + query);
    _sourceBrowserPath = data.path;
    document.getElementById('source-current-path').textContent = data.path;
    const list = document.getElementById('source-directory-list');
    const rows = [];
    if (data.parent) {
      rows.push(`<button class="source-directory" data-path="${escAttr(data.parent)}">↰ ${esc(t('sources.parent'))}</button>`);
    }
    data.entries.forEach(entry => {
      rows.push(`<button class="source-directory" data-path="${escAttr(entry.path)}">▸ ${esc(entry.name)}</button>`);
    });
    list.innerHTML = rows.join('') || `<div class="source-empty">${esc(t('sources.empty'))}</div>`;
    list.querySelectorAll('.source-directory').forEach(button => {
      button.addEventListener('click', () => loadSourceDirectory(button.dataset.path));
    });
  } catch (error) {
    toast(t('sources.error', {message: localizeMessage(error.message)}), 'error');
  }
}

document.getElementById('btn-browse-source').onclick = () => {
  const overlay = document.getElementById('source-overlay');
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
  const current = document.getElementById('cam-path').value.trim();
  loadSourceDirectory(current || S.session.source_roots?.[0]);
};
document.getElementById('btn-source-close').onclick = closeSourceBrowser;
document.getElementById('btn-source-cancel').onclick = closeSourceBrowser;
document.getElementById('btn-source-select').onclick = () => {
  if (_sourceBrowserPath) {
    document.getElementById('cam-path').value = _sourceBrowserPath;
    suggestCameraName(_sourceBrowserPath);
  }
  closeSourceBrowser();
};
document.getElementById('cam-path').addEventListener('change', event => {
  suggestCameraName(event.target.value);
});
document.getElementById('source-overlay').addEventListener('click', function(event) {
  if (event.target === this) closeSourceBrowser();
});

// ═══ Search ═══
document.getElementById('btn-search-open').onclick = () => {
  document.getElementById('search-overlay').classList.add('open');
  document.getElementById('search-input').focus();
};
document.getElementById('btn-search-close').onclick = () => {
  document.getElementById('search-overlay').classList.remove('open');
};
document.getElementById('search-overlay').addEventListener('click', function(e) {
  if (e.target === this) this.classList.remove('open');
});
document.getElementById('search-overlay').addEventListener('keydown', function(e) {
  if (e.key === 'Escape') { this.classList.remove('open'); e.stopPropagation(); }
});

let _searchDebounce;
document.getElementById('search-input').addEventListener('input', function() {
  clearTimeout(_searchDebounce);
  const q = this.value.trim();
  if (q.length < 2) { document.getElementById('search-results').innerHTML = ''; return; }
  _searchDebounce = setTimeout(async () => {
    try {
      const range = selectedDayRange();
      let url = '/api/search?q=' + encodeURIComponent(q) + '&limit=50';
      if (range) url += `&from=${range[0]}&to=${range[1]}`;
      const results = (await api(url)).filter(result => S.visibleCameraIds.includes(result.camera_id));
      const c = document.getElementById('search-results');
      if (!results.length) {
        c.innerHTML = `<div style="padding:16px;color:var(--text-dim);text-align:center;">${esc(t('search.noResults'))}</div>`;
      } else {
        c.innerHTML = results.map(r => `
          <div class="search-hit" role="button" tabindex="0"
            onclick="openSearchResult(${r.start_ts})"
            onkeydown="if(event.key==='Enter'){this.click()}">
            <strong>${esc(r.camera_name)}</strong> &middot; ${esc(r.filename)}<br>
            <span class="ts">${fmtTime(r.start_ts)}${r.end_ts ? ' → '+fmtTimeShort(r.end_ts) : ''} &middot; ${(r.duration||0).toFixed(0)}s</span>
          </div>`).join('');
      }
    } catch(e) { toast(t('cameras.errorSearch'), 'error'); }
  }, 250);
});

function openSearchResult(timestamp) {
  document.getElementById('search-overlay').classList.remove('open');
  switchTab('timeline');
  seekTo(timestamp);
}

// ═══ Keyboard ═══
document.addEventListener('keydown', e => {
  const searchOpen = document.getElementById('search-overlay').classList.contains('open');
  if (searchOpen && e.key === 'Escape') {
    document.getElementById('search-overlay').classList.remove('open');
    e.stopPropagation(); return;
  }
  if (document.getElementById('source-overlay').classList.contains('open') && e.key === 'Escape') {
    closeSourceBrowser(); e.stopPropagation(); return;
  }
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  switch(e.key) {
    case ' ': e.preventDefault(); document.getElementById('btn-play').click(); break;
    case 'ArrowLeft': e.preventDefault(); jumpToBoundary(-1); break;
    case 'ArrowRight': e.preventDefault(); jumpToBoundary(1); break;
    case '+': case '=': zoom(2); break;
    case '-': zoom(0.5); break;
    case 'f': document.getElementById('btn-zoom-fit').click(); break;
    case 'Escape':
      if (S.focusCameraId) { S.focusCameraId = null; updateGridLayout(); renderPlayers(); renderViewerCameraList(); }
      break;

  }
});

// ═══ SSE ═══
const evtSource = new EventSource(appUrl('/api/events'));
evtSource.addEventListener('scan', e => {
  const d = JSON.parse(e.data);
  const el = document.getElementById('topbar-status');
  if (d.status === 'started') el.textContent = t('cameras.scanCamera', {id: d.camera_id});
  else if (d.status === 'done') {
    el.textContent = t('status.ready'); loadTimeline(); loadCameras();
    toast(t('cameras.scanComplete', {new: d.new || 0, updated: d.updated || 0, missing: d.missing || 0}), 'info');
  }
  else if (d.status === 'error') { el.textContent = t('cameras.sourceUnavailable'); loadCameras(); toast(localizeMessage(d.error), 'error'); }
  else if (d.status === 'thumbnails') el.textContent = t('cameras.thumbnails', {done: d.done, total: d.total});
  else if (d.status === 'indexing_done') el.textContent = t('cameras.scanNew', {id: d.camera_id, new: d.new});
});
evtSource.addEventListener('partition', e => {
  const data = JSON.parse(e.data);
  const status = document.getElementById('topbar-status');
  if (data.status === 'started') {
    status.textContent = t('timeline.loadingPartition', {partition: data.partition});
    updateTimelinePartitionState(data.camera_id, 'scanning', 0, 0);
  } else if (['done', 'missing', 'error'].includes(data.status)) {
    S.loadingPartitions = Math.max(0, S.loadingPartitions - 1);
    status.textContent = data.status === 'error' ? t('cameras.sourceError') : t('status.ready');
    if (data.status === 'error') toast(localizeMessage(data.error), 'error');
    loadTimeline(undefined, undefined, false);
    loadCameras();
  }
});
evtSource.addEventListener('partition_progress', e => {
  const data = JSON.parse(e.data);
  updateTimelinePartitionState(data.camera_id, 'scanning', data.done, data.total);
  document.getElementById('topbar-status').textContent =
    t('timeline.progress', {partition: data.partition, done: data.done, total: data.total});
});

function updateTimelinePartitionState(cameraId, state, done, total) {
  const camera = S.timeline?.cameras.find(item => item.camera_id === cameraId);
  if (!camera) return;
  camera.partition_status = state;
  camera.progress_done = done;
  camera.progress_total = total;
  renderTimeline();
}

// ═══ Add / Scan ═══
document.getElementById('btn-add-cam').onclick = async () => {
  const name = document.getElementById('cam-name').value.trim();
  const path = document.getElementById('cam-path').value.trim();
  const tz = document.getElementById('cam-tz').value.trim();
  const indexingMode = document.getElementById('cam-indexing-mode').value;
  const directoryPattern = document.getElementById('cam-pattern').value.trim();
  if (!name || !path) { toast(t('cameras.required'), 'error'); return; }
  try {
    if (S.editingCameraId) {
      const editingId = S.editingCameraId;
      await api('/api/cameras/' + editingId, {
        method: 'PUT', body: {
          name, source_path: path, timezone: tz,
          indexing_mode: indexingMode, directory_pattern: directoryPattern,
        }
      });
      if (indexingMode === 'full') await api('/api/scan/' + editingId, { method: 'POST' });
      toast(t('cameras.updated'), 'info');
    } else {
      const camera = await api('/api/cameras', {
        method: 'POST', body: {
          name, source_path: path, timezone: tz,
          indexing_mode: indexingMode, directory_pattern: directoryPattern,
        }
      });
      S.visibleCameraIds.push(camera.id);
      localStorage.setItem('ctv-visible-cameras', JSON.stringify(S.visibleCameraIds));
      if (indexingMode === 'full') await api('/api/scan/' + camera.id, { method: 'POST' });
      toast(t('cameras.added'), 'info');
    }
  } catch(e) { toast(t('cameras.errorGeneric', {message: localizeMessage(e.message)}), 'error'); return; }
  resetCameraForm();
  await loadCameras();
};

const DETECTED_TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

function availableTimezones() {
  let values = [];
  if (typeof Intl.supportedValuesOf === 'function') {
    try { values = Intl.supportedValuesOf('timeZone'); }
    catch { values = []; }
  }
  if (!values.length) {
    values = ['UTC', 'Europe/London', 'Europe/Paris', 'Europe/Rome', 'America/New_York', 'Asia/Tokyo'];
  }
  return [...new Set(['UTC', DETECTED_TIMEZONE, ...values])]
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right));
}

function setCameraTimezone(timezone) {
  const select = document.getElementById('cam-tz');
  const value = timezone || DETECTED_TIMEZONE;
  if (![...select.options].some(option => option.value === value)) {
    select.add(new Option(value, value));
  }
  select.value = value;
}

function initializeTimezoneSelect() {
  const select = document.getElementById('cam-tz');
  select.replaceChildren(...availableTimezones().map(timezone => new Option(timezone, timezone)));
  setCameraTimezone(DETECTED_TIMEZONE);
}

function suggestCameraName(path) {
  if (S.editingCameraId) return;
  const input = document.getElementById('cam-name');
  if (input.value.trim()) return;
  const normalized = String(path || '').replace(/[\\/]+$/, '');
  const name = normalized.split(/[\\/]/).pop();
  if (name) input.value = name;
}

initializeTimezoneSelect();

document.getElementById('btn-scan-all').onclick = async () => {
  document.getElementById('topbar-status').textContent = t('cameras.scanRunning');
  try {
    const range = selectedDayRange();
    if (range) {
      const result = await api(
        `/api/timeline/prepare?from=${range[0]}&to=${range[1]}&cameras=${S.visibleCameraIds.join(',')}`,
        { method: 'POST' },
      );
      S.loadingPartitions += result.partitions || 0;
    }
    await api('/api/scan', { method: 'POST' });
  }
  catch(e) { toast(t('cameras.errorScan', {message: localizeMessage(e.message)}), 'error'); }
};

// ═══ Timeline resize ═══
(function() {
  const handle = document.getElementById('resize-handle');
  let resizing = false, pointerId = null, startY, startH;
  handle.addEventListener('pointerdown', e => {
    if (!e.isPrimary) return;
    resizing = true; startY = e.clientY;
    pointerId = e.pointerId;
    handle.setPointerCapture?.(pointerId);
    startH = document.getElementById('timeline-wrap').getBoundingClientRect().height || 190;
    document.body.style.cursor = 'row-resize'; document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  handle.addEventListener('pointermove', e => {
    if (!resizing || e.pointerId !== pointerId) return;
    const maxH = window.innerHeight * (isCompactViewport() ? 0.48 : 0.6);
    const newH = Math.max(96, Math.min(maxH, startH + (startY - e.clientY)));
    document.documentElement.style.setProperty('--timeline-h', newH + 'px');
    localStorage.setItem('ctv-timeline-height', String(newH));
    updateGridLayout();
  });
  const stopResize = e => {
    if (!resizing || (e.pointerId != null && e.pointerId !== pointerId)) return;
    resizing = false; pointerId = null; document.body.style.cursor = ''; document.body.style.userSelect = '';
  };
  handle.addEventListener('pointerup', stopResize);
  handle.addEventListener('pointercancel', stopResize);
})();

const savedTimelineHeight = Number(localStorage.getItem('ctv-timeline-height'));
if (savedTimelineHeight && !isCompactViewport()) {
  document.documentElement.style.setProperty('--timeline-h', savedTimelineHeight + 'px');
}
new ResizeObserver(() => updateGridLayout()).observe(document.getElementById('player-area'));

let _viewportRefreshTimer = null;
function scheduleViewportRefresh() {
  clearTimeout(_viewportRefreshTimer);
  _viewportRefreshTimer = setTimeout(() => {
    updateGridLayout();
    renderPlayers();
    if (S.timeline && S.zoomRange) renderTimeline();
  }, 180);
}
window.addEventListener('resize', scheduleViewportRefresh);
window.addEventListener('orientationchange', scheduleViewportRefresh);

// ═══ Init ═══
window._ctvInit = function() {
  updateGridLayout();
  loadSession()
    .then(() => loadCameras())
    .then(() => initializeTimelineDate())
    .then(() => loadTimeline())
    .catch(error => toast(t('cameras.errorInit', {message: error.message}), 'error'));
};

window._ctvRefreshLanguage = function() {
  document.getElementById('camera-form-title').textContent =
    t(S.editingCameraId ? 'cameras.edit' : 'cameras.add');
  document.getElementById('btn-add-cam').textContent =
    t(S.editingCameraId ? 'cameras.save' : 'cameras.addAction');
  renderCamList();
  renderCameraFilter();
  renderViewerCameraList();
  renderTimeline();
  renderPlayers();
  updatePlayButton();
  updateTimeDisplay();
};
