/* ═══════════════════════════════════════════
   CTV — Timeline: rendering, overview, cursor
   ═══════════════════════════════════════════ */

const MIN_ZOOM_RANGE = 3;
let _overviewLastUpdate = 0;

function timeToX(ts, vFrom, vTo, width) {
  return ((ts - vFrom) / ((vTo - vFrom) || 1)) * width;
}

function timelineLabelWidth() {
  const value = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--timeline-label-w'));
  return Number.isFinite(value) ? value : 110;
}

function rowWidth() {
  const inner = document.getElementById('timeline-inner');
  return Math.max(isCompactViewport() ? 320 : 400, inner.clientWidth);
}

function contentWidth() {
  return Math.max(220, rowWidth() - timelineLabelWidth());
}

function renderTimeline() {
  const body = document.getElementById('timeline-body');
  if (!S.timeline || !S.timeline.cameras.length) {
    const hasCameras = S.cameras.length > 0;
    body.innerHTML = hasCameras
      ? `<div class="empty-timeline">${S.loadingPartitions > 0 ? t('timeline.loadingDay') : t('timeline.noneSelected')}</div>`
      : S.session.is_admin
        ? `<div class="empty-timeline">${esc(t('timeline.noData'))} <a href="#" onclick="document.querySelector('.tab[data-tab=cameras]').click()">${esc(t('timeline.addCamera'))}</a>.</div>`
        : `<div class="empty-timeline">${esc(t('timeline.askAdministrator'))}</div>`;
    document.getElementById('timeline-ruler').innerHTML = '';
    document.getElementById('overview').innerHTML = '';
    return;
  }

  const [vFrom, vTo] = S.zoomRange;
  const segW = contentWidth();   // per ruler e timeToX
  S.rWidth = segW;

  renderRuler(vFrom, vTo, segW);
  renderOverview(vFrom, vTo, segW);
  renderRows(vFrom, vTo, segW, rowWidth());
  updateCursor();
}

function renderRuler(vFrom, vTo, width) {
  const ruler = document.getElementById('timeline-ruler');
  const tickStep = niceTickStep(vTo - vFrom, width);
  let html = '';
  for (let t = Math.floor(vFrom / tickStep) * tickStep; t <= vTo; t += tickStep) {
    const x = timeToX(t, vFrom, vTo, width);
    const major = (t % (tickStep * 5) === 0 || tickStep >= 3600);
    html += `<div class="tick-line${major?' major':''}" style="left:${x}px"></div>`;
    html += `<div class="tick${major?' tick-major':''}" style="left:${x}px">${fmtTick(t, tickStep)}</div>`;
  }
  ruler.innerHTML = html;
  let pr = document.getElementById('playhead-ruler');
  if (!pr) { pr = document.createElement('div'); pr.id = 'playhead-ruler'; ruler.appendChild(pr); }
}

