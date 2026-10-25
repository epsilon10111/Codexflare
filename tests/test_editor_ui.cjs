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
  const fit = [new Element('value="cover" checked'), new Element('value="contain"')];
  const main = new Element();
  const settings = { video: 'default', speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover' };
  const state = {
    settings,
    videos: [{ id: 'default', name: '默认启动动画', duration: 4, width: 1920, height: 1080, url: '/media/default' }],
    installation: { active: false, available: true, running: false },
    token: 'test-token',
    ...options.state,
  };
  const requests = [];
  const document = {
    getElementById: id => nodes[id],
    createElement: () => new Element(),
    querySelector: selector => selector === 'main' ? main : fit.find(input => input.checked),
    querySelectorAll: selector => selector === '[data-edit]' ? [nodes['video-source'], nodes['upload-button']] : fit,
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
  return { nodes, fit, requests, settings, state };
}

test('初始静止预览，参数即时更新并标记未保存', async () => {
  const { nodes, fit } = await setup();
  assert.equal(nodes.preview.src, '/media/default');
  assert.equal(nodes.preview.plays, 0);
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
  const file = new VideoFile(video.name);
  nodes['video-file'].files = [file];
  nodes['video-file'].emit('change');
  await flush();
  const request = requests.find(request => request.url === '/api/upload');
  assert.equal(request.body, file);
  assert.equal(request.headers['Content-Type'], 'application/octet-stream');
  assert.equal(request.headers['X-Filename'], encodeURIComponent(file.name));
  assert.equal(nodes.contrast.value, 1.5);
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
