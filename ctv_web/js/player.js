/* ═══════════════════════════════════════════
   CTV — Player: all cameras always visible, global clock, transitions
   ═══════════════════════════════════════════ */

let _clockStartTime = null, _clockStartWall = null, _tickId = null;
let _playerCache = {};  // camId → {recId}
let _wasBuffering = false;
let _lastDriftCheck = 0;

function seekVideo(video, recordingStart) {
  if (S.currentTime == null || video.readyState < HTMLMediaElement.HAVE_METADATA) return false;
  const expectedDuration = parseFloat(video.parentElement.dataset.duration);
  const target = CtvMedia.safeSeekTarget(S.currentTime, recordingStart, expectedDuration);
  if (Math.abs(video.currentTime - target) > 0.5) video.currentTime = target;
  return true;
}

// ── Render tutti i player ──
function renderPlayers() {
  const area = document.getElementById('player-area');
  const displayed = displayedCameras();
  const camIds = displayed.map(c => c.id);

  // Rimuovi celle per camere rimosse
  area.querySelectorAll('.player-cell').forEach(cell => {
    const cid = parseInt(cell.dataset.cam);
    if (!camIds.includes(cid)) { delete _playerCache[cid]; cell.remove(); }
  });

  // Crea/aggiorna celle per ogni camera
  camIds.forEach((cid, idx) => {
    let cell = area.querySelector(`.player-cell[data-cam="${cid}"]`);
    const cam = displayed.find(c => c.id === cid);
    const rec = findRecordingAt(cid, S.currentTime);

    if (!cell) {
      cell = document.createElement('div');
      cell.className = 'player-cell';
      cell.dataset.cam = String(cid);
      cell.ondblclick = () => {
        if (!isCompactViewport()) toggleCameraFocus(cid);
      };
      cell.onclick = () => {
        if (isCompactViewport() && S.layoutMode !== 'hotspot') toggleCameraFocus(cid);
        else promoteHotspotCamera(cid);
      };
      const existing = area.querySelectorAll('.player-cell');
      if (idx < existing.length) area.insertBefore(cell, existing[idx]);
      else area.appendChild(cell);
      _playerCache[cid] = null;
    }
    // Mantiene l'ordine DOM allineato alla vista; in hotspot il primo elemento e quello principale.
    area.appendChild(cell);

    const cached = _playerCache[cid];
    const needUpdate = !cached || cached.recId !== (rec ? String(rec.id) : '');
    if (needUpdate) {
      updatePlayerCell(cell, cam, rec, cid);
      _playerCache[cid] = { recId: rec ? String(rec.id) : '' };
    }

    const video = cell.querySelector('video');
    if (video && rec && S.currentTime != null) {
      seekVideo(video, rec.start_ts);
    }
  });
  applyHotspotCellPositions();
}