function renderOverview(vFrom, vTo, width) {
  const overview = document.getElementById('overview');
  const style = getComputedStyle(document.documentElement);
  const surface2 = style.getPropertyValue('--surface2').trim() || '#1c2333';
  const playheadColor = style.getPropertyValue('--playhead').trim() || '#f78166';

  let canvas = overview.querySelector('canvas');
  if (!canvas) {
    canvas = document.createElement('canvas');
    overview.appendChild(canvas);
    canvas.onclick = function(e) {
      if (!S.timeline) return;
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const ts = S.timeline.from + (x / rect.width) * (S.timeline.to - S.timeline.from);
      seekTo(ts);
    };
  }
  canvas.width = overview.clientWidth || 800;
  canvas.height = 32;
  const ctx = canvas.getContext('2d');
  const totalRange = (S.timeline.to - S.timeline.from) || 1;

  ctx.fillStyle = surface2;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  S.timeline.cameras.forEach(cam => {
    ctx.fillStyle = camColor(cam.camera_id);
    cam.segments.forEach(s => {
      const x = ((s.start_ts - S.timeline.from) / totalRange) * canvas.width;
      const w = Math.max(1.5, ((s.duration || 1) / totalRange) * canvas.width);
      ctx.fillRect(x, 5, w, canvas.height - 10);
    });
  });

  const vpLeft = ((vFrom - S.timeline.from) / totalRange) * canvas.width;
  const vpRight = ((vTo - S.timeline.from) / totalRange) * canvas.width;
  ctx.fillStyle = 'rgba(255,255,255,0.08)';
  ctx.fillRect(vpLeft, 0, vpRight - vpLeft, canvas.height);
  ctx.strokeStyle = 'rgba(255,255,255,0.25)';
  ctx.lineWidth = 1;
  const frameLeft = Math.max(0.5, vpLeft + 0.5);
  const frameRight = Math.min(canvas.width - 0.5, vpRight - 0.5);
  ctx.strokeRect(frameLeft, 0.5, Math.max(0, frameRight - frameLeft), canvas.height - 1);

  if (S.currentTime != null) {
    const px = ((S.currentTime - S.timeline.from) / totalRange) * canvas.width;
    ctx.strokeStyle = playheadColor; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, canvas.height); ctx.stroke();
  }

  _overviewLastUpdate = performance.now();
}

function renderRows(vFrom, vTo, segW, rW) {
  const body = document.getElementById('timeline-body');
  let html = '';
  S.timeline.cameras.forEach(cam => {
    const color = camColor(cam.camera_id);
    const segs = cam.segments
      .filter(s => (s.end_ts || s.start_ts) >= vFrom && s.start_ts <= vTo)
      .map(s => {
        const left = timeToX(s.start_ts, vFrom, vTo, segW);
        const w = s.end_ts ? timeToX(s.end_ts, vFrom, vTo, segW) - left : 3;
        const spx = Math.max(w, 3);
        const dur = s.duration || 0;
        let thumbHtml = '';
        if (s.has_thumbnail && spx > 50) {
          thumbHtml = `<img class="seg-thumb" src="${escAttr(appUrl(`/api/recordings/${s.id}/thumbnail`))}">`;
        }
        return `<div class="timeline-seg" style="left:${left}px;width:${spx}px;background:${color};"
          data-recording-id="${s.id}" data-start="${s.start_ts}" data-end="${s.end_ts||''}"
          data-camera="${escAttr(cam.camera_name)}" data-filename="${escAttr(s.filename)}"
          data-thumb="${s.has_thumbnail?'1':'0'}">
          ${thumbHtml}
          <div class="seg-info">${esc(s.filename)}${dur>0?' &middot; '+dur.toFixed(0)+'s':''}</div>
        </div>`;
      }).join('');
    let rowState = '';
    if (cam.partition_status === 'scanning') {
      rowState = cam.progress_total > 0
        ? t('timeline.loading', {done: cam.progress_done, total: cam.progress_total})
        : t('timeline.readingFolder');
    } else if (cam.partition_status === 'unknown') {
      rowState = t('timeline.waiting');
    } else if (cam.partition_status === 'error') {
      rowState = t('timeline.loadError');
    } else if (cam.partition_status === 'missing') {
      rowState = t('timeline.noFolder');
    } else if (!cam.segments.length) {
      rowState = t('timeline.noRecording');
    }
    const stateHtml = rowState
      ? `<div class="timeline-row-state ${escAttr(cam.partition_status || '')}">${esc(rowState)}</div>`
      : '';
    html += `<div class="timeline-row" data-cam="${cam.camera_id}" style="width:${rW}px">
      <div class="timeline-label"><span class="dot" style="background:${color}"></span>${esc(cam.camera_name)}</div>
      <div class="timeline-row-segments">${segs}${stateHtml}</div></div>`;
  });
  body.innerHTML = html;

  body.querySelectorAll('.timeline-seg').forEach(seg => {
    seg.addEventListener('mouseenter', showSegTooltip);
    seg.addEventListener('mouseleave', hideTooltip);
    seg.addEventListener('mousemove', moveSegTooltip);
  });
}

