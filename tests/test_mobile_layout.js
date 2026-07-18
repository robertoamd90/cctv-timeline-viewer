const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('ctv_web/index.html', 'utf8');
const css = fs.readFileSync('ctv_web/style.css', 'utf8');

const controls = html.match(/<div id="view-controls">([\s\S]*?)<\/div>\s*<div id="custom-grid-controls"/);
assert(controls, 'view controls must be grouped in one container');
assert(controls[1].includes('id="layout-select"'));
assert(controls[1].includes('id="camera-filter-wrap"'));
assert(controls[1].includes('id="auto-hotspot-control"'));

assert(css.includes('display: grid; grid-row: 3; grid-column: 1 / 5;'));
assert(css.includes('grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) max-content;'));
assert(!css.includes('#auto-hotspot-control { grid-row: 4;'));

console.log('Mobile toolbar layout tests passed');
