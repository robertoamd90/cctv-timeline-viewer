const assert = require('node:assert/strict');
const {
  hotspotPromotedOrder,
  hotspotStartCandidate,
  hotspotCurrentCandidate,
} = require('../ctv_web/js/hotspot.js');

const cameras = [
  { camera_id: 1, segments: [{ start_ts: 10, end_ts: 40 }] },
  { camera_id: 2, segments: [{ start_ts: 20, end_ts: 30 }, { start_ts: 50, end_ts: 60 }] },
  { camera_id: 3, segments: [{ start_ts: 20, end_ts: 45 }] },
];

assert.deepEqual(hotspotPromotedOrder([1, 2, 3], 3, [1, 2, 3]), [3, 1, 2]);
assert.deepEqual(hotspotPromotedOrder([3, 1, 2], 2, [1, 2]), [2, 1]);
assert.equal(hotspotStartCandidate(cameras, [1, 2, 3], 15, 21), 2);
assert.equal(hotspotStartCandidate(cameras, [1, 2, 3], 21, 49), null);
assert.equal(hotspotCurrentCandidate(cameras, [1, 2, 3], 25), 2);
assert.equal(hotspotCurrentCandidate(cameras, [1, 2, 3], 35), 3);
assert.equal(hotspotCurrentCandidate(cameras, [1, 2, 3], 46), null);

console.log('Auto Hotspot tests passed');