// ── Tooltip ──
let _ttEl;
let _ttHideTimer;
let _ttPoint = null;
function hideTooltip() { if (_ttEl) { _ttEl.style.display = 'none'; _ttEl.innerHTML = ''; } }
// Nascondi tooltip su scroll e quando il mouse esce dall'area timeline
(function() {
  const s = document.getElementById('timeline-scroll');
  s.addEventListener('scroll', hideTooltip);
  s.addEventListener('mouseleave', hideTooltip);
  // Anche wheel sullo scroll container chiude il tooltip
  s.addEventListener('wheel', () => setTimeout(hideTooltip, 50));
})();

function showSegTooltip(e) {
  clearTimeout(_ttHideTimer);
  if (!_ttEl) { _ttEl = document.createElement('div'); _ttEl.className = 'seg-tooltip'; document.body.appendChild(_ttEl); }
  const s = e.currentTarget;
  let h = '';
  if (s.dataset.thumb === '1') h += `<img class="tt-thumb" src="${escAttr(appUrl(`/api/recordings/${s.dataset.recordingId}/thumbnail`))}">`;
  h += `<div style="padding:8px 12px">`;
  h += `<div class="tt-name">${esc(s.dataset.camera)} &middot; ${esc(s.dataset.filename)}</div>`;
  const st = parseFloat(s.dataset.start), en = s.dataset.end ? parseFloat(s.dataset.end) : null;
  h += `<div class="tt-meta">${fmtTime(st)}${en ? ' → '+fmtTimeShort(en) : ''}</div>`;
  h += `</div>`;
  _ttEl.innerHTML = h; _ttEl.style.display = 'block'; moveSegTooltip(e);
  const image = _ttEl.querySelector('img');
  if (image) image.addEventListener('load', () => {
    if (_ttPoint && _ttEl.style.display !== 'none') positionSegTooltip(_ttPoint.x, _ttPoint.y);
  }, { once: true });
}
function positionSegTooltip(clientX, clientY) {
  const rect = _ttEl.getBoundingClientRect();
  const position = viewportPopoverPosition(
    { x: clientX, y: clientY },
    { width: rect.width, height: rect.height },
    { width: window.innerWidth, height: window.innerHeight },
  );
  _ttEl.style.left = `${position.left}px`;
  _ttEl.style.top = `${position.top}px`;
}
function moveSegTooltip(e) {
  if (!_ttEl || _ttEl.style.display === 'none') return;
  _ttPoint = { x: e.clientX, y: e.clientY };
  positionSegTooltip(e.clientX, e.clientY);
}
// ── Playhead ──
function ensurePlayhead() {
  if (!document.getElementById('playhead')) {
    const p = document.createElement('div'); p.id = 'playhead';
    document.getElementById('timeline-body').appendChild(p);
  }
}
function updateCursor() {
  ensurePlayhead();
  const p = document.getElementById('playhead');
  const pr = document.getElementById('playhead-ruler');
  if (S.currentTime == null || !S.zoomRange) { p.style.display='none'; if (pr) pr.style.display='none'; return; }
  const [vFrom, vTo] = S.zoomRange;
  if (S.currentTime < vFrom || S.currentTime > vTo) { p.style.display='none'; if (pr) pr.style.display='none'; return; }
  p.style.display = ''; if (pr) pr.style.display = '';
  const x = timeToX(S.currentTime, vFrom, vTo, S.rWidth);
  p.style.left = (timelineLabelWidth() + x) + 'px';  // playhead nel body → compensa label
  if (pr) pr.style.left = x + 'px';                  // playhead nel ruler → già allineato
  const overviewInterval = isCompactViewport() ? 250 : 120;
  if (performance.now() - _overviewLastUpdate >= overviewInterval) updateViewportIndicator();
}
function updateViewportIndicator() {
  if (!S.timeline) return;
  const overview = document.getElementById('overview');
  const canvas = overview.querySelector('canvas');
  if (!canvas) return;
  renderOverview(S.zoomRange[0], S.zoomRange[1], contentWidth());
}

