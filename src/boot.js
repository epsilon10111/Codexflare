(() => {
  if (new URLSearchParams(location.search).get('codexBootAnimation') !== '1') return;
  const settings = /* CODEX_BOOT_SETTINGS */ null;
  const options = settings || { speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', muted: true, duration: 10.039 };
  const timeoutMs = Math.max(8, Math.ceil(options.duration / options.speed + 4)) * 1000;
  // 位于 React 根节点外，应用提前就绪也不会截断视频。
  document.documentElement.dataset.codexBoot = 'loading';
  const scriptUrl = document.currentScript.src;
  const backgroundLink = document.getElementById('codex-background-preload');
  let backgroundImage = null;
  let backgroundReady = !backgroundLink;
  document.documentElement.dataset.codexBackground = backgroundLink ? 'loading' : 'none';
  if (backgroundLink) {
    // 与应用初始化和视频并行解码，避免揭幕后才请求大图。
    backgroundImage = new Image();
    backgroundImage.fetchPriority = 'high';
    backgroundImage.src = backgroundLink.href;
    backgroundImage.decode().then(() => {
      if (!backgroundImage) return;
      backgroundReady = true;
      document.documentElement.dataset.codexBackground = 'decoded';
    }, () => {
      if (!backgroundImage) return;
      backgroundReady = true;
      document.documentElement.dataset.codexBackground = 'error';
    });
  }
  const start = () => {
    const layer = document.createElement('div');
    layer.id = 'codex-boot';
    layer.setAttribute('role', 'region');
    layer.setAttribute('aria-label', 'Codex 启动动画');
    const video = document.createElement('video');
    video.src = new URL('./codex-boot.webm', scriptUrl).href;
    video.muted = options.muted !== false;
    video.playsInline = true;
    video.preload = 'auto';
    video.defaultPlaybackRate = options.speed;
    video.playbackRate = options.speed;
    video.style.filter = `brightness(${options.brightness}) contrast(${options.contrast}) saturate(${options.saturation})`;
    video.style.objectFit = options.fit;
    video.setAttribute('aria-hidden', 'true');
    const hint = document.createElement('span');
    hint.className = 'skip-hint';
    hint.lang = 'en';
    hint.textContent = 'Press Esc to skip';
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.textContent = '正在载入工作区…';
    status.hidden = true;
    layer.append(video, hint, status);
    document.body.append(layer);
    let finished = false;
    let timeout;
    let readyCheck;
    let paintFrame;
    let preparedSurface;
    let waiting = false;
    let audioReady = options.muted !== false;
    const enableAudio = () => {
      audioReady = true;
      clearTimeout(timeout);
      timeout = undefined;
      playWhenVisible();
    };
    const keydown = event => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        finish('skipped');
      }
    };
    const finish = reason => {
      if (finished) return;
      finished = true;
      backgroundImage = null;
      clearTimeout(timeout);
      clearTimeout(readyCheck);
      if (paintFrame !== undefined) cancelAnimationFrame(paintFrame);
      document.removeEventListener('keydown', keydown, true);
      document.removeEventListener('visibilitychange', playWhenVisible);
      document.removeEventListener('codex-boot-play', enableAudio);
      video.pause();
      document.documentElement.dataset.codexBoot = reason;
      layer.classList.add('leaving');
      setTimeout(() => layer.remove(), 230);
    };
    const readySurface = () => {
      const root = document.getElementById('root');
      if (!root) return null;
      const visible = element => element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden'
        && !element.closest('[inert], [aria-hidden="true"]');
      const controls = 'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [contenteditable="true"], [role="alert"], [data-thread-find-target="conversation"]';
      const shell = [...root.querySelectorAll('main[data-app-shell-main-surface]')].find(visible);
      if (shell) {
        // 全宽右侧页面会让主会话 inert，此时以实际可用的右侧页面为准。
        const selector = shell.querySelector('[data-app-shell-main-content-layout][data-app-shell-right-panel-full-width="true"]')
          ? 'aside[data-app-shell-focus-area="right-panel"]'
          : '[data-app-shell-main-content-layout] [data-app-shell-focus-area="main"]';
        return [...shell.querySelectorAll(selector)]
          .find(content => visible(content) && [...content.querySelectorAll(controls)].some(visible)) || null;
      }
      // shortcut: 此构建的 React 顶层开屏类名，升级后须重新核验就绪信号。
      if (root.querySelector('.startup-loader, ._delayedBlossom_ovcb0_16')) return null;
      return [...root.querySelectorAll(controls)].some(visible) ? root : null;
    };
    const prepareWorkspace = () => {
      if (finished) return;
      clearTimeout(readyCheck);
      const surface = readySurface();
      if (preparedSurface !== surface) {
        preparedSurface = null;
        if (document.documentElement.dataset.codexBackground === 'ready') {
          document.documentElement.dataset.codexBackground = 'decoded';
        }
      }
      if (backgroundReady && surface) {
        if (!backgroundLink || preparedSurface === surface) {
          if (waiting) return finish('ended');
        } else if (paintFrame === undefined) {
          // 播放期间给真实工作区留出绘制时间，片尾复用已准备好的当前节点。
          paintFrame = requestAnimationFrame(() => {
            paintFrame = requestAnimationFrame(() => {
              paintFrame = undefined;
              if (finished) return;
              if (readySurface() === surface) {
                preparedSurface = surface;
                if (document.documentElement.dataset.codexBackground === 'decoded') {
                  document.documentElement.dataset.codexBackground = 'ready';
                }
              }
              prepareWorkspace();
            });
          });
        }
      }
      if (waiting) {
        status.textContent = backgroundReady ? '正在载入工作区…' : '正在准备背景…';
      }
      if (paintFrame === undefined) readyCheck = setTimeout(prepareWorkspace, 100);
    };
    const ended = () => {
      if (finished || waiting) return;
      waiting = true;
      clearTimeout(timeout);
      prepareWorkspace();
      if (finished) return;
      document.documentElement.dataset.codexBoot = 'waiting-app';
      status.hidden = false;
      // 应用模块一直并行加载；留住视频尾帧，避免露出第二段开屏。
      timeout = setTimeout(() => finish('app-timeout'), 20000);
    };
    const playWhenVisible = () => {
      if (document.hidden || finished || waiting) return;
      timeout ??= setTimeout(() => finish('timeout'), timeoutMs);
      // 有声播放等待主进程的一次手势上下文，兼容此构建的自动播放限制。
      if (!audioReady) return;
      video.play().catch(() => finish('playback-error'));
    };
    video.addEventListener('ended', ended);
    video.addEventListener('error', () => finish('media-error'));
    document.addEventListener('keydown', keydown, true);
    document.addEventListener('visibilitychange', playWhenVisible);
    if (!audioReady) document.addEventListener('codex-boot-play', enableAudio, { once: true });
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) finish('reduced-motion');
    else {
      if (backgroundLink) prepareWorkspace();
      playWhenVisible();
    }
  };
  if (document.body) start();
  else {
    // 不等大体积应用模块加载完，body 出现即播放。
    const observer = new MutationObserver(() => {
      if (document.body) { observer.disconnect(); start(); }
    });
    observer.observe(document.documentElement, { childList: true });
  }
})();
