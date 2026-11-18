import asyncio
import base64
import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from playwright.async_api import async_playwright
from fastapi.testclient import TestClient
import core
import app
import capture


def photo():
    out = io.BytesIO()
    Image.new('RGB', (300, 200), 'red').save(out, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()


class OriginalPostTests(unittest.TestCase):
    def test_capture_root_threads_and_tiktok_without_replies(self):
        async def verify():
            with tempfile.TemporaryDirectory(prefix='commentcut-original-') as temp:
                data = Path(temp)
                (data / 'assets').mkdir()
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    try:
                        page = await browser.new_page()
                        await page.route('https://www.threads.com/**', lambda r: r.fulfill(body='<main></main>', content_type='text/html; charset=utf-8'))
                        await page.goto('https://www.threads.com/@root/post/ROOT')
                        await page.set_content(f'''<main><article data-pressable-container="true" style="width:400px;background:white">
                          <a href="/@root">Tác giả</a><span dir="auto"><a href="/@root/post/ROOT"><time>1h</time></a></span>
                          <span dir="auto">Bài viết gốc<div role="button">Translate</div></span><img src="{photo()}" width="300" height="200">
                          <footer>128 · Trả lời</footer>
                          <div aria-hidden="true"><span dir="auto">Reply to root...</span></div></article>
                          <article data-pressable-container="true" style="background:blue;height:100px"><a href="/@other/post/OTHER"><time>1m</time></a>Không chụp bình luận này</article></main>''')
                        capture_card = capture.capture_comment

                        async def capture_after_hydration(page, row, source, role):
                            await page.locator('article').first.evaluate('card => { card.outerHTML = card.outerHTML.replace(/ data-commentcut-original="true"/g, ""); }')
                            return await capture_card(page, row, source, role)

                        with patch('capture.DATA', data), patch('capture.capture_comment', capture_after_hydration):
                            result = await capture.capture_original_post(page, page.url)
                        self.assertEqual(result['text'], 'Bài viết gốc')
                        self.assertEqual(result['author'], 'Tác giả')
                        metadata = core.read(data / 'assets' / (result['image'] + '.json'))
                        self.assertEqual(metadata['role'], 'post_capture')
                        with Image.open(data / 'assets' / (result['image'] + '.png')) as image:
                            self.assertLess(image.height, 350)
                            self.assertEqual(image.getpixel((100, 100))[:3], (255, 0, 0))
                        self.assertEqual(await page.locator('[data-commentcut-original]').count(), 0)
                        await page.route('https://www.tiktok.com/**', lambda r: r.fulfill(body='<main></main>', content_type='text/html; charset=utf-8'))
                        await page.goto('https://www.tiktok.com/@root/video/123')
                        await page.set_content(f'''<article style="width:400px;background:white"><a data-e2e="browse-username">Root</a>
                          <p data-e2e="browse-video-desc">Original video</p><video poster="{photo()}" width="300" height="200"></video></article>
                          <aside data-e2e="comment-item">Other comment</aside>''')
                        with patch('capture.DATA', data):
                            result = await capture.capture_original_post(page, page.url)
                        self.assertEqual(result['text'], 'Original video')
                        with Image.open(data / 'assets' / (result['image'] + '.png')) as image:
                            self.assertEqual(image.getpixel((100, 100))[:3], (255, 0, 0))
                        await page.set_content('<article><p data-e2e="browse-video-desc">No safe root</p></article>')
                        before = set((data / 'assets').iterdir())
                        with patch('capture.DATA', data):
                            with self.assertRaisesRegex(ValueError, 'Chưa chụp được bài viết gốc'):
                                await capture.capture_original_post(page, page.url, timeout=100)
                        self.assertEqual(set((data / 'assets').iterdir()), before)
                    finally:
                        await browser.close()
        asyncio.run(verify())

    def test_batch_crawl_persists_original_image_and_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            for name in ('assets', 'projects', 'jobs', 'batches', 'cache', 'project', 'output', 'Vid_nen', 'img_meme', 'mp3_meme'):
                (data / name).mkdir()
            aid = 'd' * 32
            path = data / 'assets' / (aid + '.png')
            Image.new('RGB', (200, 100), 'gray').save(path)
            core.write(path.with_suffix('.json'), {'id': aid, 'kind': 'image', 'file': path.name, 'role': 'post_capture', 'source_url': 'https://www.threads.com/@root/post/ROOT'})

            async def collect(url, limit, progress):
                return {'url': url, 'post': 'Original', 'author': 'Root', 'post_image': aid,
                        'post_captured_at': '2026-11-04T00:00:00Z',
                        'comments': [{'text': 'Comment', 'image': aid}], 'crawl_note': 'Fixture'}

            with patch('core.DATA', data), patch('app.DATA', data), patch('collector.collect', collect), TestClient(app.app) as client:
                response = client.post('/api/batch-crawl', json={
                    'urls': ['https://www.threads.com/@root/post/ROOT'],
                    'auto_render': False,
                })
                self.assertEqual(response.status_code, 200)
                bid = response.json()['id']
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    batch = client.get(f'/api/batch-crawl/{bid}').json()
                    if batch['status'] == 'done':
                        break
                    time.sleep(0.02)
                pid = batch['items'][0]['project_id']
                saved = client.get('/api/projects/' + pid).json()
                self.assertEqual(saved['post_image'], aid)
                homes = list((data / 'project').glob('project*'))
                self.assertEqual(core.read(homes[0] / 'post.json')['image'], aid)
                self.assertEqual((homes[0] / 'images' / path.name).read_bytes(), path.read_bytes())

                # Saving stale capture fields for same URL preserves previous original post capture.
                stale = saved | {'post_image': '', 'post_captured_at': '', 'post_capture_error': 'old error'}
                stale['name'] = 'Edited title'
                self.assertEqual(client.post('/api/projects', json=stale).status_code, 200)
                restored = client.get('/api/projects/' + pid).json()
                self.assertEqual(restored['post_image'], aid)
                self.assertEqual(restored['post_capture_error'], '')
                self.assertEqual(restored['name'], 'Edited title')

                stale['url'] = 'https://www.threads.com/@root/post/OTHER'
                client.post('/api/projects', json=stale)
                self.assertEqual(client.get('/api/projects/' + pid).json()['post_image'], '')


if __name__ == '__main__':
    unittest.main()