// ── Zoom ──
function zoom(factor) {
  if (!S.zoomRange) return;
  if (_inertiaFrame) { cancelAnimationFrame(_inertiaFrame); _inertiaFrame = null; }
  const [from, to] = S.zoomRange;
  const center = S.currentTime != null ? S.currentTime : (from+to)/2;
  let newHalf = (to-from)/(2*factor);
  if (newHalf < MIN_ZOOM_RANGE/2) newHalf = MIN_ZOOM_RANGE/2;
  const maxHalf = (S.timeline.to - S.timeline.from) / 2;
  if (newHalf > maxHalf) newHalf = maxHalf;
  S.zoomRange = [Math.max(S.timeline.from, center-newHalf), Math.min(S.timeline.to, center+newHalf)];
  renderTimeline();
}
document.getElementById('btn-zoom-in').onclick = () => zoom(2);
document.getElementById('btn-zoom-out').onclick = () => zoom(0.5);
document.getElementById('btn-zoom-fit').onclick = () => {
  if (_inertiaFrame) { cancelAnimationFrame(_inertiaFrame); _inertiaFrame = null; }
  if (S.timeline) { S.zoomRange = [S.timeline.from, S.timeline.to]; renderTimeline(); }
};

// ── Pan via drag ──
let _dragging = false, _didDrag = false, _dragPointerId = null, _dragRow = null, _dragSegment = null;
let _dsX, _dsFrom, _dsTo, _suppressClickUntil = 0;
let _panRenderFrame = null, _inertiaFrame = null, _lastMoveX = 0, _lastMoveAt = 0, _velocityX = 0;
let _panSamples = [];
const timelineBody = document.getElementById('timeline-body');

function queuePanRender() {
  if (_panRenderFrame) return;
  _panRenderFrame = requestAnimationFrame(() => {
    _panRenderFrame = null;
    renderTimeline();
  });
}

function panZoomByPixels(deltaX) {
  if (!S.zoomRange || !S.timeline || !S.rWidth) return false;
  const range = S.zoomRange[1] - S.zoomRange[0];
  const dTime = -deltaX * (range / S.rWidth);
  let nf = S.zoomRange[0] + dTime, nt = S.zoomRange[1] + dTime;
  if (nf < S.timeline.from) { nt += S.timeline.from - nf; nf = S.timeline.from; }
  if (nt > S.timeline.to) { nf -= nt - S.timeline.to; nt = S.timeline.to; }
  if (nf < S.timeline.from) nf = S.timeline.from;
  if (nf === S.zoomRange[0] && nt === S.zoomRange[1]) return false;
  S.zoomRange = [nf, nt];
  queuePanRender();
  return true;
}

function startPanInertia() {
  cancelAnimationFrame(_inertiaFrame);
  if (Math.abs(_velocityX) < 0.03) return;
  let previous = performance.now();
  const step = now => {
    const elapsed = Math.min(32, now - previous);
    previous = now;
    if (!panZoomByPixels(_velocityX * elapsed)) _velocityX = 0;
    _velocityX *= Math.pow(0.94, elapsed / 16.67);
    if (Math.abs(_velocityX) >= 0.01) _inertiaFrame = requestAnimationFrame(step);
    else _inertiaFrame = null;
  };
  _inertiaFrame = requestAnimationFrame(step);
}

