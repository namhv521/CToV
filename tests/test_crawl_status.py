import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import app


class CrawlStatusTests(unittest.TestCase):
    def test_progress_and_completed_status(self):
        async def collect(url,limit,progress):
            progress({'seen':250,'captured':120,'failed':0})
            return {'comments':[{}]*120,'crawl_note':'Đã giữ 120 ảnh.'}
        with TestClient(app) as c,patch('collector.collect',collect):
            r=c.post('/api/crawl',json={'url':'https://www.threads.com/@a/post/ABC','limit':120})
            self.assertEqual(r.status_code,200)
            state=c.get('/api/crawl-status').json()
            self.assertEqual(state['status'],'done')
            self.assertEqual(state['seen'],250)
            self.assertEqual(state['captured'],120)

    def test_failed_crawl_does_not_leave_running_status(self):
        async def collect(url,limit,progress):
            raise ValueError('Profile đang được dùng')
        with TestClient(app) as c,patch('collector.collect',collect):
            self.assertEqual(c.post('/api/crawl',json={'url':'https://www.threads.com/@a/post/ABC'}).status_code,400)
            self.assertEqual(c.get('/api/crawl-status').json()['status'],'failed')
