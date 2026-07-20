/* ═══════════════════════════════════════════
   CTV — Player: all cameras always visible, global clock, transitions
   ═══════════════════════════════════════════ */

let _clockStartTime = null, _clockStartWall = null, _tickId = null;
let _playerCache = {};  // camId → {recId}
let _wasBuffering = false;

function seekVideo(video, recordingStart) {
  if (S.currentTime == null || video.readyState < HTMLMediaElement.HAVE_METADATA) return false;
  const expectedDuration = parseFloat(video.parentElement.dataset.duration);
  const target = CtvMedia.safeSeekTarget(S.currentTime, recordingStart, expectedDuration);
  if (Math.abs(video.currentTime - target) > 0.05) video.currentTime = target;
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
      <canvas class="player-freeze" hidden></canvas>
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
    v.dataset.hasPlayed = '0';
    v.dataset.metadataReady = '0';
    v.dataset.driftSeek = '0';
    v.dataset.warming = '0';
    clearFreezeFrame(v);
    empty.hidden = true;
    v.hidden = false;
    setPlayerStatus(cell, t('player.loading'));
    v.pause();
    v.playbackRate = S.speed;
    v.loop = false;
    v.onended = () => {
      if (v.dataset.metadataReady !== '1' || v.dataset.hasPlayed !== '1') return;
      if (videoReachedEnd(v)) {
        onVideoEnded(v, recId);
        return;
      }
      enterBufferingBarrier(v, t('player.buffering'));
      v.play().catch(() => {});
    };
    v.onloadedmetadata = () => {
      v.dataset.metadataReady = '1';
      seekVideo(v, rec.start_ts);
    };
    v.onloadeddata = () => clearStatusWhenReady(v);
    v.oncanplay = () => clearStatusWhenReady(v);
    v.onseeked = () => {
      v.dataset.driftSeek = '0';
      clearStatusWhenReady(v);
    };
    v.onplaying = () => {
      v.dataset.hasPlayed = '1';
      if (_wasBuffering) {
        if (v.dataset.warming !== '1') v.pause();
        return;
      }
      setPlayerStatus(cell, '');
    };
    v.onwaiting = () => {
      if (v.dataset.driftSeek !== '1') {
        enterBufferingBarrier(v, t('player.buffering'));
        return;
      }
      const waitingRecording = v.dataset.recording;
      setTimeout(() => {
        if (S.playing && v.dataset.recording === waitingRecording &&
            v.dataset.driftSeek === '1' &&
            v.readyState < HTMLMediaElement.HAVE_FUTURE_DATA) {
          enterBufferingBarrier(v, t('player.buffering'));
        }
      }, 250);
    };
    v.onstalled = () => enterBufferingBarrier(v, t('player.slowSource'));
    v.onerror = () => {
      clearFreezeFrame(v);
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
    v.dataset.hasPlayed = '0';
    v.dataset.metadataReady = '0';
    v.dataset.driftSeek = '0';
    v.dataset.warming = '0';
    clearFreezeFrame(v);
    v.pause();
    v.onended = v.onloadedmetadata = v.onloadeddata = v.oncanplay = v.onseeked = null;
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

function selectedFrameReady(video) {
  return !video.seeking && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA;
}

function clearStatusWhenReady(video) {
  if ((!S.playing && selectedFrameReady(video)) || (S.playing && videoHasPlaybackBuffer(video))) {
    setPlayerStatus(video.parentElement, '');
  }
}

function clearFreezeFrame(video) {
  const canvas = video.parentElement?.querySelector('.player-freeze');
  if (!canvas) return;
  canvas.dataset.token = String((Number(canvas.dataset.token) || 0) + 1);
  canvas.hidden = true;
}

function showFreezeFrame(video) {
  if (!selectedFrameReady(video) || !video.videoWidth || !video.videoHeight) return;
  const cell = video.parentElement;
  const canvas = cell.querySelector('.player-freeze');
  if (!canvas) return;
  const scale = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(cell.clientWidth * scale));
  const height = Math.max(1, Math.round(cell.clientHeight * scale));
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) return;
  context.fillStyle = '#0a0a0f';
  context.fillRect(0, 0, width, height);
  const fill = document.getElementById('player-area').classList.contains('fill');
  const ratio = fill
    ? Math.max(width / video.videoWidth, height / video.videoHeight)
    : Math.min(width / video.videoWidth, height / video.videoHeight);
  const drawWidth = video.videoWidth * ratio;
  const drawHeight = video.videoHeight * ratio;
  try {
    context.drawImage(video, (width - drawWidth) / 2, (height - drawHeight) / 2, drawWidth, drawHeight);
    canvas.dataset.token = String((Number(canvas.dataset.token) || 0) + 1);
    canvas.hidden = false;
  } catch (_) {
    canvas.hidden = true;
  }
}

