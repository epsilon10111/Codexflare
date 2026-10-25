const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../src/boot.js'), 'utf8');

class Events {
  listeners = new Map();
  addEventListener(type, handler, options = {}) {
    const handlers = this.listeners.get(type) || [];
    handlers.push({ handler, once: options.once });
    this.listeners.set(type, handlers);
  }
  removeEventListener(type, handler) {
    this.listeners.set(type, (this.listeners.get(type) || []).filter(item => item.handler !== handler));
  }
  emit(type, properties = {}) {
    const event = {
      defaultPrevented: false, stopped: false,
      preventDefault() { this.defaultPrevented = true; },
      stopImmediatePropagation() { this.stopped = true; },
      ...properties,
    };
    for (const { handler, once } of [...(this.listeners.get(type) || [])]) {
      if (once) this.removeEventListener(type, handler);
      handler(event);
      if (event.stopped) break;
    }
    return event;
  }
  count(type) { return (this.listeners.get(type) || []).length; }
}

class Element extends Events {
  constructor(tag) {
    super();
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.style = {};
    this.classList = new Set();
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  append(...elements) {
    for (const element of elements) {
      element.remove();
      element.parent = this;
      this.children.push(element);
    }
  }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
    this.parent = null;
  }
  replaceChildren(...elements) {
    for (const child of [...this.children]) child.remove();
    this.append(...elements);
  }
}

function boot({ search = '?codexBootAnimation=1', hidden = false, reduced = false, loading = false, bodyPresent = true, rejectPlay = false, scriptSrc = 'file:///app/webview/assets/codex-boot.js', settings = null, appReady = true, loader = null, visible = true, shell = false, mainReady = true, mainInert = false, fullWidth = false, rightReady = true, rightInert = false, background = false } = {}) {
  const document = new Events();
  document.documentElement = new Element('html');
  const body = new Element('body');
  document.body = bodyPresent ? body : null;
  if (bodyPresent) document.documentElement.append(body);
  const root = new Element('div');
  root.id = 'root';
  const readiness = { appReady, loader, visible, shell, mainReady, mainInert, fullWidth, rightReady, rightInert };
  const controls = 'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [contenteditable="true"], [role="alert"], [data-thread-find-target="conversation"]';
  const control = {
    getClientRects: () => readiness.visible ? [{}] : [],
    closest: () => null,
  };
  let main = {
    ...control,
    closest: () => readiness.mainInert ? {} : null,
    querySelectorAll: selector => {
      assert.equal(selector, controls);
      return readiness.mainReady ? [control] : [];
    },
  };
  const rightPanel = {
    ...control,
    closest: () => readiness.rightInert ? {} : null,
    querySelectorAll: selector => {
      assert.equal(selector, controls);
      return readiness.rightReady ? [control] : [];
    },
  };
  const mainShell = {
    ...control,
    querySelector: selector => {
      assert.equal(selector, '[data-app-shell-main-content-layout][data-app-shell-right-panel-full-width="true"]');
      return readiness.fullWidth ? {} : null;
    },
    querySelectorAll: selector => {
      if (selector === 'aside[data-app-shell-focus-area="right-panel"]') return [rightPanel];
      assert.equal(selector, '[data-app-shell-main-content-layout] [data-app-shell-focus-area="main"]');
      return [main];
    },
  };
  const backgroundLink = background ? { href: 'file:///app/webview/assets/codex-background.png' } : null;
  document.getElementById = id => id === 'root' ? root : id === 'codex-background-preload' ? backgroundLink : null;
  root.querySelector = selector => {
    assert.equal(selector, '.startup-loader, ._delayedBlossom_ovcb0_16');
    return readiness.loader;
  };
  root.querySelectorAll = selector => {
    if (selector === 'main[data-app-shell-main-surface]') return readiness.shell ? [mainShell] : [];
    assert.equal(selector, controls);
    return readiness.appReady ? [control] : [];
  };
  body.append(root);
  document.hidden = hidden;
  document.readyState = loading ? 'loading' : 'complete';
  document.currentScript = { src: scriptSrc };
  const videos = [];
  document.createElement = tag => {
    const element = new Element(tag);
    if (tag === 'video') {
      element.playCalls = 0;
      element.pauseCalls = 0;
      element.play = () => {
        element.playCalls++;
        return rejectPlay ? Promise.reject(new Error('Playback unavailable')) : Promise.resolve();
      };
      element.pause = () => { element.pauseCalls++; };
      videos.push(element);
    }
    return element;
  };
  let now = 0;
  let nextId = 0;
  const timers = new Map();
  const observers = [];
  const images = [];
  const context = {
    document, URL, URLSearchParams,
    Image: class {
      constructor() { images.push(this); }
      decode() {
        this.decodeCalls = (this.decodeCalls || 0) + 1;
        return new Promise((resolve, reject) => { this.resolve = resolve; this.reject = reject; });
      }
    },
    getComputedStyle: () => ({ visibility: 'visible' }),
    location: { search, href: `file:///app/webview/index.html${search}` },
    MutationObserver: class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe(target, options) {
        assert.equal(target, document.documentElement);
        assert.equal(options.childList, true);
        this.active = true;
      }
      disconnect() { this.active = false; }
    },
    matchMedia: query => {
      assert.equal(query, '(prefers-reduced-motion: reduce)');
      return { matches: reduced };
    },
    setTimeout: (callback, delay) => {
      timers.set(++nextId, { callback, at: now + delay });
      return nextId;
    },
    clearTimeout: id => timers.delete(id),
    requestAnimationFrame: callback => {
      timers.set(++nextId, { callback, at: now + 16 });
      return nextId;
    },
    cancelAnimationFrame: id => timers.delete(id),
  };
  vm.runInNewContext(source.replace('/* CODEX_BOOT_SETTINGS */ null', JSON.stringify(settings)), context, { filename: 'boot.js' });
  return {
    document, root, videos, timers, observers, readiness, images,
    replaceMain() { main = { ...main }; },
    get layer() { return document.body?.children.find(child => child.id === 'codex-boot'); },
    notifyMutation() {
      for (const observer of observers) if (observer.active) observer.callback();
    },
    attachBody() {
      document.body = body;
      document.documentElement.append(body);
      this.notifyMutation();
    },
    advance(milliseconds) {
      const end = now + milliseconds;
      for (;;) {
        const next = [...timers.entries()].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        const [id, timer] = next;
        timers.delete(id);
        now = timer.at;
        timer.callback();
      }
      now = end;
    },
  };
}

