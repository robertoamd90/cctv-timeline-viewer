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

  function medianTime(times) {
    const values = times.filter(Number.isFinite).sort((a, b) => a - b);
    if (!values.length) return null;
    const middle = Math.floor(values.length / 2);
    return values.length % 2 ? values[middle] : (values[middle - 1] + values[middle]) / 2;
  }

  return { safeSeekTarget, playbackCompleted, requiredPlaybackBuffer, medianTime };
});
