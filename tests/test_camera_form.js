const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('ctv_web/index.html', 'utf8');
const app = fs.readFileSync('ctv_web/js/app.js', 'utf8');

assert(html.includes('id="cam-offset-direction"'));
assert(html.includes('<option value="-1"'));
assert(html.includes('<option value="1"'));
assert(/id="cam-time-offset"[^>]*min="0"[^>]*max="3600"/.test(html));
assert(app.includes("timeOffset < 0 ? '-1' : '1'"));
assert(app.includes('Math.abs(timeOffset)'));
assert(app.includes("Number(document.getElementById('cam-offset-direction').value) * timeOffsetMagnitude"));
assert(html.includes('id="btn-rebuild-index"'));
assert(app.includes("api('/api/admin/rebuild-index', { method: 'POST' })"));
assert(app.includes('S.indexNeedsReload = true'));

console.log('Camera offset form tests passed');
