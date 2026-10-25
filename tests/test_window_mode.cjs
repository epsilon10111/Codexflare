const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

// Keep the constructor, restore and late resize paths together to catch conflicting patches.
const fixture = `
function createWindow(e={}) {
  let n=(e.appearance??'primary')==='primary',r=n&&e.page;
  let {show:d=true}=e,w=this.restorePrimaryWindowBounds(),k=w?.isMaximized===true,
    A=this.getPrimaryMinimumSize(),P={contextIsolation:true,nodeIntegration:false,preload:'/safe/preload.js',
    autoplayPolicy:'user-gesture-required'},L={width:w?.width??1280,height:w?.height??820,
    x:w?.x,y:w?.y,show:d,minWidth:A?.width,minHeight:A?.height,webPreferences:P},R=new m.BrowserWindow(L);
  k&&R.once(\`ready-to-show\`,()=>{R.isDestroyed()||R.maximize()});
  return R;
}
function syncPrimaryMinimumSize(){let e=this.windows;if(e.length===0)return;let t=this.getPrimaryMinimumSize();for(let n of e){if(n.setMinimumSize(t.width,t.height),n.isMaximized()||n.isFullScreen())continue;let e=n.getNormalBounds(),r=Math.max(e.width,t.width),i=Math.max(e.height,t.height);(r!==e.width||i!==e.height)&&n.setBounds({...e,width:r,height:i})}}
function onboarding(n,t){let i=Cje(t);if((0,W.default)(this.primaryWindowMode,t)){};return i}
function callPrimary(e,t,n){return B.createPrimaryWindow({title:m.app.getName(),show:e,initialRoute:t===\`/\`?void 0:t,opener:n})}
async function load(R,n,r,d,f,ee){return await R.loadURL(t.o(f,{mcpAppSandboxLocalDevelopment:ee})),R}
`;
const result = spawnSync('python', ['-c',
  'import json,sys; from tools.patch_app import patch_main; text=sys.stdin.read(); print(json.dumps({mode if muted else mode+"-audio":patch_main(text,mode,muted) for mode in ("restore","fullscreen","centered") for muted in (True,False)}))'],
{ cwd: path.resolve(__dirname, '..'), input: fixture, encoding: 'utf8' });
assert.equal(result.status, 0, result.stderr);
const scripts = JSON.parse(result.stdout);

function harness(mode, { saved = null, area = { x: 100, y: 60, width: 1800, height: 1000 }, mapped = true } = {}) {
  class Window extends EventEmitter {
    constructor(options) {
      super();
      this.options = { ...options };
      this.bounds = { x: options.x, y: options.y, width: options.width, height: options.height };
      this.visible = options.show && mapped;
      this.fullscreen = false;
      this.maximized = false;
      this.fullscreenCalls = [];
    }
    isDestroyed() { return !!this.destroyed; }
    isVisible() { return this.visible; }
    isFullScreen() { return this.fullscreen; }
    isMaximized() { return this.maximized; }
    setFullScreen(value) { this.fullscreenCalls.push(value); this.fullscreen = value; }
    maximize() { this.maximized = true; }
    getBounds() { return this.bounds; }
    getNormalBounds() { return this.bounds; }
    setBounds(bounds) { this.bounds = bounds; }
    setMinimumSize(width, height) { this.minimum = { width, height }; }
    show() { this.visible = true; this.emit('show'); }
  }
  const context = vm.createContext({
    m: { BrowserWindow: Window, app: { getName: () => 'Codex' },
      screen: { getDisplayMatching: () => ({ workArea: area }), getPrimaryDisplay: () => ({ workArea: area }) } },
    B: { getPrimaryWindow: () => null, createPrimaryWindow: options => options },
    URL, t: { o: () => 'app://-/index.html' },
    process: { env: {} }, Cje: () => ({ width: 560, height: 560 }), W: { default: () => false },
  });
  vm.runInContext(scripts[mode], context);
  const manager = { windows: [], restorePrimaryWindowBounds: () => saved,
    getPrimaryMinimumSize: () => ({ width: 480, height: 600 }) };
  return { context, manager, create(options = {}) {
    const window = context.createWindow.call(manager, { codexflareStartup: true, ...options });
    manager.windows.push(window);
    return window;
  } };
}

test('恢复模式完整保留普通大小和 ready-to-show 最大化', () => {
  const saved = { x: 240, y: 90, width: 980, height: 700, isMaximized: true };
  const { create, context } = harness('restore', { saved });
  const win = create();
  assert.deepEqual(win.bounds, { x: 240, y: 90, width: 980, height: 700 });
  win.emit('ready-to-show');
  assert.equal(win.maximized, true);
  assert.equal(win.codexflareWindowMode, 'restore');
  assert.equal(context.onboarding(win, {}), null);
  const fresh = harness('restore');
  const freshWindow = fresh.create();
  assert.equal(freshWindow.codexflareWindowMode, undefined);
  assert.equal(fresh.context.onboarding(freshWindow, {}).width, 560);
  for (const options of [{ show: false }, { page: true }, { appearance: 'detached' }, { codexflareStartup: false }]) {
    assert.equal(create(options).codexflareWindowMode, undefined);
  }
});