function assertReleased(app, reason) {
  assert.equal(app.document.documentElement.dataset.codexBoot, reason);
  assert.equal(app.videos[0].pauseCalls, 1);
  assert.equal(app.document.count('keydown'), 0);
  assert.equal(app.document.count('visibilitychange'), 0);
  assert.equal(app.document.count('codex-boot-play'), 0);
  assert.ok(app.layer.classList.has('leaving'));
  app.advance(230);
  assert.equal(app.layer, undefined);
  assert.equal(app.timers.size, 0);
}

test('非主窗口不创建动画或更改文档状态', () => {
  for (const search of ['', '?codexBootAnimation=0', '?other=1']) {
    const app = boot({ search });
    assert.equal(app.layer, undefined);
    assert.equal(app.videos.length, 0);
    assert.deepEqual(app.document.documentElement.dataset, {});
    assert.equal(app.timers.size, 0);
  }
});

test('主窗口自动静音播放，正常结束后移除遮罩', () => {
  const app = boot();
  const video = app.videos[0];
  assert.equal(video.src, 'file:///app/webview/assets/codex-boot.webm');
  assert.equal(video.muted, true);
  assert.equal(video.playsInline, true);
  assert.equal(video.playCalls, 1);
  assert.equal(video.playbackRate, 1);
  assert.equal(video.defaultPlaybackRate, 1);
  assert.equal(video.style.filter, 'brightness(1) contrast(1) saturate(1)');
  assert.equal(video.style.objectFit, 'cover');
  assert.equal(app.layer.attributes['aria-label'], 'Codex 启动动画');
  video.emit('ended');
  video.emit('error');
  assertReleased(app, 'ended');
});

