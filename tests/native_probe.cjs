// 仅注入隔离的测试副本，不安装到用户运行副本。
const { app, screen } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const output = process.env.CODEX_BOOT_PROBE_OUTPUT;
const timeout = Number(process.env.CODEX_BOOT_PROBE_TIMEOUT_MS || 30000);
const samples = [];
let captured = false;
let capturedWaiting = false;
let started = false;
let finishing = false;
let playingCapture = Promise.resolve();
async function finish(win, code) {
  if (finishing) return;
  finishing = true;
  try {
    await playingCapture;
    if (!win.isDestroyed()) {
      const image = await win.webContents.capturePage();
      fs.writeFileSync(path.join(output, 'after.png'), image.toPNG());
    }
    app.exit(code);
  } catch (error) {
    console.error(error);
    app.exit(3);
  }
}
app.on('browser-window-created', (_event, win) => {
  win.webContents.on('console-message', (event, _level, message) => {
    const line = event.message ?? message;
    if (!line?.startsWith('CODEX_BOOT_PROBE:')) return;
    const frame = JSON.parse(line.slice('CODEX_BOOT_PROBE:'.length));
    const display = screen.getDisplayMatching(win.getBounds());
    const native = { fullscreen: win.isFullScreen(), visible: win.isVisible(), maximized: win.isMaximized(),
      audible: win.webContents.isCurrentlyAudible(),
      bounds: win.getBounds(), contentBounds: win.getContentBounds(), normalBounds: win.getNormalBounds(),
      display: display.bounds, workArea: display.workArea, scaleFactor: display.scaleFactor };
    samples.push({ ...frame, native });
    fs.writeFileSync(path.join(output, 'samples.json'), JSON.stringify(samples, null, 2));
    if (!captured && frame.video?.time > 0 && !frame.video.paused) {
      captured = true;
      playingCapture = win.webContents.capturePage().then(image =>
        fs.writeFileSync(path.join(output, 'playing.png'), image.toPNG())).catch(error => {
        console.error(error);
        app.exit(3);
      });
    }
    if (!started) {
      started = true;
      setTimeout(() => finish(win, 2), timeout);
    }
    if (frame.state === 'waiting-app' && !capturedWaiting) {
      capturedWaiting = true;
      playingCapture = playingCapture.then(() => win.webContents.capturePage()).then(image =>
        fs.writeFileSync(path.join(output, 'waiting.png'), image.toPNG()));
    }
    if (frame.state === 'ended' && !frame.layer && frame.appInteractive && !frame.startupPending) finish(win, 0);
    if (frame.state === 'app-timeout' && !frame.layer) finish(win, 4);
  });
});
setTimeout(() => app.exit(2), timeout + 30000).unref();
