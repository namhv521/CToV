"""Real free speech + FFmpeg integration. Run manually; makes no paid calls."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import DATA, Project, Comment, uid, write, probe, duration
from demo import make_demo
from render import render

media=make_demo()
project=Project(name='Bản dựng kiểm tra · Google TTS',post='Đi làm vui nhất là lúc nào?',author='CommentCut · minh họa',
    comments=[Comment(author='Minh',text='Lúc đồng nghiệp bảo: hôm nay sếp nghỉ!',likes=128),
              Comment(author='An',text='Lúc nhận lương. Nhưng niềm vui kéo dài đúng năm phút.',likes=96),
              Comment(author='Linh',text='Lúc tan làm mà trời không mưa. Hạnh phúc đơn giản vậy thôi.',likes=73)])
project.options.resolution=360
project.options.max_seconds=15
project.options.background=next(a['id'] for a in media if a['kind']=='background')
project.options.default_meme=next(a['id'] for a in media if a['kind']=='image')
project.options.default_sound=next(a['id'] for a in media if a['kind']=='sound')
write(DATA/'projects'/(project.id+'.json'),project.model_dump())
jid=uid();folder=DATA/'jobs'/jid;folder.mkdir()
files=render(project,folder,lambda p,m:print(p,m,flush=True),lambda:False)
assert len([f for f in files if f.endswith('.mp4')]) >= 2, 'Expected automatic multi-part export'
for name in files:
    if name.endswith('.mp4'):
        info=probe(folder/name)
        assert {'audio','video'} <= {s['codec_type'] for s in info['streams']}
        assert duration(folder/name) <= 15.15
write(folder/'job.json',{'id':jid,'project_id':project.id,'name':project.name,'status':'done','progress':100,
                       'message':'Kiểm tra thực: Google TTS + FFmpeg','files':files,'created':__import__('time').time()})
print('PASS',folder,files)
