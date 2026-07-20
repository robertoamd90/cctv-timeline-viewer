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

  function hasProgressiveDuration(reportedDuration, expectedDuration) {
    return Number.isFinite(reportedDuration) && reportedDuration > 0 &&
      Number.isFinite(expectedDuration) && expectedDuration > reportedDuration + 0.5;
  }

  return { safeSeekTarget, playbackCompleted, hasProgressiveDuration };
});
