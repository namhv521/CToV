"""Project storage and real FFmpeg outro integration, without online TTS."""
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import core
import render
import app
from PIL import Image
from fastapi.testclient import TestClient


class ProjectMediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='commentcut-project-')
        self.data = Path(self.temp.name)
        for name in ('assets', 'projects', 'jobs', 'cache', 'project', 'output', 'Vid_nen', 'vid_meme', 'img_meme', 'mp3_meme'):
            (self.data / name).mkdir()
        for module in (core, render, app):
            mocked = patch.object(module, 'DATA', self.data)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.addCleanup(self.temp.cleanup)
        shuffle=patch('render.random.shuffle',side_effect=lambda deck:deck.reverse())
        shuffle.start();self.addCleanup(shuffle.stop)

    def with_screenshots(self, project):
        """Supply an existing screenshot fixture for render tests that focus on other behavior."""
        aid='a'*32
        source=self.data/'assets'/(aid+'.png')
        if not source.exists():
            image=Image.new('RGB',(400,180),'white')
            from PIL import ImageDraw
            ImageDraw.Draw(image).rectangle((20,20,380,160),fill='gray')
            image.save(source)
            core.write(source.with_suffix('.json'),{'id':aid,'kind':'image','file':source.name})
        if project.post and not project.post_image:project.post_image=aid
        for comment in project.comments:
            if not comment.image:comment.image=aid
        return project

    def wav(self, path, seconds):
        with wave.open(str(path), 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\0\0' * int(seconds * 16000))

    def test_folder_media_natural_order_and_resolution(self):
        for name in ('10.png', '2.png', '1.png'):
            Image.new('RGB', (20, 20)).save(self.data / 'img_meme' / name)
        rows = core.assets()
        self.assertEqual([r['name'] for r in rows], ['1.png', '2.png', '10.png'])
        self.assertEqual(core.asset(rows[0]['id'], 'image').name, '1.png')
        with self.assertRaises(ValueError): core.asset(rows[0]['id'], 'sound')

    def test_project_snapshot_and_numbering(self):
        image = self.data / 'assets' / (core.uid() + '.png')
        Image.new('RGB', (20, 20)).save(image)
        core.write(image.with_suffix('.json'), {'id': image.stem, 'kind': 'image', 'file': image.name})
        project = core.Project(post='Bài gốc', comments=[core.Comment(text='Ảnh thật', image=image.stem)])
        with TestClient(app.app) as client:
            first = client.post('/api/projects', json=project.model_dump()).json()
            second = client.post('/api/projects', json=project.model_dump()).json()
            other = client.post('/api/projects', json=core.Project().model_dump()).json()
        self.assertEqual(first['folder'], 'project1')
        self.assertEqual(second['folder'], 'project1')
        self.assertEqual(other['folder'], 'project2')
        home = self.data / 'project' / 'project1'
        self.assertEqual((home / 'images' / image.name).read_bytes(), image.read_bytes())
        self.assertEqual(core.read(home / 'comments' / 'comments.json')[0]['text'], 'Ảnh thật')

    def test_real_render_between_comments_paths_download_and_no_overwrite(self):
        background = self.data / 'Vid_nen' / 'background.mp4'
        render.run(['-f', 'lavfi', '-i', 'color=c=blue:s=360x640:r=30', '-t', '1',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', background], self.data, lambda: False)
        for number in (1, 2, 10):
            Image.new('RGB', (120, 100), 'red').save(self.data / 'img_meme' / f'{number}.png')
            self.wav(self.data / 'mp3_meme' / f'{number}.wav', 5)
        voice = self.data / 'voice.wav'
        self.wav(voice, 6)
        project = core.Project(post='Tên bài: kiểm tra?', comments=[core.Comment(text=f'Bình luận {n}') for n in range(3)])
        project.options.read_post = False
        project.options.speed = 1
        project.options.resolution = 360
        project.options.max_seconds = 15
        jid = core.uid()
        folder = self.data / 'jobs' / jid
        folder.mkdir()
        with patch('render.synthesize', return_value=voice), patch('render.random.choice', side_effect=lambda rows: rows[0]) as choice:
            files = render.render(self.with_screenshots(project), folder, lambda *_: None, lambda: False)
        choice.assert_called_once()
        manifest = core.read(folder / 'timeline.json')
        output = self.data / 'output' / 'project1'
        videos = [f for f in files if f.endswith('.mp4')]
        self.assertEqual(len(videos), 2)
        self.assertTrue(videos[0].startswith('Tên bài_ kiểm tra_'))
        for number, video in enumerate(videos, 1):
            scenes = [s for s in manifest['scenes'] if s['part'] == number]
            self.assertEqual(scenes[-1]['kind'], 'comment')
            memes=[scene for scene in scenes if scene['kind']=='meme']
            self.assertEqual(len(memes),1 if number==1 else 0)
            if memes:
                self.assertEqual(memes[0]['meme_name'],'1.png')
                work=core.project_folder(project)/'renders'/folder.name
                self.assertLessEqual(core.duration(work/memes[0]['file']),2.1)
            self.assertLessEqual(core.duration(output / video), 15.15)
            self.assertEqual({s['codec_type'] for s in core.probe(output / video)['streams']}, {'video', 'audio'})
        core.write(folder / 'job.json', {'id': jid, 'status': 'done', 'files': files})
        with TestClient(app.app) as client:
            response = client.get(f'/api/jobs/{jid}/files/{videos[0]}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, (output / videos[0]).read_bytes())
        before = [(output / f).read_bytes() for f in videos]
        self.assertFalse((core.project_folder(project)/'meme_state.json').exists())
        project.comments = project.comments[:2]
        project.options.split_mode='comments'
        project.options.comments_per_video=2
        second = self.data / 'jobs' / core.uid()
        second.mkdir()
        with patch('render.synthesize', return_value=voice):
            newer = render.render(self.with_screenshots(project), second, lambda *_: None, lambda: False)
        self.assertTrue(any('(2)' in f for f in newer if f.endswith('.mp4')))
        second_scenes=core.read(second/'timeline.json')['scenes']
        self.assertEqual([scene['meme_name'] for scene in second_scenes if scene['kind']=='meme'],['1.png'])
        self.assertEqual(before, [(output / f).read_bytes() for f in videos])
        (self.data/'img_meme'/'10.png').unlink()
        (self.data/'mp3_meme'/'10.wav').unlink()
        with patch('render.synthesize',return_value=voice):
            render.render(self.with_screenshots(project), second, lambda *_: None, lambda: False)

    def test_missing_pair_fails_before_speech(self):
        background = self.data / 'Vid_nen' / 'background.mp4'
        background.write_bytes(b'not needed by preflight')
        Image.new('RGB', (20, 20)).save(self.data / 'img_meme' / '1.png')
        project = core.Project(comments=[core.Comment(text='Test'),core.Comment(text='Next')], options=core.Options(split_mode='comments'))
        folder = self.data / 'jobs' / core.uid()
        folder.mkdir()
        with patch('render.synthesize') as speech:
            with self.assertRaisesRegex(ValueError, 'Tiếng Meme đang trống'):
                render.render(self.with_screenshots(project), folder, lambda *_: None, lambda: False)
            speech.assert_not_called()

    def test_meme_shuffle_cycles_reset_per_video_and_last_two_seconds(self):
        (self.data/'Vid_nen'/'background.mp4').touch()
        self.wav(self.data/'voice.wav',.1)
        for number in range(3):
            Image.new('RGB',(20,20),'red').save(self.data/'img_meme'/f'{number}.png')
            self.wav(self.data/'mp3_meme'/f'{number}.wav',5)
        project=core.Project(comments=[core.Comment(text=str(i)) for i in range(16)],
                             options=core.Options(split_mode='comments',comments_per_video=8,resolution=360,max_seconds=60))
        home=core.project_folder(project)
        core.write(home/'meme_state.json',{'next':999})  # Old cursor must not exhaust the new deck.
        folder=self.data/'jobs'/core.uid();folder.mkdir()
        def fake_run(args,*_args,**_kwargs):Path(args[-1]).touch()
        with patch('render.run',side_effect=fake_run),patch('render.synthesize',return_value=self.data/'voice.wav'),patch('render.duration',return_value=5),patch('render.random.shuffle',side_effect=lambda deck:deck.reverse()) as shuffle:
            render.render(self.with_screenshots(project),folder,lambda *_:None,lambda:False)
        scenes=core.read(folder/'timeline.json')['scenes']
        for part in (1,2):
            memes=[s for s in scenes if s['part']==part and s['kind']=='meme']
            self.assertEqual(len(memes),7)
            self.assertEqual([s['meme_name'] for s in memes],['0.png','1.png','2.png']*2+['0.png'])
            for scene in memes:
                self.assertEqual(scene['seconds'],2)
                self.assertEqual(Path(scene['audio']).stem,Path(scene['meme_name']).stem)
        self.assertEqual(shuffle.call_count,6)

    def test_sequential_export_survives_later_tts_failure_and_reuses_prepared_media(self):
        (self.data/'Vid_nen'/'background.mp4').touch()
        voice=self.data/'voice.wav';self.wav(voice,.1)
        project=self.with_screenshots(core.Project(comments=[core.Comment(text=t) for t in ('One','Two','Three')],
            options=core.Options(split_mode='comments',comments_per_video=2,resolution=360,
                                 use_meme_image=False,use_meme_sound=False)))
        folder=self.data/'jobs'/core.uid();folder.mkdir()
        events=[]
        def fake_run(args,*_args,**_kwargs):
            events.append(Path(args[-1]).name);Path(args[-1]).touch()
        def speech(text,*_args):
            if text=='Three':
                self.assertTrue(any(name=='export-01.mp4' for name in events))
                raise ValueError('second video failed')
            return voice
        with patch('render.run',side_effect=fake_run),patch('render.synthesize',side_effect=speech),patch('render.duration',return_value=1):
            with self.assertRaisesRegex(ValueError,'second video failed'):
                render.render(project,folder,lambda *_:None,lambda:False)
        manifest=core.read(folder/'timeline.json')
        self.assertEqual(len([name for name in manifest['files'] if name.endswith('.mp4')]),1)
        self.assertTrue((self.data/'output'/manifest['output_project']/manifest['files'][0]).exists())
        core.write(folder/'job.json',{'id':folder.name,'status':'failed','files':manifest['files']})
        with TestClient(app.app) as client:
            self.assertEqual(client.get(f'/api/jobs/{folder.name}/files/{manifest["files"][0]}').status_code,200)
            self.assertEqual(client.get(f'/api/jobs/{folder.name}/files/unlisted.mp4').status_code,404)
        second=self.data/'jobs'/core.uid();second.mkdir();events.clear()
        with patch('render.run',side_effect=fake_run),patch('render.synthesize',return_value=voice),patch('render.duration',return_value=1),patch('render.card') as card:
            render.render(project,second,lambda *_:None,lambda:False)
            card.assert_not_called()
        self.assertFalse(any(name.endswith('.partial.wav') for name in events))

    def test_script_groups_even_presets_and_selection_order(self):
        comments = [core.Comment(text=str(i), selected=i != 4) for i in range(24)]
        options = core.Options(split_mode='even', video_count=3)
        groups = core.script_groups(comments, options)
        self.assertEqual([len(g) for g in groups], [8, 8, 7])
        expected = [c.id for c in comments if c.selected]
        self.assertEqual([c.id for group in groups for c in group], expected)
        for size, lengths in ((5, [5,5,5,5,3]), (7, [7,7,7,2]), (9, [9,9,5])):
            options.split_mode = 'comments'
            options.comments_per_video = size
            groups = core.script_groups(comments, options)
            self.assertEqual([len(g) for g in groups], lengths)
            self.assertEqual([c.id for group in groups for c in group], expected)
        options.split_mode = 'even'
        options.video_count = 24
        with self.assertRaisesRegex(ValueError, 'vượt số bình luận'):
            core.script_groups(comments, options)
        for field in ('video_count', 'comments_per_video'):
            for value in (0, 121, 1.5, True):
                with self.assertRaises(ValueError): core.Options(**{field: value})
        with TestClient(app.app) as client:
            project = core.Project(comments=comments, options=options)
            response = client.post('/api/jobs', json=project.model_dump())
            self.assertEqual(response.status_code, 400)
            self.assertEqual(list((self.data / 'jobs').iterdir()), [])

    def batch_media(self, number=3):
        background = self.data / 'Vid_nen' / 'background.mp4'
        render.run(['-f', 'lavfi', '-i', 'color=c=blue:s=360x640:r=30', '-t', '1',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', background], self.data, lambda: False)
        for index in range(1, number + 1):
            Image.new('RGB', (120, 100), 'red').save(self.data / 'img_meme' / f'{index}.png')
            self.wav(self.data / 'mp3_meme' / f'{index}.wav', .3)
        voice = self.data / 'voice.wav'
        self.wav(voice, .3)
        return voice

    def test_real_batch_render_repeats_intro_and_keeps_exact_groups(self):
        voice = self.batch_media(5)
        project = core.Project(post='Mở đầu', comments=[core.Comment(text=f'Cmt {i}') for i in range(5)])
        project.options = core.Options(split_mode='even', video_count=3, resolution=360)
        folder = self.data / 'jobs' / core.uid()
        folder.mkdir()
        with patch('render.synthesize', return_value=voice) as speech:
            files = render.render(self.with_screenshots(project), folder, lambda *_: None, lambda: False)
        self.assertEqual(speech.call_count, 6)  # Intro is synthesized once and reused.
        manifest = core.read(folder / 'timeline.json')
        self.assertEqual(len([f for f in files if f.endswith('.mp4')]), 3)
        seen = []
        for index, size in enumerate((2, 2, 1), 1):
            scenes = [s for s in manifest['scenes'] if s['part'] == index]
            self.assertEqual(scenes[0]['text'], 'Mở đầu')
            self.assertEqual(scenes[0]['start'], 0)
            self.assertEqual(len([s for s in scenes if s['kind'] == 'comment']), size + 1)
            self.assertEqual(scenes[-1]['kind'],'comment')
            self.assertEqual(scenes[1]['kind'],'meme')
            self.assertEqual(scenes[2]['kind'],'comment')
            memes=[scene for scene in scenes if scene['kind']=='meme']
            self.assertEqual(len(memes),size)
            self.assertEqual(memes[0]['meme_name'],'1.png')
            seen.extend(scene['text'] for scene in scenes[1:] if scene['kind']=='comment')
        self.assertEqual(seen, [f'Cmt {i}' for i in range(5)])
        for video in (f for f in files if f.endswith('.mp4')):
            self.assertEqual({s['codec_type'] for s in core.probe(self.data/'output'/'project1'/video)['streams']}, {'audio','video'})

    def test_batch_duration_limit_does_not_silently_split(self):
        voice = self.batch_media(2)
        project = core.Project(comments=[core.Comment(text=str(i)) for i in range(3)],
                               options=core.Options(split_mode='comments', comments_per_video=5, max_seconds=15, resolution=360))
        folder = self.data / 'jobs' / core.uid()
        folder.mkdir()
        actual_duration = core.duration
        with patch('render.synthesize', return_value=voice), patch('render.duration', side_effect=lambda path: 6 if path.name.startswith('audio-') else actual_duration(path)):
            with self.assertRaisesRegex(ValueError, 'Video 1 cần'):
                render.render(self.with_screenshots(project), folder, lambda *_: None, lambda: False)
        self.assertEqual(list((self.data / 'output').rglob('*.mp4')), [])
        home = core.project_folder(project)
        self.assertFalse((home/'meme_state.json').exists())

    def test_batch_missing_memes_fails_before_tts(self):
        self.batch_media(1)
        (self.data/'mp3_meme'/'1.wav').unlink()
        project = core.Project(comments=[core.Comment(text=str(i)) for i in range(5)],
                               options=core.Options(split_mode='even', video_count=2))
        folder = self.data / 'jobs' / core.uid()
        folder.mkdir()
        with patch('render.synthesize') as speech:
            with self.assertRaisesRegex(ValueError, 'Tiếng Meme đang trống'):
                render.render(self.with_screenshots(project), folder, lambda *_: None, lambda: False)
            speech.assert_not_called()

    def test_media_only_render_keeps_picture_without_tts(self):
        self.batch_media(1)
        image = self.data/'assets'/(core.uid()+'.png')
        Image.new('RGB',(400,700),'lime').save(image)
        core.write(image.with_suffix('.json'),{'id':image.stem,'kind':'image','file':image.name})
        project = core.Project(comments=[core.Comment(text='🙏🏻',image=image.stem)],
                               options=core.Options(split_mode='comments',resolution=360,credit=''))
        folder=self.data/'jobs'/core.uid()
        folder.mkdir()
        with patch('render.synthesize') as speech:
            files=render.render(self.with_screenshots(project),folder,lambda *_:None,lambda:False)
            speech.assert_not_called()
        manifest=core.read(folder/'timeline.json')
        self.assertEqual(manifest['scenes'][0]['seconds'],3)
        self.assertEqual(manifest['scenes'][0]['audio'],'')
        self.assertTrue(any(name.endswith('.mp4') for name in files))

    def test_credit_moves_smoothly_across_comment_and_meme_boundaries(self):
        import subprocess
        import math
        self.batch_media(1)
        image = self.data/'assets'/(core.uid()+'.png')
        Image.new('RGB',(200,200),'gray').save(image)
        core.write(image.with_suffix('.json'),{'id':image.stem,'kind':'image','file':image.name})
        project = core.Project(comments=[core.Comment(image=image.stem),core.Comment(image=image.stem)],
                               options=core.Options(resolution=360,credit="CRE: Nguồn 'Nam' 100% [a]: test"))
        folder=self.data/'jobs'/core.uid();folder.mkdir()
        files=render.render(self.with_screenshots(project),folder,lambda *_:None,lambda:False)
        video=self.data/'output'/'project1'/next(name for name in files if name.endswith('.mp4'))
        frames=[0,29,89,90,91,98,99,100,180]
        select='+'.join(f'eq(n,{n})' for n in frames)
        result=subprocess.run([core.executable('ffmpeg'),'-v','error','-i',str(video),'-vf',f"select='{select}'",'-vsync','0','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
        frame_size=360*640*3
        self.assertEqual(len(result.stdout),len(frames)*frame_size)
        positions=[]
        watermark=render.credit_image(project.options)
        for i,number in enumerate(frames):
            frame=Image.frombytes('RGB',(360,640),result.stdout[i*frame_size:(i+1)*frame_size])
            pixels=frame.load()
            yellow=[(x,y) for y in range(640) for x in range(360) if pixels[x,y][0]>180 and pixels[x,y][1]>170 and pixels[x,y][2]<100]
            self.assertTrue(yellow)
            point=(min(x for x,y in yellow),min(y for x,y in yellow))
            expected=render.credit_position(360,640,watermark.width,watermark.height,number/30)
            self.assertLess(abs(point[0]-expected[0]),5)
            self.assertLess(abs(point[1]-expected[1]),5)
            positions.append(point)
        self.assertGreater(math.dist(positions[0],positions[-1]),100)
        for before,after in ((2,3),(3,4),(5,6),(6,7)):
            self.assertLessEqual(math.dist(positions[before],positions[after]),4)

    def test_credit_empty_long_unicode_and_no_static_duplicate(self):
        options=core.Options(resolution=360)
        for resolution in (360,720,1080):
            options.resolution=resolution
            options.credit='W'*70
            watermark=render.credit_image(options)
            self.assertLessEqual(watermark.width,resolution*.9+2)
            height=resolution*16//9
            for time in range(0,601):
                x,y=render.credit_position(resolution,height,watermark.width,watermark.height,time)
                self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
                self.assertLessEqual(x+watermark.width,resolution)
                self.assertLessEqual(y+watermark.height,height)
        options.resolution=360
        options.credit='Nguồn tiếng Việt'
        first=self.data/'first.png';second=self.data/'second.png'
        project=self.with_screenshots(core.Project(comments=[core.Comment(text='Test')]))
        render.card('Bình luận','Tác giả',0,options,first,project.comments[0].image)
        options.credit=''
        render.card('Bình luận','Tác giả',0,options,second,project.comments[0].image)
        self.assertEqual(first.read_bytes(),second.read_bytes())
        self.assertIsNone(render.credit_image(options))

    def test_card_preview_composites_credit_at_initial_position(self):
        import io
        with TestClient(app.app) as client:
            project=core.Project(options=core.Options(resolution=360,credit='CRE: Nguồn'))
            response=client.post('/api/card-preview',json=project.model_dump())
            self.assertEqual(response.status_code,200)
            with Image.open(io.BytesIO(response.content)) as image:
                self.assertEqual(image.size,(360,640))
                self.assertTrue(any(r>180 and g>170 and b<100 and a>0 for r,g,b,a in image.get_flattened_data()))
            project.options.credit=''
            response=client.post('/api/card-preview',json=project.model_dump())
            self.assertEqual(response.status_code,200)
            with Image.open(io.BytesIO(response.content)) as image:
                self.assertFalse(any(r>180 and g>170 and b<100 and a>0 for r,g,b,a in image.get_flattened_data()))

    def test_elevenlabs_samples_each_spoken_comment_across_parts(self):
        voice=self.batch_media(0)
        image=self.data/'assets'/(core.uid()+'.png')
        Image.new('RGB',(200,200),'gray').save(image)
        core.write(image.with_suffix('.json'),{'id':image.stem,'kind':'image','file':image.name})
        project=core.Project(post='Intro',comments=[core.Comment(text='One'),core.Comment(text='Two'),
                             core.Comment(text='🙏🏻',image=image.stem),core.Comment(text='Skip',selected=False),
                             core.Comment(text='Three'),core.Comment(text='Four')],
                             options=core.Options(provider='elevenlabs',elevenlabs_voices=('voice1','voice2','voice3','voice4'),
                             use_meme_image=False,use_meme_sound=False,split_mode='comments',comments_per_video=2,resolution=360))
        folder=self.data/'jobs'/core.uid();folder.mkdir()
        with patch('render.synthesize',return_value=voice) as speech, \
                patch('render.random.choice', side_effect=['voice4','voice4','voice2','voice1']) as choose:
            project.options.background = core.assets()[0]['id']
            files=render.render(self.with_screenshots(project),folder,lambda *_:None,lambda:False)
        self.assertEqual(choose.call_count, 4)
        self.assertEqual([(call.args[0],call.args[1].voice) for call in speech.call_args_list],
                         [('Intro','voice1'),('One','voice4'),('Two','voice4'),('Three','voice2'),('Four','voice1')])
        self.assertEqual(len([name for name in files if name.endswith('.mp4')]),3)
        self.assertEqual(project.options.voice,'')
        scenes=core.read(folder/'timeline.json')['scenes']
        self.assertFalse(any(scene['kind']=='meme' for scene in scenes))
        self.assertFalse((core.project_folder(project)/'meme_state.json').exists())

    def test_meme_image_and_sound_are_independent(self):
        voice=self.batch_media(1)
        photo=self.data/'img_meme'/'1.png'
        sound=self.data/'mp3_meme'/'1.wav'
        photo_bytes=photo.read_bytes();sound_bytes=sound.read_bytes()
        for use_image,use_sound in ((True,True),(False,True),(False,False)):
            with self.subTest(image=use_image,sound=use_sound):
                if use_image:photo.write_bytes(photo_bytes)
                else:photo.unlink(missing_ok=True)
                if use_sound:sound.write_bytes(sound_bytes)
                else:sound.unlink(missing_ok=True)
                project=core.Project(comments=[core.Comment(text='Test'),core.Comment(text='Next')],options=core.Options(resolution=360,
                                     use_meme_image=use_image,use_meme_sound=use_sound))
                folder=self.data/'jobs'/core.uid();folder.mkdir()
                with patch('render.synthesize',return_value=voice):
                    files=render.render(self.with_screenshots(project),folder,lambda *_:None,lambda:False)
                scenes=core.read(folder/'timeline.json')['scenes']
                memes=[s for s in scenes if s['kind']=='meme']
                self.assertEqual(len(memes),int(use_image or use_sound))
                if memes:
                    self.assertEqual(bool(memes[0]['audio']),use_sound)
                    self.assertEqual(memes[0]['seconds'],2)
                    work=core.project_folder(project)/'renders'/folder.name
                    with Image.open(work/memes[0]['picture']) as image:
                        self.assertEqual(image.getchannel('A').getbbox() is not None,use_image)
                self.assertTrue(any(name.endswith('.mp4') for name in files))

    def test_meme_geometry_upscales_and_preserves_ratio(self):
        options=core.Options(resolution=360)
        for width,height in ((40,20),(20,40),(20,100),(100,20)):
            source=self.data/f'{width}-{height}.png'
            Image.new('RGBA',(width,height),'red').save(source)
            target=self.data/'meme.png'
            render.meme_card(source,options,target)
            with Image.open(target) as image:
                x1,y1,x2,y2=image.getchannel('A').getbbox()
                self.assertLessEqual(x2-x1,216)
                self.assertLessEqual(y2-y1,384)
                self.assertLessEqual(abs((x1+x2)/2-180),1)
                self.assertLessEqual(abs((y1+y2)/2-288),1)
                self.assertLessEqual(abs((y2-y1)-(x2-x1)*height/width),1)
                self.assertTrue(x2-x1==216 or y2-y1==384)

    def test_intro_is_followed_by_meme_even_with_single_comment(self):
        voice=self.batch_media(1)
        project=core.Project(post='Intro',comments=[core.Comment(text='Only comment')],
                             options=core.Options(resolution=360,split_mode='comments'))
        folder=self.data/'jobs'/core.uid();folder.mkdir()
        with patch('render.synthesize',return_value=voice):
            render.render(self.with_screenshots(project),folder,lambda *_:None,lambda:False)
        scenes=core.read(folder/'timeline.json')['scenes']
        self.assertEqual([scene['kind'] for scene in scenes],['comment','meme','comment'])
        self.assertEqual([scene['text'] for scene in scenes if scene['kind']=='comment'],['Intro','Only comment'])
        self.assertFalse((core.project_folder(project)/'meme_state.json').exists())

    def test_duration_split_does_not_leave_or_consume_a_trailing_meme(self):
        voice=self.batch_media(1)
        project=core.Project(comments=[core.Comment(text=str(i)) for i in range(3)],
                             options=core.Options(resolution=360,max_seconds=15,credit=''))
        folder=self.data/'jobs'/core.uid();folder.mkdir()
        def fake_run(args,*_args,**_kwargs):Path(args[-1]).touch()
        def fake_duration(path):
            if path.name in ('audio-000.wav','audio-001.wav'):return 7
            if path.name.startswith('audio-'):return 1
            return 2
        with patch('render.run',side_effect=fake_run),patch('render.synthesize',return_value=voice),patch('render.duration',side_effect=fake_duration):
            render.render(self.with_screenshots(project),folder,lambda *_:None,lambda:False)
        scenes=core.read(folder/'timeline.json')['scenes']
        self.assertEqual([s['kind'] for s in scenes if s['part']==1],['comment'])
        self.assertEqual([s['kind'] for s in scenes if s['part']==2],['comment','meme','comment'])
        self.assertEqual(next(s['meme_name'] for s in scenes if s['kind']=='meme'),'1.png')
        self.assertFalse((core.project_folder(project)/'meme_state.json').exists())

    def test_preview_recovers_when_cache_directory_is_removed(self):
        (self.data/'cache').rmdir()
        with TestClient(app.app) as client:
            response=client.post('/api/card-preview',json=core.Project().model_dump())
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.content.startswith(b'\x89PNG'))
            (self.data/'cache').rmdir()  # Response cleanup has removed the preview file.
            voice=self.data/'voice.wav'
            self.wav(voice,.1)
            with patch('app.synthesize',return_value=voice):
                response=client.post('/api/voice-preview',json={'use_saved_voices':False})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.content[:4],b'RIFF')

    def test_missing_screenshot_fails_before_tts_without_reconstruction(self):
        project=core.Project(post='Original',comments=[core.Comment(text='Comment')])
        folder=self.data/'jobs'/core.uid();folder.mkdir()
        with patch('render.synthesize') as speech:
            with self.assertRaisesRegex(ValueError,'Thiếu ảnh chụp bài viết gốc'):
                render.render(project,folder,lambda *_:None,lambda:False)
            speech.assert_not_called()
        self.with_screenshots(project)
        project.comments[0].image=''
        with patch('render.synthesize') as speech:
            with self.assertRaisesRegex(ValueError,'Bình luận 1 thiếu ảnh chụp'):
                render.render(project,folder,lambda *_:None,lambda:False)
            speech.assert_not_called()

    def test_windows_title_safety(self):
        self.assertEqual(core.video_title(core.Project(post='CON')), '_CON')
        self.assertEqual(core.video_title(core.Project(post='A/B: C?\nDòng sau')), 'A_B_ C_')


if __name__ == '__main__': unittest.main()
