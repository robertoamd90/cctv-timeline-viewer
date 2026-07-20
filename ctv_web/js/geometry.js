/* Viewport positioning helpers shared by pointer-driven overlays. */

function viewportPopoverPosition(point, size, viewport, margin = 8, gap = 14) {
  let left = point.x + gap;
  if (left + size.width > viewport.width - margin) left = point.x - gap - size.width;
  left = Math.max(margin, Math.min(left, viewport.width - size.width - margin));

  let top = point.y - size.height / 2;
  top = Math.max(margin, Math.min(top, viewport.height - size.height - margin));
  return { left: Math.round(left), top: Math.round(top) };
}

function recenterRange(time, visibleRange, limits, anchor = 0.3) {
  const total = Math.max(0, limits[1] - limits[0]);
  const width = Math.min(total, Math.max(0, visibleRange[1] - visibleRange[0]));
  const maximumStart = limits[1] - width;
  const start = Math.max(limits[0], Math.min(time - width * anchor, maximumStart));
  return [start, start + width];
}

if (typeof module !== 'undefined') module.exports = { viewportPopoverPosition, recenterRange };
