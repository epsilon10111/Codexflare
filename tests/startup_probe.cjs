// 仅运行候选归档的动画和模拟工作区，不启动原应用主进程或后端。
const { app, BrowserWindow, protocol } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = process.env.CODEX_BACKGROUND_PROBE_OUTPUT;
app.setPath('userData', path.join(output, 'profile'));
protocol.registerSchemesAsPrivileged([{ scheme: 'background-test',
  privileges: { standard: true, secure: true, stream: true } }]);
const result = { passed: false, scope: 'candidate animation and background with isolated workspace', runs: [] };
const timeout = setTimeout(() => { console.error('Startup probe timed out'); app.exit(2); },
  Number(process.env.CODEX_STARTUP_PROBE_TIMEOUT_MS || 50000));

function observeStartup() {
  const fullWidth = new URLSearchParams(location.search).get('fullWidth') === '1';
  const stats = { fullWidth, workspaceMountedMs: null, endedMs: null, leavingMs: null, removedMs: null };
  let overlaySeen = false;
  document.addEventListener('ended', event => {
    if (event.target.tagName !== 'VIDEO') return;
    stats.endedMs = performance.now();
    stats.duration = event.target.duration;
    stats.playbackRate = event.target.playbackRate;
    stats.videoTime = event.target.currentTime;
  }, true);
  const observer = new MutationObserver(() => {
    const layer = document.getElementById('codex-boot');
    if (layer) overlaySeen = true;
    if (layer?.classList.contains('leaving') && stats.leavingMs === null) stats.leavingMs = performance.now();
    if (!overlaySeen || layer || stats.removedMs !== null) return;
    stats.removedMs = performance.now();
    stats.state = document.documentElement.dataset.codexBoot;
    stats.backgroundState = document.documentElement.dataset.codexBackground;
    observer.disconnect();
    console.log('CODEX_STARTUP_FRAME:' + JSON.stringify(stats));
  });
  observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
  overlaySeen = !!document.getElementById('codex-boot');
  setTimeout(() => {
    const template = document.getElementById('workspace-template');
    const root = template.content.querySelector('#root');
    if (fullWidth) {
      const layout = root.querySelector('[data-app-shell-main-content-layout]');
      layout.dataset.appShellRightPanelFullWidth = 'true';
      layout.setAttribute('aria-hidden', 'true');
      layout.inert = true;
      layout.style.display = 'none';
      const panel = root.querySelector('aside[data-app-shell-focus-area="right-panel"]');
      panel.hidden = false;
      panel.style.width = '100%';
      panel.style.borderLeft = '0';
    }
    document.getElementById('root').replaceWith(root);
    template.remove();
    stats.workspaceMountedMs = performance.now();
  }, 1000);
}

function pixelDifference(first, second, rect, viewportWidth) {
  assert.deepEqual(first.getSize(), second.getSize(), '截图尺寸在衔接过程中改变');
  const { width, height } = first.getSize();
  const scale = width / viewportWidth;
  const a = first.toBitmap(), b = second.toBitmap();
  let total = 0, changedPixels = 0, pixels = 0, max = 0;
  for (let y = Math.max(0, Math.ceil(rect.y * scale)); y < Math.min(height, Math.floor((rect.y + rect.height) * scale)); y++) {
    for (let x = Math.max(0, Math.ceil(rect.x * scale)); x < Math.min(width, Math.floor((rect.x + rect.width) * scale)); x++) {
      const i = (y * width + x) * 4;
      const difference = Math.max(Math.abs(a[i] - b[i]), Math.abs(a[i + 1] - b[i + 1]), Math.abs(a[i + 2] - b[i + 2]));
      max = Math.max(max, difference);
      total += difference;
      changedPixels += Number(difference > 1);
      pixels++;
    }
  }
  assert(pixels > 0, '背景测量区域为空');
  return { pixels, changedPixels, max, averageChannelDifference: total / pixels };
}

