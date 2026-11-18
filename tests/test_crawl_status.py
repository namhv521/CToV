import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image
import app
import core


class CrawlStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='commentcut-crawl-status-')
        self.data = Path(self.temp.name)
        for name in ('assets', 'projects', 'jobs', 'batches', 'cache', 'project', 'output', 'Vid_nen', 'img_meme', 'mp3_meme'):
            (self.data / name).mkdir()
        for mod in (core, app):
            m = patch.object(mod, 'DATA', self.data)
            m.start()
            self.addCleanup(m.stop)
        self.addCleanup(self.temp.cleanup)

    def test_batch_progress_and_completed_status(self):
        aid = 'a' * 32
        shot = self.data / 'assets' / f'{aid}.png'
        Image.new('RGB', (200, 100), 'white').save(shot)
        core.write(shot.with_suffix('.json'), {'id': aid, 'kind': 'image', 'file': shot.name})

        async def collect(url, limit, progress):
            progress({'seen': 250, 'captured': 120, 'failed': 0})
            return {
                'url': url,
                'post': 'Bài kiểm tra',
                'author': 'tacgia',
                'post_image': aid,
                'post_captured_at': '2026-11-18T00:00:00Z',
                'post_capture_error': '',
                'comments': [{'text': f'Cmt {i}', 'image': aid} for i in range(120)],
                'crawl_note': 'Đã giữ 120 ảnh.',
            }

        with TestClient(app.app) as c, patch('collector.collect', collect):
            r = c.post('/api/batch-crawl', json={
                'urls': ['https://www.threads.com/@a/post/ABC'],
                'limit': 120,
                'auto_render': False,
            })
            self.assertEqual(r.status_code, 200)
            bid = r.json()['id']
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = c.get(f'/api/batch-crawl/{bid}').json()
                if state['status'] == 'done':
                    break
                time.sleep(0.02)
            self.assertEqual(state['status'], 'done')
            self.assertEqual(state['items'][0]['seen'], 250)
            self.assertEqual(state['items'][0]['captured'], 120)
            self.assertEqual(state['items'][0]['comment_count'], 120)

    def test_failed_crawl_marks_item_failed_and_completes_batch(self):
        async def collect(url, limit, progress):
            raise ValueError('Profile đang được dùng')

        with TestClient(app.app) as c, patch('collector.collect', collect):
            r = c.post('/api/batch-crawl', json={
                'urls': ['https://www.threads.com/@a/post/ABC'],
                'auto_render': False,
            })
            self.assertEqual(r.status_code, 200)
            bid = r.json()['id']
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = c.get(f'/api/batch-crawl/{bid}').json()
                if state['status'] == 'done':
                    break
                time.sleep(0.02)
            self.assertEqual(state['items'][0]['status'], 'failed')
            self.assertIn('Profile đang được dùng', state['items'][0]['message'])


if __name__ == '__main__':
    unittest.main()
