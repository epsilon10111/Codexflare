const {test} = require('node:test');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const path = require('node:path');

for (const [name, fixture, bindings] of [
  ['macOS build 20586 bindings', 'macos', {O:'D',S:'C',A5e:'YPe',q:'Fe',We:'Ke'}],
  ['macOS renamed window locals', 'macos', {O:'electron',V:'manager',e:'input',n:'primary',r:'page',
    S:'bounds',k:'maximized',A:'minimum',F:'preferences',R:'a',z:'w',p:'route',P:'sandbox',f:'visible'}],
  ['Linux/Windows renamed window locals', '', {m:'electron',B:'manager',e:'input',n:'primary',r:'page',
    w:'bounds',k:'maximized',A:'minimum',P:'preferences',L:'a',R:'w',f:'route',ee:'sandbox',d:'visible'}],
]) {
  test(name, () => {
    const file = `test_window_mode${fixture ? '_'+fixture : ''}.cjs`;
    const result = spawnSync(process.execPath, ['--test',path.join(__dirname,file)], {
      encoding:'utf8',env:{...process.env,CODEXFLARE_TEST_BINDINGS:JSON.stringify(bindings)},
    });
    assert.equal(result.status,0,result.stdout+result.stderr);
  });
}
