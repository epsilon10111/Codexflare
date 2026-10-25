// 仅注入隔离的测试副本，不安装到用户运行副本。
const { app, screen } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const output = process.env.CODEX_BOOT_PROBE_OUTPUT;
const samples = [];
let captured = false;
let started = false;
app.on('browser-window-created', (_event, win) => {
  win.webContents.on('console-message', (event, _level, message) => {
    const line = event.message ?? message;
    if (!line?.startsWith('CODEX_BOOT_PROBE:')) return;
    const frame = JSON.parse(line.slice('CODEX_BOOT_PROBE:'.length));
    const native = { fullscreen: win.isFullScreen(), visible: win.isVisible(),
      bounds: win.getBounds(), display: screen.getDisplayMatching(win.getBounds()).bounds };
    samples.push({ ...frame, native });
    fs.writeFileSync(path.join(output, 'samples.json'), JSON.stringify(samples, null, 2));
    if (!captured && frame.video?.time > 1 && frame.video?.time < 3) {
      captured = true;
      win.webContents.capturePage().then(image =>
        fs.writeFileSync(path.join(output, 'playing.png'), image.toPNG()));
    }
    if (!started) {
      started = true;
      setTimeout(async () => {
        if (!win.isDestroyed()) {
          const image = await win.webContents.capturePage();
          fs.writeFileSync(path.join(output, 'after.png'), image.toPNG());
        }
        app.exit(0);
      }, 7500);
    }
  });
});
setTimeout(() => app.exit(2), 30000).unref();
