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

function boot({ search = '?codexBootAnimation=1', hidden = false, reduced = false, loading = false, bodyPresent = true, rejectPlay = false, scriptSrc = 'file:///app/webview/assets/codex-boot.js', settings = null } = {}) {
  const document = new Events();
  document.documentElement = new Element('html');
  const body = new Element('body');
  document.body = bodyPresent ? body : null;
  if (bodyPresent) document.documentElement.append(body);
  const root = new Element('div');
  root.id = 'root';
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
  const context = {
    document, URL, URLSearchParams,
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
  };
  vm.runInNewContext(source.replace('/* CODEX_BOOT_SETTINGS */ null', JSON.stringify(settings)), context, { filename: 'boot.js' });
  return {
    document, root, videos, timers, observers,
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

test('Esc 跳过并拦截快捷键，其他按键不打断动画', () => {
  const app = boot();
  app.document.emit('keydown', { key: 'Enter' });
  assert.equal(app.document.documentElement.dataset.codexBoot, 'loading');
  const event = app.document.emit('keydown', { key: 'Escape' });
  assert.equal(event.defaultPrevented, true);
  assert.equal(event.stopped, true);
  assertReleased(app, 'skipped');
});

test('跳过按钮释放动画', () => {
  const app = boot();
  app.layer.children[1].emit('click');
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

test('播放超过 8 秒后释放动画', () => {
  const app = boot();
  app.advance(7999);
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
  app.advance(7999);
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
