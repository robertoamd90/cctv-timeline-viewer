const assert = require('node:assert/strict');
const { safeSeekTarget, playbackCompleted, hasProgressiveDuration } = require('../ctv_web/js/media.js');

assert.equal(safeSeekTarget(110, 100, NaN), 10);
assert.equal(safeSeekTarget(110, 100, 8), 7.95);
assert.equal(safeSeekTarget(90, 100, 8), 0);

assert.equal(playbackCompleted({
  ended: true, currentTime: 0, expectedDuration: 10, metadataReady: true, hasPlayed: false,
}), false, 'an early ended event must not skip an unplayed clip');
assert.equal(playbackCompleted({
  ended: true, currentTime: 4, expectedDuration: 10, metadataReady: true, hasPlayed: true,
}), false, 'an ended event before the media duration must be treated as interrupted loading');
assert.equal(playbackCompleted({
  ended: false, currentTime: 9.9, expectedDuration: 10, metadataReady: false, hasPlayed: true,
}), false, 'completion requires reliable metadata');
assert.equal(playbackCompleted({
  ended: true, currentTime: 10, expectedDuration: 10, metadataReady: true, hasPlayed: true,
}), true);
assert.equal(playbackCompleted({
  ended: false, currentTime: 9.9, expectedDuration: 10, metadataReady: true, hasPlayed: true,
}), false, 'a growing Firefox duration must not be interpreted as a completed clip');

assert.equal(hasProgressiveDuration(0.0625, 26.176), true);
assert.equal(hasProgressiveDuration(26.176, 26.176), false);
assert.equal(hasProgressiveDuration(NaN, 26.176), false);

console.log('Media state tests passed');