function updatePlayerCell(cell, cam, rec, cid) {
  const name = cam ? cam.name : '?';
  let v = cell.querySelector('video');
  if (!v) {
    cell.innerHTML = `<div class="label-overlay"></div>
      <div class="hotspot-action">${esc(t('player.bringToFront'))}</div>
      <div class="player-status" hidden></div>
      <div class="empty-state" hidden></div>
      <video muted playsinline webkit-playsinline disablepictureinpicture
        controlslist="nofullscreen nodownload noremoteplayback" preload="auto" hidden></video>`;
    v = cell.querySelector('video');
    v.playsInline = true;
  }
  cell.querySelector('.label-overlay').textContent = name;
  cell.querySelector('.hotspot-action').textContent = t('player.bringToFront');
  const empty = cell.querySelector('.empty-state');

  if (rec) {
    const recId = String(rec.id);
    cell.dataset.recording = recId;
    v.dataset.recording = recId;
    cell.dataset.start = String(rec.start_ts);
    cell.dataset.duration = String(rec.duration ?? Math.max(0, (rec.end_ts ?? rec.start_ts) - rec.start_ts));
    cell.dataset.transitioning = '';
    cell.dataset.buffering = '1';
    cell.dataset.failed = '0';
    cell.dataset.endRetry = '';
    v.dataset.hasPlayed = '0';
    v.dataset.metadataReady = '0';
    v.dataset.barrierLoader = '0';
    empty.hidden = true;
    v.hidden = false;
    setPlayerStatus(cell, t('player.loading'));
    v.pause();
    v.playbackRate = S.speed;
    v.loop = false;
    v.onended = () => {
      if (videoReachedEnd(v)) {
        onVideoEnded(v, recId);
        return;
      }
      enterBufferingBarrier(v, t('player.buffering'));
      if (cell.dataset.endRetry !== recId) {
        cell.dataset.endRetry = recId;
        v.dataset.hasPlayed = '0';
        v.dataset.metadataReady = '0';
        v.load();
      }
    };
    v.onloadedmetadata = () => {
      v.dataset.metadataReady = '1';
      seekVideo(v, rec.start_ts);
    };
    v.oncanplay = () => {
      if (videoHasPlaybackBuffer(v)) setPlayerStatus(cell, '');
    };
    v.onseeked = () => {
      if (videoHasPlaybackBuffer(v)) setPlayerStatus(cell, '');
    };
    v.onplaying = () => {
      v.dataset.hasPlayed = '1';
      if (_wasBuffering && v.dataset.barrierLoader !== '1') v.pause();
      else setPlayerStatus(cell, '');
    };
    v.onwaiting = () => enterBufferingBarrier(v, t('player.buffering'));
    v.onstalled = () => enterBufferingBarrier(v, t('player.slowSource'));
    v.onerror = () => {
      cell.dataset.failed = '1'; cell.dataset.buffering = '0';
      setPlayerStatus(cell, t('player.unplayable'), true);
    };
    v.src = appUrl(`/video/${rec.id}`);
    v.load();
  } else {
    cell.dataset.recording = '';
    v.dataset.recording = '';
    cell.dataset.start = '';
    cell.dataset.duration = '';
    cell.dataset.transitioning = '';
    cell.dataset.buffering = '0';
    cell.dataset.failed = '0';
    cell.dataset.endRetry = '';
    v.dataset.hasPlayed = '0';
    v.dataset.metadataReady = '0';
    v.dataset.barrierLoader = '0';
    v.pause();
    v.onended = v.onloadedmetadata = v.oncanplay = v.onseeked = null;
    v.onplaying = v.onwaiting = v.onstalled = v.onerror = null;
    v.removeAttribute('src');
    v.load();
    v.hidden = true;
    setPlayerStatus(cell, '');
    empty.textContent = t('player.noneAtTime');
    empty.hidden = false;
  }
}

function setPlayerStatus(cell, message, error = false) {
  const status = cell.querySelector('.player-status');
  if (!status) return;
  status.textContent = message;
  status.classList.toggle('error', error);
  status.hidden = !message;
  if (!error) cell.dataset.buffering = message ? '1' : '0';
}

function findRecordingAt(cameraId, ts) {
  if (!S.timeline || ts == null) return null;
  const cam = S.timeline.cameras.find(c => c.camera_id === cameraId);
  if (!cam) return null;
  return cam.segments.find(s => ts >= s.start_ts && (s.end_ts == null || ts < s.end_ts)) || null;
}

function syncAutoHotspotAtCurrentTime() {
  if (!S.autoHotspot || S.layoutMode !== 'hotspot' || !S.timeline || S.currentTime == null) return;
  const visibleIds = visibleCameras().map(camera => camera.id);
  const candidate = hotspotCurrentCandidate(S.timeline.cameras, visibleIds, S.currentTime);
  if (candidate != null && candidate !== S.hotspotOrder[0]) {
    promoteHotspotCamera(candidate, false);
  }
}

function updateAutoHotspot(previousTime, currentTime) {
  if (!S.autoHotspot || S.layoutMode !== 'hotspot' || !S.timeline || currentTime == null) return;
  const visibleIds = visibleCameras().map(camera => camera.id);
  const started = hotspotStartCandidate(S.timeline.cameras, visibleIds, previousTime, currentTime);
  if (started != null) {
    if (started !== S.hotspotOrder[0]) promoteHotspotCamera(started, false);
    return;
  }

  const primary = S.hotspotOrder[0];
  if (primary != null && findRecordingAt(primary, currentTime)) return;
  const fallback = hotspotCameras().find(camera => findRecordingAt(camera.id, currentTime));
  if (fallback && fallback.id !== primary) promoteHotspotCamera(fallback.id, false);
}