function revealFreezeOnNextFrame(video) {
  const canvas = video.parentElement?.querySelector('.player-freeze');
  if (!canvas || canvas.hidden) return;
  const token = canvas.dataset.token;
  const reveal = () => {
    if (canvas.dataset.token === token && video.dataset.warming !== '1') canvas.hidden = true;
  };
  if (typeof video.requestVideoFrameCallback === 'function') video.requestVideoFrameCallback(reveal);
  else setTimeout(reveal, 80);
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

function bufferedAheadAt(video, current) {
  for (let i = 0; i < video.buffered.length; i++) {
    if (video.buffered.start(i) <= current + 0.05 && video.buffered.end(i) >= current) {
      return Math.max(0, video.buffered.end(i) - current);
    }
  }
  return 0;
}

function requiredBuffer(video, currentTime = video.currentTime) {
  const expectedDuration = parseFloat(video.parentElement.dataset.duration);
  return CtvMedia.requiredPlaybackBuffer(S.speed, currentTime, expectedDuration);
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
  // Let the decoder consume the tail so the native `ended` event can fire.
  if (videoReachedEnd(video)) return true;
  const expectedDuration = parseFloat(video.parentElement.dataset.duration);
  const start = parseFloat(video.parentElement.dataset.start);
  const warmingTarget = video.dataset.warming === '1' && S.currentTime != null && Number.isFinite(start)
    ? CtvMedia.safeSeekTarget(S.currentTime, start, expectedDuration)
    : null;
  const bufferPosition = warmingTarget ?? video.currentTime;
  if (Number.isFinite(expectedDuration) && bufferPosition >= expectedDuration - 0.5) {
    return !video.seeking && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA;
  }
  if (warmingTarget != null) {
    return bufferedAheadAt(video, bufferPosition) >= requiredBuffer(video, bufferPosition);
  }
  return !video.seeking && video.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA &&
    bufferedAheadAt(video, video.currentTime) >= requiredBuffer(video);
}

function absoluteVideoTime(video) {
  const start = parseFloat(video.parentElement.dataset.start);
  return Number.isFinite(start) ? start + video.currentTime : null;
}

function enterBufferingBarrier(source, message) {
  if (source) {
    source.dataset.driftSeek = '0';
    setPlayerStatus(source.parentElement, message || t('player.buffering'));
  }
  if (!S.playing) return;
  const videos = activeVideos();
  // S.currentTime is authoritative. A newly loaded video's currentTime is often
  // still zero here and must never be allowed to rewind the global clock.
  videos.forEach(video => {
    if (!videoHasPlaybackBuffer(video)) {
      video.dataset.warming = '1';
      showFreezeFrame(video);
      video.playbackRate = S.speed;
      video.play().catch(() => {});
    } else {
      video.dataset.warming = '0';
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
    if (Math.abs(video.currentTime - target) > 0.1) {
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
  getVideos().forEach(v => {
    v.dataset.warming = '0';
    clearFreezeFrame(v);
    v.pause();
  });
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
  enterBufferingBarrier(null, null);
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
    video.parentElement.dataset.buffering === '1' ||
    (video.dataset.driftSeek !== '1' && !videoHasPlaybackBuffer(video))
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
      video.dataset.warming = '0';
      setPlayerStatus(video.parentElement, '');
      video.playbackRate = S.speed;
      revealFreezeOnNextFrame(video);
      video.play().catch(() => enterBufferingBarrier(video, t('player.buffering')));
    });
    _clockStartTime = S.currentTime;
    _clockStartWall = performance.now();
  }

  const previousTime = S.currentTime;
  const videoTimes = videos.map(absoluteVideoTime).filter(Number.isFinite);
  if (videoTimes.length) {
    const synchronizedTime = CtvMedia.medianTime(videoTimes);
    const maxSpread = S.speed >= 8 ? 0.5 : 0.25;
    const spread = Math.max(...videoTimes) - Math.min(...videoTimes);
    if (spread > maxSpread) {
      const outlier = videos.reduce((worst, video) => {
        const deviation = Math.abs(absoluteVideoTime(video) - synchronizedTime);
        return !worst || deviation > worst.deviation ? { video, deviation } : worst;
      }, null).video;
      enterBufferingBarrier(outlier, t('player.buffering'));
      _tickId = requestAnimationFrame(clockTick);
      return;
    }
    S.currentTime = synchronizedTime;
    _clockStartTime = S.currentTime;
    _clockStartWall = performance.now();
  } else {
    const elapsed = (performance.now() - _clockStartWall) / 1000 * S.speed;
    S.currentTime = _clockStartTime + elapsed;
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
    ensureTimelineTimeVisible(S.currentTime, 0.2);
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
