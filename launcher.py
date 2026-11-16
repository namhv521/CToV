"""Entry point for the Windows executable."""
import asyncio
import json
import os
import sys
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


def open_when_ready():
    for _ in range(100):
        if is_running():
            webbrowser.open(URL)
            return
        sleep(.2)


if __name__ == '__main__':
    data = os.environ.get('COMMENTCUT_DATA') or str(Path(os.environ['LOCALAPPDATA']) / 'CommentCut')
    os.environ['COMMENTCUT_DATA'] = str(Path(data).resolve())
    for name in ('ffmpeg', 'ffprobe'):
        companion = Path(sys.executable).with_name(name + '.exe')
        if companion.is_file():
            os.environ.setdefault(name.upper() + '_PATH', str(companion))

    if len(sys.argv) == 3 and sys.argv[1] == '--login':
        from collector import login
        asyncio.run(login(sys.argv[2]))
    else:
        open_browser = '--no-browser' not in sys.argv[1:]
        if is_running():
            if open_browser:
                webbrowser.open(URL)
            sys.exit(0)

        import uvicorn
        from app import app

        if open_browser:
            Thread(target=open_when_ready, daemon=True).start()
        print(f'CommentCut: {URL}  |  Ctrl+C de tat.', flush=True)
        uvicorn.run(app, host=HOST, port=PORT)
