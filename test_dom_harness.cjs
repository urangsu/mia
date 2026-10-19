// Run: node test_dom_harness.cjs SAMPLE_JS.json [path-to-linkedom]
// A real DOM library executes the actual Selenium script on a synthetic fixture.
const fs = require('fs');
const {parseHTML} = require(process.argv[3] || 'linkedom');
const {document} = parseHTML(fs.readFileSync(__dirname+'/fixtures/bm_pinned_sibling.html','utf8'));
const script=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const snapshot=Function('document','return function(){'+script+'}')(document)('fmwidget-0');
if(!snapshot.grids[0].rows[0].cells.some(c=>c.colId==='date' && (c.text||c.title)==='16 Oct 2026'))
  throw Error('Pinned sibling date not joined');
if(snapshot.grids[0].rows[0].cells.some(c=>(c.text||'').includes('2025')))
  throw Error('Other grid date leaked');
console.log('DOM_PINNED_FIXTURE_OK');
