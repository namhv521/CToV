"""Portable startup works independently of installed tools and the working directory."""
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher


class LauncherTests(unittest.TestCase):
    def test_portable_runtime_uses_adjacent_data_and_bundled_tools(self):
        with tempfile.TemporaryDirectory(prefix='CommentCut tiếng Việt ') as temp:
            home = Path(temp)
            bundle = home / '_internal'
            (bundle / 'browsers').mkdir(parents=True)
            for name in ('ffmpeg', 'ffprobe'):
                (bundle / (name + '.exe')).touch()
            with patch.dict(os.environ, {}, clear=True), patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, 'executable', str(home / 'CommentCut.exe')), \
                    patch.object(launcher, '__file__', str(bundle / 'launcher.py')):
                data = launcher.configure_runtime()
                self.assertEqual(data, home / 'data')
                self.assertEqual(os.environ['COMMENTCUT_DATA'], str(data))
                for name in ('ffmpeg', 'ffprobe'):
                    self.assertEqual(os.environ[name.upper() + '_PATH'], str(bundle / (name + '.exe')))
                self.assertEqual(os.environ['PLAYWRIGHT_BROWSERS_PATH'], str(bundle / 'browsers'))
                for name in ('Vid_nen', 'vid_meme', 'img_meme', 'mp3_meme'):
                    self.assertTrue((data / name).is_dir())

    def test_explicit_data_and_tools_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            custom = Path(temp) / 'custom'
            with patch.dict(os.environ, {'COMMENTCUT_DATA': str(custom), 'FFMPEG_PATH': 'custom-ffmpeg'}, clear=True):
                self.assertEqual(launcher.configure_runtime(), custom)
                self.assertEqual(os.environ['FFMPEG_PATH'], 'custom-ffmpeg')

    def test_crawler_uses_bundled_browser_in_exe_and_chrome_in_source(self):
        from collector import browser_options
        with patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(browser_options(), {'channel': 'chromium'})
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(browser_options(), {'channel': 'chrome'})

    def test_desktop_window_uses_local_app_url_and_separate_profile(self):
        with tempfile.TemporaryDirectory() as temp, patch('launcher.subprocess.Popen') as process:
            launcher.open_desktop(Path('browser/chrome.exe'), Path(temp), launcher.URL)
            command = process.call_args.args[0]
            self.assertIn('--app=' + launcher.URL, command)
            self.assertIn('--user-data-dir=' + str(Path(temp) / 'desktop-profile'), command)
            self.assertNotIn('--no-sandbox', command)

    def test_closing_desktop_window_stops_real_local_server(self):
        import app
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            browser = data / 'chrome.exe'
            browser.touch()
            for name in ('jobs', 'batches'):
                (data / name).mkdir()
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            with patch.object(app, 'DATA', data), patch('launcher.configure_runtime', return_value=data), \
                    patch('launcher.logging.basicConfig'), patch('launcher.is_running', return_value=False), \
                    patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'argv', ['CommentCut.exe']), \
                    patch.object(launcher, 'PORT', port), patch('launcher.open_desktop') as window, \
                    patch('playwright.sync_api.sync_playwright') as playwright:
                playwright.return_value.__enter__.return_value.chromium.executable_path = str(browser)
                window.return_value.wait.return_value = 0
                launcher.main()
                window.assert_called_once()
            with socket.socket() as client:
                self.assertNotEqual(client.connect_ex(('127.0.0.1', port)), 0)


if __name__ == '__main__':
    unittest.main()
