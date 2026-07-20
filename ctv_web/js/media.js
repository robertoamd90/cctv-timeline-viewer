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

  function playbackCompleted({ currentTime, duration, metadataReady, hasPlayed }) {
    if (!metadataReady || !hasPlayed || !Number.isFinite(duration) || duration <= 0) {
      return false;
    }
    return currentTime >= duration - 0.15;
  }

  return { safeSeekTarget, playbackCompleted };
});
