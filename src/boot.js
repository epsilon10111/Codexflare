(() => {
  if (new URLSearchParams(location.search).get('codexBootAnimation') !== '1') return;
  const settings = /* CODEX_BOOT_SETTINGS */ null;
  const options = settings || { speed: 1, brightness: 1, contrast: 1, saturation: 1, fit: 'cover', duration: 4 };
  const timeoutMs = Math.max(8, Math.ceil(options.duration / options.speed + 4)) * 1000;
  // 位于 React 根节点外，应用提前就绪也不会截断视频。
  document.documentElement.dataset.codexBoot = 'loading';
  const scriptUrl = document.currentScript.src;
  const start = () => {
    const layer = document.createElement('div');
    layer.id = 'codex-boot';
    layer.setAttribute('role', 'region');
    layer.setAttribute('aria-label', 'Codex 启动动画');
    const video = document.createElement('video');
    video.src = new URL('./codex-boot.webm', scriptUrl).href;
    video.muted = true;
    video.playsInline = true;
    video.preload = 'auto';
    video.defaultPlaybackRate = options.speed;
    video.playbackRate = options.speed;
    video.style.filter = `brightness(${options.brightness}) contrast(${options.contrast}) saturate(${options.saturation})`;
    video.style.objectFit = options.fit;
    video.setAttribute('aria-hidden', 'true');
    const skip = document.createElement('button');
    skip.type = 'button';
    skip.textContent = '跳过 · Esc';
    layer.append(video, skip);
    document.body.append(layer);
    let finished = false;
    let timeout;
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
      clearTimeout(timeout);
      document.removeEventListener('keydown', keydown, true);
      document.removeEventListener('visibilitychange', playWhenVisible);
      video.pause();
      document.documentElement.dataset.codexBoot = reason;
      layer.classList.add('leaving');
      setTimeout(() => layer.remove(), 230);
    };
    const playWhenVisible = () => {
      if (document.hidden || finished) return;
      timeout ??= setTimeout(() => finish('timeout'), timeoutMs);
      video.play().catch(() => finish('playback-error'));
    };
    skip.addEventListener('click', () => finish('skipped'));
    video.addEventListener('ended', () => finish('ended'));
    video.addEventListener('error', () => finish('media-error'));
    document.addEventListener('keydown', keydown, true);
    document.addEventListener('visibilitychange', playWhenVisible);
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) finish('reduced-motion');
    else playWhenVisible();
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
