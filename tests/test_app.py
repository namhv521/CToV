"""Behavior tests; no network access or paid calls."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

os.environ['COMMENTCUT_DATA'] = tempfile.mkdtemp(prefix='commentcut-test-')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from core import DATA, Project, Comment, source_url, write, read
from collector import normalize, extract_tiktok, extract_threads
from render import stamp, card
from app import app


class AppTests(unittest.TestCase):
    def test_validation_error_identifies_field_without_echoing_input(self):
        project=Project().model_dump()
        project['options']['max_seconds']=2
        project['options']['provider']='private-invalid-value'
        with TestClient(app) as client:
            response=client.post('/api/card-preview',json=project)
        self.assertEqual(response.status_code,422)
        self.assertIsInstance(response.json()['detail'],str)
        self.assertIn('options.max_seconds',response.json()['detail'])
        self.assertNotIn('private-invalid-value',response.text)

    def test_atomic_write_retries_windows_handle(self):
        target=DATA/'cache'/'retry.json'
        real=Path.replace
        calls=[]
        def transient(path,destination):
            calls.append(1)
            if len(calls)==1: raise PermissionError('simulated active reader')
            return real(path,destination)
        with patch.object(Path,'replace',transient): write(target,{'ok':True})
        self.assertTrue(read(target)['ok'])
        self.assertEqual(len(calls),2)

    def test_job_cancellation(self):
        import time
        def wait_for_cancel(project,folder,progress,cancelled):
            deadline=time.monotonic()+3
            while not cancelled() and time.monotonic()<deadline: time.sleep(.01)
            raise InterruptedError('cancel')
        with TestClient(app) as c, patch('app.render',wait_for_cancel):
            from PIL import Image
            image=DATA/'assets'/('b'*32+'.png');Image.new('RGB',(200,100),'gray').save(image)
            write(image.with_suffix('.json'),{'id':image.stem,'kind':'image','file':image.name})
            project=Project(comments=[Comment(text='Thử hủy',image=image.stem)]).model_dump()
            row=c.post('/api/jobs',json=project).json()
            c.post('/api/jobs/'+row['id']+'/cancel')
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                current=c.get('/api/jobs/'+row['id']).json()
                if current['status']=='cancelled': break
                time.sleep(.02)
            self.assertEqual(current['status'],'cancelled')
    def test_source_validation(self):
        self.assertEqual(source_url('https://www.tiktok.com/@a/video/123'), 'https://www.tiktok.com/@a/video/123')
        for bad in ('http://www.tiktok.com/a', 'https://tiktok.com.evil.com/a', 'https://127.0.0.1',
                    'https://evil@www.tiktok.com/a', 'https://www.threads.com:123/a'):
            with self.assertRaises(ValueError): source_url(bad)

    def test_tiktok_target_scope_and_dedup(self):
        rows = extract_tiktok({'comments':[
            {'cid':'a','aweme_id':'123','user':{'nickname':'Nam'},'text':'Thật không?','digg_count':12},
            {'cid':'b','aweme_id':'999','user':{'nickname':'Khác'},'text':'Không thuộc video'},
            {'cid':'a','aweme_id':'123','user':{'nickname':'Nam'},'text':'Thật không?'}]}, '123')
        self.assertEqual(len(normalize(rows)),1)
        self.assertEqual(normalize(rows)[0]['likes'],12)

    def test_threads_does_not_take_suggested_posts(self):
        data={'items':[
            {'pk':'10','code':'ROOT','user':{'username':'root'},'caption':{'text':'Bài gốc'}},
            {'pk':'11','user':{'username':'reply'},'caption':{'text':'Phản hồi'},'text_post_app_info':{'reply_to_id':'10'}},
            {'pk':'12','code':'OTHER','user':{'username':'unrelated'},'caption':{'text':'Bài đề xuất'}}]}
        post, rows = extract_threads(data,'ROOT')
        self.assertEqual(post['text'],'Bài gốc')
        self.assertEqual([r['text'] for r in rows],['Phản hồi'])

    def test_empty_comment_rejected(self):
        with self.assertRaises(ValueError): Comment(text='   ')

    def test_threads_graphql_reply_threads(self):
        root={'pk':'10','code':'ROOT','user':{'username':'root'},'caption':{'text':'Bài gốc'}}
        reply={'pk':'11','code':'REPLY','user':{'username':'reader'},'caption':{'text':'Bình luận'}}
        unrelated={'pk':'20','code':'OTHER','user':{'username':'other'},'caption':{'text':'Đề xuất'}}
        payload={'data':{'data':{'containing_thread':{'thread_items':[{'post':root}]},
                    'reply_threads':[{'thread_items':[{'post':reply}]}]}}, 'suggested':unrelated}
        post,rows=extract_threads(payload,'ROOT')
        self.assertEqual(post['text'],'Bài gốc')
        self.assertEqual([r['text'] for r in normalize(rows)],['Bình luận'])

    def test_project_roundtrip_and_path_guard(self):
        with TestClient(app) as c:
            project=Project(name='Thử tiếng Việt', comments=[Comment(text='Xin chào')]).model_dump()
            self.assertEqual(c.post('/api/projects',json=project).status_code,200)
            loaded=c.get('/api/projects/'+project['id']).json()
            self.assertEqual(loaded['comments'][0]['text'],'Xin chào')
            self.assertEqual(c.get('/api/projects/not-an-id').status_code,400)
            self.assertEqual(c.get('/api/jobs/xxx/files/secrets.json').status_code,400)

    def test_origin_and_host_guard(self):
        with TestClient(app) as c:
            self.assertEqual(c.post('/api/settings',json={},headers={'origin':'https://evil.com'}).status_code,403)
            self.assertEqual(c.get('/api/health',headers={'host':'evil.com'}).status_code,403)

    def test_settings_secrets_not_returned(self):
        with TestClient(app) as c:
            r=c.post('/api/settings',json={'elevenlabs_key':'test-secret','vbee_token':'test-token'})
            self.assertIs(r.json()['elevenlabs_key'],True)
            self.assertNotIn('test-secret',r.text)
            c.post('/api/settings',json={'elevenlabs_key':''})
            self.assertIs(c.get('/api/settings').json()['elevenlabs_key'],True)

    def test_upload_rejects_wrong_media(self):
        with TestClient(app) as c:
            self.assertEqual(c.post('/api/assets/image',files={'file':('evil.html',b'<html>','text/html')}).status_code,400)
            self.assertEqual(c.post('/api/assets/image',files={'file':('fake.png',b'not an image','image/png')}).status_code,400)
            self.assertEqual(c.post('/api/jobs',json=Project().model_dump()).status_code,400)

    def test_card_keeps_unicode_and_dimensions(self):
        from PIL import Image
        p=DATA/'cache'/'test.png'
        source=DATA/'assets'/('c'*32+'.png')
        Image.new('RGB',(400,300),'gray').save(source)
        write(source.with_suffix('.json'),{'id':source.stem,'kind':'image','file':source.name})
        card('','',12,Project().options,p,source.stem)
        with self.assertRaisesRegex(ValueError,'Thiếu ảnh chụp thật'):
            card('Không dựng chữ','',0,Project().options,DATA/'cache'/'missing.png')
        with Image.open(p) as im:
            self.assertEqual(im.size,(720,1280))
            self.assertEqual(im.mode,'RGBA')
        self.assertEqual(stamp(61.25),'00:01:01,250')


if __name__=='__main__': unittest.main()