timelineBody.addEventListener('pointerdown', e => {
  if (!e.isPrimary || (e.pointerType === 'mouse' && e.button !== 0)) return;
  if (!S.zoomRange) return;
  if (_inertiaFrame) { cancelAnimationFrame(_inertiaFrame); _inertiaFrame = null; }
  _didDrag = false; _dragPointerId = e.pointerId;
  _dragRow = e.target.closest('.timeline-row');
  _dragSegment = e.target.closest('.timeline-seg');
  _dragging = true; _dsX = e.clientX; _dsFrom = S.zoomRange[0]; _dsTo = S.zoomRange[1];
  _lastMoveX = e.clientX; _lastMoveAt = performance.now(); _velocityX = 0;
  _panSamples = [{ x: e.clientX, at: _lastMoveAt }];
  timelineBody.setPointerCapture?.(e.pointerId);
  document.body.style.cursor = 'grabbing';
});
document.addEventListener('pointermove', e => {
  if (!_dragging || e.pointerId !== _dragPointerId) return;
  if (Math.abs(e.clientX - _dsX) > 4) {
    _didDrag = true;
    e.preventDefault();
  }
  const now = performance.now();
  const elapsed = Math.max(1, now - _lastMoveAt);
  const instantVelocity = (e.clientX - _lastMoveX) / elapsed;
  _velocityX = _velocityX * 0.65 + instantVelocity * 0.35;
  _lastMoveX = e.clientX; _lastMoveAt = now;
  _panSamples.push({ x: e.clientX, at: now });
  _panSamples = _panSamples.filter(sample => sample.at >= now - 120);
  const dTime = -(e.clientX - _dsX) * ((_dsTo - _dsFrom) / S.rWidth);
  let nf = _dsFrom + dTime, nt = _dsTo + dTime;
  if (nf < S.timeline.from) { nt += S.timeline.from - nf; nf = S.timeline.from; }
  if (nt > S.timeline.to) { nf -= nt - S.timeline.to; nt = S.timeline.to; }
  if (nf < S.timeline.from) nf = S.timeline.from;
  S.zoomRange = [nf, nt]; queuePanRender();
}, { passive: false });
function seekFromTimelineTarget(row, segment, clientX) {
  if (!row || !S.zoomRange) return;
  if (segment) {
    const rect = segment.getBoundingClientRect();
    const start = Number(segment.dataset.start);
    const end = Number(segment.dataset.end) || start;
    const fraction = Math.max(0, Math.min(1, (clientX - rect.left) / Math.max(1, rect.width)));
    seekTo(start + (end - start) * fraction);
    return;
  }
  const rect = row.getBoundingClientRect();
  const labelWidth = timelineLabelWidth();
  const x = clientX - rect.left - labelWidth;
  const segAreaW = rect.width - labelWidth;
  if (segAreaW > 0 && x >= 0 && x <= segAreaW) {
    seekTo(S.zoomRange[0] + (x / segAreaW) * (S.zoomRange[1] - S.zoomRange[0]));
  }
}

function stopTimelineDrag(e, cancelled = false) {
  if (!_dragging || (e.pointerId != null && e.pointerId !== _dragPointerId)) return;
  const wasDrag = _didDrag;
  const row = _dragRow;
  const segment = _dragSegment;
  if (wasDrag && _panSamples.length >= 2) {
    const first = _panSamples[0], last = _panSamples[_panSamples.length - 1];
    const sampleVelocity = (last.x - first.x) / Math.max(1, last.at - first.at);
    if (Math.abs(sampleVelocity) > Math.abs(_velocityX) * 0.6) _velocityX = sampleVelocity;
  }
  _dragging = false; _dragPointerId = null; _dragRow = null; _dragSegment = null;
  _panSamples = [];
  if (e.pointerId != null && timelineBody.hasPointerCapture?.(e.pointerId)) {
    timelineBody.releasePointerCapture(e.pointerId);
  }
  document.body.style.cursor = '';
  if (!cancelled && !wasDrag && row) {
    _suppressClickUntil = performance.now() + 500;
    seekFromTimelineTarget(row, segment, e.clientX);
  } else {
    updateCursor();
    if (!cancelled && wasDrag) startPanInertia();
  }
}
document.addEventListener('pointerup', stopTimelineDrag);
document.addEventListener('pointercancel', e => stopTimelineDrag(e, true));

