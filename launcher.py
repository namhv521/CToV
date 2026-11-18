"""Entry point for CommentCut Studio desktop application."""
import asyncio
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import traceback
from pathlib import Path
from threading import Thread
from time import sleep
from urllib.request import urlopen
import webbrowser


HOST, PORT = '127.0.0.1', 8766
URL = f'http://{HOST}:{PORT}'


def is_running():
    try:
        with urlopen(URL + '/api/health', timeout=.4) as response:
            status = json.load(response)
        return status.get('ok') is True and status.get('data') == os.environ['COMMENTCUT_DATA']
    except (OSError, ValueError, AttributeError):
        return False


def configure_runtime():
    bundle = Path(__file__).resolve().parent
    home = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else bundle
    data = Path(os.environ.get('COMMENTCUT_DATA') or home / 'data').resolve()
    for name in ('Vid_nen', 'vid_meme', 'img_meme', 'mp3_meme'):
        (data / name).mkdir(parents=True, exist_ok=True)
    os.environ['COMMENTCUT_DATA'] = str(data)
    for name in ('ffmpeg', 'ffprobe'):
        for directory in (bundle, home):
            companion = directory / (name + '.exe')
            if companion.is_file():
                os.environ.setdefault(name.upper() + '_PATH', str(companion))
                break
    if (bundle / 'browsers').is_dir():
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(bundle / 'browsers')
    return data


def find_system_browser():
    candidates = [
        shutil.which('chrome'),
        shutil.which('msedge'),
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    ]
    for item in candidates:
        if item and Path(item).is_file():
            return Path(item)
    return None


def open_desktop(browser, data, url):
    return subprocess.Popen(
        [
            str(browser),
            '--app=' + url,
            '--window-size=1440,920',
            '--user-data-dir=' + str(data / 'desktop-profile'),
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-background-mode',
            '--disable-extensions',
        ],
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )


def main():
    data = configure_runtime()
    logging.basicConfig(filename=data / 'desktop.log', encoding='utf-8', level=logging.INFO)
    if len(sys.argv) == 3 and sys.argv[1] == '--login':
        from collector import login
        asyncio.run(login(sys.argv[2]))
        return

    no_browser = '--no-browser' in sys.argv[1:]
    frozen = getattr(sys, 'frozen', False)
    browser = None
    if not no_browser:
        if frozen:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = Path(playwright.chromium.executable_path)
            if not browser.is_file():
                raise ValueError('Thiếu trình duyệt đi kèm. Hãy giải nén lại toàn bộ bản CommentCut portable.')
        else:
            browser = find_system_browser()

    if is_running():
        if not no_browser:
            if browser:
                open_desktop(browser, data, URL)
            else:
                webbrowser.open(URL)
        return

    import uvicorn
    from app import app

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_config=None, access_log=False))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((HOST, PORT))
    except OSError:
        listener.close()
        raise ValueError('Một bản CommentCut khác đang dùng cổng ứng dụng. Đóng bản đó rồi mở lại.') from None
    if no_browser:
        try:
            server.run(sockets=[listener])
        finally:
            listener.close()
        return

    thread = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        for _ in range(150):
            if server.started:
                break
            if not thread.is_alive():
                raise ValueError('Không khởi động được ứng dụng. Xem desktop.log trong thư mục data.')
            sleep(.2)
        else:
            raise ValueError('Ứng dụng khởi động quá lâu. Đóng rồi mở lại CommentCut.')
        if browser:
            window = open_desktop(browser, data, URL)
            rc = window.wait()
            if frozen and rc != 0:
                raise ValueError('Không mở được cửa sổ ứng dụng. Hãy giải nén lại toàn bộ bản portable.')
        else:
            webbrowser.open(URL)
            thread.join()
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logging.exception('CommentCut startup failed')
        if getattr(sys, 'frozen', False):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), 'CommentCut không khởi động được', 0x10)
        else:
            traceback.print_exc()
        sys.exit(1)