// ── Seek ──
function seekPlayersToTime() {
  let needsRender = false;
  displayedCameras().forEach(c => {
    const rec = findRecordingAt(c.id, S.currentTime);
    const cached = _playerCache[c.id];
    const newRecId = rec ? String(rec.id) : '';
    if (!cached || cached.recId !== newRecId) { needsRender = true; }
  });
  if (needsRender) {
    renderPlayers();
  } else {
    document.querySelectorAll('#player-area video').forEach(v => {
      const recStart = parseFloat(v.parentElement.dataset.start);
      if (S.currentTime != null && !isNaN(recStart)) {
        seekVideo(v, recStart);
      }
    });
  }
}

function seekCurrentTime() {
  if (S.currentTime != null) { renderPlayers(); updateCursor(); updateTimeDisplay(); }
}

// ── Video ended → move the single global clock past the segment boundary ──
function onVideoEnded(videoEl, expectedRecId = videoEl.dataset.recording) {
  const cell = videoEl.parentElement;
  const camId = parseInt(cell.dataset.cam);
  const curRecId = cell.dataset.recording;
  if (!camId || !S.timeline) return;
  if (!curRecId || curRecId !== String(expectedRecId)) return;
  if (videoEl.dataset.recording !== curRecId || cell.dataset.transitioning === curRecId) return;
  const cam = S.timeline.cameras.find(c => c.camera_id === camId);
  if (!cam) return;
  const ended = cam.segments.find(s => String(s.id) === curRecId);
  if (!ended) return;
  cell.dataset.transitioning = curRecId;
  videoEl.onended = videoEl.onwaiting = videoEl.onstalled = null;
  const boundary = ended.end_ts ?? (ended.start_ts + (ended.duration || 0));
  const previousTime = S.currentTime;
  S.currentTime = Math.max(S.currentTime || 0, boundary + 0.001);
  _clockStartTime = S.currentTime;
  _clockStartWall = performance.now();
  updateTimeDisplay(); updateCursor();
  updateAutoHotspot(previousTime, S.currentTime);
  reconcilePlaybackPosition();
}

// ── Playback ──
function getVideos() { return Array.from(document.querySelectorAll('#player-area video')); }

function activeVideos() {
  return getVideos().filter(video =>
    !video.hidden && Boolean(video.parentElement.dataset.recording) &&
    video.parentElement.dataset.failed !== '1'
  );
}

function bufferedAhead(video) {
  const current = video.currentTime;
  for (let i = 0; i < video.buffered.length; i++) {
    if (video.buffered.start(i) <= current + 0.05 && video.buffered.end(i) >= current) {
      return Math.max(0, video.buffered.end(i) - current);
    }
  }
  return 0;
}

function requiredBuffer(video) {
  const desired = S.speed >= 8 ? 4 : S.speed >= 4 ? 2 : 0.75;
  const expectedDuration = parseFloat(video.parentElement.dataset.duration);
  if (!Number.isFinite(expectedDuration)) return desired;
  return Math.min(desired, Math.max(0.1, expectedDuration - video.currentTime - 0.05));
}

function videoHasProgressiveDuration(video) {
  const expectedDuration = parseFloat(video.parentElement.dataset.duration);
  return CtvMedia.hasProgressiveDuration(video.duration, expectedDuration);
}

function videoReachedEnd(video) {
  const expectedDuration = parseFloat(video.parentElement.dataset.duration);
  return CtvMedia.playbackCompleted({
    ended: video.ended,
    currentTime: video.currentTime,
    expectedDuration,
    metadataReady: video.dataset.metadataReady === '1',
    hasPlayed: video.dataset.hasPlayed === '1',
  });
}