test('开屏遵循保存的静音设置，旧配置仍默认静音', () => {
  for (const muted of [undefined, true, false]) {
    const settings = { speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', duration: 10.039 };
    if (muted !== undefined) settings.muted = muted;
    const app = boot({ settings });
    assert.equal(app.videos[0].muted, muted !== false);
    if (muted === false) {
      assert.equal(app.videos[0].playCalls, 0);
      app.document.emit('visibilitychange');
      assert.equal(app.videos[0].playCalls, 0);
      app.document.emit('codex-boot-play');
      app.document.emit('codex-boot-play');
    }
    assert.equal(app.videos[0].playCalls, 1);
    app.videos[0].emit('ended');
    assertReleased(app, 'ended');
  }
});

test('有声播放等待主进程时仍可超时、跳过或遵循减少动态效果', () => {
  const settings = { speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', muted: false, duration: 10.039 };
  for (const reason of ['timeout', 'skipped', 'reduced-motion']) {
    const app = boot({ settings, reduced: reason === 'reduced-motion' });
    assert.equal(app.videos[0].playCalls, 0);
    if (reason === 'timeout') app.advance(15000);
    if (reason === 'skipped') app.document.emit('keydown', { key: 'Escape' });
    assertReleased(app, reason);
    app.document.emit('codex-boot-play');
    assert.equal(app.videos[0].playCalls, 0);
  }
});

test('播放授权较晚到达时重新计算完整播放超时，不截断有声视频', () => {
  const settings = { speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', muted: false, duration: 10.039 };
  const app = boot({ settings });
  app.advance(14000);
  app.document.emit('codex-boot-play');
  assert.equal(app.videos[0].playCalls, 1);
  app.advance(14999);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
  app.advance(1);
  assertReleased(app, 'timeout');
});

test('隐藏窗口收到播放授权仍等待可见，随后开始播放和超时保护', () => {
  const settings = { speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', muted: false, duration: 10.039 };
  const app = boot({ settings, hidden: true });
  app.document.emit('codex-boot-play');
  app.advance(30000);
  assert.equal(app.videos[0].playCalls, 0);
  app.document.hidden = false;
  app.document.emit('visibilitychange');
  assert.equal(app.videos[0].playCalls, 1);
  app.advance(15000);
  assertReleased(app, 'timeout');
});

test('应用先就绪不截断视频，视频后就绪则保留尾帧直到主界面可用', () => {
  const app = boot({ appReady: false });
  app.advance(1000);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
  app.videos[0].emit('ended');
  assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
  assert.equal(app.layer.children[2].hidden, false);
  assert.equal(app.videos[0].pauseCalls, 0);
  app.document.emit('visibilitychange');
  assert.equal(app.videos[0].playCalls, 1);
  app.advance(500);
  app.readiness.appReady = true;
  app.advance(100);
  assertReleased(app, 'ended');
});

test('背景在播放期间解码并准备工作区，片尾直接揭幕且不重复解码', async () => {
  const app = boot({ background: true, shell: true });
  assert.equal(app.images[0].src, 'file:///app/webview/assets/codex-background.png');
  assert.equal(app.images[0].fetchPriority, 'high');
  assert.equal(app.videos[0].playCalls, 1);
  app.images[0].resolve();
  await Promise.resolve();
  app.advance(131);
  assert.equal(app.document.documentElement.dataset.codexBackground, 'decoded');
  app.advance(1);
  assert.equal(app.document.documentElement.dataset.codexBackground, 'ready');
  assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
  assert.equal(app.layer.children[2].hidden, true);
  assert.equal(app.images[0].decodeCalls, 1);
  app.advance(2000);
  app.videos[0].emit('ended');
  assert.equal(app.layer.children[2].hidden, true);
  assertReleased(app, 'ended');
  assert.equal(app.images[0].decodeCalls, 1);
});

test('片尾图片仍在解码时继续等待，完成后预留绘制帧再揭幕', async () => {
  const app = boot({ background: true });
  app.videos[0].emit('ended');
  app.advance(500);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
  assert.equal(app.layer.children[2].textContent, '正在准备背景…');
  app.images[0].resolve();
  await Promise.resolve();
  app.advance(131);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
  app.advance(1);
  assertReleased(app, 'ended');
  assert.equal(app.images[0].decodeCalls, 1);
});

test('背景解码失败可退出，主动跳过会取消等待绘制', async () => {
  const failed = boot({ background: true });
  failed.images[0].reject(new Error('图片损坏'));
  await Promise.resolve();
  failed.videos[0].emit('ended');
  failed.advance(32);
  assert.equal(failed.document.documentElement.dataset.codexBackground, 'error');
  assertReleased(failed, 'ended');
  const skipped = boot({ background: true });
  skipped.images[0].resolve();
  await Promise.resolve();
  skipped.advance(116);
  skipped.document.emit('keydown', { key: 'Escape' });
  assertReleased(skipped, 'skipped');
});

test('工作区在视频期间晚挂载可提前准备，片尾之后挂载仍安全等待', async () => {
  for (const endedFirst of [false, true]) {
    const app = boot({ background: true, shell: true, mainReady: false });
    app.images[0].resolve();
    await Promise.resolve();
    app.advance(3000);
    assert.equal(app.document.documentElement.dataset.codexBackground, 'decoded');
    if (endedFirst) app.videos[0].emit('ended');
    app.readiness.mainReady = true;
    app.advance(131);
    assert.equal(app.document.documentElement.dataset.codexBoot, endedFirst ? 'waiting-app' : 'loading');
    app.advance(1);
    assert.equal(app.document.documentElement.dataset.codexBackground, 'ready');
    if (!endedFirst) {
      assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
      app.videos[0].emit('ended');
    }
    assertReleased(app, 'ended');
    assert.equal(app.images[0].decodeCalls, 1);
  }
});

test('片尾工作区节点已替换时不能复用旧准备结果', async () => {
  const app = boot({ background: true, shell: true });
  app.images[0].resolve();
  await Promise.resolve();
  app.advance(132);
  assert.equal(app.document.documentElement.dataset.codexBackground, 'ready');
  app.replaceMain();
  app.videos[0].emit('ended');
  assert.equal(app.document.documentElement.dataset.codexBackground, 'decoded');
  app.advance(31);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
  app.advance(1);
  assertReleased(app, 'ended');
});

test('片尾失去交互或绘制期间切换节点时重新确认工作区', async () => {
  for (const duringPaint of [false, true]) {
    const app = boot({ background: true, shell: true });
    app.images[0].resolve();
    await Promise.resolve();
    app.advance(duringPaint ? 116 : 132);
    if (duringPaint) app.replaceMain();
    else app.readiness.mainReady = false;
    app.videos[0].emit('ended');
    app.advance(16);
    assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
    if (duringPaint) {
      app.advance(32);
    } else {
      app.advance(100);
      assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
      app.readiness.mainReady = true;
      app.advance(132);
    }
    assertReleased(app, 'ended');
  }
});

test('初次解码未完成时跳过，迟到的 Promise 不会复活动画', async () => {
  const app = boot({ background: true });
  app.document.emit('keydown', { key: 'Escape' });
  assertReleased(app, 'skipped');
  const state = app.document.documentElement.dataset.codexBackground;
  app.images[0].resolve();
  await Promise.resolve();
  app.advance(100);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'skipped');
  assert.equal(app.document.documentElement.dataset.codexBackground, state);
  assert.equal(app.layer, undefined);
  assert.equal(app.timers.size, 0);
});

test('播放期间媒体失败会清理已安排的背景绘制', async () => {
  const app = boot({ background: true, shell: true });
  app.images[0].resolve();
  await Promise.resolve();
  app.advance(116);
  app.videos[0].emit('error');
  assertReleased(app, 'media-error');
  assert.equal(app.document.documentElement.dataset.codexBackground, 'decoded');
});

test('背景解码一直未完成也受等待上限保护', () => {
  const app = boot({ background: true });
  app.videos[0].emit('ended');
  app.advance(20000);
  assertReleased(app, 'app-timeout');
});

test('静态或 React 开屏仍存在时不把空壳按钮当作就绪', () => {
  for (const loader of ['startup-loader', '_delayedBlossom_ovcb0_16']) {
    const app = boot({ loader });
    app.videos[0].emit('ended');
    app.advance(100);
    assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
    app.readiness.loader = null;
    app.advance(100);
    assertReleased(app, 'ended');
  }
});

test('主会话已可用时，慢速右侧面板或内嵌应用的 blossom 不延迟揭幕', () => {
  const app = boot({ shell: true, mainReady: true, loader: '_delayedBlossom_ovcb0_16' });
  app.videos[0].emit('ended');
  assertReleased(app, 'ended');
});

test('只有窗口外壳、标题栏按钮和主区域 spinner 时继续等待', () => {
  const app = boot({ shell: true, mainReady: false, appReady: true, loader: '_delayedBlossom_ovcb0_16' });
  app.videos[0].emit('ended');
  app.advance(100);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
  app.readiness.mainReady = true;
  app.advance(100);
  assertReleased(app, 'ended');
});

test('隐藏或 inert 主区域不能因其他面板有控件而被当作就绪', () => {
  const app = boot({ shell: true, mainInert: true });
  app.videos[0].emit('ended');
  app.advance(100);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
  app.readiness.mainInert = false;
  app.advance(100);
  assertReleased(app, 'ended');
});

test('恢复全宽右侧页面时以其可见交互判断就绪，不等待 inert 主会话', () => {
  const app = boot({ shell: true, mainInert: true, fullWidth: true });
  app.videos[0].emit('ended');
  assertReleased(app, 'ended');
});

test('全宽右侧页面仍为空或 inert 时继续等待，不借用其他区域控件', () => {
  for (const state of [{ rightReady: false }, { rightInert: true }]) {
    const app = boot({ shell: true, fullWidth: true, ...state });
    app.videos[0].emit('ended');
    app.advance(100);
    assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
    app.readiness.rightReady = true;
    app.readiness.rightInert = false;
    app.advance(100);
    assertReleased(app, 'ended');
  }
});

test('开场 CSS 仅压制静态首屏，保留 React 局部加载反馈', () => {
  const css = readFileSync(join(__dirname, '../src/boot.css'), 'utf8');
  assert.match(css, /#root > \.startup-loader/);
  assert.doesNotMatch(css, /delayedBlossom/);
});

test('隐藏内容不算就绪，等待最多 20 秒且不得标记为播放成功', () => {
  const app = boot({ visible: false });
  app.videos[0].emit('ended');
  app.advance(19999);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'waiting-app');
  app.advance(1);
  assertReleased(app, 'app-timeout');
});

test('应用就绪等待期间仍可通过 Esc 跳过', () => {
  const app = boot({ appReady: false });
  app.videos[0].emit('ended');
  app.document.emit('keydown', { key: 'Escape' });
  assertReleased(app, 'skipped');
});

test('Esc 跳过并拦截快捷键，其他按键不打断动画', () => {
  const app = boot();
  app.document.emit('keydown', { key: 'Enter' });
  assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
  const event = app.document.emit('keydown', { key: 'Escape' });
  assert.equal(event.defaultPrevented, true);
  assert.equal(event.stopped, true);
  assertReleased(app, 'skipped');
});

test('跳过提示仅显示英文文本，点击不打断动画', () => {
  const app = boot();
  const hint = app.layer.children[1];
  assert.equal(hint.tagName, 'span');
  assert.equal(hint.className, 'skip-hint');
  assert.equal(hint.textContent, 'Press Esc to skip');
  assert.equal(app.layer.children.some(child => child.tagName === 'button'), false);
  hint.emit('click');
  assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
  assert.equal(app.videos[0].pauseCalls, 0);
  app.document.emit('keydown', { key: 'Escape' });
  assertReleased(app, 'skipped');
});

test('媒体错误释放动画', () => {
  const app = boot();
  app.videos[0].emit('error');
  assertReleased(app, 'media-error');
});

test('play Promise 拒绝后释放动画', async () => {
  const app = boot({ rejectPlay: true });
  await Promise.resolve();
  assertReleased(app, 'playback-error');
});

test('默认视频超过 15 秒后释放动画，不会在十秒片长内提前退出', () => {
  const app = boot();
  app.advance(14999);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
  app.advance(1);
  assertReleased(app, 'timeout');
});

test('应用视频参数，并为慢速或较长视频延长超时', () => {
  for (const [duration, speed, timeout] of [[4, 0.5, 12000], [12.25, 1, 17000], [30, 0.5, 64000], [4, 2, 8000]]) {
    const app = boot({ settings: { duration, speed, brightness: 1.2, contrast: 0.8, saturation: 0, fit: 'contain' } });
    assert.equal(app.videos[0].playbackRate, speed);
    assert.equal(app.videos[0].defaultPlaybackRate, speed);
    assert.equal(app.videos[0].style.filter, 'brightness(1.2) contrast(0.8) saturate(0)');
    assert.equal(app.videos[0].style.objectFit, 'contain');
    app.advance(timeout - 1);
    assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
    app.advance(1);
    assertReleased(app, 'timeout');
  }
});

test('隐藏窗口等到可见后播放并开始超时计时', () => {
  const app = boot({ hidden: true });
  app.advance(20000);
  assert.equal(app.videos[0].playCalls, 0);
  assert.equal(app.timers.size, 0);
  app.document.hidden = false;
  app.document.emit('visibilitychange');
  assert.equal(app.videos[0].playCalls, 1);
  app.advance(14999);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
  app.advance(1);
  assertReleased(app, 'timeout');
});

test('减少动态效果偏好直接跳过且不播放', () => {
  const app = boot({ reduced: true });
  assert.equal(app.videos[0].playCalls, 0);
  assertReleased(app, 'reduced-motion');
});

test('body 已存在即播放，不等待 DOMContentLoaded', () => {
  const app = boot({ loading: true });
  assert.ok(app.layer);
  assert.equal(app.videos[0].playCalls, 1);
  assert.equal(app.document.count('DOMContentLoaded'), 0);
  assert.equal(app.observers.length, 0);
  app.videos[0].emit('ended');
  assertReleased(app, 'ended');
});

test('body 延迟出现时等待观察器，并保留 currentScript 的原始资源地址', () => {
  const app = boot({ loading: true, bodyPresent: false, scriptSrc: 'file:///app/custom-assets/codex-boot.js' });
  assert.equal(app.layer, undefined);
  assert.equal(app.observers.length, 1);
  assert.equal(app.observers[0].active, true);
  app.notifyMutation();
  assert.equal(app.videos.length, 0);
  app.document.currentScript = null;
  app.attachBody();
  assert.equal(app.videos[0].src, 'file:///app/custom-assets/codex-boot.webm');
  assert.equal(app.videos[0].playCalls, 1);
  assert.equal(app.observers[0].active, false);
  app.notifyMutation();
  assert.equal(app.videos.length, 1);
  app.videos[0].emit('ended');
  assertReleased(app, 'ended');
});

test('React 替换根节点内容不移除独立动画遮罩', () => {
  const app = boot();
  const layer = app.layer;
  app.root.replaceChildren(new Element('main'));
  assert.equal(app.layer, layer);
  assert.equal(layer.parent, app.document.body);
  assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
  app.videos[0].emit('ended');
  assertReleased(app, 'ended');
});
