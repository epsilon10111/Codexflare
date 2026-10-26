"""Resolve CSS-module roles from the source app, including both footer layouts."""
import re

if __package__:
    from .build_layout import files, unique_asset
else:
    from build_layout import files, unique_asset

ROLES = ('WorkspaceContent', 'MainContentSurface', 'MainContentViewport',
         'ComposerLayoutRoot', 'compactScrollMask')


def css_class(text, role):
    matches = set(re.findall(r'\._' + role + r'_[A-Za-z0-9]+_\d+\b', text))
    if len(matches) != 1:
        raise ValueError(f'背景 CSS 角色必须唯一: {role} (找到 {len(matches)})')
    return matches.pop()[1:]


def loading_class(archive):
    name = unique_asset(archive, 'webview/assets', 'app-initial', 'css')
    return css_class(archive.read('webview/assets/' + name).decode(), 'delayedBlossom')


class BackgroundLayout:
    def __init__(self, archive):
        styles = {name: archive.read('webview/assets/' + name).decode()
                  for name in files(archive, 'webview/assets') if name.endswith('.css')
                  and not name.startswith('codex-')}
        text = '\n'.join(styles.values())
        self.classes = {role: css_class(text, role) for role in ROLES}
        # FooterFade's background, fade and surface exports share a CSS-module suffix.
        suffixes = [set(re.findall(r'\._' + role + r'(_[A-Za-z0-9]+_\d+)\b', text))
                    for role in ('background', 'fade', 'surface')]
        footers = set.intersection(*suffixes)
        if len(footers) > 1:
            raise ValueError('背景 FooterFade 模块不唯一')
        self.footer = footers.pop() if footers else None
        if not self.footer and not all('.' + role in text for role in ('bg-gradient-to-t', 'from-surface')):
            raise ValueError('无法识别背景 FooterFade 结构')
        shared = unique_asset(archive, 'webview/assets', 'app-shared', 'css')
        # The visual fixture loads actual source styles, including moved lazy chunks.
        owners = [name for role in ('ComposerLayoutRoot', 'WorkspaceContent', 'compactScrollMask')
                  for name, css in styles.items() if '.' + self.classes[role] in css]
        self.styles = tuple(dict.fromkeys([shared, *owners]))

    def adapt(self, text):
        for role, current in self.classes.items():
            text = re.sub(r'_' + role + r'_[A-Za-z0-9]+_\d+\b', current, text)
        if self.footer:
            text = text.replace('.bg-gradient-to-t.from-surface',
                                '._background' + self.footer + '._fade' + self.footer + '.from-surface')
        return text

    def fixture(self, text):
        text = self.adapt(text)
        if self.footer:
            for old, new in {
                'pointer-events-none absolute inset-x-0 -top-8 z-0 h-8 bg-gradient-to-t from-surface':
                    '_background{0} _fade{0} pointer-events-none absolute inset-x-0 z-0 from-surface',
                'pointer-events-none absolute inset-x-0 -top-8 z-0 bottom-0 mt-8 bg-surface':
                    '_background{0} _surface{0} pointer-events-none absolute inset-x-0 z-0 bottom-0 bg-surface',
            }.items():
                if text.count(old) != 2:
                    raise ValueError('Unexpected footer fixture structure')
                text = text.replace(old, new.format(self.footer))
        return text


def patch_background_css(text, archive):
    return BackgroundLayout(archive).adapt(text)
