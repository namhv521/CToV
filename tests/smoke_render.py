"""Local FFmpeg render smoke test without online TTS calls."""
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
import core
import render

with tempfile.TemporaryDirectory(prefix='commentcut-smoke-') as tmp:
    data = Path(tmp)
    for name in ('assets', 'projects', 'jobs', 'batches', 'cache', 'project', 'output', 'Vid_nen', 'img_meme', 'mp3_meme'):
        (data / name).mkdir()
    with patch.object(core, 'DATA', data), patch.object(render, 'DATA', data):
        bg = data / 'Vid_nen' / 'bg.mp4'
        render.run(['-f', 'lavfi', '-i', 'testsrc2=size=360x640:rate=30', '-t', '2',
                    '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', bg], data, lambda: False)
        shot = data / 'assets' / ('a' * 32 + '.png')
        Image.new('RGB', (480, 200), 'white').save(shot)
        core.write(shot.with_suffix('.json'), {'id': shot.stem, 'kind': 'image', 'file': shot.name})
        voice = data / 'voice.wav'
        with wave.open(str(voice), 'wb') as f:
            f.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            f.writeframes(b'\0\0' * (5 * 16000))
        project = core.Project(
            name='Kiểm tra dựng hàng loạt',
            comments=[core.Comment(text=f'Bình luận {i}', image=shot.stem) for i in range(4)],
            options=core.Options(split_mode='comments', comments_per_video=2, resolution=360,
                                 read_post=False, use_meme_image=False, use_meme_sound=False),
        )
        folder = data / 'jobs' / core.uid()
        folder.mkdir()
        with patch('render.synthesize', return_value=voice):
            files = render.render(project, folder, lambda p, m: print(p, m, flush=True), lambda: False)
        mp4s = [f for f in files if f.endswith('.mp4')]
        assert len(mp4s) == 2, mp4s
        print('PASS', mp4s)
