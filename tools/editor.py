#!/usr/bin/env python3
"""在独立桌面窗口中预览、配置和安装 Codex 开屏动画。"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
from urllib.parse import unquote, urlsplit

if __package__:
    from . import animation, background, manage
else:
    import animation
    import background
    import manage

manage = manage.platform_manager()

ROOT = Path(__file__).resolve().parents[1]
MAX_UPLOAD = 100 * 1024 * 1024
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/editor.css': ('editor.css', 'text/css; charset=utf-8'),
          '/editor.js': ('editor.js', 'text/javascript; charset=utf-8'),
          '/mark.svg': ('mark.svg', 'image/svg+xml')}


def original_manager():
    if sys.platform != 'darwin' or not (getattr(sys, 'frozen', False) or
                                       (animation.LOCAL / 'original-install.json').exists()):
        return None
    if __package__:
        from . import original_macos
    else:
        import original_macos
    return original_macos


def source_available():
    source = manage.fingerprint()
    supported = getattr(manage, 'supported_source', None)
    return supported(source) if supported else source['version'] == manage.VERSION


def installation_status():
    try:
        original = original_manager()
        if original is not None:
            return original.status()
        state = manage.read_state()
        available = source_available()
        problem = manage.runtime_problem(state)
        active = bool(state and state.get('active') and not problem
                      and manage.desktop_snapshot() == state.get('installed_desktop'))
        running = bool(manage.running_pids())
        message = '定制动画已启用' if active else (problem or '菜单入口已被其他操作修改')
        if active and hasattr(manage, 'LAUNCH_HINT'):
            message += '；' + manage.LAUNCH_HINT
        if not available:
            message = f'当前应用版本尚未适配，仅支持 {getattr(manage, "SUPPORTED", manage.VERSION)}；仍可预览和保存'
        elif running:
            message = '定制版 Codex 正在运行；退出定制版后返回本窗口，再点击应用。预览和保存不受影响'
        return {'active': active, 'available': available, 'running': running, 'message': message}
    except (OSError, ValueError, KeyError, struct.error, subprocess.SubprocessError) as error:
        return {'active': False, 'available': False, 'running': False,
                'message': f'当前无法应用，仍可预览和保存：{error}'}


def public_video(video_id):
    return {**animation.video_info(video_id), 'url': '/media/' + video_id}


def public_image(image_id):
    return {**background.image_info(image_id, animation.LOCAL), 'url': '/background/' + image_id}


def import_image(data, filename):
    filename = Path(filename.replace('\\', '/')).name
    if not filename or len(filename) > 240 or any(ord(char) < 32 for char in filename):
        raise ValueError('图片文件名无效或过长')
    info = background.validate_png(data)
    image_id = info['sha256']
    path = background.image_path(image_id, animation.LOCAL)
    animation.LOCAL.mkdir(parents=True, exist_ok=True)
    animation.LOCAL.chmod(0o700)
    path.parent.mkdir(exist_ok=True)
    path.parent.chmod(0o700)
    manage.atomic_write(path, data)
    manage.atomic_write(path.with_suffix('.json'), json.dumps({
        'id': image_id, 'name': filename, 'width': info['width'], 'height': info['height'],
    }, ensure_ascii=False).encode())
    return public_image(image_id)


def probe_video(path, max_duration=30):
    result = subprocess.run([
        'ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
        '-format_whitelist', 'mov,matroska,webm,avi,ogg',
        '-select_streams', 'v:0', '-show_entries',
        'stream=width,height,duration:format=duration', '-of', 'json', str(path),
    ], capture_output=True, text=True, timeout=20, check=True)
    data = json.loads(result.stdout)
    streams = data.get('streams', [])
    if not streams:
        raise ValueError('文件中没有可用的视频轨道')
    stream = streams[0]
    duration = float(data.get('format', {}).get('duration', stream.get('duration', 0)))
    width, height = stream.get('width', 0), stream.get('height', 0)
    if not math.isfinite(duration) or not 0 < duration <= max_duration:
        raise ValueError('请选择时长不超过 30 秒的有效视频')
    if not 0 < width <= 7680 or not 0 < height <= 7680 or width * height > 33177600:
        raise ValueError('视频尺寸无效或超过 8K，请先缩小视频')
    return {'duration': duration, 'width': width, 'height': height}


def import_video(source, filename):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('导入视频需要 FFmpeg 和 ffprobe；默认视频仍可使用')
    filename = Path(filename.replace('\\', '/')).name
    if not filename or len(filename) > 240 or any(ord(char) < 32 for char in filename):
        raise ValueError('视频文件名无效或过长')
    probe_video(source)
    animation.MEDIA.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='convert-', dir=animation.MEDIA) as folder:
        output = Path(folder) / 'video.webm'
        # 限制输入协议，避免导入的播放列表让 FFmpeg 访问网络资源。
        subprocess.run([
            'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-xerror',
            '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm,avi,ogg',
            '-i', str(source), '-map', '0:v:0', '-map', '0:a:0?',
            '-sn', '-dn', '-map_metadata', '-1', '-t', '30', '-vf',
            "scale=w='min(1920,iw)':h='min(1080,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30",
            '-c:v', 'libvpx-vp9', '-crf', '34', '-b:v', '0', '-threads', '2',
            '-row-mt', '1', '-cpu-used', '6', '-pix_fmt', 'yuv420p',
            '-c:a', 'libopus', '-b:a', '128k', '-ac', '2', str(output),
        ], capture_output=True, timeout=180, check=True)
        info = probe_video(output, max_duration=animation.MAX_ENCODED_DURATION)
        with output.open('rb') as video:
            video_id = hashlib.file_digest(video, 'sha256').hexdigest()
        metadata = {'id': video_id, 'name': filename, **info}
        output.chmod(0o600)
        os.replace(output, animation.video_path(video_id))
        manage.atomic_write(animation.MEDIA / f'{video_id}.json',
                            json.dumps(metadata, ensure_ascii=False).encode())
    return public_video(video_id)


def range_bounds(header, size):
    if header is None:
        return 0, size - 1
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
    if not match or not any(match.groups()):
        raise ValueError('无效视频范围')
    first, last = match.groups()
    if not first:
        if int(last) <= 0:
            raise ValueError('无效视频范围')
        return max(0, size - int(last)), size - 1
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start > end or start >= size:
        raise ValueError('视频范围超出文件')
    return start, end


class EditorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address=('127.0.0.1', 0)):
        super().__init__(address, EditorHandler)
        self.token = secrets.token_urlsafe(32)
        self.write_lock = threading.Lock()


class EditorHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "media-src 'self'; connect-src 'self'; object-src 'none'; "
                         "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        super().end_headers()

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def allowed(self, write=False):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin')
        if (host not in hosts or (origin and origin != f'http://{host}')
                or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self.reply(403, {'error': '仅允许本机界面访问'})
            return False
        if write and not secrets.compare_digest(self.headers.get('X-Editor-Token', ''), self.server.token):
            self.reply(403, {'error': '界面会话已失效，请刷新页面后重试'})
            return False
        return True

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.allowed():
            return
        path = urlsplit(self.path).path
        try:
            if path == '/api/state':
                warning = None
                try:
                    settings = animation.load_settings()
                    animation.video_info(settings['video'])
                except (ValueError, OSError) as error:
                    settings = animation.validate_settings({})
                    warning = f'已保存的设置无法读取：{error}。当前展示默认视频，请保存以恢复配置。'
                videos = [public_video('default')]
                for metadata in sorted(animation.MEDIA.glob('*.json')):
                    try:
                        videos.append(public_video(metadata.stem))
                    except (ValueError, OSError):
                        continue
                images = []
                image_ids = ['default', 'default2', 'legacy'] + [path.stem for path in sorted((animation.LOCAL / 'backgrounds').glob('*.json'))]
                for image_id in image_ids:
                    try:
                        images.append(public_image(image_id))
                    except (ValueError, OSError):
                        continue
                try:
                    background.load_selected(settings['background'], animation.LOCAL)
                except (ValueError, OSError) as error:
                    settings['background']['enabled'] = False
                    warning = (warning + ' ' if warning else '') + f'背景暂不可用：{error}。已暂停预览，请重新导入。'
                self.reply(200, {'settings': settings, 'videos': videos, 'images': images, 'warning': warning,
                                 'installation': installation_status(), 'token': self.server.token})
            elif path in STATIC:
                name, content_type = STATIC[path]
                self.send_file(ROOT / 'ui' / name, content_type)
            elif path.startswith('/media/'):
                self.send_file(animation.video_path(path.removeprefix('/media/')), 'video/webm')
            elif path.startswith('/background/'):
                self.send_file(background.image_path(path.removeprefix('/background/'), animation.LOCAL), 'image/png')
            else:
                self.reply(404, {'error': '页面不存在'})
        except (FileNotFoundError, ValueError, KeyError) as error:
            self.reply(400, {'error': str(error)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError as error:
            self.reply(500, {'error': f'读取失败：{error}'})

    def send_file(self, path, content_type):
        with path.open('rb') as file:
            size = os.fstat(file.fileno()).st_size
            header = self.headers.get('Range')
            try:
                start, end = range_bounds(header, size)
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            self.send_response(206 if header else 200)
            self.send_header('Content-Type', content_type)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(end - start + 1))
            if header:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if self.command == 'HEAD':
                return
            file.seek(start)
            remaining = end - start + 1
            while remaining:
                block = file.read(min(remaining, 64 * 1024))
                if not block:
                    break
                self.wfile.write(block)
                remaining -= len(block)

    def do_POST(self):
        if not self.allowed(write=True):
            return
        path = urlsplit(self.path).path
        if path not in ('/api/upload', '/api/background/upload', '/api/settings', '/api/install', '/api/uninstall'):
            self.reply(404, {'error': '操作不存在'})
            return
        if not self.server.write_lock.acquire(blocking=False):
            self.reply(409, {'error': '正在处理其他操作，请稍后重试'})
            return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            limit = {'/api/upload': MAX_UPLOAD, '/api/background/upload': background.MAX_UPLOAD}.get(path, 4096)
            if self.headers.get('Transfer-Encoding') or not 0 < length <= limit:
                self.reply(413, {'error': '上传不能为空；视频上限 100 MiB，PNG 上限 40 MiB，设置上限 4 KiB'})
                return
            if path == '/api/background/upload':
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('图片上传未完成，请重试')
                image = import_image(raw, unquote(self.headers.get('X-Filename', 'background.png')))
                self.reply(200, {'image': image})
                return
            if path == '/api/upload':
                animation.LOCAL.mkdir(parents=True, exist_ok=True)
                animation.LOCAL.chmod(0o700)
                with tempfile.TemporaryDirectory(prefix='upload-', dir=animation.LOCAL) as folder:
                    source = Path(folder) / 'input'
                    with source.open('wb') as upload:
                        remaining = length
                        while remaining:
                            block = self.rfile.read(min(remaining, 64 * 1024))
                            if not block:
                                raise ValueError('视频上传未完成，请重试')
                            upload.write(block)
                            remaining -= len(block)
                    video = import_video(source, unquote(self.headers.get('X-Filename', 'video')))
                self.reply(200, {'video': video})
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('设置请求未完成')
            data = json.loads(raw)
            original = original_manager() if path in ('/api/install', '/api/uninstall') else None
            if path == '/api/uninstall':
                if original is not None:
                    original.uninstall()
                    original.launch_worker()
                    status = original.status()
                    message = status['message']
                else:
                    manage.uninstall()
                    status = installation_status()
                    message = '已恢复原版入口；未停止当前会话'
                self.reply(200, {'message': message, 'installation': status})
                return
            settings = animation.validate_settings(data)
            animation.video_info(settings['video'])
            if path == '/api/install' and original is None:
                if manage.running_pids():
                    self.reply(409, {'error': '定制版 Codex 正在运行；退出定制版后返回本窗口，再点击应用。可先保存设置'})
                    return
                if not source_available():
                    raise ValueError(f'当前版本尚未适配，仅支持 {getattr(manage, "SUPPORTED", manage.VERSION)}')
            animation.save_settings(settings)
            if path == '/api/install':
                try:
                    if original is not None:
                        original.prepare()
                        original.launch_worker()
                        status = original.status()
                        message = status['message']
                    else:
                        manage.install()
                        status = installation_status()
                        message = '已应用。' + getattr(manage, 'LAUNCH_HINT', '重新打开 Codex 即可查看新的动画与背景。')
                except (OSError, ValueError, KeyError, struct.error, subprocess.CalledProcessError) as error:
                    raise ValueError(f'配置已保存，但尚未应用：{error}') from error
                self.reply(200, {'settings': settings, 'message': message, 'installation': status})
            else:
                self.reply(200, {'settings': settings})
        except (ValueError, KeyError, TypeError, struct.error) as error:
            self.reply(400, {'error': str(error)})
        except subprocess.TimeoutExpired:
            self.reply(400, {'error': '视频处理超时，请选择更小或更短的视频'})
        except subprocess.CalledProcessError:
            self.reply(400, {'error': '视频无法解码或转换失败，请尝试其他 MP4、MOV 或 WebM 文件'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError as error:
            self.reply(500, {'error': f'操作失败：{error}'})
        finally:
            self.server.write_lock.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0, help='本地端口，默认自动分配')
    parser.add_argument('--headless', '--no-browser', dest='headless', action='store_true',
                        help='仅启动本地服务，用于自动化验证')
    args = parser.parse_args()
    if not args.headless:
        try:
            if sys.platform == 'win32':
                if __package__:
                    from .desktop_windows import run
                else:
                    from desktop_windows import run
            elif sys.platform == 'darwin':
                if __package__:
                    from .desktop_macos import run
                else:
                    from desktop_macos import run
            elif __package__:
                from .desktop import run
            else:
                from desktop import run
        except (ImportError, ValueError):
            if sys.platform == 'win32':
                parser.exit(1, 'Windows 编辑器需要 pywebview 和 Microsoft Edge WebView2；请先安装 requirements-windows.txt。\n')
            if sys.platform == 'darwin':
                parser.exit(1, 'macOS 编辑器需要 PyObjC；请用 .venv/bin/python tools/editor.py 启动，依赖见 requirements-macos.txt。\n')
            system_python = Path('/usr/bin/python3')
            if system_python.exists() and Path(sys.executable).resolve() != system_python.resolve():
                os.execv(str(system_python), [str(system_python), str(Path(__file__).resolve()), *sys.argv[1:]])
            parser.exit(1, '独立窗口需要系统 Python 的 GTK 3、PyGObject 与 WebKit2 4.1。\n')
    with EditorServer(('127.0.0.1', args.port)) as server:
        url = f'http://127.0.0.1:{server.server_port}/'
        if args.headless:
            print(f'本地测试服务：{url}\n按 Ctrl+C 退出。', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        else:
            server.daemon_threads = False
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                run(url, server)
            except KeyboardInterrupt:
                pass
            finally:
                server.shutdown()
                worker.join()


if __name__ == '__main__':
    main()
