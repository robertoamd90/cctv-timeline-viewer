(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.CtvMedia = api;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  function safeSeekTarget(globalTime, recordingStart, duration) {
    const target = Math.max(0, globalTime - recordingStart);
    if (!Number.isFinite(duration) || duration <= 0) return target;
    return Math.min(target, Math.max(0, duration - 0.05));
  }

  function playbackCompleted({ ended, currentTime, expectedDuration, metadataReady, hasPlayed }) {
    if (!ended || !metadataReady || !hasPlayed) return false;
    if (!Number.isFinite(expectedDuration) || expectedDuration <= 0) return true;
    return currentTime >= expectedDuration - 0.5;
  }

  function requiredPlaybackBuffer(speed, currentTime, expectedDuration) {
    const desired = speed >= 8 ? 4 : speed >= 4 ? 2 : 0.75;
    if (!Number.isFinite(expectedDuration)) return desired;
    return Math.min(desired, Math.max(0, expectedDuration - currentTime - 0.5));
  }

  function timelinePlaybackSpeed(playbackRate, streamSpeed) {
    const mediaRate = Number.isFinite(playbackRate) && playbackRate > 0 ? playbackRate : 1;
    const encodedRate = Number.isFinite(streamSpeed) && streamSpeed > 0 ? streamSpeed : 1;
    return mediaRate * encodedRate;
  }

  function playbackPlan(profile, speed) {
    const selectedSpeed = Number.isFinite(speed) && speed > 0 ? speed : 1;
    const transcoded = profile === 'balanced' || profile === 'fast';
    return {
      transcoded,
      streamSpeed: transcoded ? Math.max(1, selectedSpeed) : 1,
      playbackRate: transcoded ? Math.min(1, selectedSpeed) : selectedSpeed,
    };
  }

  function mediaTimeForTimeline(
    globalTime, recordingStart, streamOffset, streamSpeed, expectedDuration,
  ) {
    const speed = Number.isFinite(streamSpeed) && streamSpeed > 0 ? streamSpeed : 1;
    const target = Math.max(0, (globalTime - recordingStart - streamOffset) / speed);
    if (!Number.isFinite(expectedDuration) || expectedDuration <= 0) return target;
    return Math.min(target, Math.max(0, expectedDuration - 0.05));
  }

  function timelineTimeForMedia(mediaTime, recordingStart, streamOffset, streamSpeed) {
    const speed = Number.isFinite(streamSpeed) && streamSpeed > 0 ? streamSpeed : 1;
    return recordingStart + streamOffset + mediaTime * speed;
  }

  function medianTime(times) {
    const values = times.filter(Number.isFinite).sort((a, b) => a - b);
    if (!values.length) return null;
    const middle = Math.floor(values.length / 2);
    return values.length % 2 ? values[middle] : (values[middle - 1] + values[middle]) / 2;
  }

  return {
    safeSeekTarget,
    playbackCompleted,
    requiredPlaybackBuffer,
    timelinePlaybackSpeed,
    playbackPlan,
    mediaTimeForTimeline,
    timelineTimeForMedia,
    medianTime,
  };
});
