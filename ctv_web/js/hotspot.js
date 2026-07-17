/* Pure ordering and event-selection helpers for Auto Hotspot. */

function hotspotPromotedOrder(order, cameraId, validIds) {
  const valid = new Set(validIds);
  const normalized = [
    ...order.filter(id => valid.has(id)),
    ...validIds.filter(id => !order.includes(id)),
  ];
  if (!valid.has(cameraId)) return normalized;
  return [cameraId, ...normalized.filter(id => id !== cameraId)];
}

function hotspotStartCandidate(cameras, visibleIds, fromExclusive, toInclusive) {
  if (fromExclusive == null || toInclusive == null || toInclusive < fromExclusive) return null;
  const visibleOrder = new Map(visibleIds.map((id, index) => [id, index]));
  const candidates = [];
  cameras.forEach(camera => {
    if (!visibleOrder.has(camera.camera_id)) return;
    camera.segments.forEach(segment => {
      if (segment.start_ts > fromExclusive && segment.start_ts <= toInclusive) {
        candidates.push({ cameraId: camera.camera_id, start: segment.start_ts });
      }
    });
  });
  if (!candidates.length) return null;
  const latest = Math.max(...candidates.map(candidate => candidate.start));
  return candidates
    .filter(candidate => candidate.start === latest)
    .sort((left, right) => visibleOrder.get(left.cameraId) - visibleOrder.get(right.cameraId))[0]
    .cameraId;
}

function hotspotCurrentCandidate(cameras, visibleIds, time) {
  if (time == null) return null;
  const visibleOrder = new Map(visibleIds.map((id, index) => [id, index]));
  const candidates = [];
  cameras.forEach(camera => {
    if (!visibleOrder.has(camera.camera_id)) return;
    camera.segments.forEach(segment => {
      if (time >= segment.start_ts && (segment.end_ts == null || time < segment.end_ts)) {
        candidates.push({ cameraId: camera.camera_id, start: segment.start_ts });
      }
    });
  });
  if (!candidates.length) return null;
  const latest = Math.max(...candidates.map(candidate => candidate.start));
  return candidates
    .filter(candidate => candidate.start === latest)
    .sort((left, right) => visibleOrder.get(left.cameraId) - visibleOrder.get(right.cameraId))[0]
    .cameraId;
}

if (typeof module !== 'undefined') {
  module.exports = { hotspotPromotedOrder, hotspotStartCandidate, hotspotCurrentCandidate };
}