// ── Wheel pan (solo nel tab timeline) ──
document.getElementById('timeline-scroll').addEventListener('wheel', e => {
  if (S.activeTab !== 'timeline') return;
  if (!S.zoomRange || !S.timeline) return;
  const isHorizontal = Math.abs(e.deltaX) > Math.abs(e.deltaY);
  if (!isHorizontal && !e.shiftKey) return;
  e.preventDefault();
  const delta = (isHorizontal ? e.deltaX : e.deltaY) || 0;
  const range = S.zoomRange[1] - S.zoomRange[0];
  const timePerPx = range / S.rWidth;
  const dTime = delta * timePerPx * 0.8;
  let nf = S.zoomRange[0] + dTime, nt = S.zoomRange[1] + dTime;
  if (nf < S.timeline.from) { nt += S.timeline.from - nf; nf = S.timeline.from; }
  if (nt > S.timeline.to) { nf -= nt - S.timeline.to; nt = S.timeline.to; }
  if (nf < S.timeline.from) nf = S.timeline.from;
  S.zoomRange = [nf, nt]; renderTimeline();
}, { passive: false });

// ── Click seek ──
document.getElementById('timeline-body').addEventListener('click', function(e) {
  if (_dragging || _didDrag || performance.now() < _suppressClickUntil) { _didDrag = false; return; }
  const row = e.target.closest('.timeline-row');
  seekFromTimelineTarget(row, e.target.closest('.timeline-seg'), e.clientX);
});

function seekTo(ts) {
  S.currentTime = ts;
  stopPlayback();
  if (S.zoomRange && S.timeline) {
    const [vFrom, vTo] = S.zoomRange;
    if (ts < vFrom || ts > vTo) {
      const range = vTo - vFrom;
      S.zoomRange = [ts - range * 0.3, ts + range * 0.7];
      if (S.zoomRange[0] < S.timeline.from) S.zoomRange[0] = S.timeline.from;
      if (S.zoomRange[1] > S.timeline.to) S.zoomRange[1] = S.timeline.to;
      renderTimeline();
    }
  }
  syncAutoHotspotAtCurrentTime(); updateCursor(); updateTimeDisplay(); seekPlayersToTime();
}

// ── Jump confini (solo inizio registrazioni, non fine) ──
function jumpToBoundary(direction) {
  if (S.currentTime == null || !S.timeline) return;
  stopPlayback();
  // Raccogli solo gli start_ts di tutte le registrazioni
  let starts = [];
  S.timeline.cameras.forEach(cam => cam.segments.forEach(s => starts.push(s.start_ts)));
  starts = [...new Set(starts)].sort((a,b) => a-b);
  const margin = 0.5;
  if (direction === -1) {
    for (let i = starts.length-1; i >= 0; i--) { if (starts[i] < S.currentTime - margin) { S.currentTime = starts[i]; break; } }
  } else {
    for (let i=0; i < starts.length; i++) { if (starts[i] > S.currentTime + margin) { S.currentTime = starts[i]; break; } }
  }
  if (S.zoomRange && S.timeline) {
    const [vFrom, vTo] = S.zoomRange;
    if (S.currentTime < vFrom || S.currentTime > vTo) {
      const range = vTo - vFrom;
      S.zoomRange = [S.currentTime - range * 0.3, S.currentTime + range * 0.7];
      if (S.zoomRange[0] < S.timeline.from) S.zoomRange[0] = S.timeline.from;
      if (S.zoomRange[1] > S.timeline.to) S.zoomRange[1] = S.timeline.to;
      renderTimeline();
    }
  }
  syncAutoHotspotAtCurrentTime(); updateCursor(); updateTimeDisplay(); renderPlayers();
}
