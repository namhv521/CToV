import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

import app
import core
import render


class BatchAndDaysTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='commentcut-batch-')
        self.data = Path(self.temp.name)
        for name in ('assets', 'projects', 'jobs', 'batches', 'cache', 'project', 'output', 'Vid_nen', 'img_meme', 'mp3_meme'):
            (self.data / name).mkdir()
        for module in (core, render, app):
            mocked = patch.object(module, 'DATA', self.data)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.addCleanup(self.temp.cleanup)

    def make_screenshot(self, aid='a' * 32):
        path = self.data / 'assets' / f'{aid}.png'
        if not path.exists():
            Image.new('RGB', (200, 120), 'white').save(path)
            core.write(path.with_suffix('.json'), {'id': aid, 'kind': 'image', 'file': path.name})
        return aid

    def test_auto_project_name_from_post_and_fallback(self):
        self.assertEqual(
            core.auto_project_name('   \nChuyện đi làm hôm nay cực hài\nDòng hai', 'minh', 'https://www.threads.com/@minh/post/ABC'),
            'Chuyện đi làm hôm nay cực hài',
        )
        self.assertEqual(
            core.auto_project_name('', 'minh_99', 'https://www.tiktok.com/@minh_99/video/7412345'),
            '@minh_99 · 7412345',
        )
        self.assertEqual(
            core.auto_project_name('', '', 'https://www.threads.com/@linh/post/XYZ123'),
            '@linh · XYZ123',
        )

    def test_parse_txt_file_filters_comments_duplicates_and_invalid_urls(self):
        content = (
            '﻿# Danh sách bài cần crawl\n'
            'https://www.threads.com/@a/post/ONE\n\n'
            'https://www.tiktok.com/@b/video/12345\n'
            'https://www.threads.com/@a/post/ONE\n'
            'http://insecure.example.com/post\n'
        ).encode('utf-8')
        with TestClient(app.app) as client:
            res = client.post('/api/batch-crawl/parse', files={'file': ('urls.txt', content, 'text/plain')})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['count'], 2)
        self.assertEqual(body['urls'], [
            'https://www.threads.com/@a/post/ONE',
            'https://www.tiktok.com/@b/video/12345',
        ])
        self.assertEqual(len(body['invalid']), 1)
        self.assertEqual(body['invalid'][0]['line'], 6)

    def test_crawl_days_uses_crawl_date_not_post_date_and_supports_legacy_captures(self):
        aid = self.make_screenshot()
        p1 = core.Project(
            name='Bài crawl ngày 10',
            url='https://www.threads.com/@u1/post/P1',
            crawl_date='2026-11-10',
            crawled_at='2026-11-10T09:30:00+07:00',
            comments=[core.Comment(text='C1', image=aid)],
        )
        p2 = core.Project(
            name='Bài cũ suy ra từ captured_at',
            url='https://www.threads.com/@u2/post/P2',
            comments=[core.Comment(text='C2', image=aid, captured_at='2026-11-03T10:00:00+00:00')],
        )
        with TestClient(app.app) as client:
            client.post('/api/projects', json=p1.model_dump())
            client.post('/api/projects', json=p2.model_dump())
            days = client.get('/api/crawl-days').json()
        self.assertEqual([d['date'] for d in days], ['2026-11-10', '2026-11-03'])
        self.assertEqual(days[0]['projects'][0]['name'], 'Bài crawl ngày 10')
        self.assertEqual(days[1]['projects'][0]['name'], 'Bài cũ suy ra từ captured_at')

    def test_batch_crawl_30_comments_splits_into_3_videos_of_10_and_handles_partial(self):
        aid = self.make_screenshot()
        (self.data / 'Vid_nen' / 'bg.mp4').write_bytes(b'bg')

        async def fake_collect(url, limit, progress=None):
            is_first = 'ONE' in url
            count = 30 if is_first else 23
            return {
                'url': url,
                'post': 'Tiêu đề bài viết tự động số 1' if is_first else '',
                'author': 'tacgia_hai',
                'post_image': aid if is_first else '',
                'post_captured_at': '2026-11-10T10:00:00+07:00' if is_first else '',
                'post_capture_error': '' if is_first else 'Thiếu bài gốc',
                'comments': [{'id': str(i), 'author': 'User', 'text': f'Bình luận {i}', 'likes': 100 - i, 'image': aid}
                             for i in range(count)],
                'crawl_note': f'Đã lấy {count} bình luận.',
            }

        rendered_groups = {}
        rendered_voices = {}

        def fake_render(project, folder, progress, cancelled):
            groups = core.script_groups(project.comments, project.options)
            rendered_groups[project.name] = [len(g) for g in groups]
            rendered_voices[project.name] = (project.options.provider, project.options.elevenlabs_voices)
            files = [f'{project.name} - {idx:02}.mp4' for idx in range(1, len(groups) + 1)]
            core.write(folder / 'timeline.json', {'files': files})
            return files

        with TestClient(app.app) as client, \
                patch('collector.collect', fake_collect), \
                patch('app.render', fake_render), \
                patch('speech.settings', return_value={'elevenlabs_key':'test','elevenlabs_voice':'legacy'}), \
                patch('app.executable', return_value='ffmpeg'):
            res = client.post('/api/batch-crawl', json={
                'urls': [
                    'https://www.threads.com/@u/post/ONE',
                    'https://www.tiktok.com/@tacgia_hai/video/999888',
                ],
                'limit': 30,
                'auto_render': True,
                'options': core.Options(
                    split_mode='comments',
                    comments_per_video=10,
                    elevenlabs_voices=('one', 'two', 'three', 'four'),
                    use_meme_image=False,
                    use_meme_sound=False,
                ).model_dump(),
            })
            self.assertEqual(res.status_code, 200)
            bid = res.json()['id']

            deadline = time.monotonic() + 5
            batch = None
            while time.monotonic() < deadline:
                batch = client.get(f'/api/batch-crawl/{bid}').json()
                all_jobs_done = all(
                    it.get('job', {}).get('status') == 'done'
                    for it in batch['items'] if it.get('job_id')
                )
                if batch['status'] == 'done' and all_jobs_done and len(rendered_groups) == 2:
                    break
                time.sleep(0.05)

            self.assertEqual(batch['status'], 'done')
            self.assertEqual(list(rendered_voices.values()),
                             [('elevenlabs', ('one', 'two', 'three', 'four'))] * 2)
            self.assertEqual(batch['items'][0]['name'], 'Tiêu đề bài viết tự động số 1')
            self.assertEqual(batch['items'][1]['name'], '@tacgia_hai · 999888')
            self.assertEqual(rendered_groups['Tiêu đề bài viết tự động số 1'], [10, 10, 10])
            self.assertEqual(rendered_groups['@tacgia_hai · 999888'], [10, 10, 3])

            days = client.get('/api/crawl-days').json()
            self.assertEqual(len(days), 1)
            self.assertEqual(days[0]['project_count'], 2)
            self.assertEqual(days[0]['comment_count'], 53)
            self.assertEqual(days[0]['rendered_videos'], 6)


if __name__ == '__main__':
    unittest.main()
