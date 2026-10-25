// 仅替换测试副本的入口，不启动原应用主进程或后端。
const { app, BrowserWindow, protocol } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = process.env.CODEX_BACKGROUND_PROBE_OUTPUT;
app.setPath('userData', path.join(output, 'profile'));
protocol.registerSchemesAsPrivileged([{ scheme: 'background-test', privileges: { standard: true, secure: true } }]);
const result = { passed: false, scope: 'isolated fixture with original application CSS' };
const timeout = setTimeout(() => { console.error('Background probe timed out'); app.exit(2); }, 35000);

app.whenReady().then(async () => {
  protocol.handle('background-test', request => {
    const name = decodeURIComponent(new URL(request.url).pathname).slice(1);
    if (name === 'assets/probe-black.png') {
      return new Response(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC', 'base64'),
        { headers: { 'Content-Type': 'image/png' } });
    }
    const files = {
      'background-fixture.html': 'text/html',
      'assets/app-shared-f2d570e85ceb.css': 'text/css',
      'assets/app-initial-c43288484373.css': 'text/css',
      'assets/thread-scroll-layout-24b9bd243051.css': 'text/css',
      'assets/codex-background.css': 'text/css',
      'assets/codex-background.png': 'image/png',
    };
    if (!Object.hasOwn(files, name)) return new Response(null, { status: 404 });
    try {
      return new Response(fs.readFileSync(path.join(app.getAppPath(), 'webview', name)),
        { headers: { 'Content-Type': files[name] } });
    } catch { return new Response(null, { status: 404 }); }
  });
  const win = new BrowserWindow({ width: 1440, height: 900, useContentSize: true,
    ...(process.platform === 'darwin' ? { type: 'panel', resizable: false, maximizable: false } : {}),
    title: 'Codexflare · 背景隔离验证', backgroundColor: '#181818',
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false } });
  win.setMenuBarVisibility(false);
  const page = win.webContents;
  const run = (fn, ...args) => page.executeJavaScript(`(${fn.toString()})(...${JSON.stringify(args)})`);
  const settle = () => run(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const capture = async name => {
    await settle();
    const image = await page.capturePage();
    fs.writeFileSync(path.join(output, `${name}.png`), image.toPNG());
    return image;
  };
  const state = () => run(() => {
    const main = document.querySelector('main');
    const layer = getComputedStyle(main, '::before');
    const workspace = getComputedStyle(main.querySelector('._WorkspaceContent_yl8z4_2'), '::before');
    const composerStyle = getComputedStyle(document.getElementById('composer'));
    const canvas = document.createElement('canvas'), context = canvas.getContext('2d');
    context.fillStyle = composerStyle.backgroundColor; context.fillRect(0, 0, 1, 1);
    const composerAlpha = context.getImageData(0, 0, 1, 1).data[3];
    const rect = element => { const r = element.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    return { opacity: layer.opacity, pointerEvents: layer.pointerEvents, zIndex: layer.zIndex,
      display: layer.display, mask: layer.maskImage, background: layer.backgroundImage,
      blendMode: layer.mixBlendMode, filter: layer.filter,
      layerGeometry: [layer.top, layer.left, layer.right, layer.bottom, layer.width, layer.height, layer.backgroundPosition, layer.backgroundSize],
      workspaceBackground: workspace.backgroundColor, workspaceContent: workspace.content,
      main: rect(main), viewportWidth: innerWidth,
      code: rect(document.getElementById('code')), composer: rect(document.getElementById('composer')),
      codeBackground: getComputedStyle(document.getElementById('code')).backgroundColor,
      composerBackground: composerStyle.backgroundColor, composerAlpha,
      composerOpacity: getComputedStyle(document.getElementById('composer')).opacity,
      composerBlur: getComputedStyle(document.getElementById('composer')).backdropFilter,
      footerSurface: rect(document.getElementById('footer-surface')),
      footerFade: rect(document.getElementById('footer-fade')),
      footerSurfaceBackground: getComputedStyle(document.getElementById('footer-surface')).backgroundColor,
      footerFadeBackground: getComputedStyle(document.getElementById('footer-fade')).backgroundImage,
      mainBackground: getComputedStyle(main).backgroundColor,
      panel: rect(document.getElementById('right-panel')),
      panelCode: rect(document.getElementById('panel-code')),
      panelComposer: rect(document.getElementById('panel-composer')),
      panelFrameBackground: getComputedStyle(document.getElementById('pane-frame')).backgroundColor,
      panelContentBackground: getComputedStyle(document.getElementById('pane-content')).backgroundColor };
  });
  const diff = (enabled, disabled, rect, viewportWidth) => {
    const scale = enabled.getSize().width / viewportWidth;
    const width = enabled.getSize().width;
    const a = enabled.toBitmap(), b = disabled.toBitmap();
    let total = 0, count = 0, changed = 0, max = 0;
    for (let y = Math.ceil(rect.y * scale); y < Math.floor((rect.y + rect.height) * scale); y++) {
      for (let x = Math.ceil(rect.x * scale); x < Math.floor((rect.x + rect.width) * scale); x++) {
        const i = (y * width + x) * 4;
        const value = Math.max(Math.abs(a[i] - b[i]), Math.abs(a[i + 1] - b[i + 1]), Math.abs(a[i + 2] - b[i + 2]));
        total += value; count++; changed += Number(value > 0); max = Math.max(max, value);
      }
    }
    return { averageChannelDifference: total / count, changedPixels: changed, pixels: count, max };
  };
  const hideBackground = () => page.insertCSS('main[data-app-shell-main-surface="default"]::before { visibility: hidden !important; }');
  const click = async id => {
    const point = await run(id => { const r = document.getElementById(id).getBoundingClientRect(); return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) }; }, id);
    page.sendInputEvent({ type: 'mouseDown', button: 'left', clickCount: 1, ...point });
    page.sendInputEvent({ type: 'mouseUp', button: 'left', clickCount: 1, ...point });
    await settle();
  };
  const inset = (r, x = 20, y = 10) => ({ x: r.x + x, y: r.y + y, width: r.width - x * 2, height: r.height - y * 2 });
  const checkBlack = async name => {
    const textKey = await page.insertCSS('* { color: transparent !important; text-shadow: none !important; } input::placeholder { color: transparent !important; }');
    const key = await page.insertCSS('main[data-app-shell-main-surface="default"]::before { background-image: url("background-test://fixture/assets/probe-black.png") !important; }');
    await run(async () => { const image = new Image(); image.src = 'background-test://fixture/assets/probe-black.png'; await image.decode(); });
    const visible = await capture(`${name}-black`);
    const hideKey = await hideBackground();
    const hidden = await capture(`${name}-black-disabled`);
    const current = await state();
    const pixels = diff(visible, hidden, current.main, current.viewportWidth);
    assert(pixels.max <= 1, `${name}: 黑色图像背景形成色块`); // 遮罩边缘合成允许一个色阶的舍入差。
    await page.removeInsertedCSS(hideKey);
    await page.removeInsertedCSS(key);
    await page.removeInsertedCSS(textKey);
    return pixels;
  };
  const checkSurrounds = async name => {
    const before = await capture(`${name}-composer`);
    const key = await page.insertCSS('[data-thread-scroll-footer] > [aria-hidden="true"], .thread-scroll-container > div > [aria-hidden="true"] > .bg-gradient-to-t.from-surface { visibility: hidden !important; }');
    const noDecorations = await capture(`${name}-no-footer-decoration`);
    await page.removeInsertedCSS(key);
    const current = await state();
    assert.equal(current.footerSurfaceBackground, 'rgba(0, 0, 0, 0)');
    assert.equal(current.footerFadeBackground, 'none');
    const pixels = diff(before, noDecorations, current.main, current.viewportWidth);
    assert.equal(pixels.changedPixels, 0, `${name}: 输入框外层仍遮挡背景`);
    const { composer, footerSurface } = current;
    const surround = { x: composer.x + composer.width + 2, y: composer.y + 8,
      width: footerSurface.x + footerSurface.width - composer.x - composer.width - 4, height: composer.height - 16 };
    assert(surround.width > 0 && surround.height > 0, '没有覆盖输入框外部区域');
    return { decorationPixels: pixels, surround, surface: current.footerSurface, fade: current.footerFade };
  };
  try {
    await win.loadURL('background-test://fixture/background-fixture.html');
    result.scrollMaskSupport = await run(() => ({ timeline: CSS.supports('animation-timeline', 'scroll(nearest y)'), containerHeight: CSS.supports('height', '100cqh') }));
    assert(result.scrollMaskSupport.timeline && result.scrollMaskSupport.containerHeight);
    result.image = await run(async () => {
      const url = getComputedStyle(document.querySelector('main'), '::before').backgroundImage.match(/^url\("?(.*?)"?\)$/)[1];
      const image = new Image(); image.src = url; await image.decode();
      return { width: image.naturalWidth, height: image.naturalHeight };
    });
    assert(result.image.width > 0 && result.image.height > 0);
    result.wide = await state();
    assert.equal(result.wide.opacity, '0.18');
    assert.equal(result.wide.blendMode, 'screen');
    assert.equal(result.wide.pointerEvents, 'none');
    assert.equal(result.wide.composerOpacity, '1', '不能淡化输入文字');
    assert.equal(result.wide.composerAlpha, 122, '深色表面应为48%不透明度');
    assert.equal(result.wide.composerBlur, 'blur(6px)');
    assert.equal(result.wide.zIndex, '-1');
    assert.equal(result.wide.workspaceBackground, 'rgba(0, 0, 0, 0)');
    assert.equal(result.wide.workspaceContent, '""', '未激活原应用工作区底层');
    assert.notEqual(result.wide.codeBackground, 'rgba(0, 0, 0, 0)');
    assert.notEqual(result.wide.composerBackground, 'rgba(0, 0, 0, 0)');
    assert.equal(result.wide.mainBackground, result.wide.codeBackground, '工作区与原内容底色不一致');
    await run(() => {
      window.probeClicks = [];
      for (const id of ['prompt', 'send', 'panel-prompt', 'panel-send', 'toggle-panel']) document.getElementById(id).addEventListener('click', event => window.probeClicks.push({ id, trusted: event.isTrusted }));
      document.getElementById('toggle-panel').addEventListener('click', () => { document.getElementById('right-panel').hidden = !document.getElementById('right-panel').hidden; });
    });
    const enabled = await capture('wide');
    const disableKey = await hideBackground();
    const disabled = await capture('wide-disabled');
    await page.removeInsertedCSS(disableKey);
    const { main, viewportWidth, code, composer } = result.wide;
    result.pixels = {
      left: diff(enabled, disabled, { ...main, y: main.y + 64, height: main.height - 64, width: main.width * .4 }, viewportWidth),
      right: diff(enabled, disabled, { ...main, x: main.x + main.width * .7, width: main.width * .3 }, viewportWidth),
      code: diff(enabled, disabled, { x: code.x + 20, y: code.y + 20, width: code.width - 40, height: code.height - 40 }, viewportWidth),
      composer: diff(enabled, disabled, { x: composer.x + 20, y: composer.y + 10, width: composer.width - 40, height: composer.height - 20 }, viewportWidth),
    };
    assert.equal(result.pixels.left.changedPixels, 0, '左侧受到背景影响');
    assert(result.pixels.right.averageChannelDifference > .1, '右侧背景未真正绘制');
    assert.equal(result.pixels.code.changedPixels, 0, '代码块底色未挡住背景');
    assert(result.pixels.composer.averageChannelDifference > .05, '输入表面仍完全遮挡背景');
    result.composerSurrounds = { wide: await checkSurrounds('wide') };
    // 还原真实 FooterFade 两层，确保模拟结构能够复现先前的大块遮挡。
    const footerKey = await page.insertCSS('#footer-surface { background-color: var(--color-surface) !important; } #footer-fade { background-image: linear-gradient(to top, var(--color-surface), transparent) !important; }');
    const originalFooter = await capture('original-footer-black-frame');
    const currentFooter = await state();
    result.originalFooterControl = diff(originalFooter, enabled, result.composerSurrounds.wide.surround, viewportWidth);
    assert(result.originalFooterControl.changedPixels > 0, '未复现原输入框外围黑边');
    assert.equal(currentFooter.footerSurfaceBackground, currentFooter.mainBackground);
    await page.removeInsertedCSS(footerKey);
    const opaqueKey = await page.insertCSS('main > ._WorkspaceContent_yl8z4_2::before { background-color: var(--color-surface) !important; }');
    const opaque = await capture('wide-workspace-opaque');
    const opaqueDisableKey = await hideBackground();
    const opaqueDisabled = await capture('wide-workspace-opaque-disabled');
    result.opaqueControl = diff(opaque, opaqueDisabled,
      { x: main.x + main.width * .7, y: 160, width: main.width * .3, height: main.height - 160 }, viewportWidth);
    assert.equal(result.opaqueControl.changedPixels, 0, '原工作区底层应能遮挡背景');
    await page.removeInsertedCSS(opaqueDisableKey);
    await page.removeInsertedCSS(opaqueKey);
    for (const id of ['prompt', 'send']) {
      await click(id);
      if (id === 'prompt') {
        for (const keyCode of 'Codexflare') page.sendInputEvent({ type: 'char', keyCode });
        await settle();
      }
    }
    result.interaction = await run(() => ({ clicks: window.probeClicks, text: document.getElementById('prompt').value }));
    assert.deepEqual(result.interaction.clicks, [{ id: 'prompt', trusted: true }, { id: 'send', trusted: true }]);
    assert.equal(result.interaction.text, 'Codexflare');
    await run(() => document.activeElement.blur());
    result.black = { dark: await checkBlack('dark') };
    await click('toggle-panel');
    result.panelOpen = await state();
    result.panelTextLayout = await run(() => Array.from(document.querySelectorAll('#pane-content p'), paragraph => {
      const range = document.createRange(); range.selectNodeContents(paragraph);
      const p = paragraph.getBoundingClientRect();
      return { right: p.right, scrollWidth: paragraph.scrollWidth, clientWidth: paragraph.clientWidth,
        lines: Array.from(range.getClientRects(), r => ({ left: r.left, right: r.right })) };
    }));
    assert(result.panelTextLayout.every(p => p.scrollWidth <= p.clientWidth && p.lines.every(line => line.right <= p.right + 1)), '模拟分支段落溢出');
    assert(result.panelOpen.panel.width > 300);
    assert.equal(result.panelOpen.panelFrameBackground, 'rgba(0, 0, 0, 0)');
    assert.equal(result.panelOpen.panelContentBackground, 'rgba(0, 0, 0, 0)');
    assert.deepEqual(result.panelOpen.layerGeometry, result.wide.layerGeometry, '打开面板改变了背景定位');
    result.composerSurrounds.panel = await checkSurrounds('panel');
    const withPanel = await capture('panel-open');
    const panelHideKey = await hideBackground();
    const panelDisabled = await capture('panel-disabled');
    await page.removeInsertedCSS(panelHideKey);
    const panel = result.panelOpen.panel;
    result.panelPixels = {
      background: diff(withPanel, panelDisabled, inset(panel), viewportWidth),
      code: diff(withPanel, panelDisabled, inset(result.panelOpen.panelCode), viewportWidth),
      composer: diff(withPanel, panelDisabled, inset(result.panelOpen.panelComposer), viewportWidth),
    };
    assert(result.panelPixels.background.averageChannelDifference > .1, '右侧面板遮住了背景');
    assert.equal(result.panelPixels.code.changedPixels, 0, '右侧代码底色受到影响');
    assert(result.panelPixels.composer.averageChannelDifference > .05, '右侧输入表面仍完全遮挡背景');
    for (const id of ['panel-prompt', 'panel-send']) {
      await click(id);
      if (id === 'panel-prompt') {
        for (const keyCode of 'Subagent') page.sendInputEvent({ type: 'char', keyCode });
        await settle();
      }
    }
    result.panelInteraction = await run(() => ({ clicks: window.probeClicks.slice(2), text: document.getElementById('panel-prompt').value }));
    assert.deepEqual(result.panelInteraction.clicks, [{ id: 'toggle-panel', trusted: true }, { id: 'panel-prompt', trusted: true }, { id: 'panel-send', trusted: true }]);
    assert.equal(result.panelInteraction.text, 'Subagent');
    await run(() => document.activeElement.blur());
    const contentKey = await page.insertCSS('.probe-content { visibility: hidden !important; }');
    const panelEmpty = await capture('panel-background-only');
    await run(() => { document.getElementById('right-panel').hidden = true; });
    const withoutPanel = await capture('background-only');
    result.panelContinuity = diff(panelEmpty, withoutPanel, inset(panel), viewportWidth);
    assert.equal(result.panelContinuity.changedPixels, 0, '面板打开后背景位置或底色改变');
    await page.removeInsertedCSS(contentKey);
    win.setContentSize(850, 720);
    await settle();
    result.narrow = await state();
    assert.equal(result.narrow.opacity, '0.1');
    await capture('narrow');
    result.composerSurrounds.narrow = await checkSurrounds('narrow');
    await click('toggle-panel');
    result.composerSurrounds.narrowPanel = await checkSurrounds('narrow-panel');
    await click('toggle-panel');
    win.setContentSize(1440, 900);
    await run(() => { document.documentElement.dataset.theme = 'light'; document.querySelector('main').dataset.theme = 'light'; });
    result.light = await state();
    assert.equal(result.light.opacity, '0.09');
    assert.equal(result.light.blendMode, 'multiply');
    assert.equal(result.light.filter, 'invert(1)');
    assert.equal(result.light.composerBlur, 'none', '浅色应保留不透明表面');
    assert.equal(result.light.composerAlpha, 255);
    await capture('light');
    result.composerSurrounds.light = await checkSurrounds('light');
    result.black.light = await checkBlack('light');
    await click('toggle-panel');
    await capture('light-panel');
    result.composerSurrounds.lightPanel = await checkSurrounds('light-panel');
    result.composerContrast = [];
    await run(() => { document.documentElement.dataset.theme = 'dark'; document.querySelector('main').dataset.theme = 'dark'; });
    const luminance = rgb => rgb.map(value => { const c = value / 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; }).reduce((sum, value, i) => sum + value * [.2126, .7152, .0722][i], 0);
    for (const opacity of [.18, .5]) {
      await run(opacity => document.documentElement.style.setProperty('--codex-bg-opacity', opacity), opacity);
      const colors = await run(() => {
        const color = value => { const canvas = document.createElement('canvas'); const context = canvas.getContext('2d'); context.fillStyle = value; context.fillRect(0, 0, 1, 1); return Array.from(context.getImageData(0, 0, 1, 1).data); };
        return ['prompt', 'panel-prompt'].map(id => { const input = document.getElementById(id), composer = input.closest('.composer'), r = composer.getBoundingClientRect(); return { id,
          foreground: color(getComputedStyle(input).color), button: color(getComputedStyle(composer.querySelector('button')).color),
          rect: { x: r.x + 24, y: r.y + 12, width: r.width - 48, height: r.height - 24 } }; });
      });
      const textKey = await page.insertCSS('.composer > * { visibility: hidden !important; }');
      const background = await capture(`composer-material-${opacity}`);
      await page.removeInsertedCSS(textKey);
      const bitmap = background.toBitmap(), width = background.getSize().width;
      const scale = width / (await state()).viewportWidth;
      for (const color of colors) {
        let backgroundMax = 0;
        for (let y = Math.ceil(color.rect.y * scale); y < Math.floor((color.rect.y + color.rect.height) * scale); y++) for (let x = Math.ceil(color.rect.x * scale); x < Math.floor((color.rect.x + color.rect.width) * scale); x++) {
          const i = (y * width + x) * 4; backgroundMax = Math.max(backgroundMax, luminance([bitmap[i + 2], bitmap[i + 1], bitmap[i]]));
        }
        const text = luminance(color.foreground.slice(0, 3)), button = luminance(color.button.slice(0, 3));
        const ratio = foreground => (Math.max(foreground, backgroundMax) + .05) / (Math.min(foreground, backgroundMax) + .05);
        const sample = { id: color.id, opacity, textContrast: ratio(text), buttonContrast: ratio(button) };
        assert(sample.textContrast >= 4.5 && sample.buttonContrast >= 4.5, '半透明输入区对比度不足');
        result.composerContrast.push(sample);
      }
    }
    await run(() => document.documentElement.removeAttribute('style'));
    result.composerSpecialStates = await run(() => {
      const composer = document.getElementById('composer'), values = {};
      for (const variant of ['inline', 'document', 'drag']) {
        composer.dataset.composerSurfaceVariant = variant === 'drag' ? 'default' : variant;
        if (variant === 'drag') composer.setAttribute('data-composer-drag-active', '');
        values[variant] = getComputedStyle(composer).backdropFilter;
      }
      composer.removeAttribute('data-composer-drag-active'); composer.dataset.composerSurfaceVariant = 'default';
      return values;
    });
    assert.deepEqual(result.composerSpecialStates, { inline: 'none', document: 'none', drag: 'none' });
    result.scrollMask = [];
    await run(() => {
      document.documentElement.dataset.theme = 'dark'; document.querySelector('main').dataset.theme = 'dark';
      document.getElementById('right-panel').hidden = true;
      for (const content of document.querySelectorAll('.conversation')) {
        for (let i = 0; i < 35; i++) {
          const paragraph = document.createElement('p'); paragraph.className = 'scroll-proof'; paragraph.style.margin = '0';
          paragraph.textContent = `滚动内容 ${i}：文字在输入框上方渐隐，不得透出在按钮或输入框外侧。`; content.append(paragraph);
        }
      }
    });
    const geometry = id => run(id => {
      const footer = document.getElementById(id), scroll = footer.parentElement;
      const rect = element => { const r = element.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
      return { scroll: rect(scroll), transcript: rect(scroll.firstElementChild), footer: rect(footer),
        composer: rect(footer.querySelector('.composer')), scrollHeight: scroll.scrollHeight, clientHeight: scroll.clientHeight,
        scrollTop: scroll.scrollTop, mask: getComputedStyle(scroll.firstElementChild).maskPosition, viewportWidth: innerWidth };
    }, id);
    for (const layout of ['wide', 'narrow', 'panel']) {
      win.setContentSize(layout === 'narrow' ? 850 : 1440, layout === 'narrow' ? 720 : 900);
      await run(layout => { document.getElementById('right-panel').hidden = layout !== 'panel'; }, layout);
      const id = layout === 'panel' ? 'panel-footer' : 'footer';
      for (const direction of ['column', 'column-reverse']) {
        await run((id, direction) => {
          const scroll = document.getElementById(id).parentElement;
          scroll.classList.toggle('flex-col-reverse', direction === 'column-reverse'); scroll.style.flexDirection = direction;
        }, id, direction);
        for (const fraction of [.5, 1]) {
          await run((id, direction, fraction) => {
            const scroll = document.getElementById(id).parentElement;
            scroll.scrollTop = (scroll.scrollHeight - scroll.clientHeight) * (direction === 'column' ? fraction : fraction - 1);
          }, id, direction, fraction);
          const name = `scroll-${layout}-${direction}-${fraction}`;
          const visible = await capture(name);
          const current = await geometry(id);
          const plainKey = await page.insertCSS('[data-request-input-activity-root] { container-type: normal !important; } .thread-scroll-container > :first-child { mask-image: none !important; animation: none !important; }');
          const plain = await capture(`${name}-unmasked`);
          const plainGeometry = await geometry(id);
          for (const field of ['scroll', 'transcript', 'footer', 'composer', 'scrollHeight', 'clientHeight', 'scrollTop']) assert.deepEqual(current[field], plainGeometry[field], `${name}: 遮罩改变布局 ${field}`);
          await page.removeInsertedCSS(plainKey);
          const hideKey = await page.insertCSS('.thread-scroll-container > .transcript > .probe-content { visibility: hidden !important; }');
          const hidden = await capture(`${name}-hidden`);
          await page.removeInsertedCSS(hideKey);
          const { scroll, footer, composer, viewportWidth } = current;
          const bottom = { x: scroll.x + 16, y: footer.y + 1, width: scroll.width - 32, height: footer.height - 3 };
          const top = { x: scroll.x + 16, y: scroll.y + 20, width: scroll.width - 32, height: footer.y - scroll.y - 60 };
          const sample = { layout, direction, fraction, geometry: current,
            bottom: diff(visible, hidden, bottom, viewportWidth), top: diff(visible, hidden, top, viewportWidth),
            composer: diff(visible, hidden, inset(composer), viewportWidth), unmaskedBottom: diff(plain, hidden, bottom, viewportWidth) };
          // 分数缩放下的透明层合成允许一个色阶的舍入差，与纯黑背景检查一致。
          assert(sample.bottom.max <= 1, `${name}: 滚动文字透出到输入区域`);
          assert(sample.top.changedPixels > 0, `${name}: 遮罩意外隐藏了整个会话`);
          assert(sample.composer.max <= 1, `${name}: 遮罩裁剪了输入框`);
          if (fraction === .5) assert(sample.unmaskedBottom.changedPixels > 0 && sample.unmaskedBottom.max > 1, `${name}: 负对照没有滚动文字`);
          result.scrollMask.push(sample);
        }
      }
    }
    await run(() => {
      document.querySelectorAll('.scroll-proof').forEach(element => element.remove());
      for (const scroll of document.querySelectorAll('.thread-scroll-container')) { scroll.classList.add('flex-col-reverse'); scroll.style.flexDirection = 'column-reverse'; scroll.scrollTop = 0; }
      document.documentElement.dataset.theme = 'light'; document.querySelector('main').dataset.theme = 'light';
    });
    await run(() => {
      const style = document.documentElement.style;
      style.setProperty('--codex-bg-opacity', '.3');
      style.setProperty('--codex-bg-position', '75%');
      style.setProperty('--codex-bg-scale', '60%');
    });
    result.settings = await state();
    assert.equal(result.settings.opacity, '0.15');
    assert(Math.abs(parseFloat(result.settings.layerGeometry[1]) - result.settings.main.width * .45) < 1);
    assert(Math.abs(parseFloat(result.settings.layerGeometry[4]) - result.settings.main.width * .6) < 1);
    await run(() => document.documentElement.removeAttribute('style'));
    result.layoutExclusions = await run(() => {
      const footer = document.getElementById('footer'), scroll = footer.parentElement, root = scroll.parentElement;
      footer.classList.add('home-composer-anchor');
      const home = { mask: getComputedStyle(scroll.firstElementChild).maskImage, container: getComputedStyle(root).containerType,
        surface: getComputedStyle(footer.firstElementChild).backgroundColor };
      footer.classList.remove('home-composer-anchor');
      root.append(footer); scroll.classList.add('_compactScrollMask_121j8_2');
      const compact = { mask: getComputedStyle(scroll.firstElementChild).maskImage, container: getComputedStyle(root).containerType,
        originalMask: getComputedStyle(scroll).maskImage, surface: getComputedStyle(footer.firstElementChild).backgroundColor };
      scroll.classList.remove('_compactScrollMask_121j8_2'); scroll.append(footer);
      return { home, compact };
    });
    for (const name of ['home', 'compact']) {
      assert.equal(result.layoutExclusions[name].mask, 'none', `${name}: 不应增加文字遮罩`);
      assert.equal(result.layoutExclusions[name].container, 'normal', `${name}: 不应改变容器`);
      assert.notEqual(result.layoutExclusions[name].surface, 'rgba(0, 0, 0, 0)', `${name}: 不应改变原填充`);
    }
    assert.notEqual(result.layoutExclusions.compact.originalMask, 'none', '未保留 compact 的原遮罩');
    await run(() => { document.documentElement.dataset.theme = 'dark'; document.querySelector('main').dataset.theme = 'dark'; });
    page.debugger.attach('1.3');
    result.accessibility = {};
    for (const name of ['prefers-contrast', 'prefers-reduced-transparency', 'forced-colors']) {
      const value = name === 'prefers-contrast' ? 'more' : name === 'forced-colors' ? 'active' : 'reduce';
      await page.debugger.sendCommand('Emulation.setEmulatedMedia', { features: [{ name, value }] });
      const current = await state();
      assert.equal(current.display, 'none', name);
      assert.equal(current.composerBlur, 'none', `${name}: 应保留不透明表面`);
      assert.equal(current.composerAlpha, 255, `${name}: 输入表面应完全不透明`);
      assert.notEqual(current.footerSurfaceBackground, 'rgba(0, 0, 0, 0)', `${name}: 应保留无图片时的输入框外围遮罩`);
      if (name !== 'forced-colors') assert.notEqual(current.footerFadeBackground, 'none', `${name}: 应保留原渐变`);
      result.accessibility[name] = current.display;
      if (name === 'prefers-contrast') await capture('high-contrast');
    }
    page.debugger.detach();
    result.passed = true;
  } catch (error) {
    result.error = error.stack;
    console.error(error);
  } finally {
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(result, null, 2));
    clearTimeout(timeout);
    app.exit(result.passed ? 0 : 1);
  }
}).catch(error => { console.error(error); app.exit(1); });