function videoHasPlaybackBuffer(video) {
  // Never stop at the last frames: doing so can prevent `ended` from firing.
  if (videoReachedEnd(video)) return true;
  if (videoHasProgressiveDuration(video)) {
    return !video.seeking && video.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA;
  }
  return !video.seeking &&
    video.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA &&
    bufferedAhead(video) >= requiredBuffer(video);
}

function absoluteVideoTime(video) {
  const start = parseFloat(video.parentElement.dataset.start);
  return Number.isFinite(start) ? start + video.currentTime : null;
}

function enterBufferingBarrier(source, message) {
  if (source) setPlayerStatus(source.parentElement, message || t('player.buffering'));
  if (!S.playing) return;
  const videos = activeVideos();
  // S.currentTime is authoritative. A newly loaded video's currentTime is often
  // still zero here and must never be allowed to rewind the global clock.
  videos.forEach(video => {
    const keepLoading = video === source || !videoHasPlaybackBuffer(video);
    video.dataset.barrierLoader = keepLoading ? '1' : '0';
    if (keepLoading) {
      video.playbackRate = S.speed;
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  });
  _wasBuffering = true;
  _clockStartTime = S.currentTime;
  _clockStartWall = performance.now();
}

function alignVideos(videos) {
  let aligned = true;
  videos.forEach(video => {
    const start = parseFloat(video.parentElement.dataset.start);
    if (!Number.isFinite(start) || S.currentTime == null) return;
    if (video.readyState < HTMLMediaElement.HAVE_METADATA) {
      aligned = false;
      return;
    }
    const expectedDuration = parseFloat(video.parentElement.dataset.duration);
    const target = CtvMedia.safeSeekTarget(S.currentTime, start, expectedDuration);
    if (Math.abs(video.currentTime - target) > 0.35) {
      video.currentTime = target;
      setPlayerStatus(video.parentElement, t('player.buffering'));
      aligned = false;
    }
  });
  return aligned;
}

function stopPlayback() {
  if (_tickId) { cancelAnimationFrame(_tickId); _tickId = null; }
  S.playing = false;
  _wasBuffering = false;
  getVideos().forEach(v => { v.dataset.barrierLoader = '0'; v.pause(); });
  updatePlayButton();
}

document.getElementById('btn-play').onclick = () => {
  if (S.playing) { stopPlayback(); return; }
  if (S.currentTime == null && S.timeline) {
    const firstSeg = S.timeline.cameras[0]?.segments[0];
    if (firstSeg) S.currentTime = firstSeg.start_ts;
    syncAutoHotspotAtCurrentTime(); renderPlayers(); updateCursor(); updateTimeDisplay();
  }
  if (S.currentTime == null) {
    toast(t('player.noneForDay'), 'error');
    return;
  }
  S.playing = true; updatePlayButton();
  activeVideos().forEach(v => { v.playbackRate = S.speed; v.play().catch(()=>{}); });
  startClock();
};

document.getElementById('speed-select').onchange = function() {
  S.speed = parseFloat(this.value);
  getVideos().forEach(v => { v.playbackRate = S.speed; });
};

function updatePlayButton() {
  const button = document.getElementById('btn-play');
  button.textContent = S.playing ? '⏸' : '▶';
  button.setAttribute('aria-label', S.playing ? t('controls.pause') : t('controls.play'));
}
function updateTimeDisplay() {
  document.getElementById('time-display').textContent = S.currentTime ? fmtTime(S.currentTime) : '--';
}

// ── Global clock ──
function startClock() {
  if (_tickId) cancelAnimationFrame(_tickId);
  _clockStartTime = S.currentTime;
  _clockStartWall = performance.now();
  clockTick();
}

function clockTick() {
  if (!S.playing || S.activeTab !== 'timeline') { _tickId = null; return; }
  const videos = activeVideos();
  const completed = videos.find(videoReachedEnd);
  if (completed) {
    onVideoEnded(completed, completed.dataset.recording);
    _tickId = requestAnimationFrame(clockTick);
    return;
  }
  videos.forEach(video => {
    if (video.parentElement.dataset.buffering === '1' && videoHasPlaybackBuffer(video)) {
      setPlayerStatus(video.parentElement, '');
    }
  });
  const buffering = videos.some(video =>
    video.parentElement.dataset.buffering === '1' || !videoHasPlaybackBuffer(video)
  );
  if (buffering) {
    if (!_wasBuffering) enterBufferingBarrier(null, null);
    _clockStartTime = S.currentTime;
    _clockStartWall = performance.now();
    _tickId = requestAnimationFrame(clockTick);
    return;
  }
  if (_wasBuffering) {
    if (!alignVideos(videos) || videos.some(video => !videoHasPlaybackBuffer(video))) {
      _tickId = requestAnimationFrame(clockTick);
      return;
    }
    _wasBuffering = false;
    videos.forEach(video => {
      video.dataset.barrierLoader = '0';
      setPlayerStatus(video.parentElement, '');
      video.playbackRate = S.speed;
      video.play().catch(() => enterBufferingBarrier(video, t('player.buffering')));
    });
    _clockStartTime = S.currentTime;
    _clockStartWall = performance.now();
  }

  const previousTime = S.currentTime;
  if (S.speed > 4 && videos.length) {
    const master = videos[0];
    const recordingStart = parseFloat(master.parentElement.dataset.start);
    S.currentTime = recordingStart + master.currentTime;
    _clockStartTime = S.currentTime;
    _clockStartWall = performance.now();
  } else {
    const elapsed = (performance.now() - _clockStartWall) / 1000 * S.speed;
    S.currentTime = _clockStartTime + elapsed;
  }

  if (videos.length > 1 && performance.now() - _lastDriftCheck > 500) {
    _lastDriftCheck = performance.now();
    const maxDrift = S.speed >= 8 ? 0.75 : 0.35;
    const outOfSync = videos.some(video => {
      const time = absoluteVideoTime(video);
      return time != null && Math.abs(time - S.currentTime) > maxDrift;
    });
    if (outOfSync) {
      enterBufferingBarrier(null, null);
      _tickId = requestAnimationFrame(clockTick);
      return;
    }
  }
  updateTimeDisplay();
  updateCursor();
  updateAutoHotspot(previousTime, S.currentTime);

  // Auto-scroll
  if (S.zoomRange && S.timeline) {
    const [vFrom, vTo] = S.zoomRange;
    const range = vTo - vFrom;
    if (S.currentTime > vTo - range * 0.15 && vTo < S.timeline.to) {
      const shift = range * 0.35;
      let nf = vFrom + shift, nt = vTo + shift;
      if (nt > S.timeline.to) { nt = S.timeline.to; nf = nt - range; }
      if (nf < S.timeline.from) nf = S.timeline.from;
      if (nt > nf) { S.zoomRange = [nf, nt]; renderTimeline(); }
    }
  }

  reconcilePlaybackPosition();
  _tickId = requestAnimationFrame(clockTick);
}

function reconcilePlaybackPosition() {
  if (!S.timeline || S.currentTime == null) return;
  const displayed = displayedCameras();
  if (!displayed.length) { stopPlayback(); return; }

  let anyHasRecording = displayed.some(c => findRecordingAt(c.id, S.currentTime));
  if (!anyHasRecording) {
    const displayedIds = new Set(displayed.map(c => c.id));
    let nextStart = Infinity;
    S.timeline.cameras.forEach(cam => {
      if (!displayedIds.has(cam.camera_id)) return;
      cam.segments.forEach(segment => {
        if (segment.start_ts > S.currentTime && segment.start_ts < nextStart) {
          nextStart = segment.start_ts;
        }
      });
    });
    if (nextStart === Infinity) { stopPlayback(); return; }
    const previousTime = S.currentTime;
    S.currentTime = nextStart + 0.001;
    _clockStartTime = S.currentTime;
    _clockStartWall = performance.now();
    updateTimeDisplay(); updateCursor();
    updateAutoHotspot(previousTime, S.currentTime);
  }

  const needsRender = displayed.some(c => {
    const rec = findRecordingAt(c.id, S.currentTime);
    const cachedId = _playerCache[c.id]?.recId ?? null;
    return cachedId !== (rec ? String(rec.id) : '');
  });
  if (needsRender) {
    renderPlayers();
    if (S.playing) enterBufferingBarrier(null, null);
  }
}
