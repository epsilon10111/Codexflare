(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const preview = byId('preview');
  const source = byId('video-source');
  const parameterNames = ['speed', 'brightness', 'contrast', 'saturation'];
  const backgroundNames = ['opacity', 'position', 'scale'];
  const backgroundDefaults = { enabled: true, image: 'default', opacity: .18, position: 80, scale: 70 };
  const settingsKeys = ['video', ...parameterNames, 'fit', 'muted', 'background', 'windowMode'];
  const normalizeSettings = settings => ({ muted: true, windowMode: 'restore', ...settings, background: { ...backgroundDefaults, ...settings.background } });
  let saved;
  let token;
  let videos = [];
  let images = [];
  let tab = 'animation';
  let installation = {};
  let busy = false;
  let ready = false;
  let needsRepair = false;
  let muted = true;
  let installationRefresh = null;

  const draft = () => ({
    video: source.value,
    ...Object.fromEntries(parameterNames.map(name => [name, Number(byId(name).value)])),
    fit: document.querySelector('input[name="fit"]:checked').value,
    muted,
    windowMode: byId('window-mode').value,
    background: {
      enabled: byId('background-enabled').checked, image: byId('background-source').value,
      ...Object.fromEntries(backgroundNames.map(name => [name, Number(byId(`background-${name}`).value)])),
    },
  });
  const isDirty = () => ready && (needsRepair || settingsKeys.some(key => JSON.stringify(draft()[key]) !== JSON.stringify(saved[key])));
  const selectedVideo = () => videos.find(video => video.id === source.value);
  const selectedImage = () => images.find(image => image.id === byId('background-source').value);
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
    byId('background-adjustments').disabled = !ready || busy;
    backgroundNames.forEach(name => { byId(`background-${name}`).disabled = !byId('background-enabled').checked || !selectedImage(); });
    byId('save').disabled = !ready || busy || !isDirty();
    byId('install').disabled = !ready || busy || !installation.available || (installation.running && installation.mode !== 'original');
    byId('restore').disabled = !ready || busy || !(installation.active || (installation.mode === 'original' && installation.pending));
    byId('retry-state').disabled = busy;
    byId('refresh-state').disabled = busy;
    byId('save-state').textContent = !ready ? '尚未连接' : isDirty() ? '有未保存的更改' : '设置已保存';
    byId('save-state').classList.toggle('dirty', isDirty());
    byId('window-mode-hint').textContent = {
      restore: '沿用 Codex 保存的窗口大小与位置。',
      fullscreen: '每次打开时铺满当前显示器，可退出全屏。',
      centered: '默认 1100 × 760，较小屏幕自动缩小并居中。',
    }[byId('window-mode').value];
  }

  function setBusy(message) {
    busy = Boolean(message);
    if (busy) installationRefresh = null;
    byId('busy-message').hidden = !busy;
    byId('busy-text').textContent = message;
    byId('adjustments').setAttribute('aria-busy', String(busy));
    updateControls();
  }

  function showInstallation() {
    const original = installation.mode === 'original';
    let title;
    if (original && installation.phase === 'failed') title = '应用未完成，请重试';
    else if (original && installation.pending) title = installation.running ? '已准备，等待 ChatGPT 退出' : '已准备，等待应用';
    else if (!installation.available) title = '当前无法应用';
    else if (original) title = installation.active ? '原 ChatGPT 图标已启用定制效果' : '使用原 ChatGPT 图标';
    else title = installation.running ? '定制版 Codex 正在运行' : installation.active ? '定制启动入口已启用' : '使用原版启动入口';
    byId('installation-heading').textContent = title;
    byId('installation-message').textContent = installation.message || (original ? '点击应用准备设置，退出 ChatGPT 后自动生效，下次仍从原图标启动。' : installation.running ? '请先保存工作。退出定制版 Codex 后刷新状态，再点击应用。' : '应用后，通过桌面菜单启动即可使用新的设置。');
    byId('installation-indicator').className = `installation-indicator${!installation.available || installation.pending || installation.phase === 'failed' || (installation.running && !original) ? ' warning' : installation.active ? ' active' : ''}`;
    byId('install-label').textContent = original ? '应用到 ChatGPT' : '应用到 Codex';
    byId('restore').textContent = original ? '恢复原版 ChatGPT' : '恢复原版入口';
    byId('apply-hint').textContent = original ? '点击应用准备设置；退出 ChatGPT 后自动生效，下次仍从原图标启动。' : '退出定制版 Codex 后返回本窗口，再点击应用。';
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
    preview.defaultMuted = settings.muted;
    preview.muted = settings.muted;
    byId('toggle-mute').setAttribute('aria-pressed', String(settings.muted));
    byId('toggle-mute').title = `${settings.muted ? '开启声音' : '静音'}，保存后用于开场动画`;
    byId('mute-label').textContent = settings.muted ? '静音' : '声音开启';
    byId('mute-icon').setAttribute('d', settings.muted ? 'm17 9 5 6m0-6-5 6' : 'M17 8a6 6 0 0 1 0 8M20 5a10 10 0 0 1 0 14');
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
    applyBackgroundPreview();
    updateControls();
  }

  function setSettings(settings) {
    settings = normalizeSettings(settings);
    renderImages(settings.background.image);
    byId('background-enabled').checked = settings.background.enabled;
    byId('background-source').value = settings.background.image;
    backgroundNames.forEach(name => { byId(`background-${name}`).value = settings.background[name]; });
    source.value = settings.video;
    muted = settings.muted;
    byId('window-mode').value = settings.windowMode;
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

  function renderImages(selected) {
    const choices = [...images];
    for (const id of [selected, saved?.background.image]) {
      if (id && !choices.some(image => image.id === id)) choices.push({ id, name: id === 'legacy' ? '尚未选择图片' : '图片不可用，请重新导入' });
    }
    byId('background-source').replaceChildren(...choices.map(image => {
      const option = document.createElement('option');
      option.value = image.id;
      option.textContent = ['default', 'default2'].includes(image.id) && images.some(item => item.id === image.id) ? `${image.name} · 内置` : image.name;
      return option;
    }));
  }

  function applyBackgroundPreview() {
    const settings = draft().background;
    const image = selectedImage();
    const missing = !image && settings.image !== 'legacy';
    const picture = byId('background-image');
    picture.hidden = !settings.enabled || !image;
    if (image && picture.getAttribute('src') !== image.url) picture.setAttribute('src', image.url);
    picture.style.opacity = settings.opacity;
    picture.style.width = `${settings.scale}%`;
    picture.style.left = `${settings.position - settings.scale / 2}%`;
    byId('background-placeholder').hidden = Boolean(settings.enabled && image);
    byId('background-placeholder').textContent = image ? '图片背景已关闭' : missing ? '图片不可用，请重新导入' : '上传一张 PNG，预览你的工作区。';
    byId('background-name').textContent = image?.name || (missing ? '图片不可用，请重新导入' : '尚未选择图片');
    byId('background-meta').textContent = image ? `${image.width} × ${image.height} · 仅在本机保存与处理` : '仅在本机保存与处理';
    backgroundNames.forEach(name => {
      const input = byId(`background-${name}`);
      const value = Number(input.value);
      const label = `${Math.round(name === 'opacity' ? value * 100 : value)}%`;
      byId(`background-${name}-value`).textContent = label;
      input.setAttribute('aria-valuetext', label);
      input.style.setProperty('--fill', `${(value - Number(input.min)) / (Number(input.max) - Number(input.min)) * 100}%`);
    });
  }

  function showTab(next) {
    tab = next;
    const background = tab === 'background';
    for (const name of ['animation', 'background']) {
      const button = byId(`${name}-tab`);
      button.setAttribute('aria-selected', String(tab === name));
      button.tabIndex = tab === name ? 0 : -1;
    }
    byId('animation-preview').hidden = background;
    byId('animation-source-card').hidden = background;
    byId('adjustments').hidden = background;
    byId('background-preview-card').hidden = !background;
    byId('background-source-card').hidden = !background;
    byId('background-adjustments').hidden = !background;
    byId('settings-heading').textContent = background ? '背景与融合' : '画面与播放';
    if (background) preview.pause();
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
    saved = normalizeSettings(state.settings);
    needsRepair = Boolean(state.warning);
    token = state.token;
    videos = state.videos;
    images = state.images || [];
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

  async function refreshInstallation() {
    if (!ready || busy || installationRefresh) return;
    const refresh = {};
    installationRefresh = refresh;
    try {
      const state = await request('/api/state');
      if (installationRefresh !== refresh) return;
      installation = state.installation;
      showInstallation();
      updateControls();
    } catch (error) {
      if (installationRefresh === refresh) {
        showError(error.message + ' 点击“刷新状态”可重试。');
        byId('retry-state').hidden = false;
      }
    } finally {
      if (installationRefresh === refresh) installationRefresh = null;
    }
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
        saved = normalizeSettings(result.settings);
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
      if (result.image) {
        const current = draft();
        images = images.filter(image => image.id !== result.image.id);
        images.push(result.image);
        setSettings({ ...current, background: { ...current.background, image: result.image.id, enabled: true } });
      }
      const original = installation.mode === 'original';
      const messages = {
        '/api/settings': original ? '设置已保存。点击“应用到 ChatGPT”准备更新，退出 ChatGPT 后自动生效。' : '设置已保存。点击“应用到 Codex”后，动画、背景与启动窗口设置才会生效。',
        '/api/install': original ? installation.message || '已准备，退出 ChatGPT 后自动应用；下次从原图标启动生效。' : '已应用。重新打开 Codex 后，每次启动都会沿用这些设置。',
        '/api/uninstall': original ? installation.message || '已准备恢复原版，退出 ChatGPT 后自动应用。' : '已恢复原版启动入口。下次从桌面菜单启动时使用原版 Codex。',
        '/api/upload': '视频已导入，可继续调整预览。点击“保存设置”保留本次选择。',
        '/api/background/upload': '图片已导入，可继续调整预览。点击“保存设置”保留本次选择。',
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

  for (const name of ['animation', 'background']) {
    byId(`${name}-tab`).addEventListener('click', () => showTab(name));
    byId(`${name}-tab`).addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      showTab(event.key === 'Home' ? 'animation' : event.key === 'End' ? 'background' : tab === 'animation' ? 'background' : 'animation');
      byId(`${tab}-tab`).focus();
    });
  }
  backgroundNames.forEach(name => byId(`background-${name}`).addEventListener('input', applyPreview));
  byId('background-source').addEventListener('change', applyPreview);
  byId('background-enabled').addEventListener('change', applyPreview);
  byId('window-mode').addEventListener('change', updateControls);
  byId('background-image').addEventListener('error', () => showError('图片无法预览，请重新导入有效的 PNG 图片。'));
  parameterNames.forEach(name => byId(name).addEventListener('input', applyPreview));
  document.querySelectorAll('input[name="fit"]').forEach(input => input.addEventListener('change', applyPreview));
  source.addEventListener('change', loadVideo);
  byId('reset').addEventListener('click', () => {
    const current = draft();
    if (tab === 'background') {
      setSettings({ ...current, background: { ...current.background, opacity: .18, position: 80, scale: 70 } });
      notify('背景参数已重置，当前图片与启用状态保持不变。');
    } else {
      setSettings({ ...current, speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover' });
      notify('画面与播放参数已重置，当前视频保持不变。');
    }
  });
  byId('toggle-play').addEventListener('click', () => preview.paused ? playPreview() : preview.pause());
  byId('toggle-mute').addEventListener('click', () => {
    muted = !muted;
    applyPreview();
  });
  byId('restart').addEventListener('click', () => playPreview(true));
  byId('reload-video').addEventListener('click', loadVideo);
  ['play', 'pause', 'ended'].forEach(event => preview.addEventListener(event, updatePlayback));
  preview.addEventListener('loadedmetadata', () => {
    preview.playbackRate = Number(byId('speed').value);
    preview.defaultMuted = muted;
    preview.muted = muted;
    // 静止展示稍后的画面便于调节。
    if (Number.isFinite(preview.duration)) preview.currentTime = Math.min(.7, preview.duration / 4);
  });
  preview.addEventListener('volumechange', () => {
    if (preview.muted !== muted) preview.muted = muted;
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
  byId('background-upload-button').addEventListener('click', () => byId('background-file').click());
  byId('background-file').addEventListener('change', () => {
    const file = byId('background-file').files[0];
    byId('background-file').value = '';
    if (!file || busy) return;
    if (!file.size || file.size > 40 * 1024 * 1024) {
      showError(file.size ? '图片超过 40 MiB，请选择更小的 PNG 图片。' : '这个图片文件为空，请重新选择。');
      return;
    }
    if (!/\.png$/i.test(file.name)) {
      showError('请选择 PNG 格式的背景图片。');
      return;
    }
    write('/api/background/upload', file, '正在导入背景图片，请保持窗口打开…', {
      'Content-Type': 'image/png', 'X-Filename': encodeURIComponent(file.name),
    });
  });
  byId('save').addEventListener('click', () => write('/api/settings', draft(), '正在保存设置…'));
  byId('install').addEventListener('click', () => write('/api/install', draft(), '正在生成并应用设置，请保持窗口打开…'));
  byId('restore').addEventListener('click', () => write('/api/uninstall', {}, '正在恢复原版启动入口…'));
  byId('retry-state').addEventListener('click', connect);
  byId('refresh-state').addEventListener('click', connect);
  window.addEventListener('focus', refreshInstallation);
  window.addEventListener('beforeunload', event => {
    if (!isDirty() && !busy) return;
    event.preventDefault();
    event.returnValue = '';
  });
  connect();
})();
