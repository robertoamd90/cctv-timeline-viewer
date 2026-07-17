const assert = require('node:assert/strict');
const { viewportPopoverPosition } = require('../ctv_web/js/geometry.js');

const viewport = { width: 1000, height: 700 };
const size = { width: 280, height: 220 };

assert.deepEqual(viewportPopoverPosition({ x: 400, y: 350 }, size, viewport), { left: 414, top: 240 });
assert.deepEqual(viewportPopoverPosition({ x: 990, y: 690 }, size, viewport), { left: 696, top: 472 });
assert.deepEqual(viewportPopoverPosition({ x: 2, y: 2 }, size, viewport), { left: 16, top: 8 });

console.log('Viewport geometry tests passed');
