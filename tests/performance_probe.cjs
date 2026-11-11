// Only synthetic content and an isolated profile; no application backend.
const { app, BrowserWindow, protocol } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = process.env.CODEX_BACKGROUND_PROBE_OUTPUT;
app.setPath('userData', path.join(output, 'profile'));
protocol.registerSchemesAsPrivileged([{ scheme: 'background-test', privileges: { standard: true, secure: true } }]);
const result = { passed: false, samples: [] };
const watchdog = setTimeout(() => { console.error('Long conversation timed out'); app.exit(2); }, 40000);
app.whenReady().then(async () => {
  protocol.handle('background-test', request => {
    const name = new URL(request.url).pathname.slice(1);
    const files = {
      'background-fixture.html': 'text/html',
      ...Object.fromEntries((/* CODEX_BACKGROUND_STYLES */ []).map(name => ['assets/'+name, 'text/css'])),
      'assets/codex-background.css': 'text/css', 'assets/codex-background.png': 'image/png',
    };
    if (!Object.hasOwn(files, name)) return new Response(null, { status: 404 });
    return new Response(fs.readFileSync(path.join(app.getAppPath(), 'webview', name)),
      { headers: { 'Content-Type': files[name] } });
  });
  const win = new BrowserWindow({ width: 1440, height: 900, show: true,
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false } });
  const page = win.webContents;
  const run = (fn, ...args) => page.executeJavaScript(`(${fn.toString()})(...${JSON.stringify(args)})`);
  try {
    for (const mode of ['original', 'custom']) {
      await win.loadURL('background-test://fixture/background-fixture.html');
      if (mode === 'original') await run(() => { document.querySelector('link[href$="codex-background.css"]').disabled = true; });
      const sample = await run(async mode => {
        const content = document.querySelector('.conversation');
        const fragment = document.createDocumentFragment();
        for (let i = 0; i < 2000; i++) {
          const row = document.createElement('p');
          row.textContent = `Synthetic message ${i}: ${'Long conversation text. '.repeat(8)}`;
          fragment.append(row);
        }
        content.append(fragment);
        const scroll = content.closest('.thread-scroll-container');
        const frames = [];
        let previous = performance.now();
        for (let i = 0; i < 120; i++) {
          scroll.scrollTop = -(scroll.scrollHeight - scroll.clientHeight) * ((i % 30) / 29);
          await new Promise(requestAnimationFrame);
          const now = performance.now(); frames.push(now - previous); previous = now;
        }
        frames.sort((a, b) => a - b);
        return { mode, scrollHeight: scroll.scrollHeight, frames: frames.length,
          totalMs: frames.reduce((a, b) => a + b, 0), p95FrameMs: frames[Math.floor(frames.length * .95)],
          transcriptMask: getComputedStyle(scroll.firstElementChild).maskImage,
          animation: getComputedStyle(scroll.firstElementChild).animationName,
          containerType: getComputedStyle(scroll.parentElement).containerType };
      }, mode);
      const process = app.getAppMetrics().find(item => item.pid === page.getOSProcessId());
      sample.memoryKiB = process?.memory;
      result.samples.push(sample);
      fs.writeFileSync(path.join(output, 'progress.json'), JSON.stringify(result, null, 2));
      assert(sample.scrollHeight > 100000 && sample.frames === 120);
      assert.deepEqual([sample.transcriptMask, sample.animation, sample.containerType], ['none', 'none', 'normal']);
      if (mode === 'custom') assert.equal(sample.scrollHeight, result.samples[0].scrollHeight);
      assert(sample.totalMs < 15000, 'Long conversation stopped responding');
    }
    result.passed = true;
  } catch (error) { result.error = error.stack; }
  finally {
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(result, null, 2));
    clearTimeout(watchdog);
    app.exit(result.passed ? 0 : 1);
  }
}).catch(error => { console.error(error); app.exit(1); });
