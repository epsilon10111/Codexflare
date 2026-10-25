const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../ui/index.html'), 'utf8');
const script = fs.readFileSync(path.join(__dirname, '../ui/editor.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

class Element {
  constructor(attributes = '') {
    this.listeners = {};
    this.attributes = {};
    this.style = { setProperty(name, value) { this[name] = value; } };
    this.classList = { toggle() {} };
    this.value = attributes.match(/\bvalue="([^"]*)"/)?.[1] || '';
    this.min = attributes.match(/\bmin="([^"]*)"/)?.[1];
    this.max = attributes.match(/\bmax="([^"]*)"/)?.[1];
    this.checked = /\bchecked\b/.test(attributes);
    this.hidden = /\bhidden\b/.test(attributes);
    this.children = [];
    this.paused = true;
    this.plays = 0;
  }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  emit(name, event = {}) { for (const listener of this.listeners[name] || []) listener(event); }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name]; }
  focus() { this.focused = true; }
  get value() { return this._value; }
  set value(value) { this._value = this.isSelect && !this.children.some(child => child.value === value) ? '' : value; }
  replaceChildren(...children) { this.children = children; this.value = children[0]?.value || ''; }
  click() { this.emit('click'); }
  load() {}
  pause() { this.paused = true; }
  play() { this.plays++; this.paused = false; return Promise.resolve(); }
}

class VideoFile {
  constructor(name, size = 1024) { this.name = name; this.size = size; }
}