test('仅普通初始主窗口获得模式，保持后台、Page 和其他窗口的语义', () => {
  for (const mode of ['restore', 'fullscreen', 'centered']) {
    const { create, context } = harness(mode);
    assert.equal(context.callPrimary(false, '/', null).codexflareStartup, true);
    assert.equal(context.callPrimary(true, '/', null).codexflareStartup, false);
    context.B.getPrimaryWindow = () => ({});
    assert.equal(context.callPrimary(false, '/', null).codexflareStartup, false);
    context.process.env.CODEX_ELECTRON_START_IN_BACKGROUND = '1';
    assert.equal(context.callPrimary(false, '/', null).show, false);
    for (const options of [{ show: false }, { page: true }, { appearance: 'detached' }, { codexflareStartup: false }]) {
      const win = create(options);
      assert.equal(win.codexflareWindowMode, undefined);
      assert.equal(win.options.width, 1280);
      assert.equal(win.fullscreenCalls.length, 0);
    }
  }
});

test('有声开屏仅在目标主窗口加载完成后授权一次，保留原 webPreferences', async () => {
  for (const mode of ['restore', 'fullscreen', 'centered']) {
    for (const muted of [true, false]) {
      const { create, context } = harness(mode + (muted ? '' : '-audio'));
      const preferences = create().options.webPreferences;
      assert.equal(preferences.autoplayPolicy, 'user-gesture-required');
      assert.equal(preferences.contextIsolation, true);
      assert.equal(preferences.nodeIntegration, false);
      assert.equal(preferences.preload, '/safe/preload.js');
      for (const [primary, page, show] of [[true, false, true], [true, false, false], [true, true, true], [false, false, true]]) {
        const target = primary && !page && show;
        const calls = [];
        const contents = new EventEmitter();
        contents.executeJavaScript = (script, gesture) => { calls.push({ script, gesture }); return Promise.resolve(); };
        const win = { webContents: contents, async loadURL(url) {
          assert.equal(contents.listenerCount('dom-ready'), Number(target && !muted));
          assert.equal(new URL(url).searchParams.get('codexBootAnimation'), target ? '1' : null);
        } };
        assert.equal(await context.load(win, primary, page, show), win);
        assert.equal(calls.length, 0);
        contents.emit('dom-ready');
        contents.emit('dom-ready');
        assert.deepEqual(calls, target && !muted ? [{
          script: 'document.dispatchEvent(new Event(`codex-boot-play`))', gesture: true,
        }] : []);
      }
    }
  }
});

test('开屏手势桥接失败不阻断主页面或产生未处理拒绝', async () => {
  const { context } = harness('restore-audio');
  for (const synchronous of [true, false]) {
    let loaded = false, calls = 0;
    const contents = new EventEmitter();
    contents.executeJavaScript = () => {
      calls++;
      if (synchronous) throw new Error('window closed');
      return Promise.reject(new Error('window closed'));
    };
    await context.load({ webContents: contents, async loadURL() { loaded = true; } }, true, false, true);
    contents.emit('dom-ready');
    contents.emit('dom-ready');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(loaded, true);
    assert.equal(calls, 1);
  }
});

test('全屏只进入一次，忽略保存的最大化及登录窗口尺寸建议', () => {
  for (const mapped of [true, false]) {
    const { create, context } = harness('fullscreen', { saved: { isMaximized: true }, mapped });
    const win = create();
    assert.equal(win.options.fullscreen, undefined);
    assert.equal(win.fullscreenCalls.length, mapped ? 1 : 0);
    win.show();
    win.show();
    win.emit('ready-to-show');
    assert.deepEqual(win.fullscreenCalls, [true]);
    assert.equal(win.maximized, false);
    assert.equal(context.onboarding(win, {}), null);
  }
  const { create } = harness('fullscreen', { mapped: false });
  const destroyed = create();
  destroyed.destroyed = true;
  destroyed.show();
  assert.deepEqual(destroyed.fullscreenCalls, []);
});

test('居中窗口使用 1100×760，随后最小尺寸同步不覆盖小工作区适配', () => {
  for (const area of [{ x: -1800, y: 60, width: 1800, height: 1000 }, { x: 20, y: 40, width: 420, height: 500 }]) {
    const { create, context, manager } = harness('centered', { area, saved: { isMaximized: true } });
    const win = create();
    const width = Math.min(1100, area.width), height = Math.min(760, area.height);
    assert.deepEqual(win.bounds, { x: area.x + Math.round((area.width - width) / 2),
      y: area.y + Math.round((area.height - height) / 2), width, height });
    assert.equal(win.options.minWidth, Math.min(480, width));
    assert.equal(win.options.minHeight, Math.min(600, height));
    assert.equal(context.onboarding(win, {}), null);
    const normal = create({ codexflareStartup: false });
    context.syncPrimaryMinimumSize.call(manager);
    assert.equal(win.bounds.width, width);
    assert.equal(win.bounds.height, height);
    assert.deepEqual(win.minimum, { width: Math.min(480, width), height: Math.min(600, height) });
    assert.deepEqual(normal.minimum, { width: 480, height: 600 });
    win.emit('ready-to-show');
    assert.equal(win.maximized, false);
  }
});
