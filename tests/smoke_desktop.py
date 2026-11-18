"""Verify the released ZIP without Python, Chrome, or FFmpeg on the app's PATH."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile

import httpx
from playwright.sync_api import sync_playwright


def verify(archive):
    with tempfile.TemporaryDirectory(prefix='CommentCut kiểm thử ') as temp:
        home = Path(temp)
        with zipfile.ZipFile(archive) as release:
            assert not any('/data/' in name and not name.endswith('/') for name in release.namelist()), 'Release contains user data'
            release.extractall(home)
        app_home = home / 'CommentCut'
        bundle = app_home / '_internal'
        browser = next((bundle / 'browsers').glob('chromium-*/chrome-win64/chrome.exe'))
        data = app_home / 'data'
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(('PYTHON', 'PLAYWRIGHT', 'COMMENTCUT', 'FFMPEG', 'FFPROBE', 'ELEVENLABS'))}
        environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        process = subprocess.Popen([str(app_home / 'CommentCut.exe'), '--no-browser'], cwd=home,
                                   env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            with httpx.Client(base_url='http://127.0.0.1:8766', timeout=120, trust_env=False) as client:
                for _ in range(150):
                    assert process.poll() is None, 'EXE exited during startup'
                    try:
                        health = client.get('/api/health').raise_for_status().json()
                        break
                    except httpx.ConnectError:
                        time.sleep(.2)
                else:
                    raise AssertionError('EXE did not start')
                assert health['ffmpeg'] and Path(health['data']) == data, health
                assert client.get('/').status_code == 200
                assert len(client.get('/static/BeVietnamPro-Regular.ttf').content) > 1000
                assert client.get('/api/settings').json().get('elevenlabs_key') is False
                for name in ('Vid_nen', 'vid_meme', 'img_meme', 'mp3_meme'):
                    assert (data / name).is_dir(), name
                for name in ('capture_media.js', 'post_dom.js', 'threads_dom.js'):
                    assert (bundle / name).stat().st_size > 100, name

                bg_target = data / 'Vid_nen' / 'nền kiểm thử.mp4'
                subprocess.run(
                    [str(bundle / 'ffmpeg.exe'), '-hide_banner', '-loglevel', 'error', '-y',
                     '-f', 'lavfi', '-i', 'testsrc2=size=360x640:rate=30', '-t', '3',
                     '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(bg_target)],
                    check=True, env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                )

                with sync_playwright() as playwright:
                    chromium = playwright.chromium.launch(executable_path=str(browser), headless=True, env=environment)
                    try:
                        page = chromium.new_page(viewport={'width': 1440, 'height': 920})
                        page.goto(str(client.base_url))
                        page.get_by_role('heading', name='Sản xuất hàng loạt').wait_for(timeout=10000)
                        page.screenshot(path=str(home / 'desktop.png'))
                        screenshot = page.locator('body').screenshot()
                    finally:
                        chromium.close()
                image = client.post('/api/assets/image', files={'file': ('ảnh chụp.png', screenshot, 'image/png')}).raise_for_status().json()
                client.post('/api/settings', json={'elevenlabs_key': 'offline-smoke-placeholder',
                                                   'elevenlabs_voice': 'offlinevoice',
                                                   'elevenlabs_voices': ['offlinevoice']}).raise_for_status()
                project = {'name': 'Kiểm thử portable', 'comments': [{'text': '', 'image': image['id']}],
                           'options': {'read_post': False, 'use_meme_image': False, 'use_meme_sound': False,
                                       'resolution': 360, 'credit': 'KIỂM THỬ TIẾNG VIỆT'}}
                job = client.post('/api/jobs', json=project).raise_for_status().json()
                for _ in range(120):
                    job = client.get('/api/jobs/' + job['id']).raise_for_status().json()
                    if job['status'] not in ('queued', 'running'):
                        break
                    time.sleep(.5)
                assert job['status'] == 'done', job
                video = next(name for name in job['files'] if name.endswith('.mp4'))
                video_bytes = client.get('/api/jobs/' + job['id'] + '/files/' + video).raise_for_status().content
                output = home / 'result.mp4'
                output.write_bytes(video_bytes)
                probe = subprocess.run([str(bundle / 'ffprobe.exe'), '-v', 'error', '-show_streams', '-of', 'json', str(output)],
                                       capture_output=True, check=True, env=environment,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                streams = json.loads(probe.stdout)['streams']
                assert {stream['codec_type'] for stream in streams} == {'video', 'audio'}, streams
                print('PASS: clean ZIP, Unicode path, minimal PATH, EXE API, bundled Chromium, screenshots, fonts, real MP4 with audio/video')
        finally:
            process.terminate()
            process.wait(timeout=20)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', nargs='?', default='dist/CommentCut-Windows-x64.zip')
    arguments = parser.parse_args()
    verify(Path(arguments.archive).resolve())