app.whenReady().then(async () => {
  protocol.handle('background-test', request => {
    const url = new URL(request.url);
    if (url.hostname !== 'fixture') return new Response(null, { status: 404 });
    const name = decodeURIComponent(url.pathname).slice(1);
    const files = {
      'background-fixture.html': 'text/html',
      'assets/app-shared-f2d570e85ceb.css': 'text/css',
      'assets/app-initial-c43288484373.css': 'text/css',
      'assets/thread-scroll-layout-24b9bd243051.css': 'text/css',
      'assets/codex-background.css': 'text/css',
      'assets/codex-background.png': 'image/png',
      'assets/codex-boot.css': 'text/css',
      'assets/codex-boot.js': 'text/javascript',
      'assets/codex-boot.webm': 'video/webm',
      'assets/startup-page-probe.js': 'text/javascript',
    };
    if (!Object.hasOwn(files, name)) return new Response(null, { status: 404 });
    try {
      const data = name === 'assets/startup-page-probe.js' ? Buffer.from(`(${observeStartup.toString()})()`)
        : fs.readFileSync(path.join(app.getAppPath(), 'webview', name));
      const headers = { 'Content-Type': files[name], 'Content-Length': String(data.length) };
      if (name.endsWith('.webm')) {
        headers['Accept-Ranges'] = 'bytes';
        const range = request.headers.get('Range');
        if (range) {
          const match = /^bytes=(\d+)-(\d*)$/.exec(range);
          const start = match ? Number(match[1]) : NaN;
          const end = match?.[2] ? Math.min(Number(match[2]), data.length - 1) : data.length - 1;
          if (!Number.isInteger(start) || start < 0 || start > end) return new Response(null, { status: 416 });
          headers['Content-Range'] = `bytes ${start}-${end}/${data.length}`;
          headers['Content-Length'] = String(end - start + 1);
          return new Response(data.subarray(start, end + 1), { status: 206, headers });
        }
      }
      return new Response(data, { headers });
    } catch { return new Response(null, { status: 404 }); }
  });
  const win = new BrowserWindow({ width: 1440, height: 900, useContentSize: true,
    ...(process.platform === 'darwin' ? { type: 'panel', resizable: false, maximizable: false } : {}),
    title: 'Codexflare · 开屏衔接验证', backgroundColor: '#181818',
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false } });
  win.setMenuBarVisibility(false);
  const page = win.webContents;
  const run = (fn, ...args) => page.executeJavaScript(`(${fn.toString()})(...${JSON.stringify(args)})`);
  const settle = () => run(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const save = (name, image) => fs.writeFileSync(path.join(output, `${name}.png`), image.toPNG());
  try {
    for (const fullWidth of [false, true]) {
      const name = fullWidth ? 'full-width-panel' : 'workspace';
      let listener;
      const revealed = new Promise((resolve, reject) => {
        listener = (event, _level, message) => {
          const line = event.message ?? message;
          if (!line?.startsWith('CODEX_STARTUP_FRAME:')) return;
          const stats = JSON.parse(line.slice('CODEX_STARTUP_FRAME:'.length));
          // 遮罩移除通知后立即抓取，不等额外帧，以免漏掉首帧缺图。
          page.capturePage().then(image => resolve({ stats, image }), reject);
        };
        page.on('console-message', listener);
      });
      await win.loadURL(`background-test://fixture/background-fixture.html?codexBootAnimation=1&fullWidth=${Number(fullWidth)}`);
      const { stats, image: first } = await revealed;
      page.removeListener('console-message', listener);
      const later = new Promise(resolve => setTimeout(resolve, 500));
      const capturedMs = await run(() => performance.now());
      save(`${name}-first`, first);
      await later;
      const stable = await page.capturePage();
      const stableCapturedMs = await run(() => performance.now());
      save(`${name}-500ms`, stable);
      const geometry = await run(() => {
        const main = document.querySelector('main');
        const r = main.getBoundingClientRect();
        return { viewportWidth: innerWidth, main: { x: r.x, y: r.y, width: r.width, height: r.height },
          fullWidth: main.querySelector('[data-app-shell-right-panel-full-width]')?.getAttribute('data-app-shell-right-panel-full-width'),
          mainInert: main.querySelector('[data-app-shell-main-content-layout]').inert,
          background: getComputedStyle(main, '::before').backgroundImage };
      });
      const key = await page.insertCSS('main[data-app-shell-main-surface]::before { visibility: hidden !important; }');
      await settle();
      const hidden = await page.capturePage();
      save(`${name}-background-disabled`, hidden);
      await page.removeInsertedCSS(key);
      const rect = { x: geometry.main.x + geometry.main.width * .5, y: geometry.main.y + 64,
        width: geometry.main.width * .5, height: geometry.main.height - 64 };
      const measurements = { ...stats, firstCaptureMs: capturedMs, stableCaptureMs: stableCapturedMs,
        endedToLeavingMs: stats.leavingMs - stats.endedMs,
        removedToFirstCaptureMs: capturedMs - stats.removedMs,
        geometry, region: rect,
        firstTo500ms: pixelDifference(first, stable, rect, geometry.viewportWidth),
        firstToDisabled: pixelDifference(first, hidden, rect, geometry.viewportWidth),
        stableToDisabled: pixelDifference(stable, hidden, rect, geometry.viewportWidth) };
      result.runs.push(measurements);
      assert.equal(stats.state, 'ended', `${name}: 动画未自然结束`);
      assert.equal(stats.backgroundState, 'ready', `${name}: 背景未就绪`);
      assert(Number.isFinite(stats.duration) && stats.duration > 0 && stats.videoTime >= stats.duration - .05,
        '视频未自然播放至片尾');
      assert(stats.workspaceMountedMs > 900 && stats.workspaceMountedMs < stats.endedMs, '工作区未在播放期间挂载');
      assert(stats.endedMs !== null && stats.leavingMs !== null && measurements.endedToLeavingMs < 150,
        `${name}: 片尾到揭幕仍有额外等待`);
      assert(measurements.firstTo500ms.max <= 1, `${name}: 揭幕首帧与500ms后不一致，背景可能延迟绘制`);
      assert(measurements.firstToDisabled.averageChannelDifference > .1, `${name}: 首帧背景没有真正绘制`);
      assert.equal(geometry.fullWidth, String(fullWidth));
      assert.equal(geometry.mainInert, fullWidth);
    }
    result.passed = true;
  } catch (error) {
    result.error = error.stack;
  } finally {
    clearTimeout(timeout);
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(result, null, 2));
    app.exit(result.passed ? 0 : 1);
  }
}).catch(error => { console.error(error); app.exit(1); });
