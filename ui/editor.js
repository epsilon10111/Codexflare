(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const preview = byId('preview');
  const source = byId('video-source');
  const parameterNames = ['speed', 'brightness', 'contrast', 'saturation'];
  const settingsKeys = ['video', ...parameterNames, 'fit'];
  let saved;
  let token;
  let videos = [];
  let installation = {};
  let busy = false;
  let ready = false;
  let needsRepair = false;

  const draft = () => ({
    video: source.value,
    ...Object.fromEntries(parameterNames.map(name => [name, Number(byId(name).value)])),
    fit: document.querySelector('input[name="fit"]:checked').value,
  });
  const isDirty = () => ready && (needsRepair || settingsKeys.some(key => draft()[key] !== saved[key]));
  const selectedVideo = () => videos.find(video => video.id === source.value);
  const showError = message => {
    byId('error-text').textContent = message;
    byId('error-banner').hidden = false;
  };
  const notify = message => {
    byId('notice').textContent = message;
    byId('notice').hidden = !message;
  };

  function updateControls() {
    document.querySelectorAll('[data-edit]').forEach(element => { element.disabled = !ready || busy; });
    byId('adjustments').disabled = !ready || busy;
    byId('save').disabled = !ready || busy || !isDirty();
    byId('install').disabled = !ready || busy || !installation.available || installation.running;
    byId('restore').disabled = !ready || busy || !installation.active;
    byId('retry-state').disabled = busy;
    byId('refresh-state').disabled = busy;
    byId('save-state').textContent = !ready ? '尚未连接' : isDirty() ? '有未保存的更改' : '设置已保存';
    byId('save-state').classList.toggle('dirty', isDirty());
  }

  function setBusy(message) {
    busy = Boolean(message);
    byId('busy-message').hidden = !busy;
    byId('busy-text').textContent = message;
    byId('adjustments').setAttribute('aria-busy', String(busy));
    updateControls();
  }

  function showInstallation() {
    const title = !installation.available ? '当前版本暂不支持应用' : installation.running ? '定制版 Codex 正在运行' : installation.active ? '定制启动入口已启用' : '使用原版启动入口';
    byId('installation-heading').textContent = title;
    byId('installation-message').textContent = installation.message || (installation.running ? '请先保存工作并正常退出定制版，再应用新的设置。' : '应用后，通过桌面菜单启动即可看到动画。');
    byId('installation-indicator').className = `installation-indicator${!installation.available || installation.running ? ' warning' : installation.active ? ' active' : ''}`;
  }

  function showMetadata() {
    const video = selectedVideo();
    if (!video) return;
    byId('video-name').textContent = video.name;
    byId('video-name').title = video.name;
    const duration = Number(video.duration);
    byId('video-meta').textContent = `${video.width} × ${video.height} · 原片 ${duration.toFixed(1)} 秒 · 播放 ${(duration / Number(byId('speed').value)).toFixed(1)} 秒`;
  }

  function applyPreview() {
    const settings = draft();
    preview.playbackRate = settings.speed;
    preview.style.filter = `brightness(${settings.brightness}) contrast(${settings.contrast}) saturate(${settings.saturation})`;
    preview.style.objectFit = settings.fit;
    parameterNames.forEach(name => {
      const input = byId(name);
      const value = Number(input.value);
      const label = name === 'speed' ? `${value.toFixed(1)}×` : `${Math.round(value * 100)}%`;
      byId(`${name}-value`).textContent = label;
      input.setAttribute('aria-valuetext', label);
      input.style.setProperty('--fill', `${(value - Number(input.min)) / (Number(input.max) - Number(input.min)) * 100}%`);
    });
    byId('fit-hint').textContent = settings.fit === 'cover' ? '保持比例铺满窗口，超出部分会被裁切。' : '保留完整画面，空余区域显示深色背景。';
    showMetadata();
    updateControls();
  }

  function setSettings(settings) {
    source.value = settings.video;
    parameterNames.forEach(name => { byId(name).value = settings[name]; });
    document.querySelectorAll('input[name="fit"]').forEach(input => { input.checked = input.value === settings.fit; });
    applyPreview();
  }

  function renderSources() {
    source.replaceChildren(...videos.map(video => {
      const option = document.createElement('option');
      option.value = video.id;
      option.textContent = video.id === 'default' ? `${video.name} · 内置` : video.name;
      return option;
    }));
  }

  function loadVideo() {
    const video = selectedVideo();
    if (!video) return;
    preview.pause();
    byId('media-error').hidden = true;
    byId('preview-placeholder').hidden = false;
    byId('toggle-play').disabled = true;
    byId('restart').disabled = true;
    byId('playback-state').textContent = '载入中';
    preview.src = video.url;
    preview.load();
    applyPreview();
  }

  async function request(path, body, headers = {}) {
    let response;
    try {
      response = await fetch(path, {
        method: body === undefined ? 'GET' : 'POST',
        headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-Editor-Token': token, ...headers },
        body: body === undefined ? undefined : body instanceof File ? body : JSON.stringify(body),
        cache: 'no-store',
      });
    } catch {
      throw new Error('无法连接本机编辑器。请确认编辑器仍在运行，然后重试。');
    }
    let result;
    try { result = await response.json(); }
    catch { throw new Error('本机编辑器返回了无法读取的响应，请重新连接后重试。'); }
    if (!response.ok) throw new Error(result.error || `操作失败（${response.status}），请重试。`);
    return result;
  }

  async function loadState(preserveDraft = false) {
    const current = ready && preserveDraft ? draft() : null;
    const currentVideo = current && selectedVideo();
    const state = await request('/api/state');
    saved = state.settings;
    needsRepair = Boolean(state.warning);
    token = state.token;
    videos = state.videos;
    if (currentVideo && !videos.some(video => video.id === currentVideo.id)) videos.push(currentVideo);
    installation = state.installation;
    renderSources();
    ready = true;
    setSettings(current || saved);
    showInstallation();
    byId('retry-state').hidden = true;
    if (state.warning) notify(state.warning);
    if (!current) loadVideo();
  }

  async function connect() {
    if (busy) return;
    byId('error-banner').hidden = true;
    setBusy('正在连接本机编辑器…');
    try { await loadState(ready); }
    catch (error) {
      showError(error.message);
      byId('retry-state').hidden = false;
    } finally { setBusy(''); }
  }

  async function write(path, body, message, headers) {
    if (busy || !ready) return;
    byId('error-banner').hidden = true;
    notify('');
    setBusy(message);
    try {
      const result = await request(path, body, headers);
      if (result.settings) {
        needsRepair = false;
        saved = result.settings;
        setSettings(saved);
      }
      if (result.installation) {
        installation = result.installation;
        showInstallation();
      }
      if (result.video) {
        const current = draft();
        videos = videos.filter(video => video.id !== result.video.id);
        videos.push(result.video);
        renderSources();
        setSettings({ ...current, video: result.video.id });
        loadVideo();
      }
      const messages = {
        '/api/settings': '设置已保存。点击“应用到 Codex”后，新的设置才会用于启动动画。',
        '/api/install': '已应用。请保存工作，完全退出 Codex 后重新打开，查看新的启动动画。',
        '/api/uninstall': '已恢复原版启动入口。下次从桌面菜单启动时使用原版 Codex。',
        '/api/upload': '视频已导入，可继续调整预览。点击“保存设置”保留本次选择。',
      };
      notify(result.message || messages[path]);
    } catch (error) {
      showError(error.message);
      if (path === '/api/install') {
        try { await loadState(true); } catch { byId('retry-state').hidden = false; }
      }
    } finally { setBusy(''); }
  }

  async function playPreview(restart = false) {
    if (restart || preview.ended) preview.currentTime = 0;
    try {
      await preview.play();
      byId('media-error').hidden = true;
    } catch {
      byId('media-error').hidden = false;
    }
  }

  function updatePlayback() {
    const paused = preview.paused || preview.ended;
    byId('play-label').textContent = paused ? '播放' : '暂停';
    byId('toggle-play').setAttribute('aria-label', paused ? '播放预览' : '暂停预览');
    byId('play-icon').setAttribute('d', paused ? 'm9 5 11 7-11 7Z' : 'M8 5v14M16 5v14');
    byId('playback-state').textContent = preview.ended ? '播放完毕' : paused ? '已暂停' : '播放中';
  }

  parameterNames.forEach(name => byId(name).addEventListener('input', applyPreview));
  document.querySelectorAll('input[name="fit"]').forEach(input => input.addEventListener('change', applyPreview));
  source.addEventListener('change', loadVideo);
  byId('reset').addEventListener('click', () => {
    setSettings({ video: source.value, speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover' });
    notify('画面与播放参数已重置，当前视频保持不变。');
  });
  byId('toggle-play').addEventListener('click', () => preview.paused ? playPreview() : preview.pause());
  byId('restart').addEventListener('click', () => playPreview(true));
  byId('reload-video').addEventListener('click', loadVideo);
  ['play', 'pause', 'ended'].forEach(event => preview.addEventListener(event, updatePlayback));
  preview.addEventListener('loadedmetadata', () => {
    preview.playbackRate = Number(byId('speed').value);
    // 默认片头是黑色，静止展示稍后的画面便于调节。
    if (Number.isFinite(preview.duration)) preview.currentTime = Math.min(.7, preview.duration / 4);
  });
  preview.addEventListener('loadeddata', () => {
    byId('preview-placeholder').hidden = true;
    byId('media-error').hidden = true;
    byId('toggle-play').disabled = false;
    byId('restart').disabled = false;
    updatePlayback();
  });
  preview.addEventListener('error', () => {
    byId('preview-placeholder').hidden = true;
    byId('media-error').hidden = false;
    byId('toggle-play').disabled = true;
    byId('restart').disabled = true;
    byId('playback-state').textContent = '预览不可用';
  });
  byId('upload-button').addEventListener('click', () => byId('video-file').click());
  byId('video-file').addEventListener('change', () => {
    const file = byId('video-file').files[0];
    byId('video-file').value = '';
    if (!file || busy) return;
    if (file.size > 100 * 1024 * 1024) {
      showError('视频超过 100 MiB，请选择更小的视频文件。');
      return;
    }
    if (!file.size) {
      showError('这个视频文件为空，请重新选择。');
      return;
    }
    write('/api/upload', file, '正在导入并转换视频，可能需要几十秒，请保持窗口打开…', {
      'Content-Type': 'application/octet-stream',
      'X-Filename': encodeURIComponent(file.name),
    });
  });
  byId('save').addEventListener('click', () => write('/api/settings', draft(), '正在保存设置…'));
  byId('install').addEventListener('click', () => write('/api/install', draft(), '正在生成并应用启动动画，请保持窗口打开…'));
  byId('restore').addEventListener('click', () => write('/api/uninstall', {}, '正在恢复原版启动入口…'));
  byId('retry-state').addEventListener('click', connect);
  byId('refresh-state').addEventListener('click', connect);
  window.addEventListener('beforeunload', event => {
    if (!isDirty() && !busy) return;
    event.preventDefault();
    event.returnValue = '';
  });
  connect();
})();