async function setup(options = {}) {
  const nodes = Object.fromEntries([...html.matchAll(/<[a-z][\w-]*\b([^>]*\bid="([^"]+)"[^>]*)>/g)].map(match => [match[2], new Element(match[1])]));
  nodes['video-source'].isSelect = nodes['background-source'].isSelect = true;
  nodes['window-mode'].isSelect = true;
  const modeOptions = html.match(/<select id="window-mode"[^>]*>([\s\S]*?)<\/select>/)[1];
  nodes['window-mode'].replaceChildren(...[...modeOptions.matchAll(/<option ([^>]+)>/g)].map(match => new Element(match[1])));
  if (options.resetMediaMute) nodes.preview.load = () => { nodes.preview.muted = false; };
  const fit = [new Element('value="cover" checked'), new Element('value="contain"')];
  const main = new Element();
  const settings = { video: 'default', speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover' };
  const state = {
    settings,
    videos: [{ id: 'default', name: '默认启动动画', duration: 4, width: 1920, height: 1080, url: '/media/default' }],
    images: [{ id: 'default', name: 'default1', width: 7296, height: 4096, url: '/background/default' },
             { id: 'default2', name: 'default2', width: 7296, height: 4096, url: '/background/default2' }],
    installation: { active: false, available: true, running: false },
    token: 'test-token',
    ...options.state,
  };
  const requests = [];
  const document = {
    getElementById: id => nodes[id],
    createElement: () => new Element(),
    querySelector: selector => selector === 'main' ? main : fit.find(input => input.checked),
    querySelectorAll: selector => selector === '[data-edit]' ? [nodes['video-source'], nodes['upload-button'], nodes['background-source'], nodes['background-upload-button'], nodes['window-mode'], nodes['toggle-mute']] : fit,
  };
  const context = {
    document,
    window: new Element(),
    File: VideoFile,
    fetch: async (url, request) => {
      requests.push({ url, ...request });
      const result = url === '/api/state' ? state : await options.write(url, request);
      return { ok: !result.error, status: result.error ? 400 : 200, json: async () => structuredClone(result) };
    },
  };
  vm.runInNewContext(script, context, { filename: 'editor.js' });
  await flush();
  return { nodes, fit, requests, settings, state, window: context.window };
}

test('初始静止预览，参数即时更新并标记未保存', async () => {
  const { nodes, fit } = await setup();
  assert.equal(nodes.preview.src, '/media/default');
  assert.equal(nodes.preview.plays, 0);
  assert.equal(nodes.preview.muted, true);
  assert.equal(nodes['background-source'].value, 'default');
  assert.equal(nodes['background-image'].attributes.src, '/background/default');
  assert.equal(nodes['background-source'].children[0].textContent, 'default1 · 内置');
  assert.equal(nodes.save.disabled, true);
  nodes.preview.duration = 4;
  nodes.preview.emit('loadedmetadata');
  assert.equal(nodes.preview.currentTime, .7);
  nodes.speed.value = '1.5';
  nodes.brightness.value = '.5';
  nodes.brightness.emit('input');
  assert.equal(nodes.preview.playbackRate, 1.5);
  assert.match(nodes.preview.style.filter, /brightness\(0.5\)/);
  assert.equal(nodes['brightness-value'].textContent, '50%');
  assert.equal(nodes.save.disabled, false);
  fit[0].checked = false;
  fit[1].checked = true;
  fit[1].emit('change');
  assert.equal(nodes.preview.style.objectFit, 'contain');
  nodes.reset.click();
  assert.equal(nodes.preview.playbackRate, 1);
  assert.equal(nodes.save.disabled, true);
});

test('静音按钮同步预览、刷新和保存，重置画面保留声音偏好', async () => {
  const { nodes, requests, window } = await setup({ write: (url, request) => ({ settings: JSON.parse(request.body) }) });
  assert.equal(nodes['toggle-mute'].attributes['aria-pressed'], 'true');
  nodes['toggle-mute'].click();
  assert.equal(nodes.preview.muted, false);
  assert.equal(nodes['mute-label'].textContent, '声音开启');
  assert.equal(nodes['toggle-mute'].attributes['aria-pressed'], 'false');
  assert.equal(nodes.save.disabled, false);
  let prevented = false;
  window.emit('beforeunload', { preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  nodes.reset.click();
  nodes['refresh-state'].click();
  await flush();
  assert.equal(nodes.preview.muted, false);
  assert.equal(nodes.save.disabled, false);
  nodes.save.click();
  assert.equal(nodes['toggle-mute'].disabled, true);
  await flush();
  assert.equal(JSON.parse(requests.at(-1).body).muted, false);
  assert.equal(nodes['toggle-mute'].disabled, false);
  assert.equal(nodes.save.disabled, true);
  nodes['toggle-mute'].click();
  assert.equal(nodes.preview.muted, true);
  assert.equal(nodes['mute-label'].textContent, '静音');
  assert.equal(nodes.save.disabled, false);
});

test('载入有声配置并在应用时携带声音偏好', async () => {
  const settings = { video: 'default', speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', muted: false };
  const { nodes, requests } = await setup({ state: { settings }, write: (url, request) => ({ settings: JSON.parse(request.body) }) });
  assert.equal(nodes.preview.muted, false);
  assert.equal(nodes['toggle-mute'].attributes['aria-pressed'], 'false');
  assert.equal(nodes.save.disabled, true);
  nodes.install.click();
  await flush();
  assert.equal(JSON.parse(requests.at(-1).body).muted, false);
});

test('媒体载入或音量事件重置静音属性时不会覆盖保存的偏好', async () => {
  const video = { id: 'e'.repeat(64), name: 'next.mp4', duration: 3, width: 320, height: 180, url: '/media/next' };
  const { nodes, requests } = await setup({ resetMediaMute: true, write: (url, request) =>
    url === '/api/upload' ? { video } : { settings: JSON.parse(request.body) } });
  assert.equal(nodes.preview.muted, true);
  assert.equal(nodes.preview.defaultMuted, true);
  nodes.preview.muted = false;
  nodes.preview.emit('volumechange');
  assert.equal(nodes.preview.muted, true);
  assert.equal(nodes.save.disabled, true);
  nodes['video-file'].files = [new VideoFile(video.name)];
  nodes['video-file'].emit('change');
  await flush();
  assert.equal(nodes.preview.muted, true);
  nodes.preview.muted = false;
  nodes.preview.emit('loadedmetadata');
  assert.equal(nodes.preview.muted, true);
  nodes.save.click();
  await flush();
  assert.equal(JSON.parse(requests.at(-1).body).muted, true);
  nodes['toggle-mute'].click();
  nodes.preview.muted = true;
  nodes.preview.emit('volumechange');
  assert.equal(nodes.preview.muted, false);
  assert.equal(nodes.preview.defaultMuted, false);
});

test('旧配置默认恢复窗口，切换方式支持刷新、重置与保存', async () => {
  const { nodes, requests, state, window } = await setup({ write: (url, request) => ({ settings: JSON.parse(request.body) }) });
  assert.equal(nodes['window-mode'].value, 'restore');
  assert.equal(nodes.save.disabled, true);
  assert.deepEqual(nodes['window-mode'].children.map(option => option.value), ['restore', 'fullscreen', 'centered']);
  nodes['window-mode'].value = 'centered';
  nodes['window-mode'].emit('change');
  assert.equal(nodes.save.disabled, false);
  assert.match(nodes['window-mode-hint'].textContent, /1100 × 760/);
  let prevented = false;
  window.emit('beforeunload', { preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  nodes.reset.click();
  nodes['background-tab'].click();
  nodes.reset.click();
  assert.equal(nodes['window-mode'].value, 'centered');
  assert.equal(nodes['window-mode'].hidden, false);
  state.installation.running = true;
  nodes['refresh-state'].click();
  await flush();
  assert.equal(nodes['window-mode'].value, 'centered');
  assert.equal(nodes.save.disabled, false);
  nodes.save.click();
  assert.equal(nodes['window-mode'].disabled, true);
  await flush();
  assert.equal(JSON.parse(requests.at(-1).body).windowMode, 'centered');
  assert.equal(nodes['window-mode'].disabled, false);
  assert.equal(nodes.save.disabled, true);
});

test('载入已保存全屏方式，应用请求包含修改后的启动窗口', async () => {
  const settings = { video: 'default', speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', windowMode: 'fullscreen' };
  const { nodes, requests } = await setup({ state: { settings }, write: (url, request) => ({ settings: JSON.parse(request.body) }) });
  assert.equal(nodes['window-mode'].value, 'fullscreen');
  assert.equal(nodes.save.disabled, true);
  nodes['window-mode'].value = 'restore';
  nodes['window-mode'].emit('change');
  nodes.install.click();
  await flush();
  assert.equal(requests.at(-1).url, '/api/install');
  assert.equal(JSON.parse(requests.at(-1).body).windowMode, 'restore');
  assert.equal(nodes.save.disabled, true);
});

test('保存期间阻止重复写请求，成功后清除草稿状态', async () => {
  let complete;
  const { nodes, requests } = await setup({ write: () => new Promise(resolve => { complete = resolve; }) });
  nodes.speed.value = '1.2';
  nodes.speed.emit('input');
  nodes.save.click();
  nodes.save.click();
  assert.equal(requests.filter(request => request.method === 'POST').length, 1);
  assert.equal(nodes.save.disabled, true);
  assert.equal(nodes['busy-message'].hidden, false);
  const request = requests.at(-1);
  assert.equal(request.headers['X-Editor-Token'], 'test-token');
  const settings = JSON.parse(request.body);
  assert.equal(settings.speed, 1.2);
  complete({ settings });
  await flush();
  assert.equal(nodes['busy-message'].hidden, true);
  assert.equal(nodes.save.disabled, true);
  assert.equal(nodes['save-state'].textContent, '设置已保存');
});

test('上传原始文件并保留参数草稿，文件名仅作为文本', async () => {
  const video = { id: 'a'.repeat(64), name: '<img src=x onerror=alert(1)>.mp4', duration: 8, width: 1280, height: 720, url: '/media/custom' };
  const { nodes, requests } = await setup({ write: () => ({ video }) });
  nodes.contrast.value = '1.5';
  nodes.contrast.emit('input');
  nodes['toggle-mute'].click();
  const file = new VideoFile(video.name);
  nodes['video-file'].files = [file];
  nodes['video-file'].emit('change');
  await flush();
  const request = requests.find(request => request.url === '/api/upload');
  assert.equal(request.body, file);
  assert.equal(request.headers['Content-Type'], 'application/octet-stream');
  assert.equal(request.headers['X-Filename'], encodeURIComponent(file.name));
  assert.equal(nodes.contrast.value, 1.5);
  assert.equal(nodes.preview.muted, false);
  assert.equal(nodes['video-source'].value, video.id);
  assert.equal(nodes['video-source'].children.at(-1).textContent, video.name);
  assert.equal(nodes['video-source'].children.at(-1).innerHTML, undefined);
  assert.equal(nodes.save.disabled, false);
  nodes['video-file'].files = [new VideoFile('large.mp4', 101 * 1024 * 1024)];
  nodes['video-file'].emit('change');
  assert.match(nodes['error-text'].textContent, /100 MiB/);
  assert.equal(requests.filter(request => request.url === '/api/upload').length, 1);
});

test('配置恢复警告仍可保存，运行状态刷新保留未保存参数', async () => {
  const { nodes, state } = await setup({
    state: { warning: '配置已损坏，请保存默认值以恢复。' },
    write: (url, request) => ({ settings: JSON.parse(request.body) }),
  });
  assert.equal(nodes.save.disabled, false);
  assert.match(nodes.notice.textContent, /配置已损坏/);
  nodes.save.click();
  await flush();
  assert.equal(nodes.save.disabled, true);
  state.warning = '';
  nodes.speed.value = '1.8';
  nodes.speed.emit('input');
  state.installation.running = true;
  nodes['refresh-state'].click();
  await flush();
  assert.equal(nodes.speed.value, 1.8);
  assert.equal(nodes.install.disabled, true);
  assert.equal(nodes.save.disabled, false);
});


test('背景上传保留动画草稿，参数预览与保存共用同一设置', async () => {
  const image = { id: 'b'.repeat(64), name: '<img src=x>.png', width: 1280, height: 720, url: '/background/custom' };
  const { nodes, requests, window } = await setup({ write: (url, request) => url === '/api/background/upload' ? { image } : { settings: JSON.parse(request.body) } });
  nodes.speed.value = '1.4';
  nodes.speed.emit('input');
  nodes['background-tab'].click();
  assert.equal(nodes['animation-preview'].hidden, true);
  assert.equal(nodes['background-preview-card'].hidden, false);
  assert.equal(nodes['background-tab'].attributes['aria-selected'], 'true');
  const file = new VideoFile(image.name);
  nodes['background-file'].files = [file];
  nodes['background-file'].emit('change');
  await flush();
  const uploaded = requests.at(-1);
  assert.equal(uploaded.url, '/api/background/upload');
  assert.equal(uploaded.body, file);
  assert.equal(uploaded.headers['Content-Type'], 'image/png');
  assert.equal(uploaded.headers['X-Filename'], encodeURIComponent(file.name));
  assert.equal(nodes['background-source'].value, image.id);
  assert.equal(nodes['background-source'].children.at(-1).textContent, image.name);
  assert.equal(nodes['background-image'].attributes.src, image.url);
  assert.equal(nodes.speed.value, 1.4);
  nodes['background-opacity'].value = '.32';
  nodes['background-position'].value = '85';
  nodes['background-scale'].value = '90';
  nodes['background-opacity'].emit('input');
  assert.equal(nodes['background-image'].style.opacity, .32);
  assert.equal(nodes['background-image'].style.left, '40%');
  assert.equal(nodes['background-image'].style.width, '90%');
  assert.equal(nodes['background-opacity-value'].textContent, '32%');
  let prevented = false;
  window.emit('beforeunload', { preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  nodes.save.click();
  await flush();
  const saved = JSON.parse(requests.at(-1).body);
  assert.deepEqual(saved.background, { enabled: true, image: image.id, opacity: .32, position: 85, scale: 90 });
  assert.equal(saved.speed, 1.4);
  assert.equal(nodes.save.disabled, true);
  nodes['background-enabled'].checked = false;
  nodes['background-enabled'].emit('change');
  assert.equal(nodes['background-image'].hidden, true);
  assert.equal(nodes['background-opacity'].disabled, true);
  assert.equal(nodes.save.disabled, false);
});

test('两张内置背景可切换，第二张选择经过刷新与保存保留', async () => {
  const { nodes, requests, state } = await setup({ write: (url, request) => {
    state.settings = JSON.parse(request.body);
    return { settings: state.settings };
  } });
  assert.deepEqual(nodes['background-source'].children.map(option => option.textContent), ['default1 · 内置', 'default2 · 内置']);
  nodes['background-tab'].click();
  nodes['background-source'].value = 'default2';
  nodes['background-source'].emit('change');
  assert.equal(nodes['background-image'].attributes.src, '/background/default2');
  assert.equal(nodes.save.disabled, false);
  nodes['refresh-state'].click();
  await flush();
  assert.equal(nodes['background-source'].value, 'default2');
  assert.equal(nodes.save.disabled, false);
  nodes.save.click();
  await flush();
  assert.equal(JSON.parse(requests.at(-1).body).background.image, 'default2');
  nodes['refresh-state'].click();
  await flush();
  assert.equal(nodes['background-source'].value, 'default2');
  assert.equal(nodes.save.disabled, true);
  nodes['background-source'].value = 'default';
  nodes['background-source'].emit('change');
  assert.equal(nodes['background-image'].attributes.src, '/background/default');
  assert.equal(nodes.save.disabled, false);
});

test('背景刷新保留选择、重置只作用于当前页，并支持键盘页签', async () => {
  const image = { id: 'legacy', name: '当前背景', width: 7296, height: 4096, url: '/background/legacy' };
  const settings = { video: 'default', speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', background: { image: 'legacy' } };
  const { nodes, state } = await setup({ state: { settings, images: [image] } });
  assert.equal(nodes['background-image'].attributes.src, image.url);
  assert.equal(nodes.save.disabled, true);
  nodes.speed.value = '1.7';
  nodes['background-opacity'].value = '.4';
  nodes['background-tab'].click();
  nodes['background-opacity'].emit('input');
  state.installation.running = true;
  nodes['refresh-state'].click();
  await flush();
  assert.equal(nodes['background-opacity'].value, .4);
  assert.equal(nodes.install.disabled, true);
  nodes.reset.click();
  assert.equal(nodes['background-opacity'].value, .18);
  assert.equal(nodes.speed.value, 1.7);
  nodes['background-tab'].emit('keydown', { key: 'ArrowLeft', preventDefault() {} });
  assert.equal(nodes['animation-tab'].focused, true);
  assert.equal(nodes['background-preview-card'].hidden, true);
  nodes.reset.click();
  assert.equal(nodes.save.disabled, true);
});

test('背景上传错误留在编辑器内，未保存的选择不会被覆盖', async () => {
  const { nodes, requests } = await setup({ write: () => ({ error: 'PNG 文件已损坏' }) });
  nodes['background-tab'].click();
  for (const [file, error] of [[new VideoFile('large.png', 41 * 1024 * 1024), /40 MiB/], [new VideoFile('photo.jpg'), /PNG/], [new VideoFile('empty.png', 0), /为空/]]) {
    nodes['background-file'].files = [file];
    nodes['background-file'].emit('change');
    assert.match(nodes['error-text'].textContent, error);
  }
  assert.equal(requests.filter(request => request.method === 'POST').length, 0);
  nodes['background-file'].files = [new VideoFile('broken.png')];
  nodes['background-file'].emit('change');
  await flush();
  assert.match(nodes['error-text'].textContent, /已损坏/);
  assert.equal(nodes['background-source'].value, 'default');
  assert.equal(nodes['background-upload-button'].disabled, false);
  assert.equal(nodes['busy-message'].hidden, true);
});

test('缺失背景保留有效标识和占位选项，关闭背景后仍可保存', async () => {
  const missing = 'c'.repeat(64);
  const settings = { video: 'default', speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', background: { enabled: false, image: missing, opacity: .18, position: 80, scale: 70 } };
  const { nodes, requests } = await setup({
    state: { settings, images: [], warning: '背景暂不可用，请重新导入。' },
    write: (url, request) => ({ settings: JSON.parse(request.body) }),
  });
  assert.equal(nodes['background-source'].value, missing);
  assert.match(nodes['background-source'].children.find(option => option.value === missing).textContent, /图片不可用/);
  assert.match(nodes['background-placeholder'].textContent, /图片不可用，请重新导入/);
  assert.equal(nodes['background-image'].hidden, true);
  nodes.speed.value = '1.3';
  nodes.speed.emit('input');
  nodes['refresh-state'].click();
  await flush();
  assert.equal(nodes['background-source'].value, missing);
  assert.equal(nodes.speed.value, 1.3);
  nodes.save.click();
  await flush();
  const saved = JSON.parse(requests.at(-1).body);
  assert.equal(saved.background.image, missing);
  assert.equal(saved.background.enabled, false);
  assert.equal(saved.speed, 1.3);
  assert.equal(nodes.save.disabled, true);
});

test('刷新时图片消失会显示不可用占位并保留草稿', async () => {
  const image = { id: 'd'.repeat(64), name: '已删除.png', width: 640, height: 360, url: '/background/removed' };
  const settings = { video: 'default', speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', background: { enabled: true, image: image.id, opacity: .18, position: 80, scale: 70 } };
  const { nodes, state } = await setup({ state: { settings, images: [image] } });
  nodes['background-opacity'].value = '.3';
  nodes['background-opacity'].emit('input');
  state.images = [];
  state.settings.background.enabled = false;
  state.warning = '背景暂不可用，请重新导入。';
  nodes['refresh-state'].click();
  await flush();
  assert.equal(nodes['background-source'].value, image.id);
  assert.equal(nodes['background-opacity'].value, .3);
  assert.equal(nodes['background-image'].hidden, true);
  assert.match(nodes['background-name'].textContent, /图片不可用/);
  assert.equal(nodes.save.disabled, false);
});
