const assert = require('node:assert/strict');
const { viewportPopoverPosition, recenterRange } = require('../ctv_web/js/geometry.js');

const viewport = { width: 1000, height: 700 };
const size = { width: 280, height: 220 };

assert.deepEqual(viewportPopoverPosition({ x: 400, y: 350 }, size, viewport), { left: 414, top: 240 });
assert.deepEqual(viewportPopoverPosition({ x: 990, y: 690 }, size, viewport), { left: 696, top: 472 });
assert.deepEqual(viewportPopoverPosition({ x: 2, y: 2 }, size, viewport), { left: 16, top: 8 });

assert.deepEqual(recenterRange(800, [100, 200], [0, 1000]), [770, 870]);
assert.deepEqual(recenterRange(10, [100, 200], [0, 1000]), [0, 100]);
assert.deepEqual(recenterRange(990, [100, 200], [0, 1000]), [900, 1000]);
assert.deepEqual(recenterRange(20, [0, 200], [0, 100]), [0, 100]);

console.log('Viewport geometry tests passed');
