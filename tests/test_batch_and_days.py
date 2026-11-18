import io
import tempfile
import time
import unittest
import wave
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
        for name in ('assets', 'projects', 'jobs', 'batches', 'cache', 'project', 'output', 'Vid_nen', 'vid_meme', 'img_meme', 'mp3_meme'):
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

    def make_wav(self, path: Path, seconds=1.0):
        with wave.open(str(path), 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\0\0' * int(seconds * 16000))

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
            '\ufeff# Danh sách bài cần crawl\n'
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

    def test_custom_media_folders_and_video_meme_and_combined_random_pool(self):
        aid = self.make_screenshot()
        with tempfile.TemporaryDirectory(prefix='commentcut-ext-media-') as ext_tmp:
            ext = Path(ext_tmp)
            bg_dir = ext / 'Kho_Nen'
            vm_dir = ext / 'Kho_Video_Meme'
            im_dir = ext / 'Kho_Anh_Meme'
            sm_dir = ext / 'Kho_Tieng_Meme'
            for d in (bg_dir, vm_dir, im_dir, sm_dir):
                d.mkdir()

            render.run([
                '-f', 'lavfi', '-i', 'color=c=navy:s=360x640:r=30', '-t', '2',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', bg_dir / 'gameplay.mp4',
            ], self.data, lambda: False)
            render.run([
                '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30',
                '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1.2',
                '-t', '1.2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', vm_dir / 'laugh_clip.mp4',
            ], self.data, lambda: False)
            Image.new('RGB', (160, 160), 'yellow').save(im_dir / 'doge_diff_name.png')
            self.make_wav(sm_dir / 'vine_boom_diff_name.wav', 1.0)

            voice = self.data / 'voice.wav'
            self.make_wav(voice, 0.5)

            with TestClient(app.app) as client:
                for kind, folder in (('background', bg_dir), ('meme_video', vm_dir), ('image', im_dir), ('sound', sm_dir)):
                    r = client.post('/api/media-folders', json={'kind': kind, 'path': str(folder)})
                    self.assertEqual(r.status_code, 200)
                diag = client.get('/api/health').json()['media']
                self.assertEqual(diag['background_count'], 1)
                self.assertEqual(diag['meme_video_count'], 1)
                self.assertEqual(diag['meme_image_count'], 1)
                self.assertEqual(diag['meme_sound_count'], 1)
                self.assertTrue(diag['folders']['meme_video']['is_custom'])

            # 1. Image without Sound is strictly rejected
            bad_project = core.Project(
                comments=[core.Comment(text='A', image=aid), core.Comment(text='B', image=aid)],
                options=core.Options(use_meme_video=False, use_meme_image=True, use_meme_sound=False, resolution=360),
            )
            bad_folder = self.data / 'jobs' / core.uid()
            bad_folder.mkdir()
            with self.assertRaisesRegex(ValueError, 'bắt buộc phải bật kèm Tiếng Meme'):
                render.render(bad_project, bad_folder, lambda *_: None, lambda: False)

            # 2. Video Meme ONLY (no Image, no Sound required!)
            vid_only_project = core.Project(
                name='Chỉ Video Meme',
                comments=[core.Comment(text='Cmt 1', image=aid), core.Comment(text='Cmt 2', image=aid)],
                options=core.Options(
                    read_post=False, resolution=360,
                    use_meme_video=True, use_meme_image=False, use_meme_sound=False,
                ),
            )
            f1 = self.data / 'jobs' / core.uid()
            f1.mkdir()
            with patch('render.synthesize', return_value=voice):
                out1 = render.render(vid_only_project, f1, lambda *_: None, lambda: False)
            mp4_1 = next(x for x in out1 if x.endswith('.mp4'))
            out_dir_1 = core.read(f1 / 'timeline.json')['output_project']
            self.assertEqual({s['codec_type'] for s in core.probe(self.data / 'output' / out_dir_1 / mp4_1)['streams']}, {'video', 'audio'})
            scenes_1 = core.read(f1 / 'timeline.json')['scenes']
            self.assertEqual([s.get('meme_type') for s in scenes_1 if s['kind'] == 'meme'], ['video'])

            # 3. ALL 3 ENABLED (Video Meme + mismatched-filename Image+Sound Meme in unified random pool)
            all3_project = core.Project(
                name='Trộn cả 3 loại Meme',
                comments=[core.Comment(text=f'Cmt {i}', image=aid) for i in range(3)],
                options=core.Options(
                    read_post=False, resolution=360,
                    use_meme_video=True, use_meme_image=True, use_meme_sound=True,
                ),
            )
            f2 = self.data / 'jobs' / core.uid()
            f2.mkdir()
            with patch('render.synthesize', return_value=voice):
                out2 = render.render(all3_project, f2, lambda *_: None, lambda: False)
            self.assertTrue(any(x.endswith('.mp4') for x in out2))
            scenes_2 = core.read(f2 / 'timeline.json')['scenes']
            meme_types = {s.get('meme_type') for s in scenes_2 if s['kind'] == 'meme'}
            self.assertEqual(meme_types, {'video', 'image_sound'})

    def test_preset_and_library_upload_and_delete(self):
        buf = io.BytesIO()
        Image.new('RGB', (120, 120), 'orange').save(buf, format='PNG')
        with TestClient(app.app) as client:
            up = client.post('/api/assets/image', files={'file': ('meme_1.png', buf.getvalue(), 'image/png')})
            self.assertEqual(up.status_code, 200)
            item = up.json()
            self.assertEqual(item['source_folder'], 'img_meme')
            self.assertTrue((self.data / 'img_meme' / 'meme_1.png').is_file())
            self.assertEqual(client.delete(f"/api/assets/{item['id']}").status_code, 200)
            self.assertEqual(client.get('/api/assets').json(), [])

            p = client.post('/api/preset', json={
                'limit': 50,
                'auto_render': False,
                'options': {'resolution': 1080, 'comments_per_video': 12, 'split_mode': 'comments', 'use_meme_video': True},
            }).json()
            self.assertEqual(p['limit'], 50)
            self.assertTrue(client.get('/api/preset').json()['options']['use_meme_video'])

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
                patch('speech.settings', return_value={'elevenlabs_key': 'test', 'elevenlabs_voice': 'legacy',
                                                       'elevenlabs_voices': ['saved-one', 'saved-two', 'saved-three']}), \
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
                    use_meme_video=False,
                    use_meme_image=False,
                    use_meme_sound=False,
                ).model_dump(),
            })
            self.assertEqual(res.status_code, 200)
            bid = res.json()['id']

            deadline = time.monotonic() + 30
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
                             [('elevenlabs', ('saved-one', 'saved-two', 'saved-three'))] * 2)
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
